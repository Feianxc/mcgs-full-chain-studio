from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = REPO_ROOT / "packaging" / "verify_release.py"
VERSION = "0.0.0-test"
ARCHIVE_ROOT = f"mcgs-full-chain-studio-{VERSION}"


def load_verifier():
    spec = importlib.util.spec_from_file_location("mcgs_release_verifier", VERIFY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_payload(path: str) -> bytes:
    return f"public release path-policy fixture: {path}\n".encode("utf-8")


def manifest_for(payloads: Mapping[str, bytes]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "mcgs-full-chain-studio",
        "version": VERSION,
        "created_at": "1970-01-01T00:00:00Z",
        "source_date_epoch": 0,
        "files": [
            {
                "path": path,
                "size": len(payloads[path]),
                "sha256": hashlib.sha256(payloads[path]).hexdigest(),
            }
            for path in sorted(payloads)
        ],
    }


def write_tree(root: Path, payloads: Mapping[str, bytes]) -> None:
    root.mkdir()
    for relative, payload in payloads.items():
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (root / "release-manifest.json").write_text(
        json.dumps(manifest_for(payloads), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_file(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def write_archive(archive_path: Path, payloads: Mapping[str, bytes]) -> None:
    manifest_payload = (
        json.dumps(manifest_for(payloads), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        add_file(archive, f"{ARCHIVE_ROOT}/release-manifest.json", manifest_payload)
        for relative in sorted(payloads):
            add_file(archive, f"{ARCHIVE_ROOT}/{relative}", payloads[relative])


def expect_rejected(callable_, verification_error: type[Exception], label: str) -> str:
    try:
        callable_()
    except verification_error as exc:
        return str(exc)
    raise AssertionError(f"{label} was unexpectedly accepted")


def main() -> int:
    verifier = load_verifier()
    policy = verifier.load_path_policy()
    required_files = tuple(policy["files"])
    allowed_trees = tuple(policy["trees"])
    tree_sentinels = verifier.REQUIRED_TREE_SENTINELS
    if set(allowed_trees) != set(tree_sentinels):
        raise AssertionError("tree sentinel contract does not cover the release trees")
    required_payloads = {path: fixture_payload(path) for path in required_files}
    good_payloads = {
        **required_payloads,
        **{
            sentinel: fixture_payload(sentinel)
            for sentinel in tree_sentinels.values()
        },
    }

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="release-path-policy-") as temporary:
        root = Path(temporary)
        good_tree = root / "good-tree"
        write_tree(good_tree, good_payloads)
        verifier.verify_tree(good_tree, VERSION)

        good_archive = root / "good.tar.gz"
        write_archive(good_archive, good_payloads)
        verifier.verify_archive(good_archive, VERSION)

        for forbidden_path in (
            ".venv/sitecustomize.py",
            "shared/runs/customer.json",
        ):
            forbidden_payloads = {
                **good_payloads,
                forbidden_path: b"raise SystemExit('must not run')\n",
            }
            bad_tree = root / forbidden_path.replace("/", "-").replace(".", "dot")
            write_tree(bad_tree, forbidden_payloads)
            errors.append(
                expect_rejected(
                    lambda candidate=bad_tree: verifier.verify_tree(candidate, VERSION),
                    verifier.VerificationError,
                    f"tree {forbidden_path}",
                )
            )

            bad_archive = root / (
                forbidden_path.replace("/", "-").replace(".", "dot") + ".tar.gz"
            )
            write_archive(bad_archive, forbidden_payloads)
            errors.append(
                expect_rejected(
                    lambda candidate=bad_archive: verifier.verify_archive(
                        candidate, VERSION
                    ),
                    verifier.VerificationError,
                    f"archive {forbidden_path}",
                )
            )

    report: dict[str, object] = {
        "status": "passed",
        "good_tree": True,
        "good_archive": True,
        "required_file_count": len(required_files),
        "required_tree_count": len(tree_sentinels),
        "rejections": errors,
    }
    if not isinstance(report["rejections"], list) or len(report["rejections"]) != 4:
        raise AssertionError("release path-policy report shape is invalid")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
