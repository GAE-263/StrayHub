from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import (
    EncryptedPii,
    PiiCipherPort,
    PiiContext,
    PiiRevealAuditEvent,
    PiiRevealAuditPort,
)
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerApplication,
    VolunteerApplicationProfile,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


@dataclass(frozen=True)
class DecryptedVolunteerProfile:
    applicant_name: str = field(repr=False)
    phone_number: str = field(repr=False)
    basic_profile: dict[str, Any] | None = field(repr=False)
    insurance_identity: str | None = field(repr=False)


class VolunteerPiiService:
    schema_version = "v1"
    basic_profile_fields = frozenset({"experience"})
    crm_reveal_roles = frozenset({"SHELTER_ADMIN"})
    crm_reveal_purposes = frozenset({"application_review"})

    def __init__(self, cipher: PiiCipherPort) -> None:
        self.cipher = cipher

    async def create_profile(
        self,
        *,
        repository: VolunteerAccessRepository,
        application_id: UUID,
        applicant_name: str,
        phone_number: str,
        basic_profile: dict[str, Any] | None,
        insurance_identity: str | None,
        insurance_consent_acknowledged: bool,
        insurance_collection_mode: str | None,
        insurance_purpose_code: str | None,
        insurance_policy_version: str | None,
        now: datetime,
    ) -> VolunteerApplicationProfile:
        application = await repository.application(application_id, for_update=True)
        if application is None:
            raise DomainError("volunteer_application_not_found", "志工申請不存在", 404)
        policy = await repository.policy(for_update=True)
        profile = self._build_profile(
            application=application,
            applicant_name=applicant_name,
            phone_number=phone_number,
            basic_profile=basic_profile,
            insurance_identity=insurance_identity,
            insurance_required=policy.insurance_required,
            insurance_consent_acknowledged=insurance_consent_acknowledged,
            insurance_policy=policy,
            insurance_collection_mode=insurance_collection_mode,
            insurance_purpose_code=insurance_purpose_code,
            insurance_policy_version=insurance_policy_version,
            now=now,
        )
        return await repository.add(profile)

    @staticmethod
    def _require_matching_metadata(reference: EncryptedPii, candidate: EncryptedPii) -> None:
        if (
            candidate.algorithm != reference.algorithm
            or candidate.key_version != reference.key_version
        ):
            raise DomainError("pii_cipher_metadata_mismatch", "個人資料加密服務暫時無法使用", 503)

    def _context(self, profile: VolunteerApplicationProfile, field_name: str) -> PiiContext:
        if profile.pii_schema_version != self.schema_version:
            raise DomainError("pii_schema_version_unknown", "個人資料暫時無法使用", 503)
        return PiiContext(
            organization_id=profile.organization_id,
            application_id=profile.application_id,
            field_name=field_name,
            schema_version=profile.pii_schema_version,
        )

    def build_profile(
        self,
        *,
        application: VolunteerApplication,
        applicant_name: str,
        phone_number: str,
        basic_profile: dict[str, Any] | None,
        insurance_identity: str | None,
        insurance_required: bool,
        now: datetime,
        insurance_consent_acknowledged: bool = False,
        insurance_policy: OrganizationVolunteerAccessPolicy | None = None,
        insurance_collection_mode: str | None = None,
        insurance_purpose_code: str | None = None,
        insurance_policy_version: str | None = None,
    ) -> VolunteerApplicationProfile:
        if (insurance_identity or "").strip():
            raise DomainError("insurance_identity_not_allowed", "保險身分資料需由受控流程提交", 422)
        return self._build_profile(
            application=application,
            applicant_name=applicant_name,
            phone_number=phone_number,
            basic_profile=basic_profile,
            insurance_identity=None,
            insurance_required=insurance_required,
            now=now,
            insurance_consent_acknowledged=insurance_consent_acknowledged,
            insurance_policy=insurance_policy,
            insurance_collection_mode=insurance_collection_mode,
            insurance_purpose_code=insurance_purpose_code,
            insurance_policy_version=insurance_policy_version,
        )

    def _build_profile(
        self,
        *,
        application: VolunteerApplication,
        applicant_name: str,
        phone_number: str,
        basic_profile: dict[str, Any] | None,
        insurance_identity: str | None,
        insurance_required: bool,
        now: datetime,
        insurance_consent_acknowledged: bool = False,
        insurance_policy: OrganizationVolunteerAccessPolicy | None = None,
        insurance_collection_mode: str | None = None,
        insurance_purpose_code: str | None = None,
        insurance_policy_version: str | None = None,
    ) -> VolunteerApplicationProfile:
        invalid_basic_values = basic_profile is not None and any(
            not isinstance(value, str) or len(value) > 1000 for value in basic_profile.values()
        )
        if basic_profile is not None and (
            not set(basic_profile).issubset(self.basic_profile_fields) or invalid_basic_values
        ):
            raise DomainError("basic_profile_invalid", "基本申請資料格式無效", 422)
        normalized_insurance_identity = (insurance_identity or "").strip()
        if normalized_insurance_identity and (
            not insurance_required
            or insurance_policy is None
            or insurance_policy.organization_id != application.organization_id
            or not insurance_policy.insurance_required
        ):
            raise DomainError("insurance_identity_not_allowed", "此申請不需保險身分資料", 422)
        if normalized_insurance_identity:
            if (
                not insurance_consent_acknowledged
                or insurance_collection_mode != "strayhub_temporary"
                or insurance_purpose_code != "insurance_verification"
                or insurance_policy_version != f"organization-policy-v{insurance_policy.version}"
            ):
                raise DomainError("insurance_consent_required", "請先同意保險身分資料用途", 422)
        profile = VolunteerApplicationProfile(
            organization_id=application.organization_id,
            application_id=application.id,
            pii_schema_version=self.schema_version,
            applicant_name_ciphertext=None,
            phone_ciphertext=None,
            basic_profile_ciphertext=None,
            insurance_identity_ciphertext=None,
            encryption_algorithm="AES-256-GCM",
            encryption_key_version="",
            retention_expires_at=now + timedelta(days=180),
        )
        name = self.cipher.encrypt(
            applicant_name,
            context=self._context(profile, "applicant_name"),
        )
        phone = self.cipher.encrypt(
            phone_number,
            context=self._context(profile, "phone_number"),
        )
        self._require_matching_metadata(name, phone)
        profile.applicant_name_ciphertext = name.ciphertext
        profile.phone_ciphertext = phone.ciphertext
        profile.encryption_algorithm = name.algorithm
        profile.encryption_key_version = name.key_version
        if basic_profile is not None:
            serialized_basic = json.dumps(
                basic_profile,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            encrypted_basic = self.cipher.encrypt(
                serialized_basic,
                context=self._context(profile, "basic_profile"),
            )
            self._require_matching_metadata(name, encrypted_basic)
            profile.basic_profile_ciphertext = encrypted_basic.ciphertext
        if normalized_insurance_identity:
            encrypted_identity = self.cipher.encrypt(
                normalized_insurance_identity,
                context=self._context(profile, "insurance_identity"),
            )
            self._require_matching_metadata(name, encrypted_identity)
            profile.insurance_identity_ciphertext = encrypted_identity.ciphertext
            profile.insurance_identity_delete_after = now + timedelta(days=30)
        return profile

    def _decrypt_field(
        self,
        profile: VolunteerApplicationProfile,
        *,
        field_name: str,
        ciphertext: bytes | None,
    ) -> str | None:
        if ciphertext is None:
            return None
        return self.cipher.decrypt(
            EncryptedPii(
                ciphertext=ciphertext,
                algorithm=profile.encryption_algorithm,
                key_version=profile.encryption_key_version,
            ),
            context=self._context(profile, field_name),
        )

    def _decode_basic_profile(self, basic_json: str | None) -> dict[str, Any] | None:
        if basic_json is None:
            return None
        try:
            value = json.loads(basic_json)
        except (TypeError, ValueError):
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503) from None
        if not isinstance(value, dict) or not set(value).issubset(self.basic_profile_fields):
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503)
        if any(not isinstance(item, str) or len(item) > 1000 for item in value.values()):
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503)
        return value

    def _decrypt_profile(
        self,
        profile: VolunteerApplicationProfile,
        *,
        organization_id: UUID,
        application_id: UUID,
        now: datetime,
        include_insurance: bool = False,
    ) -> DecryptedVolunteerProfile:
        if profile.organization_id != organization_id or profile.application_id != application_id:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        if profile.pii_deleted_at is not None:
            raise DomainError("pii_deleted", "個人資料已依保存政策刪除", 410)
        if profile.retention_expires_at <= now:
            raise DomainError("pii_expired", "個人資料已超過保存期限", 410)
        applicant_name = self._decrypt_field(
            profile,
            field_name="applicant_name",
            ciphertext=profile.applicant_name_ciphertext,
        )
        phone_number = self._decrypt_field(
            profile,
            field_name="phone_number",
            ciphertext=profile.phone_ciphertext,
        )
        if applicant_name is None or phone_number is None:
            raise DomainError("pii_ciphertext_invalid", "個人資料暫時無法使用", 503)
        basic_json = self._decrypt_field(
            profile,
            field_name="basic_profile",
            ciphertext=profile.basic_profile_ciphertext,
        )
        insurance_identity = None
        if (
            include_insurance
            and profile.insurance_identity_delete_after is not None
            and profile.insurance_identity_delete_after > now
        ):
            insurance_identity = self._decrypt_field(
                profile,
                field_name="insurance_identity",
                ciphertext=profile.insurance_identity_ciphertext,
            )
        return DecryptedVolunteerProfile(
            applicant_name=applicant_name,
            phone_number=phone_number,
            basic_profile=self._decode_basic_profile(basic_json),
            insurance_identity=insurance_identity,
        )

    async def reveal_profile(
        self,
        *,
        repository: VolunteerAccessRepository,
        application_id: UUID,
        tenant_context: TenantContext,
        purpose_code: str,
        request_id: UUID,
        policy_version: str,
        now: datetime,
        audit: PiiRevealAuditPort,
    ) -> DecryptedVolunteerProfile:
        organization_id = repository.organization_id
        if tenant_context.platform_scope or tenant_context.organization_id != organization_id:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        membership = await repository.active_membership(
            tenant_context.user_id,
            for_update=True,
        )
        if membership is None:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        profile = await repository.application_profile(application_id, for_update=True)
        if profile is None:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        effective_context = TenantContext(
            user_id=tenant_context.user_id,
            organization_id=organization_id,
            role=membership.role,
        )
        return await self._reveal_loaded_profile(
            profile,
            organization_id=organization_id,
            application_id=application_id,
            tenant_context=effective_context,
            purpose_code=purpose_code,
            request_id=request_id,
            policy_version=policy_version,
            now=now,
            audit=audit,
        )

    async def _reveal_loaded_profile(
        self,
        profile: VolunteerApplicationProfile,
        *,
        organization_id: UUID,
        application_id: UUID,
        tenant_context: TenantContext,
        purpose_code: str,
        request_id: UUID,
        policy_version: str,
        now: datetime,
        audit: PiiRevealAuditPort,
    ) -> DecryptedVolunteerProfile:
        if profile.organization_id != organization_id or profile.application_id != application_id:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        if tenant_context.platform_scope or tenant_context.organization_id != organization_id:
            raise DomainError("pii_profile_not_found", "個人資料不存在", 404)
        if profile.pii_deleted_at is not None:
            raise DomainError("pii_deleted", "個人資料已依保存政策刪除", 410)
        if profile.retention_expires_at <= now:
            raise DomainError("pii_expired", "個人資料已超過保存期限", 410)
        normalized_role = tenant_context.role.strip()
        normalized_purpose = purpose_code.strip()
        normalized_policy_version = policy_version.strip()
        if not all((normalized_role, normalized_purpose, normalized_policy_version)):
            raise DomainError("pii_reveal_context_required", "缺少個人資料查看用途", 422)
        if (
            normalized_role not in self.crm_reveal_roles
            or normalized_purpose not in self.crm_reveal_purposes
        ):
            raise DomainError("pii_reveal_forbidden", "無法查看個人資料", 403)
        provided_fields = tuple(
            field_name
            for field_name, ciphertext in (
                ("applicant_name", profile.applicant_name_ciphertext),
                ("phone_number", profile.phone_ciphertext),
                ("basic_profile", profile.basic_profile_ciphertext),
            )
            if ciphertext is not None
        )
        try:
            await audit.persist_committed_reveal(
                PiiRevealAuditEvent(
                    organization_id=organization_id,
                    application_id=application_id,
                    actor_user_id=tenant_context.user_id,
                    actor_role=normalized_role,
                    purpose_code=normalized_purpose,
                    request_id=request_id,
                    policy_version=normalized_policy_version,
                    provided_fields=provided_fields,
                    encryption_key_version=profile.encryption_key_version,
                    retention_expires_at=profile.retention_expires_at,
                )
            )
        except Exception as exc:
            raise DomainError("pii_audit_unavailable", "個人資料稽核服務暫時無法使用", 503) from exc
        return self._decrypt_profile(
            profile,
            organization_id=organization_id,
            application_id=application_id,
            now=now,
            include_insurance=False,
        )

    def purge_expired(self, profile: VolunteerApplicationProfile, *, now: datetime) -> bool:
        if profile.pii_deleted_at is not None:
            return False
        if profile.retention_expires_at <= now:
            profile.applicant_name_ciphertext = None
            profile.phone_ciphertext = None
            profile.basic_profile_ciphertext = None
            profile.insurance_identity_ciphertext = None
            profile.insurance_identity_delete_after = None
            profile.pii_deleted_at = now
            return True
        if (
            profile.insurance_identity_delete_after is not None
            and profile.insurance_identity_delete_after <= now
        ):
            profile.insurance_identity_ciphertext = None
            profile.insurance_identity_delete_after = None
            return True
        return False
