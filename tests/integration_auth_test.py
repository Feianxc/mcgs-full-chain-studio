from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from protocol_studio.security import LOGIN_CSRF_COOKIE_NAME, hash_password


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
    match = re.search(r'id="loginCsrf"[^>]*value="([^"]+)"', response.text)
    assert match is not None
    cookie_token = client.cookies.get(LOGIN_CSRF_COOKIE_NAME)
    assert cookie_token and secrets.compare_digest(cookie_token, match.group(1))
    return match.group(1)


def main() -> int:
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
        with TestClient(app_module.app, base_url="https://testserver") as client:
            for path in ("/", "/protocol/"):
                response = client.get(path, follow_redirects=False)
                assert response.status_code == 303, (path, response.status_code)
                assert "/login" in response.headers.get("location", "")

            assert client.get("/login").status_code == 200
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

        assert security_db.is_file()
        assert security_db.resolve().is_relative_to(runtime_root.resolve())
        if runs_root.exists():
            assert not any(runs_root.iterdir())

    print(json.dumps({"status": "passed", "suite": "integration_auth"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
