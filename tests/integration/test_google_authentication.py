"""Real PostgreSQL runtime-role tests; each test rolls back its outer transaction."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.google_service import GoogleAuthenticationService
from services.api.app.application.authentication.invitation_service import InvitationService
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.scope import (
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.models.identity import (
    GoogleAuthTransaction,
    GoogleUserBinding,
    Organization,
    OrganizationInvitation,
    OrganizationJoinApplication,
    OrganizationMembership,
    SessionRecord,
    User,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


class Verifier:
    nonce = ""
    sub = "synthetic-sub"

    async def verify(self, token, *, client_id):
        return {"sub": self.sub, "nonce": self.nonce}


async def test_join_application_review_role_rejection_and_isolation(setup):
    env = setup
    login, _, _ = await register(env)
    user_id = login["user_id"]
    service = InvitationService(env.db)
    target = await service.join_target(user_id=user_id, organization_id=env.org.id)
    assert target == {"id": env.org.id, "name": env.org.name}
    # Name lookup restores identity-only scope; no tenant data or memberships appear.
    assert await env.db.scalar(text("SELECT current_setting('app.current_org_id')")) == ""
    assert (await env.db.scalars(select(Organization))).all() == []
    first = await service.apply(user_id=user_id, organization_id=env.org.id)
    duplicate = await service.apply(user_id=user_id, organization_id=env.org.id)
    assert first["id"] == duplicate["id"]
    assert first["role"] is None
    from sqlalchemy.exc import DBAPIError

    # A self-service scope cannot grant a role even by bypassing the service.
    async with env.db.begin_nested():
        changed = await env.db.execute(
            text(
                "UPDATE organization_join_applications SET status='approved', role='STAFF' "
                "WHERE id=:id"
            ),
            {"id": first["id"]},
        )
        assert changed.rowcount == 0
    with pytest.raises(DBAPIError):
        async with env.db.begin_nested():
            env.db.add(
                OrganizationJoinApplication(
                    organization_id=env.org.id,
                    organization_name=env.org.name,
                    user_id=user_id,
                    status="pending",
                )
            )
            await env.db.flush()
    second = await service.apply(user_id=user_id, organization_id=env.other_org.id)
    assert len(await service.applications(user_id=user_id)) == 2
    await set_authentication_user_scope(env.db, env.admin.id)
    assert (await env.db.scalars(select(OrganizationJoinApplication))).all() == []
    with pytest.raises(DomainError) as denied:
        await service.review(
            context=env.context,
            organization_id=env.org.id,
            application_id=second["id"],
            approve=True,
            role="STAFF",
        )
    assert denied.value.code == "join_not_found"
    with pytest.raises(DomainError) as invalid:
        await service.review(
            context=env.context,
            organization_id=env.org.id,
            application_id=first["id"],
            approve=True,
            role="PLATFORM_ADMIN",
        )
    assert invalid.value.code == "invalid_role"
    rejected = await service.review(
        context=env.context, organization_id=env.org.id, application_id=first["id"], approve=False
    )
    assert rejected["status"] == "rejected"
    assert await service.applications(context=env.context, organization_id=env.org.id) == []
    with pytest.raises(DomainError) as cooldown:
        await service.apply(user_id=user_id, organization_id=env.org.id)
    assert cooldown.value.code == "join_retry_later"
    await set_organization_scope(env.db, env.org.id)
    item = await env.db.get(OrganizationJoinApplication, first["id"])
    item.reviewed_at = datetime.now(timezone.utc) - timedelta(days=2)
    await env.db.flush()
    retry = await service.apply(user_id=user_id, organization_id=env.org.id)
    approved = await service.review(
        context=env.context,
        organization_id=env.org.id,
        application_id=retry["id"],
        approve=True,
        role="STAFF",
    )
    assert approved["status"] == "approved"
    assert approved["role"] == "STAFF"
    with pytest.raises(DomainError) as repeated:
        await service.review(
            context=env.context,
            organization_id=env.org.id,
            application_id=retry["id"],
            approve=True,
            role="SHELTER_ADMIN",
        )
    assert repeated.value.code == "join_already_reviewed"
    await set_authentication_user_scope(env.db, user_id)
    memberships = (
        await env.db.scalars(
            select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        )
    ).all()
    assert [(m.organization_id, m.role) for m in memberships] == [(env.org.id, "STAFF")]


async def test_concurrent_registration_creates_one_identity_and_rolls_back_partial_failure():
    import asyncio

    from services.api.app.persistence.models.audit import AuditRecord
    from services.api.app.persistence.models.identity import RefreshTokenRecord
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    sub = str(uuid4())
    transaction_ids = []
    barrier = asyncio.Barrier(2)

    async def attempt():
        async with maker() as db, db.begin():
            await db.execute(text("SET LOCAL ROLE strayhub_runtime"))
            verifier = Verifier()
            verifier.sub = sub
            service = GoogleAuthenticationService(
                SessionService(
                    AuthenticationRepository(db),
                    password_hasher=Argon2PasswordHasher(),
                    access_token=SimpleNamespace(issue=lambda claims: "test-jwt"),
                ),
                verifier,
            )
            transaction, browser = await service.begin(
                purpose="login", client_id="test", display_name="Concurrent synthetic"
            )
            transaction_ids.append(transaction["transaction_id"])
            verifier.nonce = transaction["nonce"]
            await barrier.wait()
            return await service.exchange(
                transaction_id=transaction["transaction_id"],
                credential="synthetic",
                browser=browser,
                csrf=transaction["csrf_token"],
                client_id="test",
            )

    try:
        results = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=15)
        assert results[0]["user_id"] == results[1]["user_id"]
        assert results[0]["session_id"] != results[1]["session_id"]
        async with maker() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(GoogleUserBinding)
                    .where(GoogleUserBinding.google_sub == sub)
                )
                == 1
            )
        failure_name = str(uuid4())

        def fail_issue(claims):
            raise RuntimeError("synthetic issuance failure")

        with pytest.raises(RuntimeError):
            async with maker() as db, db.begin():
                await db.execute(text("SET LOCAL ROLE strayhub_runtime"))
                verifier = Verifier()
                verifier.sub = failure_name
                service = GoogleAuthenticationService(
                    SessionService(
                        AuthenticationRepository(db),
                        password_hasher=Argon2PasswordHasher(),
                        access_token=SimpleNamespace(issue=fail_issue),
                    ),
                    verifier,
                )
                transaction, browser = await service.begin(
                    purpose="login", client_id="test", display_name=failure_name
                )
                verifier.nonce = transaction["nonce"]
                await service.exchange(
                    transaction_id=transaction["transaction_id"],
                    credential="synthetic",
                    browser=browser,
                    csrf=transaction["csrf_token"],
                    client_id="test",
                )
        async with maker() as db:
            assert (
                await db.scalar(
                    select(func.count()).select_from(User).where(User.display_name == failure_name)
                )
                == 0
            )
    finally:
        # Exact synthetic identities created by this test only; never demo data.
        async with maker() as db, db.begin():
            ids = list(
                (
                    await db.scalars(
                        select(GoogleUserBinding.user_id).where(GoogleUserBinding.google_sub == sub)
                    )
                ).all()
            )
            sessions = select(SessionRecord.id).where(SessionRecord.user_id.in_(ids))
            await db.execute(
                delete(RefreshTokenRecord).where(RefreshTokenRecord.session_id.in_(sessions))
            )
            await db.execute(
                delete(GoogleAuthTransaction).where(GoogleAuthTransaction.id.in_(transaction_ids))
            )
            await db.execute(delete(SessionRecord).where(SessionRecord.user_id.in_(ids)))
            await db.execute(delete(AuditRecord).where(AuditRecord.actor_user_id.in_(ids)))
            await db.execute(delete(GoogleUserBinding).where(GoogleUserBinding.google_sub == sub))
            await db.execute(delete(User).where(User.id.in_(ids)))
        await engine.dispose()


@pytest_asyncio.fixture
async def setup():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as connection:
        outer = await connection.begin()
        db = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        repo = AuthenticationRepository(db)
        org = await repo.add(Organization(code=str(uuid4()), name="Google test A", status="active"))
        other_org = await repo.add(
            Organization(code=str(uuid4()), name="Google test B", status="active")
        )
        hasher = Argon2PasswordHasher()
        admin = await repo.add(
            User(
                username=str(uuid4()),
                display_name="Manager",
                password_hash=hasher.hash("test-password"),
                status="active",
            )
        )
        await repo.add(
            OrganizationMembership(
                user_id=admin.id, organization_id=org.id, role="SHELTER_ADMIN", status="active"
            )
        )
        await db.commit()
        await connection.execute(text("SET LOCAL ROLE strayhub_runtime"))
        sessions = SessionService(
            repo,
            password_hasher=hasher,
            access_token=SimpleNamespace(issue=lambda claims: "test-jwt"),
        )
        verifier = Verifier()
        verifier.sub = str(uuid4())
        service = GoogleAuthenticationService(sessions, verifier)
        context = RequestContext(
            user_id=admin.id, organization_id=org.id, membership_id=None, role="SHELTER_ADMIN"
        )
        try:
            yield SimpleNamespace(
                db=db,
                repo=repo,
                service=service,
                sessions=sessions,
                verifier=verifier,
                org=org,
                other_org=other_org,
                admin=admin,
                context=context,
            )
        finally:
            await db.close()
            await outer.rollback()
    await engine.dispose()


async def register(s, name="New account"):
    transaction, browser = await s.service.begin(
        purpose="login", client_id="test", display_name=name
    )
    s.verifier.nonce = transaction["nonce"]
    result = await s.service.exchange(
        transaction_id=transaction["transaction_id"],
        credential="synthetic",
        browser=browser,
        csrf=transaction["csrf_token"],
        client_id="test",
    )
    return result, transaction, browser


async def test_new_user_has_no_roles_can_refresh_and_logout(setup):
    s = setup
    result, transaction, browser = await register(s)
    user = await s.repo.get_user(result["user_id"])
    assert user.username is None and user.password_hash is None and user.platform_role is None
    assert await s.repo.memberships(user.id) == []
    account = await s.service.account(user_id=user.id, session_id=result["session_id"])
    assert account["state"] == "account_only" and account["organizations"] == []
    refreshed = await s.sessions.refresh(refresh_token=result["refresh_token"])
    assert refreshed["refresh_token"] != result["refresh_token"]
    with pytest.raises(DomainError):
        await s.service.exchange(
            transaction_id=transaction["transaction_id"],
            credential="synthetic",
            browser=browser,
            csrf=transaction["csrf_token"],
            client_id="test",
        )
    await s.sessions.logout(session_id=result["session_id"])
    with pytest.raises(DomainError):
        await s.sessions.refresh(refresh_token=refreshed["refresh_token"])


async def test_browser_csrf_nonce_and_registration_intent_are_required(setup):
    s = setup
    transaction, browser = await s.service.begin(purpose="login", client_id="test")
    s.verifier.nonce = transaction["nonce"]
    arguments = dict(
        transaction_id=transaction["transaction_id"],
        credential="synthetic",
        browser=browser,
        csrf=transaction["csrf_token"],
        client_id="test",
    )
    for override in ({"browser": "wrong"}, {"csrf": "wrong"}, {"client_id": "wrong"}):
        with pytest.raises(DomainError) as error:
            await s.service.exchange(**(arguments | override))
        assert error.value.status_code == 403
    s.verifier.nonce = "wrong"
    with pytest.raises(DomainError):
        await s.service.exchange(**arguments)
    s.verifier.nonce = transaction["nonce"]
    with pytest.raises(DomainError) as error:
        await s.service.exchange(**arguments)
    assert error.value.code == "google_registration_required"
    assert (
        await s.db.scalar(
            select(func.count())
            .select_from(GoogleUserBinding)
            .where(GoogleUserBinding.google_sub == s.verifier.sub)
        )
        == 0
    )


async def test_link_preserves_identity_and_unlink_revokes_sessions(setup):
    s = setup
    session = await s.repo.add(
        SessionRecord(
            user_id=s.admin.id,
            status="active",
            session_origin="local_web",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    with pytest.raises(DomainError):
        await s.service.begin(
            purpose="link",
            client_id="test",
            user_id=s.admin.id,
            session_id=session.id,
            password="wrong",
        )
    transaction, browser = await s.service.begin(
        purpose="link",
        client_id="test",
        user_id=s.admin.id,
        session_id=session.id,
        password="test-password",
    )
    s.verifier.nonce = transaction["nonce"]
    arguments = dict(
        transaction_id=transaction["transaction_id"],
        credential="synthetic",
        browser=browser,
        csrf=transaction["csrf_token"],
        client_id="test",
        actor_user_id=s.admin.id,
        actor_session_id=session.id,
    )
    with pytest.raises(DomainError):
        await s.service.exchange(**(arguments | {"actor_session_id": uuid4()}))
    assert await s.service.exchange(**arguments) == {"state": "linked"}
    issued, _, _ = await register(s)
    assert issued["user_id"] == s.admin.id
    assert len(await s.repo.memberships(s.admin.id)) == 1
    await s.service.unlink(user_id=s.admin.id, password="test-password")
    assert (await s.repo.google_binding(user_id=s.admin.id)).status == "revoked"
    assert (await s.repo.get_session(issued["session_id"])).status == "revoked"


async def test_invitation_requires_claim_and_admin_confirmation_with_rls(setup):
    s = setup
    result, _, _ = await register(s)
    user_id = result["user_id"]
    invitations = InvitationService(s.db)
    created = await invitations.create(context=s.context, organization_id=s.org.id, role="STAFF")
    with pytest.raises(DomainError):
        await invitations.decide(
            context=s.context, organization_id=s.org.id, invitation_id=created["id"], approve=True
        )
    await set_authentication_user_scope(s.db, user_id)
    assert (await s.db.scalars(select(OrganizationInvitation))).all() == []
    assert await invitations.list(user_id=user_id) == []
    claimed = await invitations.claim(user_id=user_id, token=created["invitation_token"])
    assert claimed["status"] == "claimed"
    assert await s.repo.memberships(user_id) == []
    assert len(await invitations.list(user_id=user_id)) == 1
    await set_organization_scope(s.db, s.other_org.id)
    assert (await s.db.scalars(select(OrganizationInvitation))).all() == []
    with pytest.raises(DomainError):
        await invitations.create(context=s.context, organization_id=s.other_org.id, role="STAFF")
    approved = await invitations.decide(
        context=s.context, organization_id=s.org.id, invitation_id=created["id"], approve=True
    )
    assert approved["status"] == "approved"
    account = await s.service.account(user_id=user_id, session_id=result["session_id"])
    assert account["organizations"][0]["role"] == "STAFF"
    assert account["organizations"][0]["id"] == s.org.id


async def test_google_only_cannot_unlink_and_remote_refresh_is_denied(setup):
    s = setup
    result, _, _ = await register(s)
    with pytest.raises(DomainError):
        await s.service.unlink(user_id=result["user_id"], password="anything")
    with pytest.raises(DomainError):
        await s.sessions.refresh(
            refresh_token=result["refresh_token"], public_exposure_profile="shared-demo-dev"
        )


async def test_expired_transaction_and_disabled_user_fail_closed(setup):
    s = setup
    result, _, _ = await register(s)
    user = await s.repo.get_user(result["user_id"])
    user.status = "disabled"
    transaction, browser = await s.service.begin(purpose="login", client_id="test")
    s.verifier.nonce = transaction["nonce"]
    with pytest.raises(DomainError):
        await s.service.exchange(
            transaction_id=transaction["transaction_id"],
            credential="synthetic",
            browser=browser,
            csrf=transaction["csrf_token"],
            client_id="test",
        )
    row = await s.db.get(GoogleAuthTransaction, transaction["transaction_id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(DomainError) as error:
        await s.service.exchange(
            transaction_id=transaction["transaction_id"],
            credential="synthetic",
            browser=browser,
            csrf=transaction["csrf_token"],
            client_id="test",
        )
    assert error.value.status_code == 403


async def test_http_google_browser_exchange_me_refresh_logout_and_tenant_denial(setup, monkeypatch):
    import httpx
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from services.api.app.api import google_authentication
    from services.api.app.api.authentication import get_session_service
    from services.api.app.api.dependencies import request_session
    from services.api.app.config.settings import get_settings
    from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
    from services.api.app.main import app

    s = setup
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    settings = get_settings()
    for field, value in {
        "auth_jwt_active_private_key": private,
        "auth_jwt_active_public_key": public,
        "google_auth_enabled": True,
        "google_auth_client_id": "test.apps.googleusercontent.com",
        "google_auth_origin": "http://localhost:3001",
        "login_trusted_proxy_enabled": False,
    }.items():
        monkeypatch.setattr(settings, field, value)
    s.sessions.access_token = JwtAccessTokenAdapter(
        private_key=private,
        public_keys={settings.auth_jwt_active_public_key_reference: public},
        issuer=settings.auth_jwt_issuer,
        audience=settings.auth_jwt_audience,
        ttl_seconds=900,
        active_kid=settings.auth_jwt_active_public_key_reference,
    )
    monkeypatch.setattr(google_authentication, "google_identity_verifier", s.verifier)

    async def session_override():
        return s.db

    app.dependency_overrides[request_session] = session_override
    app.dependency_overrides[get_session_service] = lambda: s.sessions
    headers = {"Origin": "http://localhost:3001", "X-StrayHub-Account": "1"}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:3001"
        ) as client:
            bad = await client.post("/v1/auth/google/transactions", json={"purpose": "login"})
            assert bad.status_code == 403
            begin = await client.post(
                "/v1/auth/google/transactions",
                json={"purpose": "login", "display_name": "HTTP test"},
                headers=headers,
            )
            assert begin.status_code == 200, begin.text
            assert (
                "HttpOnly" in begin.headers["set-cookie"]
                and "SameSite=strict" in begin.headers["set-cookie"]
            )
            transaction = begin.json()
            s.verifier.nonce = transaction["nonce"]
            exchange_headers = headers | {"X-CSRF-Token": transaction["csrf_token"]}
            payload = {"transaction_id": transaction["transaction_id"], "credential": "synthetic"}
            bad = await client.post("/v1/auth/google/exchange", json=payload, headers=headers)
            assert bad.status_code == 403
            response = await client.post(
                "/v1/auth/google/exchange", json=payload, headers=exchange_headers
            )
            assert response.status_code == 200, response.text
            result = response.json()
            bearer = {"Authorization": "Bearer " + result["access_token"]}
            for path in ("/v1/auth/me", "/v1/auth/account"):
                response = await client.get(path, headers=bearer)
                assert response.status_code == 200, response.text
            response = await client.get(f"/v1/auth/join-target/{s.org.id}", headers=bearer)
            assert response.json() == {"id": str(s.org.id), "name": s.org.name}
            response = await client.post(
                "/v1/auth/join-applications",
                json={"organization_id": str(s.org.id), "role": "SHELTER_ADMIN"},
                headers=bearer | headers,
            )
            assert response.status_code == 422
            response = await client.post(
                "/v1/auth/join-applications",
                json={"organization_id": str(s.org.id)},
                headers=bearer,
            )
            assert response.status_code == 403
            response = await client.post(
                "/v1/auth/join-applications",
                json={"organization_id": str(s.org.id)},
                headers=bearer | headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "pending"
            assert response.json()["role"] is None
            response = await client.get("/v1/auth/join-applications", headers=bearer)
            assert len(response.json()) == 1
            response = await client.post(
                "/v1/auth/invitations/claim",
                json={"invitation_token": "synthetic-unused-token" * 3},
                headers=bearer | headers,
            )
            assert response.status_code == 410
            response = await client.get("/v1/management/animals", headers=bearer)
            assert response.status_code in {403, 409}, response.text
            response = await client.put(
                "/v1/auth/active-shelter-context",
                json={"organization_id": str(s.org.id)},
                headers=bearer,
            )
            assert response.status_code == 404
            response = await client.post(
                "/v1/auth/refresh", json={"refresh_token": result["refresh_token"]}
            )
            assert response.status_code == 200
            response = await client.post("/v1/auth/logout", headers=bearer)
            assert response.status_code == 204
            response = await client.get("/v1/auth/account", headers=bearer)
            assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(request_session, None)
        app.dependency_overrides.pop(get_session_service, None)
