from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency fallback
    certifi = None


ASSET_REF_PATTERN = re.compile(
    r"""(?:src|href)=["']([^"']*assets/index-[^"'?#\s]+\.(?:js|css)(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)
ASSET_NAME_PATTERN = re.compile(r"assets/index-[^\"'?#\s]+\.(?:js|css)", re.IGNORECASE)
REQUIRED_TRACK_TERMS = ("用户轨道", "模型轨道")
BANNED_USER_VISIBLE_TERMS = (
    "运营复盘口径仍在迁移",
    "Phase 5 baseline",
    "research contract",
    "pending_rebuild",
    "manifest",
    "verified",
    "missing_news_evidence",
    "event_conflict_high",
    "market_data_stale",
    "用于汇总价格、事件与降级状态的融合层",
)
TEXT_LIKE_KEYS = {
    "action_label",
    "auto_execute_note",
    "confidence_label",
    "description",
    "detail",
    "direction_label",
    "fill_rule_label",
    "gate",
    "label",
    "latest_reason",
    "message",
    "note",
    "status_label",
    "step_trigger_label",
    "summary",
    "title",
}
TEXT_LIST_KEYS = {
    "constraints",
    "highlights",
    "invalidators",
    "notes",
    "risk_flags",
}
IGNORED_TEXT_KEYS = {
    "action",
    "action_definition",
    "artifact_id",
    "artifact_type",
    "auth_mode",
    "benchmark_definition",
    "benchmark_source",
    "cost_definition",
    "cost_source",
    "current_value",
    "direction",
    "id",
    "label_definition",
    "manifest_id",
    "policy_type",
    "quantity_definition",
    "recommendation_key",
    "review_window_definition",
    "role",
    "source",
    "source_classification",
    "status",
    "validation_artifact_id",
    "validation_manifest_id",
    "validation_mode",
}
NOISY_FINGERPRINT_KEYS = {
    "created_at",
    "data_latency_seconds",
    "ended_at",
    "generated_at",
    "id",
    "last_data_time",
    "last_market_data_at",
    "last_resumed_at",
    "paused_at",
    "session_key",
    "started_at",
    "updated_at",
}
NOISY_LAUNCH_GATE_CURRENT_VALUE_LABELS = {
    "刷新与性能预算",
}
API_ENDPOINTS = {
    "dashboard-operations": "/dashboard/operations",
    "settings-runtime": "/settings/runtime",
    "dashboard-candidates": "/dashboard/candidates",
}


class ReleaseVerificationError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _build_opener(cookie_jar: CookieJar | None = None):
    handlers: list[Any] = [
        request.ProxyHandler({}),
        request.HTTPSHandler(context=_ssl_context()),
    ]
    if cookie_jar is not None:
        handlers.append(request.HTTPCookieProcessor(cookie_jar))
    return request.build_opener(*handlers)


def _read_response_bytes(response) -> bytes:
    payload = response.read()
    return payload if isinstance(payload, bytes) else bytes(payload)


def _decode_body(payload: bytes, content_type: str | None = None) -> str:
    charset = "utf-8"
    if content_type:
        match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
    return payload.decode(charset, errors="replace")


def _request_bytes(
    opener,
    url: str,
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
) -> bytes:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with opener.open(req, timeout=timeout) as response:
            return _read_response_bytes(response)
    except error.HTTPError as exc:
        detail = _decode_body(exc.read(), exc.headers.get("content-type"))
        raise ReleaseVerificationError(f"{method} {url} failed: {exc.code} {detail}".strip()) from exc
    except error.URLError as exc:
        raise ReleaseVerificationError(f"{method} {url} failed: {exc.reason}") from exc


def _request_text(
    opener,
    url: str,
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
) -> str:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with opener.open(req, timeout=timeout) as response:
            payload = _read_response_bytes(response)
            return _decode_body(payload, response.headers.get("content-type"))
    except error.HTTPError as exc:
        detail = _decode_body(exc.read(), exc.headers.get("content-type"))
        raise ReleaseVerificationError(f"{method} {url} failed: {exc.code} {detail}".strip()) from exc
    except error.URLError as exc:
        raise ReleaseVerificationError(f"{method} {url} failed: {exc.reason}") from exc


def _request_json(
    opener,
    url: str,
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
) -> dict[str, Any]:
    rendered = _request_text(opener, url, timeout=timeout, headers=headers, method=method, body=body)
    try:
        payload = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ReleaseVerificationError(f"{method} {url} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReleaseVerificationError(f"{method} {url} returned non-object JSON")
    return payload


def extract_asset_references(html: str) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in ASSET_REF_PATTERN.findall(html):
        name_match = ASSET_NAME_PATTERN.search(ref)
        if not name_match:
            continue
        name = name_match.group(0)
        if name in seen:
            continue
        seen.add(name)
        assets.append({"name": name, "ref": ref})
    return assets


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _asset_hashes_from_dist(dist_dir: Path) -> dict[str, str]:
    index_path = dist_dir / "index.html"
    if not index_path.exists():
        raise ReleaseVerificationError(f"Missing frontend build output: {index_path}")
    html = index_path.read_text(encoding="utf-8")
    assets = extract_asset_references(html)
    if not assets:
        raise ReleaseVerificationError(f"No index assets found in {index_path}")
    hashes: dict[str, str] = {}
    for asset in assets:
        asset_path = dist_dir / asset["name"]
        if not asset_path.exists():
            raise ReleaseVerificationError(f"Missing asset from build output: {asset_path}")
        hashes[asset["name"]] = _sha256_file(asset_path)
    return hashes


def _asset_hashes_from_served_html(
    opener,
    page_url: str,
    html: str,
    *,
    timeout: int,
) -> tuple[dict[str, str], dict[str, str]]:
    assets = extract_asset_references(html)
    if not assets:
        raise ReleaseVerificationError(f"No index assets found in served page: {page_url}")
    hashes: dict[str, str] = {}
    asset_urls: dict[str, str] = {}
    for asset in assets:
        asset_url = parse.urljoin(page_url, asset["ref"])
        asset_urls[asset["name"]] = asset_url
        hashes[asset["name"]] = sha256_bytes(_request_bytes(opener, asset_url, timeout=timeout))
    return hashes, asset_urls


def normalize_payload_for_fingerprint(payload: Any) -> Any:
    return _normalize_payload_for_fingerprint(payload, path=())


def _normalize_payload_for_fingerprint(payload: Any, *, path: tuple[str, ...]) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(payload):
            if _should_drop_fingerprint_key(key):
                continue
            if _should_drop_contextual_fingerprint_field(payload, key, path=path):
                continue
            normalized_value = _normalize_payload_for_fingerprint(payload[key], path=(*path, key))
            normalized[key] = normalized_value
        return normalized
    if isinstance(payload, list):
        return [_normalize_payload_for_fingerprint(item, path=path) for item in payload]
    return payload


def _should_drop_fingerprint_key(key: str) -> bool:
    lowered = key.lower()
    return (
        key in NOISY_FINGERPRINT_KEYS
        or lowered.endswith("_at")
        or lowered.endswith("_time")
        or lowered.endswith("_timestamp")
        or lowered in {"token_id", "last_modified"}
    )


def _should_drop_contextual_fingerprint_field(
    parent: dict[str, Any],
    key: str,
    *,
    path: tuple[str, ...],
) -> bool:
    return (
        (
            key in {"current_value", "status"}
            and path
            and path[-1] == "launch_gates"
            and parent.get("gate") in NOISY_LAUNCH_GATE_CURRENT_VALUE_LABELS
        )
        or (key == "message" and path and path[-1] == "intraday_source_status")
        or (key in {"observed", "status"} and path and path[-1] == "performance_thresholds")
        or (key == "warning_gate_count" and path and path[-1] == "launch_readiness")
    )


def fingerprint_payload(payload: dict[str, Any]) -> str:
    normalized = normalize_payload_for_fingerprint(payload)
    rendered = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(rendered.encode("utf-8"))


def collect_user_visible_text_fragments(payload: Any) -> list[str]:
    fragments: list[str] = []
    _collect_user_visible_text(payload, fragments)
    return [fragment for fragment in fragments if fragment]


def _collect_user_visible_text(payload: Any, fragments: list[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in IGNORED_TEXT_KEYS:
                continue
            if key in TEXT_LIKE_KEYS and isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    fragments.append(stripped)
                continue
            if key in TEXT_LIST_KEYS and isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        fragments.append(item.strip())
                continue
            _collect_user_visible_text(value, fragments)
        return
    if isinstance(payload, list):
        for item in payload:
            _collect_user_visible_text(item, fragments)


def find_banned_terms_in_text(text: str, banned_terms: Iterable[str] = BANNED_USER_VISIBLE_TERMS) -> list[str]:
    lowered = text.lower()
    return [term for term in banned_terms if term.lower() in lowered]


def audit_user_visible_operations_text(
    operations_payload: dict[str, Any],
    *,
    required_terms: Iterable[str] = REQUIRED_TRACK_TERMS,
    banned_terms: Iterable[str] = BANNED_USER_VISIBLE_TERMS,
) -> dict[str, Any]:
    fragments = sorted(set(collect_user_visible_text_fragments(operations_payload)))
    combined_text = "\n".join(fragments)
    missing_required_terms = [term for term in required_terms if term not in combined_text]
    banned_hits = find_banned_terms_in_text(combined_text, banned_terms)
    return {
        "passed": not missing_required_terms and not banned_hits,
        "required_terms": list(required_terms),
        "missing_required_terms": missing_required_terms,
        "banned_terms": list(banned_terms),
        "banned_hits": banned_hits,
        "text_fragment_count": len(fragments),
        "combined_text": combined_text,
        "fragments": fragments,
    }


def build_release_manifest(
    *,
    release_id: str,
    commit_sha: str,
    released_at: str,
    repo_root: Path,
    runtime_root: Path,
    local_frontend_url: str,
    local_api_base_url: str,
    canonical_base_url: str,
    artifact_root: Path,
    previous_successful_manifest: dict[str, Any] | None,
    asset_sets: dict[str, Any],
    api_fingerprints: dict[str, Any],
    operations_text_audit: dict[str, Any],
    artifact_paths: dict[str, str],
) -> dict[str, Any]:
    previous_manifest_path = None
    previous_commit_sha = None
    if previous_successful_manifest:
        previous_manifest_path = previous_successful_manifest.get("manifest_path")
        previous_commit_sha = previous_successful_manifest.get("commit_sha")
    return {
        "status": "passed",
        "release_id": release_id,
        "released_at": released_at,
        "commit_sha": commit_sha,
        "manifest_path": str(artifact_root / "manifest.json"),
        "repo_root": str(repo_root),
        "runtime_root": str(runtime_root),
        "local_frontend_url": local_frontend_url,
        "local_api_base_url": local_api_base_url,
        "canonical_base_url": canonical_base_url,
        "artifact_root": str(artifact_root),
        "asset_sets": asset_sets,
        "api_fingerprints": api_fingerprints,
        "operations_text_audit": operations_text_audit,
        "artifacts": artifact_paths,
        "rollback": {
            "previous_successful_manifest_path": previous_manifest_path,
            "previous_successful_commit_sha": previous_commit_sha,
        },
    }


def _write_text(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def _build_api_headers(header_name: str, header_value: str | None) -> dict[str, str]:
    if not header_value:
        return {}
    return {header_name: header_value}


def _load_previous_successful_manifest(output_root: Path) -> dict[str, Any] | None:
    latest_path = output_root / "latest-successful.json"
    if not latest_path.exists():
        return None
    try:
        return json.loads(latest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseVerificationError(f"Invalid prior release manifest: {latest_path}") from exc


def _derive_canonical_login_url(canonical_base_url: str, override: str | None) -> str:
    if override:
        return override
    parsed = parse.urlsplit(canonical_base_url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, "/auth/login", "", ""))


def _canonical_next_path(canonical_base_url: str) -> str:
    parsed = parse.urlsplit(canonical_base_url)
    path = parsed.path or "/"
    return f"{path}?{parsed.query}" if parsed.query else path


def _login_canonical(
    opener,
    *,
    login_url: str,
    canonical_base_url: str,
    username: str,
    password: str,
    timeout: int,
    cookie_jar: CookieJar,
) -> None:
    body = json.dumps(
        {
            "username": username,
            "password": password,
            "next": _canonical_next_path(canonical_base_url),
        }
    ).encode("utf-8")
    payload = _request_json(
        opener,
        login_url,
        timeout=timeout,
        headers={"content-type": "application/json"},
        method="POST",
        body=body,
    )
    if "redirectTo" not in payload:
        raise ReleaseVerificationError(f"Canonical login did not return redirectTo: {login_url}")
    if not any(cookie.name == "hz_auth_session" for cookie in cookie_jar):
        raise ReleaseVerificationError("Canonical login did not yield hz_auth_session cookie")


def verify_release_parity(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).resolve()
    runtime_root = Path(args.runtime_root).resolve()
    output_root = Path(args.release_output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    previous_successful_manifest = _load_previous_successful_manifest(output_root)

    commit_sha = args.expected_commit_sha.strip()
    released_at = datetime.now(timezone.utc).isoformat()
    release_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{commit_sha[:12]}"
    artifact_root = output_root / release_id
    artifact_root.mkdir(parents=True, exist_ok=True)

    anonymous_opener = _build_opener()
    local_frontend_url = _trailing_slash(args.local_frontend_url)
    local_api_base_url = _trailing_slash(args.local_api_base_url)
    canonical_base_url = _trailing_slash(args.canonical_base_url)

    repo_dist = repo_root / "frontend" / "dist"
    runtime_dist = runtime_root / "frontend" / "dist"
    repo_index_html_path = repo_dist / "index.html"
    runtime_index_html_path = runtime_dist / "index.html"

    if not repo_index_html_path.exists():
        raise ReleaseVerificationError(f"Repo frontend build output missing: {repo_index_html_path}")
    if not runtime_index_html_path.exists():
        raise ReleaseVerificationError(f"Runtime frontend build output missing: {runtime_index_html_path}")

    repo_html = repo_index_html_path.read_text(encoding="utf-8")
    runtime_dist_html = runtime_index_html_path.read_text(encoding="utf-8")
    _write_text(artifact_root / "repo-index.html", repo_html)
    _write_text(artifact_root / "runtime-dist-index.html", runtime_dist_html)

    repo_assets = _asset_hashes_from_dist(repo_dist)
    runtime_dist_assets = _asset_hashes_from_dist(runtime_dist)

    local_frontend_html = _request_text(anonymous_opener, local_frontend_url, timeout=args.timeout_seconds)
    _write_text(artifact_root / "runtime-served-index.html", local_frontend_html)
    local_frontend_assets, local_asset_urls = _asset_hashes_from_served_html(
        anonymous_opener,
        local_frontend_url,
        local_frontend_html,
        timeout=args.timeout_seconds,
    )

    if repo_assets != runtime_dist_assets:
        raise ReleaseVerificationError("Repo build assets do not match runtime dist assets")
    if repo_assets != local_frontend_assets:
        raise ReleaseVerificationError("Repo build assets do not match localhost served assets")

    canonical_username = args.canonical_username or os.getenv("ASHARE_CANONICAL_USERNAME", "")
    canonical_password = args.canonical_password or os.getenv("ASHARE_CANONICAL_PASSWORD", "")
    if not canonical_username or not canonical_password:
        raise ReleaseVerificationError(
            "Canonical release verification requires ASHARE_CANONICAL_USERNAME and ASHARE_CANONICAL_PASSWORD"
        )
    cookie_jar = CookieJar()
    canonical_opener = _build_opener(cookie_jar)
    canonical_login_url = _derive_canonical_login_url(canonical_base_url, args.canonical_login_url)
    _login_canonical(
        canonical_opener,
        login_url=canonical_login_url,
        canonical_base_url=canonical_base_url,
        username=canonical_username,
        password=canonical_password,
        timeout=args.timeout_seconds,
        cookie_jar=cookie_jar,
    )

    canonical_frontend_html = _request_text(canonical_opener, canonical_base_url, timeout=args.timeout_seconds)
    _write_text(artifact_root / "canonical-index.html", canonical_frontend_html)
    canonical_frontend_assets, canonical_asset_urls = _asset_hashes_from_served_html(
        canonical_opener,
        canonical_base_url,
        canonical_frontend_html,
        timeout=args.timeout_seconds,
    )

    if repo_assets != canonical_frontend_assets:
        raise ReleaseVerificationError("Repo build assets do not match canonical served assets")

    api_headers = _build_api_headers(args.beta_access_header_name, args.beta_access_key)
    api_fingerprints: dict[str, Any] = {}
    snapshot_paths: dict[str, str] = {
        "repo_index_html": str(artifact_root / "repo-index.html"),
        "runtime_dist_index_html": str(artifact_root / "runtime-dist-index.html"),
        "runtime_served_index_html": str(artifact_root / "runtime-served-index.html"),
        "canonical_index_html": str(artifact_root / "canonical-index.html"),
    }
    canonical_operations_payload: dict[str, Any] | None = None
    local_operations_payload: dict[str, Any] | None = None
    for slug, endpoint in API_ENDPOINTS.items():
        local_url = parse.urljoin(local_api_base_url, endpoint.lstrip("/"))
        canonical_url = parse.urljoin(_trailing_slash(parse.urljoin(canonical_base_url, "api/")), endpoint.lstrip("/"))
        local_payload = _request_json(
            anonymous_opener,
            local_url,
            timeout=args.timeout_seconds,
            headers=api_headers,
        )
        canonical_payload = _request_json(
            canonical_opener,
            canonical_url,
            timeout=args.timeout_seconds,
            headers=api_headers,
        )
        local_snapshot_path = artifact_root / f"local-{slug}.json"
        canonical_snapshot_path = artifact_root / f"canonical-{slug}.json"
        _write_json(local_snapshot_path, local_payload)
        _write_json(canonical_snapshot_path, canonical_payload)
        snapshot_paths[f"local_{slug}"] = str(local_snapshot_path)
        snapshot_paths[f"canonical_{slug}"] = str(canonical_snapshot_path)

        local_normalized = normalize_payload_for_fingerprint(local_payload)
        canonical_normalized = normalize_payload_for_fingerprint(canonical_payload)
        local_fingerprint = fingerprint_payload(local_payload)
        canonical_fingerprint = fingerprint_payload(canonical_payload)
        api_fingerprints[endpoint] = {
            "local_url": local_url,
            "canonical_url": canonical_url,
            "local_fingerprint": local_fingerprint,
            "canonical_fingerprint": canonical_fingerprint,
            "match": local_fingerprint == canonical_fingerprint,
            "local_snapshot_path": str(local_snapshot_path),
            "canonical_snapshot_path": str(canonical_snapshot_path),
            "normalized_local_size": len(json.dumps(local_normalized, ensure_ascii=False)),
            "normalized_canonical_size": len(json.dumps(canonical_normalized, ensure_ascii=False)),
        }
        if local_fingerprint != canonical_fingerprint:
            raise ReleaseVerificationError(f"API fingerprint mismatch for {endpoint}")
        if slug == "dashboard-operations":
            local_operations_payload = local_payload
            canonical_operations_payload = canonical_payload

    if local_operations_payload is None or canonical_operations_payload is None:
        raise ReleaseVerificationError("Operations payload was not captured during release verification")

    local_operations_audit = audit_user_visible_operations_text(local_operations_payload)
    canonical_operations_audit = audit_user_visible_operations_text(canonical_operations_payload)
    if not local_operations_audit["passed"]:
        raise ReleaseVerificationError(
            f"Local operations text audit failed: missing={local_operations_audit['missing_required_terms']}, "
            f"banned={local_operations_audit['banned_hits']}"
        )
    if not canonical_operations_audit["passed"]:
        raise ReleaseVerificationError(
            f"Canonical operations text audit failed: missing={canonical_operations_audit['missing_required_terms']}, "
            f"banned={canonical_operations_audit['banned_hits']}"
        )

    operations_text_audit = {
        "local": local_operations_audit,
        "canonical": canonical_operations_audit,
        "match": local_operations_audit["combined_text"] == canonical_operations_audit["combined_text"],
    }
    if not operations_text_audit["match"]:
        raise ReleaseVerificationError("Local and canonical operations text projections do not match")

    asset_sets = {
        "repo_build": {
            "index_html_path": str(repo_index_html_path),
            "assets": repo_assets,
        },
        "runtime_dist": {
            "index_html_path": str(runtime_index_html_path),
            "assets": runtime_dist_assets,
        },
        "runtime_served": {
            "page_url": local_frontend_url,
            "assets": local_frontend_assets,
            "asset_urls": local_asset_urls,
        },
        "canonical_served": {
            "page_url": canonical_base_url,
            "assets": canonical_frontend_assets,
            "asset_urls": canonical_asset_urls,
            "login_url": canonical_login_url,
        },
        "all_match": (
            repo_assets == runtime_dist_assets == local_frontend_assets == canonical_frontend_assets
        ),
    }

    manifest = build_release_manifest(
        release_id=release_id,
        commit_sha=commit_sha,
        released_at=released_at,
        repo_root=repo_root,
        runtime_root=runtime_root,
        local_frontend_url=local_frontend_url,
        local_api_base_url=local_api_base_url,
        canonical_base_url=canonical_base_url,
        artifact_root=artifact_root,
        previous_successful_manifest=previous_successful_manifest,
        asset_sets=asset_sets,
        api_fingerprints=api_fingerprints,
        operations_text_audit=operations_text_audit,
        artifact_paths=snapshot_paths,
    )
    manifest_path = artifact_root / "manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(output_root / "latest-successful.json", manifest)
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify repo/runtime/canonical release parity.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--local-frontend-url", default=os.getenv("ASHARE_LOCAL_FRONTEND_URL", "http://127.0.0.1:5173/"))
    parser.add_argument("--local-api-base-url", default=os.getenv("ASHARE_LOCAL_API_BASE_URL", "http://127.0.0.1:8000/"))
    parser.add_argument(
        "--canonical-base-url",
        default=os.getenv("ASHARE_CANONICAL_BASE_URL", "https://hernando-zhao.cn/projects/ashare-dashboard/"),
    )
    parser.add_argument("--canonical-login-url", default=os.getenv("ASHARE_CANONICAL_LOGIN_URL"))
    parser.add_argument("--canonical-username", default=os.getenv("ASHARE_CANONICAL_USERNAME"))
    parser.add_argument("--canonical-password", default=os.getenv("ASHARE_CANONICAL_PASSWORD"))
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument(
        "--release-output-root",
        default=os.getenv("ASHARE_RELEASE_OUTPUT_ROOT"),
    )
    parser.add_argument(
        "--beta-access-header-name",
        default=os.getenv("ASHARE_BETA_ACCESS_HEADER", "X-Ashare-Beta-Key"),
    )
    parser.add_argument(
        "--beta-access-key",
        default=os.getenv("ASHARE_RELEASE_BETA_ACCESS_KEY") or os.getenv("ASHARE_BETA_ACCESS_KEY"),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("ASHARE_RELEASE_TIMEOUT_SECONDS", "20")),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.release_output_root:
        args.release_output_root = str(Path(args.repo_root).resolve() / "output" / "releases")
    try:
        manifest_path = verify_release_parity(args)
    except ReleaseVerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
