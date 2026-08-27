"""Operator-only MOA sync. The caller owns the transaction; no HTTP exposure."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.audit_service import AuditService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.qr_token_service import QrTokenService
from services.api.app.domain.moa_import import SOURCE, MoaBatch, MoaNameObservation
from services.api.app.infrastructure.moa_open_data import MoaOpenDataClient, MoaPhoto
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.animal_external_source import AnimalExternalSource
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


def organization_identity(shelter_id: str):
    code = f"MOA-SHELTER-{shelter_id}"
    return uuid5(NAMESPACE_URL, f"strayhub:{SOURCE}:shelter:{shelter_id}"), code


class PhotoAction(StrEnum):
    REUSE_LOCAL = "reuse_local"
    DOWNLOAD_REQUIRED = "download_required"
    REPAIR_LOCAL = "repair_local"
    MANUAL_PHOTO_PRESERVED = "manual_photo_preserved"
    MISSING_IMAGE = "missing_image"


@dataclass(frozen=True)
class PhotoPlan:
    action: PhotoAction
    reason: str


class MoaImportService:
    def __init__(self, session: AsyncSession, storage: ObjectStoragePort):
        self.session = session
        self.storage = storage

    @staticmethod
    async def download_photos(
        batch: MoaBatch,
        client: MoaOpenDataClient,
        plans: dict[str, PhotoPlan] | None = None,
    ):
        semaphore = asyncio.Semaphore(3)

        async def download(record):
            if not record.image_url:
                return record.external_id, "missing_image"
            async with semaphore:
                try:
                    return record.external_id, await client.fetch_photo(record.image_url)
                except ValueError as exc:
                    return record.external_id, str(exc)

        selected = (
            batch.selected
            if plans is None
            else tuple(
                row
                for row in batch.selected
                if plans[row.external_id].action
                in {PhotoAction.DOWNLOAD_REQUIRED, PhotoAction.REPAIR_LOCAL}
            )
        )
        return dict(await asyncio.gather(*(download(row) for row in selected)))

    async def plan_photos(self, *, batch: MoaBatch) -> dict[str, PhotoPlan]:
        """Batch-load metadata, then validate importer-owned local bytes before reuse."""
        org_id, code = organization_identity(batch.shelter_id)
        await set_platform_scope(self.session)
        organization = await self.session.scalar(
            select(Organization).where(Organization.code == code)
        )
        if organization is None:
            return {
                row.external_id: PhotoPlan(
                    PhotoAction.DOWNLOAD_REQUIRED if row.image_url else PhotoAction.MISSING_IMAGE,
                    "new_import" if row.image_url else "source_image_missing",
                )
                for row in batch.selected
            }
        if organization.id != org_id:
            raise ValueError("organization_code_collision")
        await set_organization_scope(self.session, org_id)
        mappings = list(
            (
                await self.session.scalars(
                    select(AnimalExternalSource).where(
                        AnimalExternalSource.organization_id == org_id,
                        AnimalExternalSource.source == SOURCE,
                        AnimalExternalSource.external_id.in_(
                            row.external_id for row in batch.selected
                        ),
                    )
                )
            ).all()
        )
        by_external_id = {row.external_id: row for row in mappings}
        animal_ids = [row.animal_id for row in mappings]
        animals = (
            list(
                (
                    await self.session.scalars(
                        select(Animal).where(
                            Animal.organization_id == org_id, Animal.id.in_(animal_ids)
                        )
                    )
                ).all()
            )
            if animal_ids
            else []
        )
        by_animal_id = {row.id: row for row in animals}
        object_keys = [row.photo_object_key for row in mappings if row.photo_object_key]
        assets = (
            list(
                (
                    await self.session.scalars(
                        select(MediaAsset).where(
                            MediaAsset.organization_id == org_id,
                            MediaAsset.object_key.in_(object_keys),
                        )
                    )
                ).all()
            )
            if object_keys
            else []
        )
        by_object_key = {row.object_key: row for row in assets}
        plans: dict[str, PhotoPlan] = {}
        for record in batch.selected:
            mapping = by_external_id.get(record.external_id)
            animal = by_animal_id.get(mapping.animal_id) if mapping else None
            if mapping and animal and animal.current_photo_key:
                if animal.current_photo_key != mapping.photo_object_key:
                    plans[record.external_id] = PhotoPlan(
                        PhotoAction.MANUAL_PHOTO_PRESERVED, "current_photo_not_importer_owned"
                    )
                    continue
            if not record.image_url:
                invalid = await self._local_photo_problem(org_id, mapping, animal, by_object_key)
                plans[record.external_id] = PhotoPlan(
                    PhotoAction.REUSE_LOCAL if invalid is None else PhotoAction.MISSING_IMAGE,
                    "source_image_missing_local_retained"
                    if invalid is None
                    else "source_image_missing",
                )
                continue
            if mapping is None or animal is None:
                plans[record.external_id] = PhotoPlan(PhotoAction.DOWNLOAD_REQUIRED, "new_import")
                continue
            previous_locator = mapping.source_snapshot.get("album_file")
            if previous_locator != record.image_url:
                plans[record.external_id] = PhotoPlan(
                    PhotoAction.DOWNLOAD_REQUIRED, "source_locator_changed"
                )
                continue
            invalid = await self._local_photo_problem(org_id, mapping, animal, by_object_key)
            plans[record.external_id] = (
                PhotoPlan(PhotoAction.REUSE_LOCAL, "verified_local_photo")
                if invalid is None
                else PhotoPlan(PhotoAction.REPAIR_LOCAL, invalid)
            )
        return plans

    async def _local_photo_problem(self, org_id, mapping, animal, assets_by_key):
        if mapping is None or animal is None:
            return "metadata_incomplete"
        checksum = mapping.photo_source_checksum
        key = mapping.photo_object_key
        if (
            not checksum
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum.lower())
            or not key
            or animal.current_photo_key != key
            or f"/{checksum}/" not in key
        ):
            return "metadata_incomplete"
        asset = assets_by_key.get(key)
        if asset is None:
            return "missing_asset"
        if asset.status != "processed" or not asset.checksum:
            return "asset_not_processed"
        try:
            stored = await self.storage.get(scope=ObjectScope(org_id), key=key)
        except Exception:
            return "missing_object"
        if hashlib.sha256(stored).hexdigest() != asset.checksum:
            return "checksum_mismatch"
        return None

    async def run(
        self,
        *,
        batch: MoaBatch,
        shelter: str,
        limit: int,
        photos: dict[str, MoaPhoto | str] | None = None,
        names: dict[str, MoaNameObservation] | None = None,
        name_detail_requests: int = 0,
        photo_plans: dict[str, PhotoPlan] | None = None,
        dry_run: bool = False,
    ):
        if not self.session.in_transaction():
            raise ValueError("caller_transaction_required")
        now = datetime.now(timezone.utc)
        org_id, code = organization_identity(batch.shelter_id)
        counts = Counter(
            {
                key: 0
                for key in (
                    "animals_created",
                    "animals_updated",
                    "animals_unchanged",
                    "source_unavailable",
                    "images_downloaded",
                    "images_remote_requests",
                    "images_skipped_remote",
                    "images_reused",
                    "images_updated",
                    "images_repaired",
                    "image_failures",
                    "qr_created",
                    "qr_reused",
                    "images_preserved_manual",
                    "records_failed",
                    "names_official_applied",
                    "names_official_unchanged",
                    "names_fallback",
                    "name_conflicts_preserved",
                    "name_enrichment_failures",
                )
            }
        )
        summary = {
            "dry_run": dry_run,
            "name_detail_requests": name_detail_requests,
            "source": SOURCE,
            "records_fetched": batch.fetched_count,
            "shelter": shelter.strip(),
            "organization_code": code,
            "organization_id": str(org_id),
            "eligible_dogs": batch.eligible_count,
            "requested_limit": limit,
            "selected": len(batch.selected),
            "records_with_image": sum(bool(r.image_url) for r in batch.selected),
            "errors": [{"stage": "normalization", **e} for e in batch.errors],
        }
        # Existing privileged CLI boundary: only organization bootstrap is platform-scoped.
        await set_platform_scope(self.session)
        if not dry_run:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"moa-import:{code}"},
            )
        organization = await self.session.scalar(
            select(Organization).where(Organization.code == code)
        )
        if organization is not None and organization.id != org_id:
            raise ValueError("organization_code_collision")
        if not batch.selected:
            raise ValueError("no_valid_selected_records")
        sample = batch.selected[0].snapshot
        if not dry_run:
            if organization is None:
                organization = Organization(
                    id=org_id,
                    code=code,
                    name=shelter.strip(),
                    status="active",
                    timezone="Asia/Taipei",
                )
                self.session.add(organization)
            for field, source_field, max_length in (
                ("address", "shelter_address", 500),
                ("contact", "shelter_tel", 300),
            ):
                if not getattr(organization, field):
                    setattr(organization, field, sample.get(source_field, "")[:max_length] or None)
            await self.session.flush()
        await set_organization_scope(self.session, org_id)
        mappings = list(
            (
                await self.session.scalars(
                    select(AnimalExternalSource).where(
                        AnimalExternalSource.organization_id == org_id,
                        AnimalExternalSource.source == SOURCE,
                    )
                )
            ).all()
        )
        by_id = {row.external_id: row for row in mappings}
        for mapping in mappings:
            if mapping.source_shelter_id != batch.shelter_id:
                raise ValueError("source_shelter_mismatch")
            if mapping.external_id in batch.present_ids:
                if not dry_run:
                    mapping.last_seen_at = now
                    mapping.source_status = "present"
            elif not batch.errors:
                counts["source_unavailable"] += 1
                if not dry_run:
                    mapping.source_status = "unavailable"
        for record in batch.selected:
            mapping = by_id.get(record.external_id)
            observation = (names or {}).get(
                record.external_id, MoaNameObservation(error_code="name_detail_not_requested")
            )
            if dry_run:
                animal = await self.session.get(Animal, mapping.animal_id) if mapping else None
                name, _, name_counts, name_errors = await self._name_plan(
                    org_id, record, mapping, animal, observation, now, created=mapping is None
                )
                counts.update(name_counts)
                summary["errors"].extend(name_errors)
                fields = {**record.fields, "name": name}
                changed = animal and any(getattr(animal, k) != v for k, v in fields.items())
                counts[
                    "animals_created"
                    if not mapping
                    else "animals_updated"
                    if changed
                    else "animals_unchanged"
                ] += 1
                plan = (photo_plans or {}).get(record.external_id)
                if plan:
                    self._count_photo_plan(counts, plan, dry_run=True)
                continue
            # Flush presence before SAVEPOINT, then isolate a malformed/conflicting animal.
            try:
                async with self.session.begin_nested():
                    result = await self._record(
                        org_id,
                        record,
                        mapping,
                        now,
                        (photos or {}).get(record.external_id, "missing_image"),
                        observation,
                        (photo_plans or {}).get(record.external_id),
                    )
                counts.update(result[0])
                summary["errors"].extend(result[1])
            except Exception:
                # DB errors can include payloads/SQL/token values; never print raw exceptions.
                counts["records_failed"] += 1
                summary["errors"].append(
                    {
                        "stage": "record",
                        "external_id": record.external_id,
                        "code": "record_sync_failed",
                    }
                )
        await self.session.flush()
        summary.update(counts)
        if dry_run:
            summary["image_plan"] = "local validation only; remote images are not downloaded"
        return summary

    @staticmethod
    def _count_photo_plan(counts, plan, *, dry_run=False):
        if plan.action in {PhotoAction.DOWNLOAD_REQUIRED, PhotoAction.REPAIR_LOCAL}:
            counts["images_remote_requests"] += 1
            if not dry_run:
                counts["images_downloaded"] += 1
        else:
            counts["images_skipped_remote"] += 1
        if plan.action is PhotoAction.REUSE_LOCAL:
            counts["images_reused"] += 1
        elif plan.action is PhotoAction.MANUAL_PHOTO_PRESERVED:
            counts["images_preserved_manual"] += 1

    async def _legacy_name_owned(self, org_id, record, mapping, animal):
        if mapping.source != SOURCE or animal.name != record.fields["name"]:
            return False
        if str(mapping.source_snapshot.get("animal_id")) != mapping.external_id:
            return False
        if mapping.source_snapshot.get("animal_subid") != (record.fields["shelter_number"] or ""):
            return False
        audits = (
            await self.session.scalars(
                select(AuditRecord).where(
                    AuditRecord.organization_id == org_id,
                    AuditRecord.resource_id == animal.id,
                    func.lower(AuditRecord.resource_type) == "animal",
                )
            )
        ).all()
        proven = False
        for audit in audits:
            before, after = audit.before_data or {}, audit.after_data or {}
            if not isinstance(before, dict) or not isinstance(after, dict):
                return False
            importer = (
                audit.actor_type == "system"
                and audit.actor_reference == "moa_importer"
                and audit.source_channel == "import"
                and audit.action in {"import_create", "import_update"}
            )
            if importer:
                proven |= (
                    after.get("name") == animal.name
                    and after.get("source") == SOURCE
                    and str(after.get("external_id")) == mapping.external_id
                )
            elif "name" in before or "name" in after:
                # Includes an edit away from and then back to the fallback.
                if "name" not in before or "name" not in after or before["name"] != after["name"]:
                    return False
            elif audit.action != "animal.status_changed":
                # Unexplained profile history is not proof of importer ownership.
                return False
        return proven

    async def _name_plan(self, org_id, record, mapping, animal, observation, now, *, created):
        previous_snapshot = mapping.source_snapshot if mapping is not None else {}
        previous = previous_snapshot.get("name_enrichment")
        previous = previous if isinstance(previous, dict) else {}

        def prior_name(key):
            value = previous.get(key)
            return value if isinstance(value, str) and len(value) <= 200 else None

        current = animal.name if animal is not None else record.fields["name"]
        last_applied = prior_name("last_applied_name")
        if created:
            owned = True
        elif "name_enrichment" in previous_snapshot:
            owned = last_applied is not None and current == last_applied
        else:
            owned = await self._legacy_name_owned(org_id, record, mapping, animal)
        if owned:
            last_applied = current
        counts, errors = Counter(), []
        metadata = {
            "source": "official_detail" if observation.normalized_name else "fallback",
            "raw_name": observation.raw_name,
            "normalized_name": observation.normalized_name,
            "last_applied_name": last_applied,
            "last_successful_name": prior_name("last_successful_name"),
            "fetched_at": now.isoformat(),
            "detail_action": "AnnounceMentDataDetail",
            "identity_verified": observation.error_code is None,
            "ownership": "importer" if owned else "unowned",
        }
        if not owned:
            counts["name_conflicts_preserved"] += 1
        if observation.error_code:
            counts["name_enrichment_failures"] += 1
            metadata.update(
                status="failed",
                error_code=observation.error_code,
                source=previous.get("source")
                if previous.get("source") in {"fallback", "official_detail"}
                else None,
            )
            errors.append(
                {
                    "stage": "name_enrichment",
                    "external_id": record.external_id,
                    "code": observation.error_code,
                }
            )
        elif not owned:
            metadata["status"] = "conflict"
        elif observation.normalized_name:
            counts[
                "names_official_unchanged"
                if current == observation.normalized_name
                else "names_official_applied"
            ] += 1
            current = observation.normalized_name
            metadata.update(
                status="applied", last_applied_name=current, last_successful_name=current
            )
        else:
            counts["names_fallback"] += 1
            # An authoritative blank does not downgrade a previously applied name.
            metadata["status"] = "official_empty"
        snapshot = {**record.snapshot, "name_enrichment": metadata}
        if (
            len(json.dumps(metadata, ensure_ascii=False).encode()) > 6144
            or len(json.dumps(snapshot, ensure_ascii=False).encode()) > 32768
        ):
            raise ValueError("source_snapshot_too_large")
        return current, snapshot, counts, errors

    async def _record(self, org_id, record, mapping, now, photo, observation, photo_plan=None):
        counts, errors = Counter(), []
        created = mapping is None
        if created:
            animal = Animal(
                id=uuid5(NAMESPACE_URL, f"strayhub:{SOURCE}:animal:{record.external_id}"),
                organization_id=org_id,
                status="active",
                **record.fields,
            )
            self.session.add(animal)
            await self.session.flush()
            mapping = AnimalExternalSource(
                organization_id=org_id,
                animal_id=animal.id,
                source=SOURCE,
                external_id=record.external_id,
                source_shelter_id=record.shelter_id,
                last_seen_at=now,
                last_imported_at=now,
                source_status="present",
                source_snapshot=record.snapshot,
            )
            self.session.add(mapping)
        else:
            animal = await self.session.scalar(
                select(Animal)
                .where(Animal.id == mapping.animal_id, Animal.organization_id == org_id)
                .with_for_update()
            )
            if animal is None:
                raise ValueError("mapped_animal_unavailable")
        before = {field: getattr(animal, field) for field in record.fields}
        name, snapshot, name_counts, name_errors = await self._name_plan(
            org_id, record, mapping, animal, observation, now, created=created
        )
        counts.update(name_counts)
        errors.extend(name_errors)
        fields = {**record.fields, "name": name}
        for field, value in fields.items():
            setattr(animal, field, value)
        previous_photo = animal.current_photo_key
        mapping.source_updated_at = record.source_updated_at
        mapping.source_snapshot = snapshot
        mapping.last_imported_at = mapping.last_seen_at = now
        mapping.source_status = "present"
        if photo_plan is None:
            photo_plan = PhotoPlan(
                PhotoAction.MISSING_IMAGE
                if photo == "missing_image"
                else PhotoAction.DOWNLOAD_REQUIRED,
                "legacy_call",
            )
        if (
            animal.current_photo_key
            and animal.current_photo_key != mapping.photo_object_key
            and photo_plan.action in {PhotoAction.DOWNLOAD_REQUIRED, PhotoAction.REPAIR_LOCAL}
        ):
            # Keep this check in the write path as defense in depth for callers that
            # did not use the planner, or for a concurrent manager photo change.
            photo_plan = PhotoPlan(
                PhotoAction.MANUAL_PHOTO_PRESERVED, "current_photo_not_importer_owned"
            )
        self._count_photo_plan(counts, photo_plan)
        if photo_plan.action in {
            PhotoAction.REUSE_LOCAL,
            PhotoAction.MANUAL_PHOTO_PRESERVED,
            PhotoAction.MISSING_IMAGE,
        }:
            pass
        elif isinstance(photo, str):
            counts["image_failures"] += 1
            errors.append({"stage": "image", "external_id": record.external_id, "code": photo})
        else:
            try:
                key, reused = await self._photo(org_id, record.external_id, photo)
            except Exception:
                counts["image_failures"] += 1
                errors.append(
                    {
                        "stage": "image",
                        "external_id": record.external_id,
                        "code": "image_storage_failed",
                    }
                )
            else:
                mapping.photo_source_checksum = photo.source_checksum
                mapping.photo_object_key = animal.current_photo_key = key
                if photo_plan.action is PhotoAction.REPAIR_LOCAL:
                    counts["images_repaired"] += 1
                else:
                    counts["images_reused" if reused else "images_updated"] += 1
        changed = before != fields or previous_photo != animal.current_photo_key
        counts[
            "animals_created" if created else "animals_updated" if changed else "animals_unchanged"
        ] += 1
        await self.session.flush()
        if animal.status == "active":
            _, _, qr_created = await QrTokenService(
                AnimalRepository(self.session, org_id), QrCodeRepository(self.session, org_id)
            ).create_or_reuse(animal_id=animal.id)
            counts["qr_created" if qr_created else "qr_reused"] += 1
        if created or changed:
            await AuditService(self.session).record(
                organization_id=org_id,
                actor_user_id=None,
                actor_reference="moa_importer",
                action="import_create" if created else "import_update",
                resource_type="animal",
                resource_id=animal.id,
                source_channel="import",
                before=None if created else before,
                after={**fields, "source": SOURCE, "external_id": record.external_id},
            )
        return counts, errors

    async def _photo(self, org_id, external_id, photo):
        key = f"moa/animals/{external_id}/{photo.source_checksum}/primary.{photo.extension}"
        # Nested savepoint also isolates a MediaAsset DB failure from the animal upsert.
        async with self.session.begin_nested():
            asset = await self.session.scalar(
                select(MediaAsset).where(
                    MediaAsset.organization_id == org_id, MediaAsset.object_key == key
                )
            )
            cleaned = MediaProcessingService.sanitize(
                photo.data, declared_content_type=photo.content_type
            )
            if asset:
                try:
                    stored = await self.storage.get(scope=ObjectScope(org_id), key=key)
                    if hashlib.sha256(stored).hexdigest() == cleaned.checksum == asset.checksum:
                        return key, True
                except Exception:
                    pass  # A missing/corrupt object is repaired from validated source bytes.
            await MediaProcessingService(self.storage).store_cleaned(
                organization_id=org_id,
                object_key=key,
                data=photo.data,
                declared_content_type=photo.content_type,
            )
            stored = await self.storage.get(scope=ObjectScope(org_id), key=key)
            if hashlib.sha256(stored).hexdigest() != cleaned.checksum:
                raise ValueError("stored_checksum_mismatch")
            if not asset:
                asset = MediaAsset(organization_id=org_id, object_key=key)
                self.session.add(asset)
            asset.purpose = "animal_primary_photo"
            asset.checksum = cleaned.checksum
            asset.content_type = cleaned.content_type
            asset.status = "processed"
            asset.exif_removed = True
            await self.session.flush()
        return key, False
