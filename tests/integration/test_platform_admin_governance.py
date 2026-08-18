from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.platform_admin_management import (
    PlatformAdminManagementService,
)
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.models.identity import (
    Organization,
    OrganizationMembership,
    User,
)
from services.api.app.persistence.models.volunteer_access import VolunteerApplication
from services.api.app.persistence.repositories.platform_admin_repository import (
    PlatformAdminRepository,
)
from sqlalchemy import select


class _IntegrationHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        return encoded_hash == f"hashed:{password}"

    def needs_rehash(self, encoded_hash: str) -> bool:
        return False


def test_platform_admin_migration_bootstrap_contract_is_fail_closed():
    migration = Path(
        "services/api/migrations/versions/0029_platform_admin_governance.py"
    ).read_text()
    assert "active_admin_count" in migration
    assert "repair existing users" in migration
    assert "if user_count" in migration


def test_local_seed_keeps_one_platform_admin_and_shelter_admin_separate():
    seed = Path("scripts/seed_local.py").read_text()
    assert 'username == "local-platform-admin"' in seed
    assert 'platform_role="PLATFORM_ADMIN"' in seed
    assert '"local-shelter-admin-a"' in seed


@pytest.mark.asyncio
async def test_candidate_list_excludes_any_volunteer_history() -> None:
    await engine.dispose(close=False)
    now = datetime.now(timezone.utc)
    organization = Organization(
        name="平台管理員候選清單測試收容所",
        code=f"PLATFORM-CANDIDATES-{uuid4().hex[:12]}",
        status="active",
    )
    eligible = User(
        username=f"platform-candidate-{uuid4().hex[:12]}",
        display_name="可提升帳號",
        status="active",
    )
    active_member = User(
        username=f"volunteer-active-{uuid4().hex[:12]}",
        display_name="仍有志工 Membership",
        status="active",
    )
    expired_member = User(
        username=f"volunteer-expired-{uuid4().hex[:12]}",
        display_name="已過期志工 Membership",
        status="active",
    )
    revoked_member = User(
        username=f"volunteer-revoked-{uuid4().hex[:12]}",
        display_name="已撤銷志工 Membership",
        status="active",
    )
    rejected_application = User(
        username=f"volunteer-rejected-{uuid4().hex[:12]}",
        display_name="已拒絕志工申請",
        status="active",
    )
    withdrawn_application = User(
        username=f"volunteer-withdrawn-{uuid4().hex[:12]}",
        display_name="已撤回志工申請",
        status="active",
    )
    pending_application = User(
        username=f"volunteer-pending-{uuid4().hex[:12]}",
        display_name="待審核志工申請",
        status="active",
    )

    async with session_factory() as session:
        await set_platform_scope(session)
        session.add_all(
            [
                organization,
                eligible,
                active_member,
                expired_member,
                revoked_member,
                rejected_application,
                withdrawn_application,
                pending_application,
            ]
        )
        await session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=active_member.id,
                    role="VOLUNTEER",
                    status="active",
                    valid_from=now - timedelta(days=1),
                    expires_at=now + timedelta(days=1),
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=expired_member.id,
                    role="VOLUNTEER",
                    status="expired",
                    valid_from=now - timedelta(days=3),
                    expires_at=now - timedelta(days=1),
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=revoked_member.id,
                    role="VOLUNTEER",
                    status="revoked",
                    valid_from=now - timedelta(days=3),
                    expires_at=now + timedelta(days=1),
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=rejected_application.id,
                    status="rejected",
                    decided_at=now,
                    decision_reason="測試拒絕",
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=withdrawn_application.id,
                    status="withdrawn",
                    withdrawn_at=now,
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=pending_application.id,
                    status="pending",
                ),
            ]
        )
        await session.flush()

        candidates = await PlatformAdminRepository(session).list_candidates()

        candidate_usernames = {candidate.username for candidate in candidates}
        excluded_usernames = {
            active_member.username,
            expired_member.username,
            revoked_member.username,
            rejected_application.username,
            withdrawn_application.username,
            pending_application.username,
        }
        assert eligible.username in candidate_usernames
        assert candidate_usernames.isdisjoint(excluded_usernames)
        await session.rollback()


@pytest.mark.asyncio
async def test_persisted_volunteer_history_rejects_promote_and_replacement_and_rolls_back():
    await engine.dispose(close=False)
    now = datetime.now(timezone.utc)
    organization = Organization(
        name="平台管理員志工歷史交易測試收容所",
        code=f"PLATFORM-HISTORY-{uuid4().hex[:12]}",
        status="active",
    )
    history_users = [
        User(
            username=f"volunteer-history-{status}-{uuid4().hex[:12]}",
            display_name=f"志工歷史 {status}",
            status="active",
        )
        for status in ("expired", "revoked", "rejected", "withdrawn", "pending")
    ]

    async with session_factory() as session:
        await set_platform_scope(session)
        repository = PlatformAdminRepository(session)
        active_admins = [
            admin for admin in await repository.list_admins() if admin.status == "active"
        ]
        if len(active_admins) == 0:
            outgoing = User(
                username=f"history-outgoing-{uuid4().hex[:12]}",
                display_name="歷史測試原管理員",
                status="active",
                platform_role="PLATFORM_ADMIN",
            )
            second_admin = User(
                username=f"history-second-{uuid4().hex[:12]}",
                display_name="歷史測試第二管理員",
                status="active",
                platform_role="PLATFORM_ADMIN",
            )
            session.add_all([organization, outgoing, second_admin, *history_users])
        elif len(active_admins) == 1:
            outgoing = active_admins[0]
            second_admin = User(
                username=f"history-second-{uuid4().hex[:12]}",
                display_name="歷史測試第二管理員",
                status="active",
                platform_role="PLATFORM_ADMIN",
            )
            session.add_all([organization, second_admin, *history_users])
        else:
            outgoing = active_admins[0]
            session.add_all([organization, *history_users])
        await session.flush()

        expired, revoked, rejected, withdrawn, pending = history_users
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=expired.id,
                    role="VOLUNTEER",
                    status="expired",
                    valid_from=now - timedelta(days=5),
                    expires_at=now - timedelta(days=1),
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=revoked.id,
                    role="VOLUNTEER",
                    status="revoked",
                    valid_from=now - timedelta(days=5),
                    expires_at=now + timedelta(days=1),
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=rejected.id,
                    status="rejected",
                    decided_at=now,
                    decision_reason="測試拒絕",
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=withdrawn.id,
                    status="withdrawn",
                    withdrawn_at=now,
                ),
                VolunteerApplication(
                    organization_id=organization.id,
                    user_id=pending.id,
                    status="pending",
                ),
            ]
        )
        await session.flush()

        service = PlatformAdminManagementService(repository, _IntegrationHasher())
        history_ids = [user.id for user in history_users]
        for user in history_users:
            with pytest.raises(DomainError) as promote_error:
                await service.promote(user.id)
            assert promote_error.value.code == "account_not_eligible"

            with pytest.raises(DomainError) as replacement_error:
                await service.replace(
                    outgoing_user_id=outgoing.id,
                    replacement_user_id=user.id,
                )
            assert replacement_error.value.code == "platform_admin_replacement_invalid"
            assert user.platform_role is None

        assert outgoing.platform_role == "PLATFORM_ADMIN"
        await session.rollback()

    async with session_factory() as verification_session:
        await set_platform_scope(verification_session)
        result = await verification_session.execute(select(User.id).where(User.id.in_(history_ids)))
        assert result.scalars().all() == []
