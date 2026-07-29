from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tarfile
import tempfile
from collections.abc import Callable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = REPO_ROOT / "packaging" / "build_release.py"
VERIFY_PATH = REPO_ROOT / "packaging" / "verify_release.py"
POLICY_PATH = REPO_ROOT / "packaging" / "release-allowlist.json"
PUBLIC_TREE_PATH = REPO_ROOT / "scripts" / "check_public_tree.py"
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"
VERSION = "0.0.0-contract-test"
EXPECTED_ROOT = f"mcgs-full-chain-studio-{VERSION}"

EXPECTED_DOCKER_COPY_FILES = frozenset(
    {
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "pyproject.toml",
        "requirements.production.lock.txt",
    }
)
EXPECTED_DOCKER_COPY_TREES = frozenset(
    {"assembly_studio", "mvp_generator", "protocol_studio", "resources"}
)
DOCKER_CONTEXT_METADATA = frozenset({".dockerignore", "Dockerfile"})
EXPECTED_DOCKER_BASE_IMAGE = (
    "python:3.11.6-slim-bookworm@"
    "sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b"
)
REQUIRED_DOCKER_DENY_PATTERNS = frozenset(
    {
        ".git",
        ".git/**",
        "**/.git",
        "**/.git/**",
        ".env*",
        "**/.env*",
        "**/*.db",
        "**/*.sqlite",
        "**/*.sqlite3",
        "runs",
        "runs/**",
        "**/runs",
        "**/runs/**",
        "dist",
        "dist/**",
        "**/dist",
        "**/dist/**",
        ".audit*",
        "**/.audit*",
        ".cache",
        "**/.cache",
        "__pycache__",
        "**/__pycache__",
        "node_modules",
        "**/node_modules",
        "customer-data",
        "**/customer-data",
        "customer_data",
        "**/customer_data",
        "customers",
        "**/customers",
        "shared",
        "**/shared",
        "客户资料",
        "**/客户资料",
        "项目实例",
        "**/项目实例",
    }
)


def load_fixture_policy() -> tuple[tuple[str, ...], tuple[str, ...]]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise RuntimeError("release policy fixture must be an object")
    files = policy.get("files")
    trees = policy.get("trees")
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(value, str) and value for value in files)
        or not isinstance(trees, list)
        or not all(isinstance(value, str) and value for value in trees)
    ):
        raise RuntimeError("release policy fixture has invalid path lists")
    return tuple(files), tuple(trees)


REQUIRED_FILES, ALLOWED_TREES = load_fixture_policy()
EXPECTED_TREE_SENTINELS = {
    ".github": ".github/workflows/ci.yml",
    "assembly_studio": "assembly_studio/templates/index.html",
    "deploy": "deploy/deploy-release.sh",
    "mvp_generator": "mvp_generator/__init__.py",
    "packaging": "packaging/build_release.py",
    "protocol_studio": "protocol_studio/app.py",
    "resources": "resources/protocol/schemas/project-config.schema.json",
    "scripts": "scripts/validate_repository.py",
    "tests": "tests/run_all.py",
}
if set(ALLOWED_TREES) != set(EXPECTED_TREE_SENTINELS):
    raise RuntimeError("test sentinel contract does not cover the release trees")


def fixture_payload(path: str) -> bytes:
    return f"public packaging contract fixture: {path}\n".encode("utf-8")


