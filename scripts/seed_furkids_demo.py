"""Seed the deterministic FurKids demo dataset and its approved primary photos."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from io import BytesIO
from typing import cast
from uuid import UUID, uuid5

import httpx
from PIL import Image, UnidentifiedImageError
from scripts.demo_credentials import require_demo_password
from services.api.app.application.animal_selection import AnimalSelectionService
from services.api.app.application.media_sanitization import MAX_IMAGE_BYTES
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.qr_token_service import issue_printable_qr_token
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.domain.animal_profile import AnimalProfile
from services.api.app.domain.organization_timezone import local_to_utc
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport, MediaAsset
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.medical_care import CareReminderSeries, MedicalRecord
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
)
from services.api.app.persistence.models.volunteer_management import (
    OrganizationVolunteerNumberCounter,
    VolunteerProfile,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ORGANIZATION_NAME = "毛小孩幸福聯盟協會"
ORGANIZATION_CODE = "FURKIDS-ASIA"
TIMEZONE_NAME = "Asia/Taipei"
FURKIDS_NAMESPACE = UUID("bfdd56f6-859d-48ca-8762-bddae8e2114a")
SOURCE_ALBUM_URL = "https://furkidsasia.weebly.com/album.html"


def stable_id(kind: str, key: str) -> UUID:
    return uuid5(FURKIDS_NAMESPACE, f"{kind}:{key}")


@dataclass(frozen=True)
class AnimalSpec:
    key: str
    name: str
    shelter_number: str
    area_name: str
    profile_url: str
    selected_image_url: str
    source_sha256: str
    source_facts: dict[str, object]

    @property
    def id(self) -> UUID:
        return stable_id("animal", self.key)

    @property
    def photo_object_key(self) -> str:
        return f"furkids-demo/animals/{self.shelter_number}/primary.jpg"


ANIMAL_SPECS: tuple[AnimalSpec, ...] = (
    AnimalSpec(
        "huang-mei",
        "獒黃妹",
        "MTF-20140531-001",
        "M-01",
        "https://furkidsasia.weebly.com/295224064322969-huang-mei",
        "https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/1347663248_orig.jpg",
        "5d8041f538f6294bda9c811adcda02e30c06a58c693f7949caa8c92973df1bf4",
        {
            "intake_date": "2014-05-31",
            "life_stage": "高齡犬",
            "temperament": ["親人", "溫和", "親暱"],
            "dog_interaction": "來源描述與其他犬互動時需留意",
        },
    ),
    AnimalSpec(
        "yi-cuo",
        "獒一搓",
        "MTF-20241213-001",
        "M-02",
        "https://furkidsasia.weebly.com/295221996825619-yi-cuo",
        "https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/s-52420615-0_orig.jpg",
        "9be308fb745887a3920fbaedb0a086bbadbef77c77152e3bafdde0d6af68aee0",
        {
            "sex": "公犬",
            "intake_date": "2024-12-13",
            "temperament": ["親人", "親暱", "面對人不特別害羞"],
            "source_note": "公開頁面中英文性別文字互相矛盾；依固定產品決策採公犬。",
        },
    ),
    AnimalSpec(
        "ua-ha",
        "獒瓦蛤",
        "MTF-20240515-001",
        "M-03",
        "https://furkidsasia.weebly.com/295222992634532-ua-ha",
        "https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/447692789-851850686969842-5265211632358069069-n_1.jpg",
        "6b42425edaf27d4bfb2a33220200c2cb9d22a68bf6a98c15d7671ed777555c7b",
        {
            "intake_date": "2024-05-15",
            "temperament": ["親人", "愛玩"],
            "dog_interaction": "面對其他犬較害羞或謹慎",
            "care_note": "來源描述有腸胃敏感情形",
        },
    ),
    AnimalSpec(
        "cash",
        "獒凱西",
        "MTF-20200605-001",
        "M-04",
        "https://furkidsasia.weebly.com/295222097735199-cash",
        "https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/editor/1620557754.jpg?1600933902",
        "66353360f6e83cdb33bb4e18f6d6f9e4af00a272c566b3647d2e257a79d2af20",
        {
            "intake_date": "2020-06-05",
            "temperament": ["親人", "愛玩", "合群"],
        },
    ),
    AnimalSpec(
        "fu-fu",
        "柴福福",
        "SBA-20170922-001",
        "S-01",
        "https://furkidsasia.weebly.com/266123111931119-fu-fu",
        "https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/s-249888796_1.jpg",
        "5555f76bfdea9873dfd93fa78179847c8ffaa777004f8f369943a3a87a43d17e",
        {
            "sex": "公犬",
            "breed": "柴犬系米克斯",
            "intake_date": "2017-09-22",
            "medical_fact": "來源描述為先天雙眼失明",
            "temperament": ["親人", "喜歡探索"],
        },
    ),
)


@dataclass(frozen=True)
class DownloadedPhoto:
    data: bytes
    content_type: str


@dataclass(frozen=True)
class PhotoIngestionResult:
    object_key: str
    content_type: str
    checksum: str
    downloaded: bool


PhotoDownloader = Callable[[str], Awaitable[DownloadedPhoto]]


async def download_approved_photo(url: str) -> DownloadedPhoto:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return DownloadedPhoto(response.content, content_type)


def _stored_photo_is_valid(data: bytes, asset: MediaAsset) -> bool:
    if not data or len(data) > MAX_IMAGE_BYTES:
        return False
    if hashlib.sha256(data).hexdigest() != asset.checksum:
        return False
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.format == "JPEG" and not image.getexif() and "exif" not in image.info
    except (UnidentifiedImageError, OSError):
        return False


class ApprovedPhotoIngestor:
    def __init__(
        self,
        storage: ObjectStoragePort,
        *,
        download: PhotoDownloader = download_approved_photo,
    ) -> None:
        self.storage = storage
        self.download = download
        self.media = MediaProcessingService(storage)

    async def ensure(
        self,
        *,
        organization_id: UUID,
        spec: AnimalSpec,
        existing_asset: MediaAsset | None = None,
    ) -> PhotoIngestionResult:
        object_key = spec.photo_object_key
        if existing_asset is not None:
            if (
                existing_asset.organization_id != organization_id
                or existing_asset.object_key != object_key
            ):
                raise RuntimeError(f"{spec.name} 的既有照片資產租戶或 object key 不一致")
            if (
                existing_asset.status == "processed"
                and existing_asset.purpose == "animal_primary"
                and existing_asset.content_type == "image/jpeg"
                and existing_asset.exif_removed
            ):
                try:
                    stored_data = await self.storage.get(
                        scope=ObjectScope(organization_id), key=object_key
                    )
                except Exception:
                    stored_data = b""
                if _stored_photo_is_valid(stored_data, existing_asset):
                    return PhotoIngestionResult(
                        object_key,
                        existing_asset.content_type,
                        existing_asset.checksum,
                        False,
                    )

        try:
            downloaded = await self.download(spec.selected_image_url)
        except Exception as exc:
            raise RuntimeError(f"{spec.name} 核准原圖下載失敗") from exc
        if hashlib.sha256(downloaded.data).hexdigest() != spec.source_sha256:
            raise RuntimeError(f"{spec.name} 核准原圖 checksum 不符")
        try:
            stored = await self.media.store_cleaned(
                organization_id=organization_id,
                object_key=object_key,
                data=downloaded.data,
                declared_content_type=downloaded.content_type,
            )
        except Exception as exc:
            raise RuntimeError(f"{spec.name} 核准原圖驗證或儲存失敗") from exc
        return PhotoIngestionResult(
            stored.key,
            stored.metadata.content_type,
            stored.metadata.checksum,
            True,
        )


def apply_primary_photo(
    *,
    organization_id: UUID,
    spec: AnimalSpec,
    animal: Animal,
    asset: MediaAsset,
    photo: PhotoIngestionResult,
) -> None:
    if (
        animal.organization_id != organization_id
        or animal.shelter_number != spec.shelter_number
        or asset.organization_id != organization_id
        or photo.object_key != spec.photo_object_key
    ):
        raise RuntimeError(f"{spec.name} 的照片與動物或租戶不一致")
    asset.object_key = photo.object_key
    asset.content_type = photo.content_type
    asset.checksum = photo.checksum
    asset.status = "processed"
    asset.purpose = "animal_primary"
    asset.exif_removed = True
    animal.current_photo_key = photo.object_key


CARE_REPORT_COUNTS = {
    "huang-mei": 4,
    "yi-cuo": 3,
    "ua-ha": 5,
    "cash": 4,
    "fu-fu": 4,
}

# Source facts and synthetic operational guidance are separately documented.
# Source age lower bounds are deliberately not converted into birth dates.
ANIMAL_PROFILES: dict[str, AnimalProfile] = {
    "huang-mei": AnimalProfile(
        sex="female",
        breed="獒犬",
        intake_date=date(2014, 5, 31),
        age_description="10歲以上",
        behavior_notes="親人、溫柔且喜歡撒嬌；與其他犬隻互動時需特別留意。",
        care_guidance="與其他犬隻保持適當距離；互動與牽行請依現場人員安排。",
    ),
    "yi-cuo": AnimalProfile(
        sex="male",
        breed="藏獒",
        intake_date=date(2024, 12, 13),
        age_description="5歲以上",
        behavior_notes="親人、愛撒嬌；初次見面也願意主動靠近人。",
    ),
    "ua-ha": AnimalProfile(
        sex="female",
        breed="藏獒",
        intake_date=date(2024, 5, 15),
        age_description="5歲以上",
        behavior_notes="親人、愛玩；面對其他犬隻較謹慎，在陌生環境喜歡跟著熟悉的人。",
        care_guidance="腸胃較敏感，飲食及零食請依現場安排。",
    ),
    "cash": AnimalProfile(
        sex="female",
        breed="混種獒犬",
        intake_date=date(2020, 6, 5),
        age_description="7歲以上",
        behavior_notes="親人、愛玩且合群。",
    ),
    "fu-fu": AnimalProfile(
        sex="male",
        breed="混種柴犬",
        intake_date=date(2017, 9, 22),
        age_description="5歲以上",
        behavior_notes="喜歡探索環境，對人親近、愛撒嬌，也會主動與其他犬隻互動。",
        care_guidance="視覺障礙；接近或觸碰前先以聲音讓牠知道你的位置，並依現場安排引導動線。",
    ),
}

MEDICAL_SPECS = (
    ("huang-mei", "examination", "[合成示範] 例行狀況檢視", None),
    ("huang-mei", "weight", "[合成示範] 體重紀錄", 34.2),
    ("yi-cuo", "examination", "[合成示範] 例行狀況檢視", None),
    ("ua-ha", "visit", "[合成示範] 例行照護訪視", None),
    ("ua-ha", "weight", "[合成示範] 體重紀錄", 28.6),
    ("cash", "examination", "[合成示範] 例行狀況檢視", None),
    ("fu-fu", "examination", "[合成示範] 特殊照護狀況檢視", None),
    ("fu-fu", "weight", "[合成示範] 體重紀錄", 12.4),
)

REMINDER_SPECS = (
    ("huang-mei", "高齡犬狀況追蹤"),
    ("ua-ha", "腸胃與體重狀況追蹤"),
    ("fu-fu", "特殊照護狀況追蹤"),
)

NORMAL_ANSWERS = {
    "care_completion": "care_completion.completed",
    "feeding": "feeding.normal",
    "water": "water.observed",
    "activity": "activity.usual",
    "urination": "urination.observed",
    "defecation": "defecation.formed",
    "human_interaction": "human_interaction.usual",
    "emotion": "emotion.calm",
}


def build_seed_plan() -> dict[str, object]:
    return {
        "organization": {
            "name": ORGANIZATION_NAME,
            "code": ORGANIZATION_CODE,
            "status": "active",
            "timezone": TIMEZONE_NAME,
        },
        "animals": [asdict(spec) | {"id": str(spec.id)} for spec in ANIMAL_SPECS],
        "source_derived": {spec.name: spec.source_facts for spec in ANIMAL_SPECS},
        "synthetic_counts": {
            "medical_records": len(MEDICAL_SPECS),
            "care_reminders": len(REMINDER_SPECS),
            "care_reports": sum(CARE_REPORT_COUNTS.values()),
        },
        "persistence_models": [
            "Organization",
            "ShelterArea",
            "Animal",
            "AnimalQrCode",
            "MedicalRecord",
            "CareReminderSeries",
            "CareReport",
            "MediaAsset",
        ],
    }


async def _one_or_create(session: AsyncSession, statement, factory):
    item = (await session.execute(statement)).scalar_one_or_none()
    if item is None:
        item = factory()
        session.add(item)
        await session.flush()
    return item


async def _seed_identity(
    session: AsyncSession, organization: Organization, password: str
) -> tuple[User, User, OrganizationMembership]:
    hasher = Argon2PasswordHasher()
    admin = await _one_or_create(
        session,
        select(User).where(User.username == "demo-furkids-admin"),
        lambda: User(
            id=stable_id("user", "admin"),
            username="demo-furkids-admin",
            display_name="FurKids 示範管理員",
            password_hash=hasher.hash(password),
            status="active",
        ),
    )
    volunteer = await _one_or_create(
        session,
        select(User).where(User.username == "demo-furkids-volunteer"),
        lambda: User(
            id=stable_id("user", "volunteer"),
            username="demo-furkids-volunteer",
            display_name="FurKids 示範志工",
            password_hash=hasher.hash(password),
            status="active",
        ),
    )
    for user, display_name in (
        (admin, "FurKids 示範管理員"),
        (volunteer, "FurKids 示範志工"),
    ):
        user.display_name = display_name
        user.status = "active"
        user.password_hash = hasher.hash(password)
    admin_membership = await _one_or_create(
        session,
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == admin.id,
        ),
        lambda: OrganizationMembership(
            id=stable_id("membership", "admin"),
            organization_id=organization.id,
            user_id=admin.id,
            role="SHELTER_ADMIN",
            status="active",
        ),
    )
    admin_membership.role = "SHELTER_ADMIN"
    admin_membership.status = "active"
    membership = await _one_or_create(
        session,
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == volunteer.id,
        ),
        lambda: OrganizationMembership(
            id=stable_id("membership", "volunteer"),
            organization_id=organization.id,
            user_id=volunteer.id,
            role="VOLUNTEER",
            status="active",
            valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            volunteer_no="V001",
        ),
    )
    membership.role = "VOLUNTEER"
    membership.status = "active"
    membership.valid_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
    membership.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    membership.volunteer_no = "V001"
    counter = await _one_or_create(
        session,
        select(OrganizationVolunteerNumberCounter).where(
            OrganizationVolunteerNumberCounter.organization_id == organization.id
        ),
        lambda: OrganizationVolunteerNumberCounter(
            organization_id=organization.id, next_value=2
        ),
    )
    counter.next_value = max(counter.next_value, 2)
    profile = await _one_or_create(
        session,
        select(VolunteerProfile).where(VolunteerProfile.user_id == volunteer.id),
        lambda: VolunteerProfile(user_id=volunteer.id, surname="陳"),
    )
    profile.surname = "陳"
    policy = await _one_or_create(
        session,
        select(OrganizationVolunteerAccessPolicy).where(
            OrganizationVolunteerAccessPolicy.organization_id == organization.id
        ),
        lambda: OrganizationVolunteerAccessPolicy(
            organization_id=organization.id,
            applications_enabled=True,
            default_grant_duration_hours=692520,
        ),
    )
    policy.applications_enabled = True
    policy.default_grant_duration_hours = 692520
    application = await _one_or_create(
        session,
        select(VolunteerApplication).where(
            VolunteerApplication.organization_id == organization.id,
            VolunteerApplication.user_id == volunteer.id,
            VolunteerApplication.status == "approved",
        ),
        lambda: VolunteerApplication(
            id=stable_id("application", "volunteer"),
            organization_id=organization.id,
            user_id=volunteer.id,
            status="approved",
            source_channel="management",
            submitted_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            decided_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
            decided_by_user_id=admin.id,
        ),
    )
    grant = await _one_or_create(
        session,
        select(VolunteerAccessGrant).where(VolunteerAccessGrant.application_id == application.id),
        lambda: VolunteerAccessGrant(
            id=stable_id("grant", "volunteer"),
            organization_id=organization.id,
            user_id=volunteer.id,
            membership_id=membership.id,
            application_id=application.id,
            status="active",
            valid_from=membership.valid_from,
            expires_at=membership.expires_at,
            approved_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
            approved_by_user_id=admin.id,
            policy_version_used=policy.version,
            duration_hours_used=692520,
        ),
    )
    grant.status = "active"
    grant.organization_id = organization.id
    grant.user_id = volunteer.id
    grant.membership_id = membership.id
    grant.valid_from = membership.valid_from
    grant.expires_at = membership.expires_at
    grant.policy_version_used = policy.version
    grant.duration_hours_used = 692520
    grant.revoked_at = None
    grant.revoked_by_user_id = None
    grant.revocation_reason = None
    return admin, volunteer, membership


async def _seed_areas(session: AsyncSession, organization: Organization) -> dict[str, ShelterArea]:
    result: dict[str, ShelterArea] = {}
    for parent_name, children in (
        ("大型犬區", ("M-01", "M-02", "M-03", "M-04")),
        ("特殊照護區", ("S-01",)),
    ):
        parent = await _one_or_create(
            session,
            select(ShelterArea).where(
                ShelterArea.organization_id == organization.id,
                ShelterArea.name == parent_name,
                ShelterArea.parent_id.is_(None),
            ),
            lambda parent_name=parent_name: ShelterArea(
                id=stable_id("area", parent_name),
                organization_id=organization.id,
                name=parent_name,
                area_type="area",
                status="active",
            ),
        )
        parent.area_type = "area"
        parent.status = "active"
        for child_name in children:
            child = await _one_or_create(
                session,
                select(ShelterArea).where(
                    ShelterArea.organization_id == organization.id,
                    ShelterArea.name == child_name,
                    ShelterArea.parent_id == parent.id,
                ),
                lambda child_name=child_name, parent=parent: ShelterArea(
                    id=stable_id("area", child_name),
                    organization_id=organization.id,
                    name=child_name,
                    area_type="cage",
                    parent_id=parent.id,
                    status="active",
                ),
            )
            child.area_type = "cage"
            child.status = "active"
            result[child_name] = child
    return result


async def _seed_qr(session: AsyncSession, organization: Organization, animal: Animal) -> None:
    qr_id = stable_id("animal-qr", animal.shelter_number or animal.id.hex)
    qr = await session.get(AnimalQrCode, qr_id)
    if qr is None:
        qr = AnimalQrCode(id=qr_id, organization_id=organization.id, animal_id=animal.id)
        session.add(qr)
    raw_token = issue_printable_qr_token(qr_id)
    qr.token_digest = hashlib.sha256(raw_token.encode()).hexdigest()
    qr.status = "active"
    qr.revoked = False
    other_active = (
        await session.execute(
            select(AnimalQrCode).where(
                AnimalQrCode.organization_id == organization.id,
                AnimalQrCode.animal_id == animal.id,
                AnimalQrCode.id != qr_id,
                AnimalQrCode.status == "active",
                AnimalQrCode.revoked.is_(False),
            )
        )
    ).scalars()
    for other in other_active:
        other.status = "revoked"
        other.revoked = True


def _answer_snapshots() -> dict[str, dict[str, str]]:
    return {
        key: {"code": code, "display_name": code.rsplit(".", 1)[-1]}
        for key, code in NORMAL_ANSWERS.items()
    }


async def seed(
    session: AsyncSession | None = None,
    *,
    password: str | None = None,
    storage: ObjectStoragePort | None = None,
    download: PhotoDownloader = download_approved_photo,
) -> dict[str, object]:
    password = require_demo_password(password)
    owns_session = session is None
    if session is None:
        session = session_factory()
    storage = storage or MinioStorageAdapter()
    if isinstance(storage, MinioStorageAdapter):
        await storage.ensure_bucket()
    photo_ingestor = ApprovedPhotoIngestor(storage, download=download)
    try:
        async with session.begin():
            organization = await _one_or_create(
                session,
                select(Organization).where(Organization.code == ORGANIZATION_CODE),
                lambda: Organization(
                    id=stable_id("organization", ORGANIZATION_CODE),
                    name=ORGANIZATION_NAME,
                    code=ORGANIZATION_CODE,
                    status="active",
                    timezone=TIMEZONE_NAME,
                ),
            )
            organization.name = ORGANIZATION_NAME
            organization.status = "active"
            organization.timezone = TIMEZONE_NAME
            organization.service_area = "新北市"
            organization.region = "north"
            if not organization.address:
                organization.address = "新北市（示範資料）"
            admin, volunteer, membership = await _seed_identity(session, organization, password)
            areas = await _seed_areas(session, organization)
            animals: dict[str, Animal] = {}
            photos_downloaded = 0
            photos_reused = 0
            for spec in ANIMAL_SPECS:
                animal = await _one_or_create(
                    session,
                    select(Animal).where(
                        Animal.organization_id == organization.id,
                        Animal.shelter_number == spec.shelter_number,
                    ),
                    lambda spec=spec: Animal(
                        id=spec.id,
                        organization_id=organization.id,
                        name=spec.name,
                        shelter_number=spec.shelter_number,
                        area_id=areas[spec.area_name].id,
                        status="active",
                    ),
                )
                animal.name = spec.name
                animal.area_id = areas[spec.area_name].id
                animal.status = "active"
                animal.is_adoptable = True
                for field, value in ANIMAL_PROFILES[spec.key].model_dump().items():
                    setattr(animal, field, value)
                asset = (
                    await session.execute(
                        select(MediaAsset).where(MediaAsset.object_key == spec.photo_object_key)
                    )
                ).scalar_one_or_none()
                if asset is not None and asset.organization_id != organization.id:
                    raise RuntimeError(f"{spec.name} 的照片 object key 已屬於其他租戶")
                photo = await photo_ingestor.ensure(
                    organization_id=organization.id,
                    spec=spec,
                    existing_asset=asset,
                )
                if asset is None:
                    asset = MediaAsset(
                        id=stable_id("media-asset", spec.key),
                        organization_id=organization.id,
                        object_key=photo.object_key,
                    )
                    session.add(asset)
                apply_primary_photo(
                    organization_id=organization.id,
                    spec=spec,
                    animal=animal,
                    asset=asset,
                    photo=photo,
                )
                photos_downloaded += int(photo.downloaded)
                photos_reused += int(not photo.downloaded)
                animals[spec.key] = animal
                await _seed_qr(session, organization, animal)

            for index, (animal_key, record_type, title, weight_kg) in enumerate(MEDICAL_SPECS):
                record_id = stable_id("medical-record", f"{animal_key}:{index}")
                record = await session.get(MedicalRecord, record_id)
                values = {
                    "organization_id": organization.id,
                    "animal_id": animals[animal_key].id,
                    "occurred_at": local_to_utc(
                        datetime.combine(date(2026, 8, 10 + index), time(10, 0)), TIMEZONE_NAME
                    ),
                    "occurred_timezone": TIMEZONE_NAME,
                    "record_type": record_type,
                    "title": title,
                    "content": "StrayHub 合成展示資料；非來源機構的真實醫療紀錄。",
                    "clinic": None,
                    "veterinarian": None,
                    "weight_kg": weight_kg,
                    "status": "active",
                    "created_by_user_id": admin.id,
                    "updated_by_user_id": admin.id,
                }
                if record is None:
                    session.add(MedicalRecord(id=record_id, **values))
                else:
                    for key, value in values.items():
                        setattr(record, key, value)

            for animal_key, title in REMINDER_SPECS:
                series_id = stable_id("reminder-series", animal_key)
                series = await session.get(CareReminderSeries, series_id)
                values = {
                    "lineage_id": stable_id("reminder-lineage", animal_key),
                    "organization_id": organization.id,
                    "animal_id": animals[animal_key].id,
                    "reminder_type": "follow_up",
                    "title": title,
                    "instructions": "StrayHub 合成展示提醒；請依現場實際狀況與正式照護指示處理。",
                    "assignee_membership_id": None,
                    "anchor_local_date": date(2026, 8, 5),
                    "anchor_local_time": time(9, 0),
                    "start_ordinal": 0,
                    "end_ordinal": None,
                    "frequency": "monthly",
                    "interval": 1,
                    "end_local_date": None,
                    "status": "active",
                    "created_by_user_id": admin.id,
                    "updated_by_user_id": admin.id,
                }
                if series is None:
                    session.add(CareReminderSeries(id=series_id, **values))
                else:
                    for key, value in values.items():
                        setattr(series, key, value)

            for animal_key, count in CARE_REPORT_COUNTS.items():
                animal = animals[animal_key]
                for index in range(count):
                    report_id = stable_id("care-report", f"{animal_key}:{index}")
                    report = await session.get(CareReport, report_id)
                    submitted_at = local_to_utc(
                        datetime.combine(date(2026, 8, 20 - index), time(9 + (index % 2) * 7, 0)),
                        TIMEZONE_NAME,
                    )
                    values = {
                        "organization_id": organization.id,
                        "draft_id": None,
                        "animal_id": animal.id,
                        "volunteer_user_id": volunteer.id,
                        "membership_id": membership.id,
                        "answers": dict(NORMAL_ANSWERS),
                        "answer_snapshots": _answer_snapshots(),
                        "animal_name_snapshot": animal.name,
                        "shelter_number_snapshot": animal.shelter_number,
                        "note": "StrayHub 合成日常照護回報。",
                        "status": "saved",
                        "ai_job_status": "not_required",
                        "submitted_at": submitted_at,
                    }
                    if report is None:
                        session.add(CareReport(id=report_id, **values))
                    else:
                        for key, value in values.items():
                            setattr(report, key, value)
            await session.flush()
            synthetic_counts = cast(dict[str, int], build_seed_plan()["synthetic_counts"])
            return {
                "organization": ORGANIZATION_CODE,
                "animals": len(ANIMAL_SPECS),
                "active_qr_codes": len(ANIMAL_SPECS),
                **synthetic_counts,
                "photos_ingested": len(ANIMAL_SPECS),
                "photos_downloaded": photos_downloaded,
                "photos_reused": photos_reused,
            }
    finally:
        if owns_session:
            await session.close()


async def verify_qr_first_path() -> dict[str, bool]:
    """Verify the seeded QR resolves for the scope-free demo volunteer."""
    async with session_factory() as session:
        async with session.begin():
            organization = (
                await session.execute(
                    select(Organization).where(Organization.code == ORGANIZATION_CODE)
                )
            ).scalar_one()
            volunteer = (
                await session.execute(select(User).where(User.username == "demo-furkids-volunteer"))
            ).scalar_one()
            membership = (
                await session.execute(
                    select(OrganizationMembership).where(
                        OrganizationMembership.organization_id == organization.id,
                        OrganizationMembership.user_id == volunteer.id,
                    )
                )
            ).scalar_one()
            animal = (
                await session.execute(
                    select(Animal).where(
                        Animal.organization_id == organization.id,
                        Animal.shelter_number == ANIMAL_SPECS[0].shelter_number,
                    )
                )
            ).scalar_one()
            qr = await session.get(
                AnimalQrCode,
                stable_id("animal-qr", ANIMAL_SPECS[0].shelter_number),
            )
            assert qr is not None
            await set_organization_scope(session, organization.id)
            animals = AnimalRepository(session, organization.id)
            selection = AnimalSelectionService(
                animals,
                QrCodeRepository(session, organization.id),
                VolunteerReportingAuthorizationService(AuthenticationRepository(session), animals),
            )
            raw_token = issue_printable_qr_token(qr.id)
            resolved = await selection.resolve_qr(
                raw_token=raw_token,
                user_id=volunteer.id,
                organization_id=organization.id,
                membership_id=membership.id,
                role="VOLUNTEER",
            )
            confirmed = await selection.confirm(
                animal_id=animal.id,
                user_id=volunteer.id,
                organization_id=organization.id,
                membership_id=membership.id,
                role="VOLUNTEER",
            )
            return {
                "manager_qr_reconstructable": hashlib.sha256(raw_token.encode()).hexdigest()
                == qr.token_digest,
                "volunteer_qr_resolve": resolved.animal.id == animal.id,
                "animal_confirmation": confirmed.animal.id == animal.id,
            }


def main() -> None:
    async def run() -> dict[str, object]:
        result = await seed()
        result["qr_first_verification"] = await verify_qr_first_path()
        return result

    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
