#!/usr/bin/env python3
"""Fingerprint one deployed runtime or verify it against an external baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from email.parser import BytesParser
from pathlib import Path
from typing import NoReturn


SCHEMA_VERSION = 2
VERIFY_SCHEMA_VERSION = 1
BASELINE_SCHEMA_VERSION = 1
PROJECT = "mcgs-full-chain-studio"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RELEASE_ID_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$")
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
FINGERPRINT_FIELDS = frozenset(
    {
        "schema_version",
        "runtime_root_sha256",
        "release_root_sha256",
        "requirements_lock_sha256",
        "interpreter",
        "distributions",
        "distributions_sha256",
    }
)
INTERPRETER_FIELDS = frozenset({"realpath", "sha256", "mode", "uid", "gid"})
BASELINE_FIELDS = frozenset(
    {
        "schema_version",
        "project",
        "release_id",
        "version",
        "release_root",
        "archive_sha256",
        "release_manifest_sha256",
        "runtime_guard_helper_sha256",
        "runtime_fingerprint",
    }
)


class VerificationError(ValueError):
    """A stable, non-sensitive verification failure."""


def fail_verification(message: str) -> NoReturn:
    raise VerificationError(message)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def strict_json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        text = payload.decode("utf-8", errors="strict")

        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise VerificationError(f"{label} JSON is invalid") from exc
    if not isinstance(value, dict):
        fail_verification(f"{label} JSON is invalid")
    return value


def metadata_prefix(path: Path) -> bytes:
    value = path.lstat()
    return f"{stat.S_IMODE(value.st_mode):04o}:{value.st_uid}:{value.st_gid}".encode(
        "ascii"
    )


def tree_digest(root: Path, *, excluded_top_levels: frozenset[str] = frozenset()) -> str:
    digest = hashlib.sha256()
    digest.update(b"ROOT\0" + metadata_prefix(root) + b"\0")
    candidates = (
        path
        for path in root.rglob("*")
        if path.relative_to(root).parts
        and path.relative_to(root).parts[0] not in excluded_top_levels
    )
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        prefix = metadata_prefix(path)
        if path.is_symlink():
            digest.update(
                b"L\0"
                + relative
                + b"\0"
                + prefix
                + b"\0"
                + os.readlink(path).encode("utf-8")
                + b"\0"
            )
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + prefix + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + prefix + b"\0")
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            digest.update(b"\0")
        else:
            raise ValueError("unsupported runtime entry")
    return digest.hexdigest()


def has_posix_acl(path: Path) -> bool:
    if not hasattr(os, "listxattr"):
        return False
    try:
        names = os.listxattr(path, follow_symlinks=False)
    except (OSError, TypeError) as exc:
        raise ValueError("cannot inspect runtime ACL metadata") from exc
    return any(
        name in {"system.posix_acl_access", "system.posix_acl_default"}
        for name in names
    )


def require_root_owned_immutable(root: Path) -> None:
    """Reject release entries whose Unix ownership, mode, or ACL permits mutation."""

    for path in (root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())):
        value = path.lstat()
        if value.st_uid != 0 or value.st_gid != 0:
            raise ValueError("release entry is not owned by root:root")
        if not stat.S_ISLNK(value.st_mode) and stat.S_IMODE(value.st_mode) & 0o022:
            raise ValueError("release entry is writable by group or other")
        if has_posix_acl(path):
            raise ValueError("release entry has an extended or default ACL")


def require_exact_root_object(
    path: Path, *, directory: bool, mode: int, label: str
) -> None:
    value = path.lstat()
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if path.is_symlink() or not expected_kind(value.st_mode):
        fail_verification(f"{label} permissions are unsafe")
    if value.st_uid != 0 or value.st_gid != 0 or stat.S_IMODE(value.st_mode) != mode:
        fail_verification(f"{label} permissions are unsafe")
    try:
        if has_posix_acl(path):
            fail_verification(f"{label} permissions are unsafe")
    except ValueError as exc:
        raise VerificationError(f"{label} permissions are unsafe") from exc


def distribution_inventory(root: Path) -> tuple[list[str], str]:
    rows: list[str] = []
    for metadata_path in sorted(root.rglob("*.dist-info/METADATA")):
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise ValueError("distribution metadata must be a regular non-symlink file")
        message = BytesParser().parsebytes(metadata_path.read_bytes(), headersonly=True)
        name = (message.get("Name") or "").strip().lower().replace("_", "-")
        version = (message.get("Version") or "").strip()
        if not name or not version or any(character.isspace() for character in name + version):
            raise ValueError("invalid distribution metadata")
        rows.append(f"{name}=={version}")
    rows.sort()
    payload = ("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")
    return rows, hashlib.sha256(payload).hexdigest()


def canonical_real_file(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"{label} does not resolve to a regular file")
    return resolved


def create_fingerprint(
    runtime_argument: Path,
    python_argument: Path,
    *,
    lock_argument: Path | None = None,
    release_argument: Path | None = None,
    immutable: bool = False,
) -> dict[str, object]:
    runtime_root = runtime_argument.resolve(strict=True)
    if runtime_argument.is_symlink() or not runtime_root.is_dir():
        raise ValueError("runtime root must be a real directory")
    try:
        python_argument.parent.resolve(strict=True).relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError("runtime python path escaped the deployment root") from exc
    interpreter = canonical_real_file(python_argument, "runtime interpreter")

    release_root_sha256: str | None = None
    if release_argument is not None:
        release_root = release_argument.resolve(strict=True)
        if release_argument.is_symlink() or not release_root.is_dir():
            raise ValueError("release root must be a real directory")
        try:
            runtime_root.relative_to(release_root)
        except ValueError as exc:
            raise ValueError("runtime root escaped the release root") from exc
        if immutable:
            require_root_owned_immutable(release_root)
        release_root_sha256 = tree_digest(
            release_root,
            excluded_top_levels=frozenset(
                {runtime_root.relative_to(release_root).parts[0]}
            ),
        )
    elif immutable:
        raise ValueError("--require-root-owned-immutable requires --release-root")

    lock_sha256: str | None = None
    if lock_argument is not None:
        lock_path = lock_argument.resolve(strict=True)
        if lock_argument.is_symlink() or not lock_path.is_file():
            raise ValueError("requirements lock must be a regular non-symlink file")
        lock_sha256 = hash_file(lock_path)

    distributions, distributions_sha256 = distribution_inventory(runtime_root)
    interpreter_stat = interpreter.stat()
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_root_sha256": tree_digest(runtime_root),
        "release_root_sha256": release_root_sha256,
        "requirements_lock_sha256": lock_sha256,
        "interpreter": {
            "realpath": str(interpreter),
            "sha256": hash_file(interpreter),
            "mode": f"{stat.S_IMODE(interpreter_stat.st_mode):04o}",
            "uid": interpreter_stat.st_uid,
            "gid": interpreter_stat.st_gid,
        },
        "distributions": distributions,
        "distributions_sha256": distributions_sha256,
    }


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def validate_fingerprint_contract(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != FINGERPRINT_FIELDS:
        fail_verification("baseline contract is invalid")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 2:
        fail_verification("baseline contract is invalid")
    for name in ("runtime_root_sha256", "distributions_sha256"):
        if not valid_sha256(value.get(name)):
            fail_verification("baseline contract is invalid")
    for name in ("release_root_sha256", "requirements_lock_sha256"):
        if not valid_sha256(value.get(name)):
            fail_verification("baseline contract is invalid")
    distributions = value.get("distributions")
    if not isinstance(distributions, list) or any(
        not isinstance(row, str) or not row for row in distributions
    ):
        fail_verification("baseline contract is invalid")
    interpreter = value.get("interpreter")
    if not isinstance(interpreter, dict) or set(interpreter) != INTERPRETER_FIELDS:
        fail_verification("baseline contract is invalid")
    if not isinstance(interpreter.get("realpath"), str) or not interpreter["realpath"]:
        fail_verification("baseline contract is invalid")
    if not valid_sha256(interpreter.get("sha256")):
        fail_verification("baseline contract is invalid")
    if not isinstance(interpreter.get("mode"), str) or re.fullmatch(
        r"[0-7]{4}", interpreter["mode"]
    ) is None:
        fail_verification("baseline contract is invalid")
    if type(interpreter.get("uid")) is not int or type(interpreter.get("gid")) is not int:
        fail_verification("baseline contract is invalid")
    return value


def resolve_release(
    release_argument: Path, releases_root_argument: Path, *, require_symlink: bool
) -> tuple[Path, Path, str]:
    releases_root = releases_root_argument.resolve(strict=True)
    if releases_root_argument.is_symlink() or not releases_root.is_dir():
        fail_verification("releases root is invalid")
    if require_symlink:
        try:
            value = release_argument.lstat()
        except OSError as exc:
            raise VerificationError("current release link is invalid") from exc
        if not stat.S_ISLNK(value.st_mode):
            fail_verification("current release link is invalid")
    elif release_argument.is_symlink():
        fail_verification("release root is invalid")
    try:
        release_root = release_argument.resolve(strict=True)
    except OSError as exc:
        raise VerificationError("current release link is invalid") from exc
    if not release_root.is_dir() or release_root.parent != releases_root:
        fail_verification("current release escaped releases root")
    release_id = release_root.name
    if RELEASE_ID_PATTERN.fullmatch(release_id) is None:
        fail_verification("release identity is invalid")
    return release_root, releases_root, release_id


def verify_release(
    release_argument: Path,
    releases_root_argument: Path,
    baseline_directory_argument: Path,
    *,
    expected_manifest_sha256: str | None,
    immutable: bool,
    require_symlink: bool,
) -> dict[str, object]:
    helper_argument = Path(__file__)
    try:
        helper_stat = helper_argument.lstat()
    except OSError as exc:
        raise VerificationError("runtime guard helper is invalid") from exc
    if not stat.S_ISREG(helper_stat.st_mode) or helper_argument.is_symlink():
        fail_verification("runtime guard helper is invalid")
    try:
        helper_path = helper_argument.resolve(strict=True)
    except OSError as exc:
        raise VerificationError("runtime guard helper is invalid") from exc
    helper_sha256 = hash_file(helper_path)

    release_root, _releases_root, release_id = resolve_release(
        release_argument, releases_root_argument, require_symlink=require_symlink
    )
    baseline_directory = baseline_directory_argument.resolve(strict=True)
    if baseline_directory_argument.is_symlink() or not baseline_directory.is_dir():
        fail_verification("baseline directory is invalid")
    baseline_path = baseline_directory / f"{release_id}.json"
    try:
        baseline_stat = baseline_path.lstat()
    except OSError as exc:
        raise VerificationError("runtime baseline is missing") from exc
    if not stat.S_ISREG(baseline_stat.st_mode) or baseline_path.is_symlink():
        fail_verification("runtime baseline is invalid")

    if immutable:
        require_exact_root_object(
            baseline_directory.parent,
            directory=True,
            mode=0o755,
            label="runtime guard directory",
        )
        require_exact_root_object(
            baseline_directory,
            directory=True,
            mode=0o755,
            label="baseline directory",
        )
        require_exact_root_object(
            Path(__file__),
            directory=False,
            mode=0o444,
            label="runtime guard helper",
        )
        require_exact_root_object(
            baseline_path,
            directory=False,
            mode=0o444,
            label="runtime baseline",
        )

    baseline_bytes = baseline_path.read_bytes()
    baseline = strict_json_object(baseline_bytes, "baseline")
    if set(baseline) != BASELINE_FIELDS:
        fail_verification("baseline contract is invalid")
    if (
        type(baseline.get("schema_version")) is not int
        or baseline["schema_version"] != BASELINE_SCHEMA_VERSION
        or baseline.get("project") != PROJECT
        or baseline.get("release_id") != release_id
        or not isinstance(baseline.get("version"), str)
        or VERSION_PATTERN.fullmatch(baseline["version"]) is None
        or baseline.get("release_root") != str(release_root)
        or not valid_sha256(baseline.get("archive_sha256"))
        or not valid_sha256(baseline.get("release_manifest_sha256"))
        or not valid_sha256(baseline.get("runtime_guard_helper_sha256"))
    ):
        fail_verification("baseline contract is invalid")
    if baseline["runtime_guard_helper_sha256"] != helper_sha256:
        fail_verification("runtime guard helper digest mismatch")
    fingerprint = validate_fingerprint_contract(baseline.get("runtime_fingerprint"))

    baseline_manifest_sha256 = baseline["release_manifest_sha256"]
    if expected_manifest_sha256 is not None:
        if (
            SHA256_PATTERN.fullmatch(expected_manifest_sha256) is None
            or expected_manifest_sha256 != baseline_manifest_sha256
        ):
            fail_verification("expected manifest digest mismatch")
    manifest_path = release_root / "release-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        fail_verification("release manifest is invalid")
    if hash_file(manifest_path) != baseline_manifest_sha256:
        fail_verification("manifest digest mismatch")

    try:
        actual = create_fingerprint(
            release_root / ".venv",
            release_root / ".venv" / "bin" / "python",
            lock_argument=release_root / "requirements.production.lock.txt",
            release_argument=release_root,
            immutable=immutable,
        )
    except (OSError, ValueError) as exc:
        raise VerificationError("runtime fingerprint could not be recomputed") from exc
    if actual != fingerprint:
        fail_verification("runtime fingerprint mismatch")
    return {
        "schema_version": VERIFY_SCHEMA_VERSION,
        "status": "passed",
        "release_id": release_id,
        "version": baseline["version"],
        "release_manifest_sha256": baseline_manifest_sha256,
        "runtime_fingerprint_sha256": canonical_json_sha256(actual),
        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "runtime_guard_helper_sha256": helper_sha256,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--python", dest="python_path", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--release-root", type=Path)
    verification_mode = parser.add_mutually_exclusive_group()
    verification_mode.add_argument("--verify-current", type=Path)
    verification_mode.add_argument("--verify-release", type=Path)
    parser.add_argument("--releases-root", type=Path)
    parser.add_argument("--baseline-directory", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--require-root-owned-immutable", action="store_true")
    args = parser.parse_args()
    verify_argument = args.verify_current or args.verify_release
    if verify_argument is not None:
        if args.runtime_root is not None or args.python_path is not None:
            parser.error("fingerprint and verification modes are mutually exclusive")
        if args.lock is not None or args.release_root is not None:
            parser.error("verification mode does not accept fingerprint path options")
        if args.releases_root is None or args.baseline_directory is None:
            parser.error("verification mode requires releases and baseline directories")
    else:
        if args.runtime_root is None or args.python_path is None:
            parser.error("fingerprint mode requires --runtime-root and --python")
        if args.releases_root is not None or args.baseline_directory is not None:
            parser.error("fingerprint mode does not accept verification directories")
        if args.expected_manifest_sha256 is not None:
            parser.error("fingerprint mode does not accept an expected manifest digest")
    return args


def main() -> int:
    args = parse_arguments()
    verify_argument = args.verify_current or args.verify_release
    if verify_argument is not None:
        try:
            result = verify_release(
                verify_argument,
                args.releases_root,
                args.baseline_directory,
                expected_manifest_sha256=args.expected_manifest_sha256,
                immutable=args.require_root_owned_immutable,
                require_symlink=args.verify_current is not None,
            )
        except (OSError, VerificationError, ValueError) as exc:
            message = str(exc) if isinstance(exc, VerificationError) else "verification failed"
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
    else:
        try:
            result = create_fingerprint(
                args.runtime_root,
                args.python_path,
                lock_argument=args.lock,
                release_argument=args.release_root,
                immutable=args.require_root_owned_immutable,
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
