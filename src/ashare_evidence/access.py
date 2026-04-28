from __future__ import annotations

from dataclasses import dataclass
import os

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class BetaAccessContext:
    mode: str
    role: str
    token_id: str


@dataclass(frozen=True)
class BetaAccessConfig:
    mode: str
    header_name: str
    allowlist: dict[str, str]


DEFAULT_ALLOWLIST = {
    "viewer-key": "viewer",
    "analyst-key": "analyst",
    "operator-key": "operator",
}


def load_beta_access_config() -> BetaAccessConfig:
    mode = os.getenv("ASHARE_BETA_ACCESS_MODE", "open").strip().lower() or "open"
    header_name = os.getenv("ASHARE_BETA_ACCESS_HEADER", "X-Ashare-Beta-Key").strip() or "X-Ashare-Beta-Key"
    raw_allowlist = os.getenv("ASHARE_BETA_ALLOWLIST", "").strip()
    allowlist: dict[str, str] = {}
    if raw_allowlist:
        for entry in raw_allowlist.split(","):
            token, _, role = entry.strip().partition(":")
            if token and role:
                allowlist[token.strip()] = role.strip()
    elif mode in {"allowlist", "header_allowlist"}:
        allowlist = dict(DEFAULT_ALLOWLIST)
    return BetaAccessConfig(mode=mode, header_name=header_name, allowlist=allowlist)


def require_beta_access(request: Request) -> BetaAccessContext:
    config = load_beta_access_config()
    if config.mode in {"open", "disabled", "off"}:
        return BetaAccessContext(mode=config.mode, role="anonymous", token_id="open-access")

    header_value = request.headers.get(config.header_name)
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"beta access denied: missing {config.header_name} header",
        )

    role = config.allowlist.get(header_value)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="beta access denied: supplied key is not in the allowlist",
        )

    return BetaAccessContext(mode=config.mode, role=role, token_id=header_value[:8])


def require_beta_write_access(access: BetaAccessContext) -> BetaAccessContext:
    if access.role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer key is read-only for watchlist mutations")
    return access
