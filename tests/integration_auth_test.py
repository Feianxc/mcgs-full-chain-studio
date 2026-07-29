from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from protocol_studio.security import (
    LOGIN_CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    hash_password,
)


def set_cookie_header(response: object, cookie_name: str) -> str:
    headers = getattr(response, "headers")
    prefix = f"{cookie_name}="
    matches = [
        header
        for header in headers.get_list("set-cookie")
        if header.startswith(prefix)
    ]
    assert len(matches) == 1, (cookie_name, len(matches))
    return matches[0]


def assert_secure_cookie_contract(
    response: object,
    cookie_name: str,
    *,
    same_site: str,
) -> None:
    header = set_cookie_header(response, cookie_name)
    attributes = {part.strip().lower() for part in header.split(";")[1:]}
    assert "secure" in attributes
    assert "httponly" in attributes
    assert f"samesite={same_site.lower()}" in attributes


def assert_cookie_cleared(response: object, cookie_name: str) -> None:
    header = set_cookie_header(response, cookie_name)
    cookie_pair, *attribute_parts = header.split(";")
    assert cookie_pair in {f'{cookie_name}=""', f"{cookie_name}="}
    attributes = {part.strip().lower() for part in attribute_parts}
    assert "max-age=0" in attributes
    assert any(attribute.startswith("expires=") for attribute in attributes)
    assert "path=/" in attributes


def expected_release_manifest_sha256(project_root: Path) -> str | None:
    manifest_path = project_root / "release-manifest.json"
    assert not manifest_path.is_symlink()
    if not manifest_path.exists():
        return None
    assert manifest_path.is_file()
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def assert_release_manifest_header(
    response: object,
    header_name: str,
    expected_digest: str | None,
) -> None:
    headers = getattr(response, "headers")
    values = headers.get_list(header_name)
    if expected_digest is None:
        assert values == []
    else:
        assert values == [expected_digest]


def synthetic_config() -> dict:
    return {
        "workflow_version": "unified_protocol_v1",
        "project": {
            "name": "合成认证集成测试",
            "code": "SYNTH-AUTH-001",
            "protocol_title": "动环通讯协议",
        },
        "routes": {
            "A": {
                "start_boxes": {"count": 1, "instance_names": ["S1"]},
                "plug_boxes": {
                    "board_number_start": 101,
                    "sequence": [{"type_code": "3P*1", "count": 1, "layout_pattern": "1"}],
                },
            },
            "B": {"copy_from_A": True},
        },
        "extensions": {
            "single_cabinet": {"enabled": False, "cabinet_count": 0},
            "repeater": {"enabled": False, "A_count": 0, "B_count": 0},
            "alarm_state_word": {"enabled": True, "base_address": 6100, "word_mode": "16bit"},
        },
        "profiles": {},
    }


def login_form_csrf(client: TestClient) -> str:
    response = client.get("/login")
    assert response.status_code == 200
    assert_secure_cookie_contract(
        response,
        LOGIN_CSRF_COOKIE_NAME,
        same_site="strict",
    )
    match = re.search(r'id="loginCsrf"[^>]*value="([^"]+)"', response.text)
    assert match is not None
    cookie_token = client.cookies.get(LOGIN_CSRF_COOKIE_NAME)
    assert cookie_token and secrets.compare_digest(cookie_token, match.group(1))
    return match.group(1)


