from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc
PASSWORD_SCHEME = "scrypt"
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_DKLEN = 32
SESSION_COOKIE_NAME = "protocol_studio_session"
LOGIN_CSRF_COOKIE_NAME = "protocol_studio_login_csrf"


def utc_now() -> datetime:
    return datetime.now(UTC)


def datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_username(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("密码不能为空")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 512:
        raise ValueError("密码过长")
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password_bytes,
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        dklen=PASSWORD_DKLEN,
    )
    return (
        f"{PASSWORD_SCHEME}$n={PASSWORD_N},r={PASSWORD_R},p={PASSWORD_P},dk={PASSWORD_DKLEN}"
        f"${_b64encode(salt)}${_b64encode(derived)}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, params_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        params = {}
        for item in params_text.split(","):
            key, value = item.split("=", 1)
            params[key] = int(value)
        candidate = hashlib.scrypt(
            str(password or "").encode("utf-8"),
            salt=_b64decode(salt_text),
            n=params["n"],
            r=params["r"],
            p=params["p"],
            dklen=params["dk"],
        )
        return hmac.compare_digest(candidate, _b64decode(digest_text))
    except (KeyError, TypeError, ValueError):
        return False


def validate_new_password(password: str, username: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("新密码至少需要 12 位")
    if len(password.encode("utf-8")) > 256:
        errors.append("新密码过长")
    categories = sum(
        (
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[^A-Za-z0-9\s]", password)),
        )
    )
    if categories < 3:
        errors.append("新密码需包含大写字母、小写字母、数字、符号中的至少三类")
    if re.search(r"\s", password):
        errors.append("新密码不能包含空格")
    normalized_username = normalize_username(username)
    if normalized_username and normalized_username.lower() in password.lower():
        errors.append("新密码不能包含账号名")
    return errors


@dataclass(frozen=True)
class SecuritySettings:
    enabled: bool
    database_path: Path
    admin_username: str
    bootstrap_password_hash: str
    force_password_change: bool
    cookie_secure: bool
    session_idle_seconds: int
    session_absolute_seconds: int
    allowed_hosts: tuple[str, ...]
    external_origin: str

    @classmethod
    def from_env(cls, workspace_root: Path) -> "SecuritySettings":
        enabled = env_flag("PROTOCOL_STUDIO_AUTH_ENABLED", False)
        database_value = os.environ.get("PROTOCOL_STUDIO_SECURITY_DB", "").strip()
        database_path = (
            Path(database_value).expanduser().resolve()
            if database_value
            else (workspace_root / ".protocol-studio-security.sqlite3").resolve()
        )
        username = normalize_username(os.environ.get("PROTOCOL_STUDIO_ADMIN_USERNAME", "FEIAN"))
        password_hash = os.environ.get("PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH", "").strip()
        external_origin = os.environ.get("PROTOCOL_STUDIO_EXTERNAL_ORIGIN", "").strip().rstrip("/")
        allowed_hosts = tuple(
            dict.fromkeys(
                item.strip()
                for item in os.environ.get(
                    "PROTOCOL_STUDIO_ALLOWED_HOSTS",
                    "localhost,127.0.0.1,testserver",
                ).split(",")
                if item.strip()
            )
        )
        settings = cls(
            enabled=enabled,
            database_path=database_path,
            admin_username=username,
            bootstrap_password_hash=password_hash,
            force_password_change=env_flag("PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE", True),
            cookie_secure=env_flag("PROTOCOL_STUDIO_COOKIE_SECURE", external_origin.startswith("https://")),
            session_idle_seconds=max(
                900,
                int(os.environ.get("PROTOCOL_STUDIO_SESSION_IDLE_SECONDS", str(12 * 60 * 60))),
            ),
            session_absolute_seconds=max(
                3600,
                int(os.environ.get("PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS", str(7 * 24 * 60 * 60))),
            ),
            allowed_hosts=allowed_hosts,
            external_origin=external_origin,
        )
        if enabled:
            settings.validate()
        return settings

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Z0-9_.-]{2,64}", self.admin_username):
            raise RuntimeError("PROTOCOL_STUDIO_ADMIN_USERNAME 格式无效")
        if not self.bootstrap_password_hash.startswith(f"{PASSWORD_SCHEME}$"):
            raise RuntimeError("启用账号系统时必须提供有效的 PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH")
        if not self.allowed_hosts:
            raise RuntimeError("PROTOCOL_STUDIO_ALLOWED_HOSTS 不能为空")
        if self.cookie_secure and self.external_origin and not self.external_origin.startswith("https://"):
            raise RuntimeError("安全 Cookie 要求 PROTOCOL_STUDIO_EXTERNAL_ORIGIN 使用 HTTPS")


@dataclass(frozen=True)
class AuthSession:
    token_hash: str
    username: str
    csrf_token: str
    must_change_password: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    status_code: int
    message: str
    token: str = ""
    session: AuthSession | None = None
    retry_after: int | None = None


class SecurityManager:
    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings
        self._dummy_password_hash = ""
        if settings.enabled:
            self._dummy_password_hash = hash_password(secrets.token_urlsafe(28))
            self._initialize_database()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.settings.database_path, timeout=20)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 20000")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.settings.database_path.parent, 0o700)
        except OSError:
            pass
        now_text = datetime_text(utc_now())
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    client_ip TEXT NOT NULL,
                    user_agent TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_username_idx ON sessions(username);
                CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    username TEXT NOT NULL,
                    client_ip TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS security_events_lookup_idx
                    ON security_events(event_type, client_ip, created_at);
                """
            )
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (self.settings.admin_username,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, must_change_password,
                        failed_attempts, locked_until, created_at, updated_at
                    ) VALUES (?, ?, ?, 0, NULL, ?, ?)
                    """,
                    (
                        self.settings.admin_username,
                        self.settings.bootstrap_password_hash,
                        1 if self.settings.force_password_change else 0,
                        now_text,
                        now_text,
                    ),
                )
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (now_text,),
            )
        try:
            os.chmod(self.settings.database_path, 0o600)
        except OSError:
            pass

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

    def _event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        username: str,
        client_ip: str,
        detail: str = "",
    ) -> None:
        connection.execute(
            """
            INSERT INTO security_events (created_at, event_type, username, client_ip, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime_text(utc_now()),
                event_type[:64],
                normalize_username(username)[:64],
                str(client_ip or "unknown")[:96],
                str(detail or "")[:240],
            ),
        )

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        client_ip: str,
        user_agent: str,
    ) -> LoginResult:
        normalized = normalize_username(username)
        now = utc_now()
        now_text = datetime_text(now)
        recent_cutoff = datetime_text(now - timedelta(minutes=15))
        with self._connect() as connection:
            ip_failures = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM security_events
                    WHERE event_type = 'login_failed' AND client_ip = ? AND created_at >= ?
                    """,
                    (client_ip, recent_cutoff),
                ).fetchone()["count"]
            )
            if ip_failures >= 12:
                self._event(connection, "login_rate_limited", normalized, client_ip)
                return LoginResult(False, 429, "尝试次数过多，请 15 分钟后再试", retry_after=900)

            user = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
            stored_hash = user["password_hash"] if user is not None else self._dummy_password_hash
            locked_until = parse_datetime(user["locked_until"]) if user is not None else None
            if locked_until and locked_until > now:
                retry_after = max(1, int((locked_until - now).total_seconds()))
                self._event(connection, "login_locked", normalized, client_ip)
                return LoginResult(
                    False,
                    429,
                    f"账号暂时锁定，请 {max(1, (retry_after + 59) // 60)} 分钟后再试",
                    retry_after=retry_after,
                )

            if not verify_password(password, stored_hash) or user is None:
                failed_attempts = int(user["failed_attempts"] if user is not None else 0) + 1
                new_lock = now + timedelta(minutes=15) if user is not None and failed_attempts >= 5 else None
                if user is not None:
                    connection.execute(
                        """
                        UPDATE users
                        SET failed_attempts = ?, locked_until = ?, updated_at = ?
                        WHERE username = ?
                        """,
                        (
                            failed_attempts,
                            datetime_text(new_lock) if new_lock else None,
                            now_text,
                            normalized,
                        ),
                    )
                self._event(connection, "login_failed", normalized, client_ip)
                if new_lock:
                    return LoginResult(False, 429, "尝试次数过多，账号已锁定 15 分钟", retry_after=900)
                return LoginResult(False, 401, "账号或密码不正确")

            token = secrets.token_urlsafe(48)
            token_digest = self.token_hash(token)
            csrf_token = secrets.token_urlsafe(32)
            expires_at = now + timedelta(seconds=self.settings.session_absolute_seconds)
            connection.execute(
                """
                UPDATE users
                SET failed_attempts = 0, locked_until = NULL, updated_at = ?, last_login_at = ?
                WHERE username = ?
                """,
                (now_text, now_text, normalized),
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    token_hash, username, csrf_token, created_at, last_seen_at,
                    expires_at, client_ip, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_digest,
                    normalized,
                    csrf_token,
                    now_text,
                    now_text,
                    datetime_text(expires_at),
                    str(client_ip or "unknown")[:96],
                    str(user_agent or "")[:320],
                ),
            )
            self._event(connection, "login_success", normalized, client_ip)
            session = AuthSession(
                token_hash=token_digest,
                username=normalized,
                csrf_token=csrf_token,
                must_change_password=bool(user["must_change_password"]),
                created_at=now,
                last_seen_at=now,
                expires_at=expires_at,
            )
            return LoginResult(True, 200, "登录成功", token=token, session=session)

    def get_session(self, token: str) -> AuthSession | None:
        if not token:
            return None
        token_digest = self.token_hash(token)
        now = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, u.must_change_password
                FROM sessions AS s
                JOIN users AS u ON u.username = s.username
                WHERE s.token_hash = ?
                """,
                (token_digest,),
            ).fetchone()
            if row is None:
                return None
            created_at = parse_datetime(row["created_at"])
            last_seen_at = parse_datetime(row["last_seen_at"])
            expires_at = parse_datetime(row["expires_at"])
            if created_at is None or last_seen_at is None or expires_at is None:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest,))
                return None
            idle_expiry = last_seen_at + timedelta(seconds=self.settings.session_idle_seconds)
            if expires_at <= now or idle_expiry <= now:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest,))
                self._event(connection, "session_expired", row["username"], "session")
                return None
            if now - last_seen_at >= timedelta(minutes=5):
                last_seen_at = now
                connection.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (datetime_text(now), token_digest),
                )
            return AuthSession(
                token_hash=token_digest,
                username=row["username"],
                csrf_token=row["csrf_token"],
                must_change_password=bool(row["must_change_password"]),
                created_at=created_at,
                last_seen_at=last_seen_at,
                expires_at=expires_at,
            )

    def logout(self, token: str, *, client_ip: str) -> None:
        token_digest = self.token_hash(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username FROM sessions WHERE token_hash = ?",
                (token_digest,),
            ).fetchone()
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest,))
            if row is not None:
                self._event(connection, "logout", row["username"], client_ip)

    def change_password(
        self,
        session: AuthSession,
        current_password: str,
        new_password: str,
        *,
        client_ip: str,
    ) -> tuple[bool, str]:
        errors = validate_new_password(new_password, session.username)
        if errors:
            return False, "；".join(errors)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE username = ?",
                (session.username,),
            ).fetchone()
            if row is None or not verify_password(current_password, row["password_hash"]):
                self._event(connection, "password_change_failed", session.username, client_ip)
                return False, "当前密码不正确"
            if verify_password(new_password, row["password_hash"]):
                return False, "新密码不能与当前密码相同"
            now_text = datetime_text(utc_now())
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?, must_change_password = 0,
                    failed_attempts = 0, locked_until = NULL, updated_at = ?
                WHERE username = ?
                """,
                (hash_password(new_password), now_text, session.username),
            )
            connection.execute("DELETE FROM sessions WHERE username = ?", (session.username,))
            self._event(connection, "password_changed", session.username, client_ip)
        return True, "密码已更新，请重新登录"

    def security_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.enabled,
            "session_idle_minutes": self.settings.session_idle_seconds // 60,
            "session_absolute_hours": self.settings.session_absolute_seconds // 3600,
            "lockout_attempts": 5,
            "lockout_minutes": 15,
        }
