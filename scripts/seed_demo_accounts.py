"""Minimum synthetic identities for the three real demo shelters, not test fixtures."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from scripts.local_demo import DEMO_SHELTERS, guard
from scripts.seed_observation_vocabulary import seed_vocabulary
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
)
from sqlalchemy import select


def stable_id(label):
    return uuid5(NAMESPACE_URL, "strayhub:three-shelter-demo:" + label)


async def seed():
    guard()
    now = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        await set_platform_scope(session)
        orgs = {
            o.code: o
            for o in (
                await session.scalars(
                    select(Organization).where(Organization.code.in_(DEMO_SHELTERS))
                )
            ).all()
        }
        if set(orgs) != set(DEMO_SHELTERS):
            raise RuntimeError("seed_all_three_shelters_before_accounts")
        for organization in orgs.values():
            organization.service_area = "新北市"
            if not organization.address:
                organization.address = "新北市（示範資料）"
            await set_organization_scope(session, organization.id)
            policy = await session.scalar(
                select(OrganizationVolunteerAccessPolicy).where(
                    OrganizationVolunteerAccessPolicy.organization_id == organization.id
                )
            )
            if policy is None:
                policy = OrganizationVolunteerAccessPolicy(
                    organization_id=organization.id,
                    applications_enabled=True,
                )
                session.add(policy)
            policy.applications_enabled = True
            await session.flush()
        await set_platform_scope(session)
        admin = await session.scalar(select(User).where(User.username == "demo-furkids-admin"))
        if admin is None:
            raise RuntimeError("furkids_admin_required")
        hasher = Argon2PasswordHasher()
        for username, display, role in (
            ("demo-platform-admin", "三收容所示範平台管理員", "PLATFORM_ADMIN"),
            ("demo-xindian-volunteer", "新店示範志工", None),
            ("demo-wugu-volunteer", "五股示範志工", None),
        ):
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    id=stable_id(username),
                    username=username,
                    display_name=display,
                    password_hash=hasher.hash("local-only-password"),
                    status="active",
                    platform_role=role,
                )
                session.add(user)
                await session.flush()
            elif user.id != stable_id(username):
                raise RuntimeError("demo_username_collision")
            user.status = "active"
        await seed_vocabulary(session)
        for code, short in (("MOA-SHELTER-51", "xindian"), ("MOA-SHELTER-58", "wugu")):
            org = orgs[code]
            await set_organization_scope(session, org.id)
            volunteer = await session.scalar(
                select(User).where(User.username == f"demo-{short}-volunteer")
            )
            for user, role in ((admin, "SHELTER_ADMIN"), (volunteer, "VOLUNTEER")):
                member = await session.scalar(
                    select(OrganizationMembership).where(
                        OrganizationMembership.organization_id == org.id,
                        OrganizationMembership.user_id == user.id,
                    )
                )
                if member is None:
                    member = OrganizationMembership(
                        id=stable_id(f"member:{code}:{user.username}"),
                        organization_id=org.id,
                        user_id=user.id,
                        role=role,
                        status="active",
                        valid_from=now - timedelta(hours=1) if role == "VOLUNTEER" else None,
                        expires_at=now + timedelta(days=7) if role == "VOLUNTEER" else None,
                    )
                    session.add(member)
                    await session.flush()
                member.role = role
                member.status = "active"
                member.valid_from = now - timedelta(hours=1) if role == "VOLUNTEER" else None
                member.expires_at = now + timedelta(days=7) if role == "VOLUNTEER" else None
                if role != "VOLUNTEER":
                    continue
                aid = stable_id(f"application:{code}")
                application = await session.get(VolunteerApplication, aid)
                if application is None:
                    application = VolunteerApplication(
                        id=aid,
                        organization_id=org.id,
                        user_id=user.id,
                        status="approved",
                        source_channel="management",
                        submitted_at=now,
                        decided_at=now,
                        decided_by_user_id=admin.id,
                    )
                    session.add(application)
                    await session.flush()
                gid = stable_id(f"grant:{code}")
                grant = await session.get(VolunteerAccessGrant, gid)
                if grant is None:
                    grant = VolunteerAccessGrant(
                        id=gid,
                        organization_id=org.id,
                        user_id=user.id,
                        membership_id=member.id,
                        application_id=aid,
                        status="active",
                        valid_from=member.valid_from,
                        expires_at=member.expires_at,
                        approved_at=now,
                        approved_by_user_id=admin.id,
                        policy_version_used=1,
                        duration_hours_used=169,
                    )
                    session.add(grant)
                grant.status = "active"
                grant.valid_from = member.valid_from
                grant.expires_at = member.expires_at
                grant.revoked_at = None
                grant.revoked_by_user_id = None
                grant.revocation_reason = None
                await session.flush()
        return {
            "accounts": 5,
            "management_shelters": list(DEMO_SHELTERS),
            "volunteer_access": "one shelter per volunteer",
            "volunteer_application_policies": {code: "enabled" for code in DEMO_SHELTERS},
            "daily_scopes_created": 0,
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False))
