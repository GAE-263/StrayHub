"""Operator-only MOA sync. The caller owns the transaction; no HTTP exposure."""

from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.audit_service import AuditService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.qr_token_service import QrTokenService
from services.api.app.domain.moa_import import SOURCE, MoaBatch
from services.api.app.infrastructure.moa_open_data import MoaOpenDataClient, MoaPhoto
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.animal_external_source import AnimalExternalSource
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


def organization_identity(shelter_id: str):
    code = f"MOA-SHELTER-{shelter_id}"
    return uuid5(NAMESPACE_URL, f"strayhub:{SOURCE}:shelter:{shelter_id}"), code


class MoaImportService:
    def __init__(self, session: AsyncSession, storage: ObjectStoragePort):
        self.session = session
        self.storage = storage

    @staticmethod
    async def download_photos(batch: MoaBatch, client: MoaOpenDataClient):
        semaphore = asyncio.Semaphore(3)

        async def download(record):
            if not record.image_url:
                return record.external_id, "missing_image"
            async with semaphore:
                try:
                    return record.external_id, await client.fetch_photo(record.image_url)
                except ValueError as exc:
                    return record.external_id, str(exc)

        return dict(await asyncio.gather(*(download(row) for row in batch.selected)))

    async def run(
        self,
        *,
        batch: MoaBatch,
        shelter: str,
        limit: int,
        photos: dict[str, MoaPhoto | str] | None = None,
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
                    "images_reused",
                    "images_updated",
                    "image_failures",
                    "qr_created",
                    "qr_reused",
                    "images_preserved_manual",
                    "records_failed",
                )
            }
        )
        summary = {
            "dry_run": dry_run,
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
            if dry_run:
                animal = await self.session.get(Animal, mapping.animal_id) if mapping else None
                changed = animal and any(getattr(animal, k) != v for k, v in record.fields.items())
                counts[
                    "animals_created"
                    if not mapping
                    else "animals_updated"
                    if changed
                    else "animals_unchanged"
                ] += 1
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
            summary["image_plan"] = (
                "fetch/decode/checksum; reuse unchanged, ingest changed; no downloads in dry-run"
            )
        return summary

    async def _record(self, org_id, record, mapping, now, photo):
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
        for field, value in record.fields.items():
            setattr(animal, field, value)
        previous_photo = animal.current_photo_key
        mapping.source_updated_at = record.source_updated_at
        mapping.source_snapshot = record.snapshot
        mapping.last_imported_at = mapping.last_seen_at = now
        mapping.source_status = "present"
        if isinstance(photo, str):
            counts["image_failures"] += 1
            errors.append({"stage": "image", "external_id": record.external_id, "code": photo})
        elif animal.current_photo_key and animal.current_photo_key != mapping.photo_object_key:
            counts["images_preserved_manual"] += 1
            counts["images_downloaded"] += 1
        else:
            counts["images_downloaded"] += 1
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
                counts["images_reused" if reused else "images_updated"] += 1
        changed = before != record.fields or previous_photo != animal.current_photo_key
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
                after={**record.fields, "source": SOURCE, "external_id": record.external_id},
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
