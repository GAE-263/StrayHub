"""Account-only API: same-origin mutations, browser transactions and explicit tenant approval."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.authentication import get_session_service
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    identity_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import (
    resolve_public_exposure_profile,
    resolve_trusted_client_ip,
)
from services.api.app.application.authentication.google_service import (
    GoogleAuthenticationService,
    digest,
)
from services.api.app.application.authentication.invitation_service import InvitationService
from services.api.app.application.authentication.login_abuse import LoginAbuseKeys
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.auth.google_identity_verifier import google_identity_verifier
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Google account"])
Database = Annotated[AsyncSession, Depends(request_session)]
Sessions = Annotated[SessionService, Depends(get_session_service)]


class TransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: str = Field(pattern="^(login|link)$")
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str = Field(default="", max_length=1024)


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: UUID
    credential: str = Field(min_length=1, max_length=8192)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_token: str = Field(min_length=40, max_length=128)


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(STAFF|SHELTER_ADMIN)$")


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    role: Literal["STAFF", "SHELTER_ADMIN"] | None = None


class JoinTargetResponse(BaseModel):
    id: UUID
    name: str


class ApplicationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    user_id: UUID
    status: Literal["pending", "approved", "rejected"]
    role: Literal["STAFF", "SHELTER_ADMIN"] | None
    created_at: datetime
    reviewed_at: datetime | None
    display_name: str | None = None


class GoogleConfigurationResponse(BaseModel):
    enabled: bool
    client_id: str | None = None


class GoogleTransactionResponse(BaseModel):
    transaction_id: UUID
    nonce: str
    csrf_token: str
    client_id: str
    expires_in: int


class GoogleSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    session_id: UUID
    user_id: UUID
    expires_in: int


class GoogleLinkedResponse(BaseModel):
    state: Literal["linked"]


class AccountUserResponse(BaseModel):
    id: UUID
    display_name: str
    username: str | None
    platform_role: str | None


class AccountOrganizationResponse(BaseModel):
    id: UUID
    code: str
    name: str
    role: str


class AccountLoginMethods(BaseModel):
    password: bool
    google: bool


class AccountResponse(BaseModel):
    user: AccountUserResponse
    state: Literal["account_only", "ready"]
    organizations: list[AccountOrganizationResponse]
    login_methods: AccountLoginMethods


class InvitationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    role: Literal["STAFF", "SHELTER_ADMIN"]
    status: Literal["open", "claimed", "approved", "revoked", "expired"]
    expires_at: datetime
    claimed_by: UUID | None
    display_name: str | None = None


class CreatedInvitationResponse(InvitationResponse):
    invitation_token: str


def check_surface(request: Request, *, mutation: bool = True, require_feature: bool = True):
    settings = get_settings()
    try:
        profile = resolve_public_exposure_profile(
            request, trusted_proxy_enabled=settings.login_trusted_proxy_enabled
        )
    except ValueError:
        raise DomainError("public_exposure_invalid", "此入口無法使用帳號功能", 403) from None
    if profile or (require_feature and not settings.google_auth_enabled):
        raise DomainError("google_not_available", "此入口尚未開放 Google 登入", 404)
    origin = settings.google_auth_origin
    parsed = urlsplit(origin)
    local = settings.app_env in {"local", "test", "testing"}
    if (
        parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or not parsed.hostname
        or not (
            parsed.scheme == "https"
            or (local and parsed.scheme == "http" and parsed.hostname == "localhost")
        )
    ):
        raise DomainError("google_not_configured", "Google 登入尚未設定", 503)
    if mutation and (
        request.headers.getlist("origin") != [origin]
        or request.headers.get("content-type", "").split(";", 1)[0] != "application/json"
        or request.headers.get("x-strayhub-account") != "1"
        or request.url.query
    ):
        raise DomainError("account_origin_invalid", "帳號請求來源無效", 403)
    if require_feature and not settings.google_auth_client_id.endswith(
        ".apps.googleusercontent.com"
    ):
        raise DomainError("google_not_configured", "Google 登入尚未設定", 503)
    return settings


async def rate_limit(request, db, *, user_id=None):
    settings = get_settings()
    try:
        ip = resolve_trusted_client_ip(
            request,
            trusted_proxy_enabled=settings.login_trusted_proxy_enabled,
            allow_local_test_peer=settings.app_env in {"local", "test", "testing"},
        )
    except ValueError:
        raise DomainError("login_source_unavailable", "登入暫時無法處理", 503) from None
    keys = LoginAbuseKeys(settings.login_abuse_hmac_secret)
    repository = AuthenticationRepository(db)
    # Persist attempt accounting before the business transaction, including failures.
    decision = await repository.consume_login_ip_attempt(
        digest("google:" + keys.ip_digest(ip)), now=datetime.now(timezone.utc)
    )
    if user_id is not None:
        account_decision = await repository.consume_login_ip_attempt(
            digest("account:" + keys.account_digest(str(user_id))), now=datetime.now(timezone.utc)
        )
        if not account_decision.allowed:
            decision = account_decision
    await db.commit()
    if not decision.allowed:
        raise DomainError(
            "login_rate_limited",
            "請稍後再試",
            429,
            headers={"Retry-After": str(decision.retry_after or 1)},
        )


def cookie_name(transaction_id: UUID, secure: bool) -> str:
    return ("__Host-" if secure else "") + "strayhub-google-" + str(transaction_id)


@router.get(
    "/v1/auth/google/config",
    response_model=GoogleConfigurationResponse,
    openapi_extra={"security": []},
)
async def configuration(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        settings = check_surface(request, mutation=False)
    except DomainError:
        return {"enabled": False}
    return {"enabled": True, "client_id": settings.google_auth_client_id}


@router.post(
    "/v1/auth/google/transactions",
    response_model=GoogleTransactionResponse,
    openapi_extra={"security": []},
)
async def begin(
    request: Request,
    response: Response,
    payload: TransactionRequest,
    db: Database,
    sessions: Sessions,
    authorization: Annotated[str | None, Header()] = None,
):  # noqa: B008
    settings = check_surface(request)
    context = None
    if payload.purpose == "link":
        context = await identity_request_context(request, db, authorization)
    await rate_limit(request, db, user_id=context.user_id if context else None)
    result, browser = await GoogleAuthenticationService(sessions, google_identity_verifier).begin(
        purpose=payload.purpose,
        client_id=settings.google_auth_client_id,
        display_name=(payload.display_name or "").strip() or None,
        user_id=context.user_id if context else None,
        session_id=context.session_id if context else None,
        password=payload.password,
    )
    await db.commit()
    secure = settings.google_auth_origin.startswith("https:")
    response.set_cookie(
        cookie_name(result["transaction_id"], secure),
        browser,
        max_age=300,
        secure=secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/v1/auth/join-target/{organization_id}", response_model=JoinTargetResponse)
async def join_target(
    request: Request,
    response: Response,
    organization_id: UUID,
    db: Database,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):
    check_surface(request, mutation=False, require_feature=False)
    response.headers["Cache-Control"] = "no-store"
    return await InvitationService(db).join_target(
        user_id=context.user_id, organization_id=organization_id
    )


@router.get("/v1/auth/join-applications", response_model=list[ApplicationResponse])
async def my_applications(
    request: Request,
    response: Response,
    db: Database,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):
    check_surface(request, mutation=False, require_feature=False)
    response.headers["Cache-Control"] = "no-store"
    return await InvitationService(db).applications(user_id=context.user_id)


@router.post("/v1/auth/join-applications", response_model=ApplicationResponse)
async def submit_application(
    request: Request,
    response: Response,
    payload: JoinRequest,
    db: Database,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):
    check_surface(request, require_feature=False)
    await rate_limit(request, db, user_id=context.user_id)
    result = await InvitationService(db).apply(
        user_id=context.user_id, organization_id=payload.organization_id
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/v1/organizations/{organization_id}/join-applications",
    response_model=list[ApplicationResponse],
)
async def list_applications(
    request: Request,
    response: Response,
    organization_id: UUID,
    db: Database,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
):
    check_surface(request, mutation=False, require_feature=False)
    response.headers["Cache-Control"] = "no-store"
    return await InvitationService(db).applications(
        context=context, organization_id=organization_id
    )


@router.post(
    "/v1/organizations/{organization_id}/join-applications/{application_id}/decision",
    response_model=ApplicationResponse,
)
async def review_application(
    request: Request,
    response: Response,
    organization_id: UUID,
    application_id: UUID,
    payload: ReviewRequest,
    db: Database,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
):
    check_surface(request, require_feature=False)
    result = await InvitationService(db).review(
        context=context,
        organization_id=organization_id,
        application_id=application_id,
        approve=payload.approve,
        role=payload.role,
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/v1/auth/google/exchange",
    response_model=GoogleSessionResponse | GoogleLinkedResponse,
    openapi_extra={"security": []},
)
async def exchange(
    request: Request,
    response: Response,
    payload: ExchangeRequest,
    db: Database,
    sessions: Sessions,
    authorization: Annotated[str | None, Header()] = None,
):  # noqa: B008
    settings = check_surface(request)
    context = None
    if authorization:
        context = await identity_request_context(request, db, authorization)
    await rate_limit(request, db, user_id=context.user_id if context else None)
    secure = settings.google_auth_origin.startswith("https:")
    cookie = cookie_name(payload.transaction_id, secure)
    result = await GoogleAuthenticationService(sessions, google_identity_verifier).exchange(
        transaction_id=payload.transaction_id,
        credential=payload.credential,
        browser=request.cookies.get(cookie, ""),
        csrf=request.headers.get("x-csrf-token", ""),
        client_id=settings.google_auth_client_id,
        actor_user_id=context.user_id if context else None,
        actor_session_id=context.session_id if context else None,
    )
    await db.commit()
    response.delete_cookie(cookie, path="/", secure=secure, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/v1/auth/account", response_model=AccountResponse)
async def account(
    request: Request,
    response: Response,
    db: Database,
    sessions: Sessions,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, mutation=False, require_feature=False)
    result = await GoogleAuthenticationService(sessions, google_identity_verifier).account(
        user_id=context.user_id,
        session_id=context.session_id,
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.delete("/v1/auth/google/binding", status_code=204)
async def unlink(
    request: Request,
    payload: PasswordRequest,
    db: Database,
    sessions: Sessions,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, require_feature=False)
    await rate_limit(request, db, user_id=context.user_id)
    await GoogleAuthenticationService(sessions, google_identity_verifier).unlink(
        user_id=context.user_id,
        password=payload.password,
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/v1/auth/invitations", response_model=list[InvitationResponse])
async def my_invitations(
    request: Request,
    response: Response,
    db: Database,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, mutation=False, require_feature=False)
    response.headers["Cache-Control"] = "no-store"
    return await InvitationService(db).list(user_id=context.user_id)


@router.post("/v1/auth/invitations/claim", response_model=InvitationResponse)
async def claim(
    request: Request,
    payload: ClaimRequest,
    db: Database,
    context: RequestContext = Depends(identity_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, require_feature=False)
    raise DomainError("invitation_replaced", "請使用收容所申請連結", 410)


@router.get(
    "/v1/organizations/{organization_id}/invitations", response_model=list[InvitationResponse]
)
async def list_invitations(
    request: Request,
    organization_id: UUID,
    db: Database,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, mutation=False, require_feature=False)
    return await InvitationService(db).list(context=context, organization_id=organization_id)


@router.post(
    "/v1/organizations/{organization_id}/invitations",
    status_code=201,
    response_model=CreatedInvitationResponse,
)
async def create_invitation(
    request: Request,
    response: Response,
    organization_id: UUID,
    payload: InvitationRequest,
    db: Database,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, require_feature=False)
    raise DomainError("invitation_replaced", "請使用收容所申請連結", 410)


@router.post(
    "/v1/organizations/{organization_id}/invitations/{invitation_id}/decision",
    response_model=InvitationResponse,
)
async def decide_invitation(
    request: Request,
    organization_id: UUID,
    invitation_id: UUID,
    payload: DecisionRequest,
    db: Database,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
):  # noqa: B008
    check_surface(request, require_feature=False)
    result = await InvitationService(db).decide(
        context=context,
        organization_id=organization_id,
        invitation_id=invitation_id,
        approve=payload.approve,
    )
    await db.commit()
    return result