REQUIRED_PAYLOADS = {path: fixture_payload(path) for path in REQUIRED_FILES}
FULL_PAYLOADS = {
    **REQUIRED_PAYLOADS,
    **{
        sentinel: fixture_payload(sentinel)
        for sentinel in EXPECTED_TREE_SENTINELS.values()
    },
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load packaging module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def manifest_entries(payloads: Mapping[str, bytes]) -> list[dict[str, object]]:
    return [
        {
            "path": path,
            "size": len(payloads[path]),
            "sha256": hashlib.sha256(payloads[path]).hexdigest(),
        }
        for path in sorted(payloads)
    ]


def manifest_with(
    payloads: Mapping[str, bytes] | None = None,
    **overrides: object,
) -> dict[str, object]:
    selected_payloads = FULL_PAYLOADS if payloads is None else payloads
    manifest: dict[str, object] = {
        "schema_version": 1,
        "project": "mcgs-full-chain-studio",
        "version": VERSION,
        "created_at": "1970-01-01T00:00:00Z",
        "source_date_epoch": 0,
        "files": manifest_entries(selected_payloads),
    }
    manifest.update(overrides)
    return manifest


def write_tree(
    root: Path,
    manifest: dict[str, object],
    payloads: Mapping[str, bytes] | None = None,
) -> None:
    selected_payloads = FULL_PAYLOADS if payloads is None else payloads
    root.mkdir()
    for relative, payload in selected_payloads.items():
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (root / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_file(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def write_archive(
    path: Path,
    manifest: dict[str, object],
    payloads: Mapping[str, bytes] | None = None,
    *,
    top_level: str = EXPECTED_ROOT,
    extra_empty_directory: str | None = None,
) -> None:
    selected_payloads = FULL_PAYLOADS if payloads is None else payloads
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        add_file(archive, f"{top_level}/release-manifest.json", manifest_payload)
        for relative in sorted(selected_payloads):
            add_file(
                archive,
                f"{top_level}/{relative}",
                selected_payloads[relative],
            )
        if extra_empty_directory is not None:
            info = tarfile.TarInfo(f"{extra_empty_directory.rstrip('/')}/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = 0
            archive.addfile(info)


def expect_rejected(
    action: Callable[[], object],
    verification_error: type[Exception],
    label: str,
    expected_message: str,
) -> dict[str, str]:
    try:
        action()
    except verification_error as exc:
        message = str(exc)
        if expected_message not in message:
            raise AssertionError(
                f"{label} failed for the wrong reason: {message!r}"
            ) from exc
        return {"case": label, "message": message}
    raise AssertionError(f"{label} was unexpectedly accepted")


def invoke_builder(builder, argv: list[str]) -> tuple[int, str, str]:
    standard_output = io.StringIO()
    standard_error = io.StringIO()
    with redirect_stdout(standard_output), redirect_stderr(standard_error):
        exit_code = builder.main(argv)
    return exit_code, standard_output.getvalue(), standard_error.getvalue()


def policy_fixture() -> dict[str, object]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise AssertionError("policy fixture root must remain an object")
    return policy


def docker_copy_sources() -> set[str]:
    sources: set[str] = set()
    for line in DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("COPY "):
            continue
        tokens = shlex.split(stripped)
        if len(tokens) < 3 or tokens[0] != "COPY" or any(
            token.startswith("--") for token in tokens[1:-1]
        ):
            raise AssertionError("Dockerfile COPY syntax left the tested contract")
        sources.update(token.rstrip("/") for token in tokens[1:-1])
    return sources


def verify_docker_base_image() -> str:
    from_lines = [
        line.strip()
        for line in DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("FROM ")
    ]
    expected = f"FROM {EXPECTED_DOCKER_BASE_IMAGE}"
    if from_lines != [expected]:
        raise AssertionError(
            "Dockerfile must use the reviewed CPython base image by immutable "
            f"manifest-list digest: expected {[expected]!r}, got {from_lines!r}"
        )
    return EXPECTED_DOCKER_BASE_IMAGE


def dockerignore_patterns() -> list[str]:
    patterns = [
        line.strip()
        for line in DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not patterns or patterns[0] != "**":
        raise AssertionError(".dockerignore must begin by excluding the complete context")
    return patterns


def verify_docker_context_contract(builder) -> dict[str, object]:
    base_image = verify_docker_base_image()
    copy_sources = docker_copy_sources()
    expected_copy_sources = EXPECTED_DOCKER_COPY_FILES | EXPECTED_DOCKER_COPY_TREES
    if copy_sources != expected_copy_sources:
        raise AssertionError(
            f"Dockerfile COPY sources changed: {sorted(copy_sources)}"
        )

    selected = builder.collect_files(REPO_ROOT, policy_fixture())
    selected_relative = {
        builder.relative_text(REPO_ROOT, path)
        for path in selected
    }
    expected_allowed_files = set(DOCKER_CONTEXT_METADATA)
    expected_allowed_files.update(EXPECTED_DOCKER_COPY_FILES)
    expected_allowed_files.update(
        relative
        for relative in selected_relative
        if PurePosixPath(relative).parts[0] in EXPECTED_DOCKER_COPY_TREES
    )

    expected_allowed_directories: set[str] = set()
    for relative in expected_allowed_files:
        parts = PurePosixPath(relative).parts
        for length in range(1, len(parts)):
            expected_allowed_directories.add(PurePosixPath(*parts[:length]).as_posix())

    patterns = dockerignore_patterns()
    allow_patterns = [value[1:] for value in patterns if value.startswith("!")]
    if len(allow_patterns) != len(set(allow_patterns)):
        raise AssertionError(".dockerignore contains duplicate allow entries")
    if any(any(character in value for character in "*?[") for value in allow_patterns):
        raise AssertionError(".dockerignore allow entries must be exact paths, not globs")

    allowed_files = {value for value in allow_patterns if not value.endswith("/")}
    allowed_directories = {
        value.rstrip("/") for value in allow_patterns if value.endswith("/")
    }
    if allowed_files != expected_allowed_files:
        missing = sorted(expected_allowed_files - allowed_files)
        extra = sorted(allowed_files - expected_allowed_files)
        raise AssertionError(
            f".dockerignore exact file allowlist mismatch; missing={missing}, extra={extra}"
        )
    if allowed_directories != expected_allowed_directories:
        missing = sorted(expected_allowed_directories - allowed_directories)
        extra = sorted(allowed_directories - expected_allowed_directories)
        raise AssertionError(
            f".dockerignore directory allowlist mismatch; missing={missing}, extra={extra}"
        )

    allow_indices = [index for index, value in enumerate(patterns) if value.startswith("!")]
    deny_indices = [
        index
        for index, value in enumerate(patterns)
        if index > 0 and not value.startswith("!")
    ]
    if not allow_indices or not deny_indices or max(allow_indices) > min(deny_indices):
        raise AssertionError(".dockerignore hard denials must remain after every allow entry")
    deny_patterns = {patterns[index] for index in deny_indices}
    missing_denials = sorted(REQUIRED_DOCKER_DENY_PATTERNS - deny_patterns)
    if missing_denials:
        raise AssertionError(f".dockerignore is missing hard denials: {missing_denials}")

    sensitive_examples = {
        ".env",
        ".env.production",
        ".git/config",
        "customer-data/acme.xlsx",
        "dist/release.tar.gz",
        "protocol_studio/.env.local",
        "protocol_studio/.audit-output/report.json",
        "protocol_studio/__pycache__/app.pyc",
        "protocol_studio/customer_data/site.json",
        "protocol_studio/runs/security.sqlite3",
        "resources/protocol/examples/customer.sqlite3",
        "客户资料/项目.xlsx",
    }
    leaked_examples = sorted(sensitive_examples.intersection(allowed_files))
    if leaked_examples:
        raise AssertionError(f"sensitive Docker context examples are allowlisted: {leaked_examples}")

    return {
        "base_image": base_image,
        "copy_sources": sorted(copy_sources),
        "allowed_file_count": len(allowed_files),
        "allowed_directory_count": len(allowed_directories),
        "hard_deny_pattern_count": len(deny_patterns),
        "sensitive_examples_excluded": len(sensitive_examples),
    }


def verify_public_tree_contract(scanner, root: Path) -> dict[str, object]:
    public_root = root / "public-tree-scanner"
    public_root.mkdir()

    paths, findings = scanner.scan_tree(public_root)
    if not isinstance(paths, list) or not isinstance(findings, list) or paths or findings:
        raise AssertionError("public-tree scanner did not preserve the 0-item list contract")

    safe_one = public_root / "safe-one.txt"
    safe_one.write_text("safe public fixture\n", encoding="utf-8")
    paths, findings = scanner.scan_tree(public_root)
    if len(paths) != 1 or findings:
        raise AssertionError("public-tree scanner did not preserve the 1-item list contract")

    for name in ("safe-two.txt", "safe-three.txt"):
        (public_root / name).write_text("safe public fixture\n", encoding="utf-8")
    paths, findings = scanner.scan_tree(public_root)
    if len(paths) != 3 or findings:
        raise AssertionError("public-tree scanner did not preserve the N-item list contract")

    outside = root / "outside-public-root.txt"
    outside.write_text("outside fixture\n", encoding="utf-8")
    outside_findings = scanner.scan_paths(public_root, [outside])
    if (
        not isinstance(outside_findings, list)
        or len(outside_findings) != 1
        or outside_findings[0].code != "outside-root"
    ):
        raise AssertionError("public-tree scanner did not reject a direct outside-root path")

    symlink_report: dict[str, object] = {
        "platform": os.name,
        "available": False,
        "cases": [],
        "unavailable_reason": None,
    }
    in_tree_link = public_root / "in-tree-link.txt"
    escaping_link = public_root / "escaping-link.txt"
    try:
        in_tree_link.symlink_to(safe_one.name)
        escaping_link.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        in_tree_link.unlink(missing_ok=True)
        escaping_link.unlink(missing_ok=True)
        error_code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
        symlink_report["unavailable_reason"] = f"{type(exc).__name__}:{error_code}"
        if os.name != "nt":
            raise AssertionError("real symlink tests are unexpectedly unavailable") from exc
    else:
        if escaping_link.resolve() != outside.resolve():
            raise AssertionError("root-escaping symlink fixture has the wrong target")
        paths, findings = scanner.scan_tree(public_root)
        finding_pairs = {(item.path, item.code) for item in findings}
        expected_pairs = {
            ("escaping-link.txt", "symbolic-link"),
            ("in-tree-link.txt", "symbolic-link"),
        }
        if len(paths) != 5 or finding_pairs != expected_pairs:
            raise AssertionError(
                f"public-tree symlink rejection mismatch: {sorted(finding_pairs)}"
            )
        serialized_findings = json.loads(
            json.dumps([item.as_dict() for item in findings], ensure_ascii=False)
        )
        if not isinstance(serialized_findings, list) or not all(
            isinstance(item, dict) for item in serialized_findings
        ):
            raise AssertionError("symlink findings did not preserve the JSON array contract")
        symlink_report.update(
            {
                "available": True,
                "cases": ["in-tree", "root-escaping"],
                "unavailable_reason": None,
            }
        )

    if (
        not isinstance(symlink_report["available"], bool)
        or not isinstance(symlink_report["cases"], list)
        or not all(isinstance(value, str) for value in symlink_report["cases"])
        or (
            symlink_report["unavailable_reason"] is not None
            and not isinstance(symlink_report["unavailable_reason"], str)
        )
    ):
        raise AssertionError("symlink availability report has invalid JSON types")

    return {
        "file_cardinalities_tested": [0, 1, 3],
        "outside_root_rejected": True,
        "symlinks": symlink_report,
    }


def verify_policy_case(
    verifier,
    root: Path,
    label: str,
    policy: dict[str, object],
    expected_message: str,
) -> dict[str, str]:
    path = root / f"policy-{label}.json"
    path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return expect_rejected(
        lambda: verifier.load_path_policy(path),
        verifier.VerificationError,
        f"policy_{label}",
        expected_message,
    )


def verify_manifest_case(
    verifier,
    root: Path,
    label: str,
    manifest: dict[str, object],
    payloads: Mapping[str, bytes],
    expected_message: str,
) -> list[dict[str, str]]:
    rejections: list[dict[str, str]] = []
    tree = root / f"{label}-tree"
    write_tree(tree, manifest, payloads)
    rejections.append(
        expect_rejected(
            lambda: verifier.verify_tree(tree, VERSION),
            verifier.VerificationError,
            f"tree_{label}",
            expected_message,
        )
    )

    archive = root / f"{label}.tar.gz"
    write_archive(archive, manifest, payloads)
    rejections.append(
        expect_rejected(
            lambda: verifier.verify_archive(archive, VERSION),
            verifier.VerificationError,
            f"archive_{label}",
            expected_message,
        )
    )
    return rejections


def main() -> int:
    verifier = load_module("mcgs_packaging_contract_verifier", VERIFY_PATH)
    builder = load_module("mcgs_packaging_contract_builder", BUILD_PATH)
    scanner = load_module("mcgs_packaging_contract_public_tree", PUBLIC_TREE_PATH)
    if verifier.REQUIRED_TREE_SENTINELS != EXPECTED_TREE_SENTINELS:
        raise AssertionError("verifier tree sentinels differ from the tested contract")
    docker_context_contract = verify_docker_context_contract(builder)
    rejections: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="packaging-contract-") as temporary:
        root = Path(temporary)
        public_tree_contract = verify_public_tree_contract(scanner, root)

        valid_tree = root / "valid-tree"
        write_tree(valid_tree, manifest_with())
        verifier.verify_tree(valid_tree, VERSION)

        valid_archive = root / "valid.tar.gz"
        write_archive(valid_archive, manifest_with())
        verifier.verify_archive(valid_archive, VERSION)
        verifier.verify_archive(valid_archive, None)

        project_version = builder.read_project_version(REPO_ROOT)
        check_exit, check_output, check_error = invoke_builder(
            builder,
            [
                "--version",
                "0.0.0-ci",
                "--root",
                str(REPO_ROOT),
                "--check-only",
            ],
        )
        if check_exit != 0 or check_error:
            raise AssertionError(
                f"check-only placeholder version failed: exit={check_exit}, "
                f"stderr={check_error!r}"
            )
        check_report = json.loads(check_output)
        if (
            not isinstance(check_report, dict)
            or check_report.get("mode") != "check-only"
            or check_report.get("version") != project_version
        ):
            raise AssertionError("check-only did not report the pyproject version")

        build_output = root / "must-remain-empty"
        build_exit, build_stdout, build_stderr = invoke_builder(
            builder,
            [
                "--version",
                "0.0.0-ci",
                "--root",
                str(REPO_ROOT),
                "--output-dir",
                str(build_output),
            ],
        )
        if (
            build_exit == 0
            or build_stdout
            or "does not match pyproject.toml" not in build_stderr
            or build_output.exists()
        ):
            raise AssertionError("actual build accepted a mismatched requested version")

        real_output = root / "real-build"
        previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        try:
            real_exit, real_stdout, real_stderr = invoke_builder(
                builder,
                [
                    "--version",
                    project_version,
                    "--root",
                    str(REPO_ROOT),
                    "--output-dir",
                    str(real_output),
                ],
            )
        finally:
            if previous_epoch is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
        if real_exit != 0 or real_stderr:
            raise AssertionError(
                f"real temporary build failed: exit={real_exit}, stderr={real_stderr!r}"
            )
        real_report = json.loads(real_stdout)
        archive_name = real_report.get("archive")
        if not isinstance(archive_name, str) or not archive_name:
            raise AssertionError("real build did not report an archive name")
        real_archive = real_output / archive_name
        real_manifest = verifier.verify_archive(real_archive, project_version)
        if real_manifest["version"] != project_version:
            raise AssertionError("real archive version does not match pyproject")

        for field, bad_value, expected_message in (
            ("schema_version", True, "unsupported manifest schema or project"),
            (
                "created_at",
                "2026-01-01T00:00:00+00:00",
                "created_at must use UTC ISO-8601 format",
            ),
        ):
            rejections.extend(
                verify_manifest_case(
                    verifier,
                    root,
                    field,
                    manifest_with(**{field: bad_value}),
                    FULL_PAYLOADS,
                    expected_message,
                )
            )

        mismatched_time_manifest = manifest_with(
            created_at="1970-01-01T00:00:01Z",
            source_date_epoch=0,
        )
        rejections.extend(
            verify_manifest_case(
                verifier,
                root,
                "created_at_epoch_mismatch",
                mismatched_time_manifest,
                FULL_PAYLOADS,
                "created_at does not match source_date_epoch UTC value",
            )
        )

        empty_payloads: dict[str, bytes] = {}
        readme_payloads = {"README.md": REQUIRED_PAYLOADS["README.md"]}
        missing_required = "LICENSE" if "LICENSE" in REQUIRED_PAYLOADS else REQUIRED_FILES[0]
        missing_payloads = {
            path: payload for path, payload in FULL_PAYLOADS.items() if path != missing_required
        }
        duplicate_entries = manifest_entries(FULL_PAYLOADS)
        duplicate_entries.append(dict(duplicate_entries[0]))
        duplicate_entries.sort(key=lambda item: str(item["path"]))
        bool_size_entries = [dict(item) for item in manifest_entries(FULL_PAYLOADS)]
        bool_size_entries[0]["size"] = True

        manifest_contract_cases = (
            (
                "files_empty",
                manifest_with(empty_payloads),
                empty_payloads,
                "files must be a non-empty array",
            ),
            (
                "files_bool",
                manifest_with(empty_payloads, files=True),
                empty_payloads,
                "files must be an array",
            ),
            (
                "files_only_readme",
                manifest_with(readme_payloads),
                readme_payloads,
                "manifest is missing required release files",
            ),
            (
                "files_missing_required",
                manifest_with(missing_payloads),
                missing_payloads,
                f"manifest is missing required release files: {missing_required}",
            ),
            (
                "files_duplicate_path",
                manifest_with(files=duplicate_entries),
                FULL_PAYLOADS,
                "duplicate manifest path",
            ),
            (
                "files_bool_size",
                manifest_with(files=bool_size_entries),
                FULL_PAYLOADS,
                ".size must be a non-negative integer",
            ),
        )
        for label, manifest, payloads, expected_message in manifest_contract_cases:
            rejections.extend(
                verify_manifest_case(
                    verifier,
                    root,
                    label,
                    manifest,
                    payloads,
                    expected_message,
                )
            )

        target_tree = "deploy"
        target_sentinel = EXPECTED_TREE_SENTINELS[target_tree]
        missing_tree_payloads = {
            path: payload
            for path, payload in FULL_PAYLOADS.items()
            if not path.startswith(f"{target_tree}/")
        }
        non_sentinel_tree_path = f"{target_tree}/optional-contract-fixture.txt"
        non_sentinel_tree_payloads = {
            **missing_tree_payloads,
            non_sentinel_tree_path: fixture_payload(non_sentinel_tree_path),
        }
        tree_contract_cases = (
            (
                "all_trees_missing",
                REQUIRED_PAYLOADS,
                "manifest is missing required release trees",
            ),
            (
                "required_tree_empty",
                missing_tree_payloads,
                f"manifest is missing required release trees: {target_tree}",
            ),
            (
                "tree_without_sentinel",
                non_sentinel_tree_payloads,
                f"manifest is missing required tree sentinels: {target_sentinel}",
            ),
        )
        for label, payloads, expected_message in tree_contract_cases:
            rejections.extend(
                verify_manifest_case(
                    verifier,
                    root,
                    label,
                    manifest_with(payloads),
                    payloads,
                    expected_message,
                )
            )

        policy_bool = policy_fixture()
        policy_bool["trees"] = True
        policy_null = policy_fixture()
        policy_null["trees"] = None
        policy_empty = policy_fixture()
        policy_empty["trees"] = []
        policy_duplicate = policy_fixture()
        policy_duplicate["trees"] = [*ALLOWED_TREES, ALLOWED_TREES[0]]
        policy_missing_key = policy_fixture()
        policy_missing_key.pop("trees")
        policy_missing_tree = policy_fixture()
        policy_missing_tree["trees"] = [
            tree for tree in ALLOWED_TREES if tree != target_tree
        ]
        policy_contract_cases = (
            ("trees_bool", policy_bool, "release allowlist trees is invalid"),
            ("trees_null", policy_null, "release allowlist trees is invalid"),
            (
                "trees_empty",
                policy_empty,
                "release allowlist trees must not be empty",
            ),
            (
                "trees_duplicate",
                policy_duplicate,
                "release allowlist trees contains duplicates",
            ),
            (
                "trees_missing_key",
                policy_missing_key,
                "release allowlist keys do not match the contract",
            ),
            (
                "trees_missing_required",
                policy_missing_tree,
                "release allowlist tree set does not match the project contract",
            ),
        )
        for label, policy, expected_message in policy_contract_cases:
            rejections.append(
                verify_policy_case(
                    verifier,
                    root,
                    label,
                    policy,
                    expected_message,
                )
            )

        wrong_top_level = root / "wrong-top-level.tar.gz"
        write_archive(
            wrong_top_level,
            manifest_with(),
            top_level="mcgs-full-chain-studio-wrong",
        )
        rejections.append(
            expect_rejected(
                lambda: verifier.verify_archive(wrong_top_level, VERSION),
                verifier.VerificationError,
                "archive_wrong_top_level",
                "archive top-level directory mismatch",
            )
        )

        extra_empty_top_level = root / "extra-empty-top-level.tar.gz"
        write_archive(
            extra_empty_top_level,
            manifest_with(),
            extra_empty_directory="unexpected-empty",
        )
        rejections.append(
            expect_rejected(
                lambda: verifier.verify_archive(extra_empty_top_level, VERSION),
                verifier.VerificationError,
                "archive_extra_empty_top_level",
                "archive must contain exactly one top-level directory",
            )
        )

        extra_inner_directory = root / "extra-inner-directory.tar.gz"
        write_archive(
            extra_inner_directory,
            manifest_with(),
            extra_empty_directory=f"{EXPECTED_ROOT}/unexpected-empty",
        )
        rejections.append(
            expect_rejected(
                lambda: verifier.verify_archive(extra_inner_directory, VERSION),
                verifier.VerificationError,
                "archive_extra_inner_directory",
                "archive contains an unexpected directory member",
            )
        )

    file_cardinalities = [0, 1, len(FULL_PAYLOADS)]
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "passed",
        "valid_tree": True,
        "valid_archive": True,
        "required_tree_count": len(EXPECTED_TREE_SENTINELS),
        "check_only_version": project_version,
        "actual_build_mismatch_rejected": True,
        "real_archive_verified": True,
        "real_archive_file_count": len(real_manifest["files"]),
        "docker_context": docker_context_contract,
        "public_tree_contract": public_tree_contract,
        "manifest_file_cardinalities_tested": file_cardinalities,
        "rejections": rejections,
    }
    if not isinstance(report["schema_version"], int) or isinstance(
        report["schema_version"], bool
    ):
        raise AssertionError("report schema_version type is invalid")
    if not isinstance(report["manifest_file_cardinalities_tested"], list) or any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in report["manifest_file_cardinalities_tested"]
    ):
        raise AssertionError("manifest cardinalities report shape is invalid")
    if not isinstance(report["rejections"], list) or len(report["rejections"]) != 33:
        raise AssertionError("packaging contract report shape is invalid")
    serialized_report = json.dumps(report, ensure_ascii=False, indent=2)
    decoded_report = json.loads(serialized_report)
    if (
        not isinstance(decoded_report, dict)
        or not isinstance(decoded_report.get("docker_context"), dict)
        or not isinstance(decoded_report.get("public_tree_contract"), dict)
        or not isinstance(
            decoded_report["public_tree_contract"].get("file_cardinalities_tested"),
            list,
        )
    ):
        raise AssertionError("packaging report did not preserve object and array JSON contracts")
    print(serialized_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
