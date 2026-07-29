from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from _test_support import REPO_ROOT, add_repo_to_import_path

add_repo_to_import_path()

from fastapi.testclient import TestClient

from protocol_studio.security import (
    LOGIN_CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    hash_password,
)


RUNTIME_TEMP = tempfile.TemporaryDirectory(prefix="mcgs-security-tests-")
TEST_ROOT = Path(RUNTIME_TEMP.name)
DATABASE_PATH = TEST_ROOT / "security.sqlite3"
RUNS_ROOT = TEST_ROOT / "runs"
ADMIN_USERNAME = "FIXTURE.ADMIN"
INITIAL_PASSWORD = f"{secrets.token_urlsafe(18)}Aa1!"
UPDATED_PASSWORD = f"{secrets.token_urlsafe(18)}Bb2!"

os.environ.update(
    {
        "PROTOCOL_STUDIO_AUTH_ENABLED": "true",
        "PROTOCOL_STUDIO_SECURITY_DB": str(DATABASE_PATH),
        "MCGS_FULL_CHAIN_RUNS_ROOT": str(RUNS_ROOT),
        "PROTOCOL_STUDIO_RUNS_ROOT": str(RUNS_ROOT),
        "PROTOCOL_STUDIO_ADMIN_USERNAME": ADMIN_USERNAME,
        "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": hash_password(INITIAL_PASSWORD),
        "PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": "true",
        "PROTOCOL_STUDIO_COOKIE_SECURE": "true",
        "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": "https://testserver",
        "PROTOCOL_STUDIO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
    }
)

from protocol_studio.app import app  # noqa: E402


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def login_csrf_from_page(client: TestClient) -> str:
    response = client.get("/login")
    expect(response.status_code == 200, f"login page status: {response.status_code}")
    match = re.search(r'id="loginCsrf" type="hidden" value="([^"]+)"', response.text)
    expect(match is not None, "login CSRF field missing")
    cookie_value = client.cookies.get(LOGIN_CSRF_COOKIE_NAME)
    expect(bool(cookie_value), "login CSRF cookie missing")
    expect(cookie_value == match.group(1), "login CSRF cookie and form token differ")
    return match.group(1)


def login(client: TestClient, password: str, csrf_token: str):
    return client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": password, "csrf_token": csrf_token},
    )


