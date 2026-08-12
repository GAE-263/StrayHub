"""Seed deterministic, fictional multi-tenant data for the local MVP."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    SessionRecord,
    User,
)
from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.reportable_scope import DailyReportableScope
from services.api.app.persistence.models.shelter_area import ShelterArea
from sqlalchemy import select

from .seed_observation_vocabulary import PLATFORM_OPTIONS

CATEGORY_NAMES = {
    "care_completion": "照護完成",
    "walk_completion": "散步完成",
    "feeding": "進食",
    "water": "飲水",
    "activity": "活動",
    "urination": "排尿",
    "defecation": "排便",
    "resource_guarding": "護食",
    "human_interaction": "人際互動",
    "animal_interaction": "動物互動",
    "emotion": "情緒",
    "walk": "散步",
    "appearance_special_status": "外觀／特殊狀態",
}

OPTION_NAMES = {
    "completed": "已完成",
    "partially_completed": "部分完成",
    "not_provided": "未提供",
    "not_observed": "未觀察到",
    "uncertain": "不確定",
    "not_done": "未完成",
    "normal": "正常",
    "less": "較少",
    "almost_none": "幾乎沒有",
    "observed": "有觀察到",
    "usual": "平常",
    "lower": "較低",
    "higher": "較高",
    "unwilling": "不願意",
    "formed": "成形",
    "soft": "偏軟",
    "watery": "水樣",
    "different_color": "顏色不同",
    "different_shape": "形狀不同",
    "tense": "緊繃",
    "vocalizes": "發出聲音",
    "blocks": "阻擋",
    "moves_food": "移動食物",
    "no_approach": "不靠近",
    "seeking": "主動尋求",
    "avoidant": "迴避",
    "calm": "平靜",
    "alert": "警覺",
    "excited": "興奮",
    "withdrawn": "退縮",
    "seeking_interaction": "尋求互動",
    "willing": "願意",
    "exploring": "探索",
    "reluctant": "猶豫",
    "slow_or_stopping": "變慢或停下",
    "tries_to_return": "嘗試返回",
    "human_reaction": "對人的反應",
    "animal_reaction": "對動物的反應",
    "changed": "外觀改變",
    "scratching": "搔抓",
    "red_area": "泛紅區域",
    "reduced_hair": "毛髮變少",
    "lying_long": "長時間躺臥",
    "different_walk": "行走不同",
    "other": "其他",
}


def _display_name(code: str) -> str:
    return OPTION_NAMES.get(code.rsplit(".", 1)[-1], code.rsplit(".", 1)[-1].replace("_", "／"))


async def _get_or_create(session, model, statement, factory):
    value = (await session.execute(statement)).scalar_one_or_none()
    if value is None:
        value = factory()
        session.add(value)
        await session.flush()
    return value


async def seed() -> dict[str, dict[str, str]]:
    hasher = Argon2PasswordHasher()
    now = datetime.now(timezone.utc)
    result: dict[str, dict[str, str]] = {}
    async with session_factory() as session:
        async with session.begin():
            platform_admin = await _get_or_create(
                session,
                User,
                select(User).where(User.username == "local-platform-admin"),
                lambda: User(
                    username="local-platform-admin",
                    display_name="本機平台管理員",
                    password_hash=hasher.hash("local-only-password"),
                    platform_role="PLATFORM_ADMIN",
                    status="active",
                ),
            )
            platform_admin.display_name = "本機平台管理員"
            platform_admin.platform_role = "PLATFORM_ADMIN"
            platform_admin.status = "active"
            result["PLATFORM"] = {
                "username": platform_admin.username,
                "role": platform_admin.platform_role,
            }
            for org_code, org_name in (("ORG-A", "虛構收容所 A"), ("ORG-B", "虛構收容所 B")):
                organization = await _get_or_create(
                    session,
                    Organization,
                    select(Organization).where(Organization.code == org_code),
                    lambda org_code=org_code, org_name=org_name: Organization(
                        code=org_code, name=org_name, status="active"
                    ),
                )
                organization.status = "active"
                area = await _get_or_create(
                    session,
                    ShelterArea,
                    select(ShelterArea).where(
                        ShelterArea.organization_id == organization.id,
                        ShelterArea.name == f"MVP Cage {org_code[-1]}",
                    ),
                    lambda organization=organization, org_code=org_code: ShelterArea(
                        organization_id=organization.id,
                        name=f"MVP Cage {org_code[-1]}",
                        area_type="cage",
                        status="active",
                    ),
                )
                animal = await _get_or_create(
                    session,
                    Animal,
                    select(Animal).where(
                        Animal.organization_id == organization.id,
                        Animal.shelter_number == "VAAAG114080610",
                    ),
                    lambda organization=organization, area=area: Animal(
                        organization_id=organization.id,
                        name="小黑",
                        shelter_number="VAAAG114080610",
                        area_id=area.id,
                        status="active",
                    ),
                )
                animal.status = "active"
                animal.area_id = area.id
                staff_username = f"local-staff-{org_code[-1].lower()}"
                volunteer_username = f"local-volunteer-{org_code[-1].lower()}"
                staff = await _get_or_create(
                    session,
                    User,
                    select(User).where(User.username == staff_username),
                    lambda staff_username=staff_username, org_code=org_code: User(
                        username=staff_username,
                        display_name=f"本機工作人員 {org_code[-1]}",
                        password_hash=hasher.hash("local-only-password"),
                        status="active",
                    ),
                )
                volunteer = await _get_or_create(
                    session,
                    User,
                    select(User).where(User.username == volunteer_username),
                    lambda volunteer_username=volunteer_username, org_code=org_code: User(
                        username=volunteer_username,
                        display_name=f"本機志工 {org_code[-1]}",
                        password_hash=hasher.hash("local-only-password"),
                        status="active",
                    ),
                )
                for user, role in ((staff, "STAFF"), (volunteer, "VOLUNTEER")):
                    membership = await _get_or_create(
                        session,
                        OrganizationMembership,
                        select(OrganizationMembership).where(
                            OrganizationMembership.organization_id == organization.id,
                            OrganizationMembership.user_id == user.id,
                        ),
                        lambda user=user, role=role, organization=organization: (
                            OrganizationMembership(
                                organization_id=organization.id,
                                user_id=user.id,
                                role=role,
                                status="active",
                            )
                        ),
                    )
                    membership.role = role
                    membership.status = "active"
                if org_code == "ORG-A":
                    shelter_admin = await _get_or_create(
                        session,
                        User,
                        select(User).where(User.username == "local-shelter-admin-a"),
                        lambda: User(
                            username="local-shelter-admin-a",
                            display_name="本機收容所管理員 A",
                            password_hash=hasher.hash("local-only-password"),
                            status="active",
                        ),
                    )
                    shelter_admin.display_name = "本機收容所管理員 A"
                    shelter_admin.status = "active"
                    shelter_admin_membership = await _get_or_create(
                        session,
                        OrganizationMembership,
                        select(OrganizationMembership).where(
                            OrganizationMembership.organization_id == organization.id,
                            OrganizationMembership.user_id == shelter_admin.id,
                        ),
                        lambda shelter_admin=shelter_admin, organization=organization: (
                            OrganizationMembership(
                                organization_id=organization.id,
                                user_id=shelter_admin.id,
                                role="SHELTER_ADMIN",
                                status="active",
                            )
                        ),
                    )
                    shelter_admin_membership.role = "SHELTER_ADMIN"
                    shelter_admin_membership.status = "active"
                active_session = await _get_or_create(
                    session,
                    SessionRecord,
                    select(SessionRecord).where(
                        SessionRecord.user_id == volunteer.id,
                        SessionRecord.active_organization_id == organization.id,
                        SessionRecord.status == "active",
                    ),
                    lambda volunteer=volunteer, organization=organization: SessionRecord(
                        user_id=volunteer.id,
                        active_organization_id=organization.id,
                        status="active",
                        expires_at=now + timedelta(days=7),
                    ),
                )
                line_user_id = f"Ulocal-volunteer-{org_code[-1]}"
                await _get_or_create(
                    session,
                    LineUserBinding,
                    select(LineUserBinding).where(LineUserBinding.line_user_id == line_user_id),
                    lambda line_user_id=line_user_id, volunteer=volunteer: LineUserBinding(
                        line_user_id=line_user_id,
                        user_id=volunteer.id,
                        status="active",
                    ),
                )
                raw_qr_token = f"local-mvp-qr-{org_code}"
                await _get_or_create(
                    session,
                    AnimalQrCode,
                    select(AnimalQrCode).where(AnimalQrCode.animal_id == animal.id),
                    lambda organization=organization, animal=animal, raw_qr_token=raw_qr_token: (
                        AnimalQrCode(
                            organization_id=organization.id,
                            animal_id=animal.id,
                            token_digest=hashlib.sha256(raw_qr_token.encode()).hexdigest(),
                            status="active",
                            revoked=False,
                        )
                    ),
                )
                scope = await _get_or_create(
                    session,
                    DailyReportableScope,
                    select(DailyReportableScope).where(
                        DailyReportableScope.organization_id == organization.id,
                        DailyReportableScope.animal_id == animal.id,
                        DailyReportableScope.volunteer_user_id == volunteer.id,
                    ),
                    lambda organization=organization, animal=animal, volunteer=volunteer: (
                        DailyReportableScope(
                            organization_id=organization.id,
                            animal_id=animal.id,
                            volunteer_user_id=volunteer.id,
                            starts_at=now - timedelta(days=1),
                            ends_at=now + timedelta(days=1),
                            status="active",
                        )
                    ),
                )
                scope.starts_at = now - timedelta(days=1)
                scope.ends_at = now + timedelta(days=1)

                for category_code, option_codes in PLATFORM_OPTIONS.items():
                    category = await _get_or_create(
                        session,
                        ObservationCategory,
                        select(ObservationCategory).where(
                            ObservationCategory.organization_id.is_(None),
                            ObservationCategory.code == category_code,
                        ),
                        lambda category_code=category_code: ObservationCategory(
                            organization_id=None,
                            code=category_code,
                            display_name=CATEGORY_NAMES[category_code],
                            description="本機非診斷性照護觀察語彙",
                            status="active",
                        ),
                    )
                    category.display_name = CATEGORY_NAMES[category_code]
                    for option_code in option_codes:
                        option = await _get_or_create(
                            session,
                            ObservationOption,
                            select(ObservationOption).where(
                                ObservationOption.category_id == category.id,
                                ObservationOption.code == option_code,
                            ),
                            lambda option_code=option_code, category=category: ObservationOption(
                                category_id=category.id,
                                organization_id=None,
                                code=option_code,
                                display_name=_display_name(option_code),
                                description="本機展示選項",
                                status="active",
                                requires_note=option_code.endswith(".other"),
                            ),
                        )
                        option.display_name = _display_name(option_code)
                        option.description = "本機展示選項"
                result[org_code] = {
                    "organization_id": str(organization.id),
                    "staff_username": staff.username,
                    "volunteer_username": volunteer.username,
                    "session_id": str(active_session.id),
                    "line_user_id": line_user_id,
                    "qr_token": raw_qr_token,
                    "animal_id": str(animal.id),
                }
                if org_code == "ORG-A":
                    result[org_code]["shelter_admin_username"] = shelter_admin.username
    return result


def main() -> None:
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
