from __future__ import annotations

from dataclasses import dataclass
import os

from fastapi import HTTPException, Request, status

from ashare_evidence.account_space import ROLE_MEMBER, ROLE_ROOT
from ashare_evidence.access import BetaAccessContext, load_beta_access_config

USER_LOGIN_HEADER = "X-HZ-User-Login"
USER_ROLE_HEADER = "X-HZ-User-Role"
ACT_AS_LOGIN_HEADER = "X-Ashare-Act-As-Login"


@dataclass(frozen=True)
class StockAccessContext:
    actor_login: str
    actor_role: str
    target_login: str
    can_act_as: bool
    auth_mode: str


def _map_legacy_role(role: str) -> str:
    if role == "operator":
        return ROLE_ROOT
    return ROLE_MEMBER


def _fallback_legacy_context(request: Request) -> StockAccessContext:
    config = load_beta_access_config()
    if config.mode in {"open", "disabled", "off"}:
        actor_login = os.getenv("ASHARE_DEV_ACTOR_LOGIN", "root").strip() or "root"
        actor_role = os.getenv("ASHARE_DEV_ACTOR_ROLE", ROLE_ROOT).strip().lower() or ROLE_ROOT
        if actor_role not in {ROLE_ROOT, ROLE_MEMBER}:
            actor_role = ROLE_ROOT
        return StockAccessContext(
            actor_login=actor_login,
            actor_role=actor_role,
            target_login=actor_login,
            can_act_as=actor_role == ROLE_ROOT,
            auth_mode="dev_open",
        )

    header_value = request.headers.get(config.header_name)
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"missing authenticated identity headers ({USER_LOGIN_HEADER}/{USER_ROLE_HEADER})",
        )
    role = config.allowlist.get(header_value)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="legacy beta access denied")
    actor_login = "root" if role == "operator" else f"member-{header_value[:8]}"
    actor_role = _map_legacy_role(role)
    return StockAccessContext(
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=actor_login,
        can_act_as=actor_role == ROLE_ROOT,
        auth_mode=f"legacy_{config.mode}",
    )


def require_stock_access(request: Request) -> StockAccessContext:
    actor_login = str(request.headers.get(USER_LOGIN_HEADER, "")).strip()
    actor_role = str(request.headers.get(USER_ROLE_HEADER, "")).strip().lower()
    if not actor_login or not actor_role:
        cookie_header = str(request.headers.get("cookie", ""))
        if "hz_auth_session=" in cookie_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"authenticated session missing trusted identity headers ({USER_LOGIN_HEADER}/{USER_ROLE_HEADER})",
            )
        return _fallback_legacy_context(request)
    if actor_role not in {ROLE_ROOT, ROLE_MEMBER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="unsupported stock role")
    act_as_login = str(request.headers.get(ACT_AS_LOGIN_HEADER, "")).strip()
    if act_as_login and actor_role != ROLE_ROOT and act_as_login != actor_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="member cannot act as another account")
    target_login = act_as_login or actor_login
    return StockAccessContext(
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=target_login,
        can_act_as=actor_role == ROLE_ROOT,
        auth_mode="root_domain_headers",
    )


def require_stock_root(access: StockAccessContext) -> StockAccessContext:
    if access.actor_role != ROLE_ROOT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="root role required")
    return access