def main() -> int:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml requirements.production.lock.txt ./" in dockerfile
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert (REPO_ROOT / "requirements.production.lock.txt").is_file()
    expected_release_digest = expected_release_manifest_sha256(REPO_ROOT)

    with tempfile.TemporaryDirectory(prefix="mcgs-auth-integration-") as temp_dir:
        runtime_root = Path(temp_dir)
        security_db = runtime_root / "security.sqlite3"
        runs_root = runtime_root / "runs"
        admin_username = "FIXTURE.ADMIN"
        login_password = f"{secrets.token_urlsafe(18)}Aa1!"

        os.environ.update(
            {
                "PROTOCOL_STUDIO_AUTH_ENABLED": "true",
                "PROTOCOL_STUDIO_SECURITY_DB": str(security_db),
                "MCGS_FULL_CHAIN_RUNS_ROOT": str(runs_root),
                "PROTOCOL_STUDIO_RUNS_ROOT": str(runs_root),
                "PROTOCOL_STUDIO_ADMIN_USERNAME": admin_username,
                "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": hash_password(login_password),
                "PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": "false",
                "PROTOCOL_STUDIO_COOKIE_SECURE": "true",
                "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": "https://testserver",
                "PROTOCOL_STUDIO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
            }
        )

        import protocol_studio.app as app_module

        assert app_module.RUNS_ROOT.resolve() == runs_root.resolve()
        project_metadata = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        expected_version = project_metadata["project"]["version"]
        assert app_module.PROJECT_VERSION == expected_version
        assert app_module.app.version == expected_version
        assert app_module.RELEASE_MANIFEST_SHA256 == expected_release_digest
        assert (
            app_module.read_release_manifest_sha256(REPO_ROOT)
            == expected_release_digest
        )
        synthetic_manifest = runtime_root / "release-manifest.json"
        synthetic_manifest.write_bytes(b'{"fixture":true}\n')
        synthetic_manifest_digest = hashlib.sha256(
            synthetic_manifest.read_bytes()
        ).hexdigest()
        assert (
            app_module.read_release_manifest_sha256(runtime_root)
            == synthetic_manifest_digest
        )
        with TestClient(app_module.app, base_url="https://testserver") as client:
            health = client.get("/api/health")
            assert health.status_code == 200
            assert health.json() == {
                "status": "ok",
                "time": health.json()["time"],
                "version": expected_version,
                "release_manifest_sha256": expected_release_digest,
            }
            assert re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",
                health.json()["time"],
            )
            assert_release_manifest_header(
                health,
                app_module.RELEASE_MANIFEST_HEADER,
                expected_release_digest,
            )
            original_manifest_digest = app_module.RELEASE_MANIFEST_SHA256
            try:
                app_module.RELEASE_MANIFEST_SHA256 = synthetic_manifest_digest
                release_health = client.get("/api/health")
            finally:
                app_module.RELEASE_MANIFEST_SHA256 = original_manifest_digest
            assert release_health.status_code == 200
            assert (
                release_health.json()["release_manifest_sha256"]
                == synthetic_manifest_digest
            )
            assert_release_manifest_header(
                release_health,
                app_module.RELEASE_MANIFEST_HEADER,
                synthetic_manifest_digest,
            )

            for path in ("/", "/protocol", "/protocol/"):
                response = client.get(path, follow_redirects=False)
                assert response.status_code == 303, (path, response.status_code)
                assert response.headers.get("location") == "/login"

            hostile_origin = client.get(
                "/?next=https://evil.invalid/steal",
                headers={
                    "Host": "localhost",
                    "X-Forwarded-Host": "evil.invalid",
                    "X-Forwarded-Proto": "http",
                },
                follow_redirects=False,
            )
            assert hostile_origin.status_code == 303
            assert hostile_origin.headers.get("location") == "/login"
            assert "evil.invalid" not in hostile_origin.headers.get("location", "")

            assert client.get("/login").status_code == 200
            expired_notice = client.get("/login?reason=session_expired")
            assert expired_notice.status_code == 200
            assert "请登录后继续使用" in expired_notice.text
            bootstrap = client.get("/api/bootstrap")
            assert bootstrap.status_code == 401
            assert bootstrap.json().get("code") == "auth_required"
            for asset_path in (
                "/assembly-static/app.js",
                "/assembly-static/styles.css",
                "/static/app.js",
            ):
                asset = client.get(asset_path)
                assert asset.status_code == 200, (asset_path, asset.status_code)
                assert len(asset.content) > 100

            login_csrf = login_form_csrf(client)
            accepted = client.post(
                "/api/auth/login",
                json={
                    "username": admin_username,
                    "password": login_password,
                    "csrf_token": login_csrf,
                },
            )
            assert accepted.status_code == 200 and accepted.json().get("ok") is True
            assert_secure_cookie_contract(
                accepted,
                SESSION_COOKIE_NAME,
                same_site="lax",
            )
            old_session_token = client.cookies.get(SESSION_COOKIE_NAME)
            assert isinstance(old_session_token, str) and len(old_session_token) >= 48
            assert client.cookies.get(LOGIN_CSRF_COOKIE_NAME) is None

            assembly_entry = client.get("/")
            protocol_entry = client.get("/protocol/")
            assert assembly_entry.status_code == 200
            assert protocol_entry.status_code == 200
            assert "/assembly-static/app.js" in assembly_entry.text
            assert "/static/app.js" in protocol_entry.text
            session = client.get("/api/auth/session")
            assert session.status_code == 200
            session_payload = session.json()
            csrf_token = session_payload.get("csrf_token")
            assert isinstance(csrf_token, str) and len(csrf_token) >= 32

            payload = {"config": synthetic_config()}
            missing_csrf = client.post("/api/recommend", json=payload)
            assert missing_csrf.status_code == 403
            assert missing_csrf.json().get("code") == "csrf_invalid"

            wrong_csrf = client.post(
                "/api/recommend",
                headers={"X-CSRF-Token": secrets.token_urlsafe(32)},
                json=payload,
            )
            assert wrong_csrf.status_code == 403
            assert wrong_csrf.json().get("code") == "csrf_invalid"

            accepted_unsafe = client.post(
                "/api/recommend",
                headers={"X-CSRF-Token": csrf_token},
                json=payload,
            )
            assert accepted_unsafe.status_code == 200, accepted_unsafe.text
            assert isinstance(accepted_unsafe.json(), dict)

            logged_out = client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": csrf_token},
            )
            assert logged_out.status_code == 200
            assert logged_out.json().get("ok") is True
            assert_cookie_cleared(logged_out, SESSION_COOKIE_NAME)
            assert client.cookies.get(SESSION_COOKIE_NAME) is None

            old_cookie_header = {"Cookie": f"{SESSION_COOKIE_NAME}={old_session_token}"}
            old_session_api = client.get("/api/bootstrap", headers=old_cookie_header)
            assert old_session_api.status_code == 401
            assert old_session_api.json().get("code") == "auth_required"
            old_session_page = client.get(
                "/",
                headers=old_cookie_header,
                follow_redirects=False,
            )
            assert old_session_page.status_code == 303
            assert old_session_page.headers.get("location") == "/login"

        assert security_db.is_file()
        assert security_db.resolve().is_relative_to(runtime_root.resolve())
        connection = sqlite3.connect(security_db)
        try:
            revoked_row = connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE token_hash = ?",
                (app_module.SECURITY_MANAGER.token_hash(old_session_token),),
            ).fetchone()
            assert revoked_row is not None
            assert isinstance(revoked_row[0], int) and revoked_row[0] == 0

            logout_events = connection.execute(
                "SELECT event_type FROM security_events WHERE event_type = ? ORDER BY id",
                ("logout",),
            ).fetchall()
            assert isinstance(logout_events, list)
            assert len(logout_events) == 1
            assert all(row == ("logout",) for row in logout_events)
        finally:
            connection.close()
        if runs_root.exists():
            assert not any(runs_root.iterdir())

    print(json.dumps({"status": "passed", "suite": "integration_auth"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