def verify_auth_disabled_compatibility() -> None:
    child_env = os.environ.copy()
    child_env.update(
        {
            "PROTOCOL_STUDIO_AUTH_ENABLED": "false",
            "PROTOCOL_STUDIO_SECURITY_DB": str(TEST_ROOT / "disabled.sqlite3"),
            "MCGS_FULL_CHAIN_RUNS_ROOT": str(TEST_ROOT / "disabled-runs"),
            "PROTOCOL_STUDIO_RUNS_ROOT": str(TEST_ROOT / "disabled-runs"),
            "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": "",
            "PROTOCOL_STUDIO_COOKIE_SECURE": "false",
            "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": "",
        }
    )
    snippet = """
import json
from fastapi.testclient import TestClient
from protocol_studio.app import app
with TestClient(app, base_url='http://testserver') as client:
    root = client.get('/', follow_redirects=False)
    protocol = client.get('/protocol/', follow_redirects=False)
    bootstrap = client.get('/api/bootstrap')
    auth = client.post('/api/auth/login', json={'username':'x','password':'x','csrf_token':'x'*16})
    print(json.dumps({'root': root.status_code, 'protocol': protocol.status_code, 'bootstrap': bootstrap.status_code, 'auth': auth.status_code}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=REPO_ROOT,
        env=child_env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    expect(completed.returncode == 0, f"auth-disabled child failed: {completed.stderr}")
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    expect(
        payload == {"root": 200, "protocol": 200, "bootstrap": 200, "auth": 404},
        f"auth-disabled mismatch: {payload}",
    )


def main() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        root = client.get("/", follow_redirects=False)
        expect(root.status_code == 303, f"unauthenticated root status: {root.status_code}")
        expect(root.headers.get("location") == "/login", "root login redirect is not exact")
        protocol = client.get("/protocol/", follow_redirects=False)
        expect(protocol.status_code == 303, f"unauthenticated protocol status: {protocol.status_code}")
        expect(protocol.headers.get("location") == "/login", "protocol login redirect is not exact")

        hostile_origin = client.get(
            "/?next=https://evil.invalid/steal",
            headers={
                "Host": "localhost",
                "X-Forwarded-Host": "evil.invalid",
                "X-Forwarded-Proto": "http",
            },
            follow_redirects=False,
        )
        expect(hostile_origin.status_code == 303, "host-independent redirect status drifted")
        expect(
            hostile_origin.headers.get("location") == "/login",
            "host or query input influenced the login redirect",
        )

        bootstrap = client.get("/api/bootstrap")
        expect(bootstrap.status_code == 401, f"unauthenticated bootstrap status: {bootstrap.status_code}")
        expect(bootstrap.json().get("code") == "auth_required", "missing auth_required code")

        health = client.get("/api/health")
        expect(health.status_code == 200 and health.json().get("status") == "ok", "health endpoint unavailable")
        for header in (
            "content-security-policy",
            "strict-transport-security",
            "x-content-type-options",
            "x-frame-options",
            "referrer-policy",
            "permissions-policy",
        ):
            expect(bool(health.headers.get(header)), f"security header missing: {header}")

        csrf_token = login_csrf_from_page(client)
        rejected = login(client, "definitely-wrong", csrf_token)
        expect(rejected.status_code == 401, f"wrong password status: {rejected.status_code}")

        accepted = login(client, INITIAL_PASSWORD, csrf_token)
        expect(accepted.status_code == 200 and accepted.json().get("ok") is True, "correct login failed")
        expect(accepted.json().get("must_change_password") is True, "first login did not require password change")
        set_cookie = accepted.headers.get("set-cookie", "")
        expect("HttpOnly" in set_cookie, "session cookie is not HttpOnly")
        expect("Secure" in set_cookie, "session cookie is not Secure")
        expect("SameSite=lax" in set_cookie, "session cookie SameSite is not Lax")
        expect(bool(client.cookies.get(SESSION_COOKIE_NAME)), "session cookie missing")

        workspace = client.get("/")
        expect(workspace.status_code == 200, f"authenticated root status: {workspace.status_code}")
        expect(client.get("/protocol/").status_code == 200, "authenticated protocol entry unavailable")

        blocked = client.get("/api/bootstrap")
        expect(blocked.status_code == 403, f"bootstrap was not blocked before password change: {blocked.status_code}")
        expect(blocked.json().get("code") == "password_change_required", "password_change_required code missing")

        no_csrf = client.post("/api/recommend", json={"config": {}})
        expect(no_csrf.status_code == 403, f"missing-CSRF status: {no_csrf.status_code}")
        expect(no_csrf.json().get("code") == "csrf_invalid", "missing-CSRF code mismatch")

        session_response = client.get("/api/auth/session")
        expect(session_response.status_code == 200, "session endpoint failed")
        session_payload = session_response.json()
        csrf_token = session_payload.get("csrf_token", "")
        expect(session_payload.get("must_change_password") is True, "session force-change state mismatch")
        expect(len(csrf_token) >= 32, "session CSRF token invalid")

        changed = client.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": csrf_token},
            json={"current_password": INITIAL_PASSWORD, "new_password": UPDATED_PASSWORD},
        )
        expect(changed.status_code == 200 and changed.json().get("ok") is True, f"password change failed: {changed.text}")
        expect(not client.cookies.get(SESSION_COOKIE_NAME), "session cookie survived password change")
        expect(client.get("/api/auth/session").status_code == 401, "server session survived password change")

        csrf_token = login_csrf_from_page(client)
        old_login = login(client, INITIAL_PASSWORD, csrf_token)
        expect(old_login.status_code == 401, "old password still works")
        new_login = login(client, UPDATED_PASSWORD, csrf_token)
        expect(new_login.status_code == 200, f"new password login failed: {new_login.text}")
        expect(new_login.json().get("must_change_password") is False, "force-change flag was not cleared")
        session_payload = client.get("/api/auth/session").json()
        csrf_token = session_payload["csrf_token"]
        expect(client.get("/api/bootstrap").status_code == 200, "business API unavailable after password change")

        logged_out = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
        expect(logged_out.status_code == 200, "logout failed")
        expect(client.get("/api/bootstrap").status_code == 401, "logout did not invalidate access")

        csrf_token = login_csrf_from_page(client)
        lock_responses = [login(client, "wrong-for-lockout", csrf_token) for _ in range(5)]
        expect(lock_responses[-1].status_code == 429, "fifth failed login did not lock account")
        expect(lock_responses[-1].headers.get("retry-after") == "900", "lockout retry duration mismatch")

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        expect({"users", "sessions", "security_events"}.issubset(tables), f"security tables missing: {tables}")
        event_count = connection.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
        expect(isinstance(event_count, int) and event_count >= 10, "security event audit trail incomplete")
    finally:
        connection.close()

    verify_auth_disabled_compatibility()
    RUNTIME_TEMP.cleanup()
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": 26,
                "auth_disabled_compatibility": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
