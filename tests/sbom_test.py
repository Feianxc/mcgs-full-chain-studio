from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "packaging" / "generate_sbom.py"
EPOCH = 1_700_000_000
TIMESTAMP = "2023-11-14T22:13:20Z"
LICENSE_TEXT = b"Synthetic license text for SBOM contract tests.\n"
APPLICATION_NAME = "synthetic-sbom-app"
APPLICATION_VERSION = "9.8.7"
APPLICATION_REF = "pkg:pypi/synthetic-sbom-app@9.8.7"


@dataclass(frozen=True)
class WheelSpec:
    name: str
    version: str
    requires_dist: tuple[str, ...] = ()
    license_expression: str | None = None
    license_classifiers: tuple[str, ...] = ()
    license_file: str | None = None
    metadata_name: str | None = None
    metadata_version: str | None = None
    build_tag: str | None = None
    unsafe_member: str | None = None


def load_generator():
    spec = importlib.util.spec_from_file_location("mcgs_generate_sbom_tested", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load SBOM generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_name(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def wheel_filename(spec: WheelSpec) -> str:
    distribution = canonical_name(spec.name).replace("-", "_")
    build = f"-{spec.build_tag}" if spec.build_tag else ""
    return f"{distribution}-{spec.version}{build}-py3-none-any.whl"


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def write_wheel(wheelhouse: Path, spec: WheelSpec) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    filename = wheel_filename(spec)
    path = wheelhouse / filename
    distribution = canonical_name(spec.name).replace("-", "_")
    dist_info = f"{distribution}-{spec.version}.dist-info"
    metadata_name = spec.metadata_name or spec.name
    metadata_version = spec.metadata_version or spec.version
    metadata_lines = [
        "Metadata-Version: 2.4",
        f"Name: {metadata_name}",
        f"Version: {metadata_version}",
    ]
    if spec.license_expression:
        metadata_lines.append(f"License-Expression: {spec.license_expression}")
    metadata_lines.extend(
        f"Classifier: {classifier}" for classifier in spec.license_classifiers
    )
    if spec.license_file:
        metadata_lines.append(f"License-File: {spec.license_file}")
    metadata_lines.extend(
        f"Requires-Dist: {requirement}" for requirement in spec.requires_dist
    )
    metadata_payload = ("\n".join(metadata_lines) + "\n\n").encode("utf-8")
    members: list[tuple[str, bytes]] = [
        (f"{dist_info}/METADATA", metadata_payload),
        (f"{dist_info}/WHEEL", b"Wheel-Version: 1.0\nTag: py3-none-any\n"),
    ]
    if spec.license_file and ".." not in spec.license_file.split("/"):
        members.append(
            (f"{dist_info}/licenses/{spec.license_file}", LICENSE_TEXT)
        )
    if spec.unsafe_member:
        members.append((spec.unsafe_member, b"must never be extracted\n"))
    with zipfile.ZipFile(path, "w") as archive:
        for member_name, payload in sorted(members):
            archive.writestr(zip_info(member_name), payload)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pyproject(
    root: Path,
    *,
    name: object = APPLICATION_NAME,
    version: object = APPLICATION_VERSION,
    dependencies: tuple[object, ...] = ("Alpha==1.0",),
) -> Path:
    def toml_value(value: object) -> str:
        if type(value) is str:
            return json.dumps(value)
        if type(value) is bool:
            return "true" if value else "false"
        raise AssertionError(f"unsupported synthetic TOML value: {value!r}")

    path = root / "pyproject.toml"
    lines = [
        "[project]",
        f"name = {toml_value(name)}",
        f"version = {toml_value(version)}",
        "dependencies = [",
    ]
    lines.extend(f"  {toml_value(item)}," for item in dependencies)
    lines.extend(("]", ""))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_lock(
    path: Path,
    wheels: list[tuple[WheelSpec, Path]],
    *,
    hashes: dict[str, str] | None = None,
    continued: bool = False,
) -> None:
    overrides = hashes or {}
    lines = ["# synthetic, fully hashed production lock"]
    for spec, wheel in wheels:
        digest = overrides.get(canonical_name(spec.name), sha256(wheel))
        if continued:
            lines.extend(
                (
                    f"{spec.name}=={spec.version} \\",
                    f"    --hash=sha256:{digest}",
                )
            )
        else:
            lines.append(f"{spec.name}=={spec.version} --hash=sha256:{digest}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@contextmanager
def environment_value(name: str, value: str | None) -> Iterator[None]:
    original = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original


def expect_error(
    action: Callable[[], object],
    error_type: type[Exception],
    expected_message: str,
    label: str,
) -> dict[str, str]:
    try:
        action()
    except error_type as exc:
        message = str(exc)
        if expected_message not in message:
            raise AssertionError(
                f"{label} failed for the wrong reason: {message!r}"
            ) from exc
        return {"case": label, "message": message}
    raise AssertionError(f"{label} was unexpectedly accepted")


def properties(component: dict[str, object]) -> dict[str, str]:
    values = component.get("properties")
    if not isinstance(values, list):
        raise AssertionError("component properties must be an array")
    result: dict[str, str] = {}
    for item in values:
        if not isinstance(item, dict):
            raise AssertionError("component property must be an object")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise AssertionError("component property name/value must be strings")
        if name in result:
            raise AssertionError(f"duplicate component property: {name}")
        result[name] = value
    return result


def validate_document(
    document: dict[str, object], expected_count: int, expected_epoch: int
) -> None:
    if set(document) != {
        "bomFormat",
        "specVersion",
        "version",
        "metadata",
        "components",
        "dependencies",
    }:
        raise AssertionError("CycloneDX root keys are not deterministic")
    if document["bomFormat"] != "CycloneDX" or document["specVersion"] != "1.5":
        raise AssertionError("CycloneDX identity is invalid")
    if type(document["version"]) is not int or document["version"] != 1:
        raise AssertionError("CycloneDX version must be an integer, never a bool")
    components = document["components"]
    dependencies = document["dependencies"]
    metadata = document["metadata"]
    if not isinstance(components, list) or len(components) != expected_count:
        raise AssertionError("components must preserve 0/1/N array shape")
    if not isinstance(dependencies, list) or len(dependencies) != expected_count + 1:
        raise AssertionError("dependencies must preserve 1/N array shape")
    if not isinstance(metadata, dict):
        raise AssertionError("metadata must be an object")
    if metadata.get("timestamp") != (
        TIMESTAMP if expected_epoch == EPOCH else "1970-01-01T00:00:00Z"
    ):
        raise AssertionError("metadata timestamp is not reproducible UTC")
    metadata_properties = metadata.get("properties")
    if not isinstance(metadata_properties, list) or len(metadata_properties) != 1:
        raise AssertionError("metadata properties must be a one-item array")
    epoch_value = metadata_properties[0].get("value")
    if epoch_value != str(expected_epoch) or not isinstance(epoch_value, str):
        raise AssertionError("SOURCE_DATE_EPOCH property must be a string")
    root_component = metadata.get("component")
    if not isinstance(root_component, dict) or root_component.get("type") != "application":
        raise AssertionError("root application component is missing")
    if (
        root_component.get("name") != APPLICATION_NAME
        or root_component.get("version") != APPLICATION_VERSION
        or root_component.get("purl") != APPLICATION_REF
        or root_component.get("bom-ref") != APPLICATION_REF
    ):
        raise AssertionError("root application is not bound to pyproject identity")
    root_dependency = dependencies[0]
    if not isinstance(root_dependency, dict) or not isinstance(
        root_dependency.get("dependsOn"), list
    ):
        raise AssertionError("root dependency shape is invalid")
    if root_dependency.get("ref") != APPLICATION_REF:
        raise AssertionError("root dependency ref is not bound to pyproject identity")
    for component in components:
        if not isinstance(component, dict):
            raise AssertionError("component must be an object")
        for field in ("hashes", "licenses", "properties"):
            if not isinstance(component.get(field), list):
                raise AssertionError(f"component {field} must stay an array")
        component_properties = properties(component)
        if not component_properties["mcgs:wheel:size"].isdigit():
            raise AssertionError("wheel size property must be a decimal string")
        hashes = component["hashes"]
        if len(hashes) != 1 or hashes[0].get("alg") != "SHA-256":
            raise AssertionError("component SHA-256 shape is invalid")
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(
            dependency.get("dependsOn"), list
        ):
            raise AssertionError("every dependency must keep dependsOn as an array")


def validate_written_output(output: Path, temporary_root: Path) -> dict[str, object]:
    raw = output.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise AssertionError("independent JSON read did not produce an object")
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if sidecar.read_text(encoding="utf-8") != f"{digest}  {output.name}\n":
        raise AssertionError("checksum sidecar does not match exact JSON bytes")
    decoded = raw.decode("utf-8")
    forbidden = {
        str(temporary_root.resolve()),
        temporary_root.resolve().as_posix(),
        str(temporary_root.resolve()).replace("\\", "\\\\"),
    }
    if any(value and value in decoded for value in forbidden):
        raise AssertionError("SBOM leaked an absolute input/output path")
    leftovers = list(output.parent.glob(f".{output.name}.*.tmp"))
    leftovers.extend(
        output.parent.glob(f".{output.with_suffix(output.suffix + '.sha256').name}.*.tmp")
    )
    if leftovers:
        raise AssertionError("atomic writer left staged files behind")
    return document


def make_case(
    root: Path,
    specs: list[WheelSpec],
    *,
    direct_dependencies: tuple[str, ...] | None = None,
) -> tuple[Path, Path, list[Path]]:
    root.mkdir(parents=True)
    if direct_dependencies is None:
        if not specs:
            raise AssertionError("synthetic package case must not be empty")
        direct_dependencies = (f"{specs[0].name}=={specs[0].version}",)
    write_pyproject(root, dependencies=direct_dependencies)
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    wheels = [write_wheel(wheelhouse, spec) for spec in specs]
    lock = root / "requirements.production.lock.txt"
    write_lock(lock, list(zip(specs, wheels)))
    return lock, wheelhouse, wheels


def main() -> int:
    generator = load_generator()
    rejections: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="sbom-contract-") as temporary:
        temporary_root = Path(temporary)

        # A truncated/empty production lock must never yield a root-only SBOM.
        zero_root = temporary_root / "zero"
        zero_root.mkdir()
        write_pyproject(zero_root)
        zero_lock = zero_root / "requirements.production.lock.txt"
        zero_lock.write_text("# deliberately empty lock\n", encoding="utf-8")
        zero_wheelhouse = zero_root / "wheelhouse"
        zero_wheelhouse.mkdir()
        zero_output = zero_root / "synthetic.cdx.json"
        rejections.append(
            expect_error(
                lambda: generator.generate_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    zero_output,
                    project_root=zero_root,
                    source_date_epoch=0,
                ),
                generator.SbomError,
                "requirements lock must contain at least one package",
                "empty_lock_programmatic",
            )
        )
        if zero_output.exists() or zero_output.with_suffix(
            zero_output.suffix + ".sha256"
        ).exists():
            raise AssertionError("empty lock left a false-success SBOM artifact")

        empty_cli_stdout = io.StringIO()
        empty_cli_stderr = io.StringIO()
        with environment_value("SOURCE_DATE_EPOCH", "0"):
            with redirect_stdout(empty_cli_stdout), redirect_stderr(empty_cli_stderr):
                empty_cli_exit = generator.main(
                    [
                        "--lock",
                        str(zero_lock),
                        "--wheelhouse",
                        str(zero_wheelhouse),
                        "--output",
                        str(zero_output),
                        "--root",
                        str(zero_root),
                    ]
                )
        empty_cli_message = empty_cli_stderr.getvalue()
        if (
            empty_cli_exit == 0
            or empty_cli_stdout.getvalue()
            or "requirements lock must contain at least one package"
            not in empty_cli_message
            or zero_output.exists()
        ):
            raise AssertionError("CLI did not fail closed for an empty lock")
        rejections.append(
            {"case": "empty_lock_cli", "message": empty_cli_message.strip()}
        )

        # One component: exercise license expression, classifier and embedded text.
        one_spec = WheelSpec(
            "Alpha_Pkg",
            "1.0.0",
            license_expression="MIT",
            license_classifiers=("License :: OSI Approved :: MIT License",),
            license_file="LICENSE.txt",
        )
        one_lock, one_wheelhouse, one_wheels = make_case(
            temporary_root / "one-a", [one_spec]
        )
        write_lock(one_lock, [(one_spec, one_wheels[0])], continued=True)
        one_output = one_lock.parent / "synthetic.cdx.json"
        one_output.write_text("must be atomically replaced", encoding="utf-8")
        one_output.with_suffix(one_output.suffix + ".sha256").write_text(
            "must be atomically replaced", encoding="utf-8"
        )
        one_document = generator.generate_sbom(
            one_lock,
            one_wheelhouse,
            one_output,
            project_root=one_lock.parent,
            application_name=APPLICATION_NAME,
            application_version=APPLICATION_VERSION,
            source_date_epoch=EPOCH,
        )
        validate_document(one_document, 1, EPOCH)
        one_readback = validate_written_output(one_output, temporary_root)
        if one_readback != one_document:
            raise AssertionError("one-component independent readback changed values")
        one_component = one_document["components"][0]
        one_properties = properties(one_component)
        if one_component["name"] != "alpha-pkg" or one_component["purl"] != (
            "pkg:pypi/alpha-pkg@1.0.0"
        ):
            raise AssertionError("component name/purl normalization is invalid")
        if one_properties["mcgs:wheel:filename"] != one_wheels[0].name:
            raise AssertionError("wheel filename property is invalid")
        if int(one_properties["mcgs:wheel:size"]) != one_wheels[0].stat().st_size:
            raise AssertionError("wheel size property is invalid")
        if one_component["hashes"][0]["content"] != sha256(one_wheels[0]):
            raise AssertionError("wheel hash is invalid")
        license_choices = one_component["licenses"]
        if license_choices != [{"expression": "MIT"}]:
            raise AssertionError("License-Expression was not preserved as SPDX expression")
        evidence = one_component.get("evidence")
        if not isinstance(evidence, dict) or not isinstance(
            evidence.get("licenses"), list
        ):
            raise AssertionError("classifier/LICENSE evidence is missing")
        evidence_names = [
            item["license"].get("name")
            for item in evidence["licenses"]
            if isinstance(item, dict) and isinstance(item.get("license"), dict)
        ]
        if "MIT License" not in evidence_names:
            raise AssertionError("license Classifier was not parsed")
        if one_properties.get("mcgs:python:license-expression:0000") != "MIT":
            raise AssertionError("License-Expression property was not preserved")
        if one_properties.get("mcgs:python:license-classifier:0000") != (
            "License :: OSI Approved :: MIT License"
        ):
            raise AssertionError("license Classifier property was not preserved")
        embedded = [
            item["license"]["text"]["content"]
            for item in evidence["licenses"]
            if "license" in item and "text" in item["license"]
        ]
        if len(embedded) != 1 or base64.b64decode(embedded[0]) != LICENSE_TEXT:
            raise AssertionError("embedded LICENSE content was not parsed")

        # Rebuild identical synthetic inputs under a different absolute path.
        deterministic_lock, deterministic_wheelhouse, _ = make_case(
            temporary_root / "one-b", [one_spec]
        )
        deterministic_output = deterministic_lock.parent / "synthetic.cdx.json"
        generator.generate_sbom(
            deterministic_lock,
            deterministic_wheelhouse,
            deterministic_output,
            pyproject_path=deterministic_lock.parent / "pyproject.toml",
            source_date_epoch=EPOCH,
        )
        validate_written_output(deterministic_output, temporary_root)
        if deterministic_output.read_bytes() != one_output.read_bytes():
            raise AssertionError("same logical inputs did not produce identical JSON bytes")
        if deterministic_output.with_suffix(
            deterministic_output.suffix + ".sha256"
        ).read_bytes() != one_output.with_suffix(one_output.suffix + ".sha256").read_bytes():
            raise AssertionError("same output filename did not produce identical sidecar bytes")

        # N components: order is canonical and Requires-Dist becomes a dependency graph.
        many_specs = [
            WheelSpec(
                "Charlie",
                "3.0",
                license_classifiers=("License :: Other/Proprietary License",),
            ),
            WheelSpec(
                "Alpha",
                "1.0",
                requires_dist=("Bravo>=2", "Bravo; python_version >= '3.11'"),
                license_expression="Apache-2.0",
            ),
            WheelSpec(
                "Bravo",
                "2.0",
                requires_dist=("Charlie (~=3.0)", "ExternalThing; extra == 'test'"),
            ),
        ]
        many_lock, many_wheelhouse, _ = make_case(
            temporary_root / "many",
            many_specs,
            direct_dependencies=("Alpha==1.0",),
        )
        many_output = many_lock.parent / "synthetic.cdx.json"
        many_document = generator.generate_sbom(
            many_lock,
            many_wheelhouse,
            many_output,
            project_root=many_lock.parent,
            source_date_epoch=EPOCH,
        )
        validate_document(many_document, 3, EPOCH)
        validate_written_output(many_output, temporary_root)
        if [item["name"] for item in many_document["components"]] != [
            "alpha",
            "bravo",
            "charlie",
        ]:
            raise AssertionError("components are not sorted by canonical package name")
        graph = {item["ref"]: item["dependsOn"] for item in many_document["dependencies"]}
        if graph[APPLICATION_REF] != ["pkg:pypi/alpha@1.0"]:
            raise AssertionError("root dependency must contain direct pins only")
        if graph["pkg:pypi/alpha@1.0"] != ["pkg:pypi/bravo@2.0"]:
            raise AssertionError("Alpha Requires-Dist edge was not parsed")
        if graph["pkg:pypi/bravo@2.0"] != ["pkg:pypi/charlie@3.0"]:
            raise AssertionError("Bravo Requires-Dist edge was not parsed")
        if graph["pkg:pypi/charlie@3.0"] != []:
            raise AssertionError("leaf dependsOn must remain an empty array")

        # CLI uses SOURCE_DATE_EPOCH and reports only basenames, never absolute paths.
        cli_output = one_lock.parent / "cli.cdx.json"
        standard_output = io.StringIO()
        standard_error = io.StringIO()
        with environment_value("SOURCE_DATE_EPOCH", "0"):
            with redirect_stdout(standard_output), redirect_stderr(standard_error):
                cli_exit = generator.main(
                    [
                        "--lock",
                        str(one_lock),
                        "--wheelhouse",
                        str(one_wheelhouse),
                        "--output",
                        str(cli_output),
                        "--root",
                        str(one_lock.parent),
                    ]
                )
        if cli_exit != 0 or standard_error.getvalue():
            raise AssertionError(
                f"valid CLI failed: exit={cli_exit}, stderr={standard_error.getvalue()!r}"
            )
        cli_report = json.loads(standard_output.getvalue())
        if (
            not isinstance(cli_report, dict)
            or type(cli_report.get("component_count")) is not int
            or cli_report.get("component_count") != 1
            or cli_report.get("output") != "cli.cdx.json"
            or str(temporary_root) in standard_output.getvalue()
        ):
            raise AssertionError("CLI report shape or path privacy is invalid")
        cli_document = validate_written_output(cli_output, temporary_root)
        validate_document(cli_document, 1, 0)

        negative_root = temporary_root / "negative"
        negative_root.mkdir()

        duplicate_lock_root = negative_root / "duplicate-lock"
        duplicate_lock, duplicate_wheelhouse, duplicate_wheels = make_case(
            duplicate_lock_root, [WheelSpec("Alpha", "1.0")]
        )
        digest = sha256(duplicate_wheels[0])
        duplicate_lock.write_text(
            "\n".join(
                (
                    f"Alpha==1.0 --hash=sha256:{digest}",
                    f"alpha==1.0 --hash=sha256:{digest}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    duplicate_lock,
                    duplicate_wheelhouse,
                    project_root=duplicate_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "duplicate locked package",
                "duplicate_locked_package",
            )
        )

        missing_root = negative_root / "missing"
        missing_root.mkdir()
        write_pyproject(missing_root)
        missing_lock = missing_root / "requirements.production.lock.txt"
        missing_lock.write_text(
            f"Alpha==1.0 --hash=sha256:{'0' * 64}\n", encoding="utf-8"
        )
        missing_wheelhouse = missing_root / "wheelhouse"
        missing_wheelhouse.mkdir()
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    missing_lock,
                    missing_wheelhouse,
                    project_root=missing_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "missing wheel",
                "missing_wheel",
            )
        )

        extra_lock, extra_wheelhouse, _ = make_case(
            negative_root / "extra", [WheelSpec("Alpha", "1.0")]
        )
        write_wheel(extra_wheelhouse, WheelSpec("Bravo", "2.0"))
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    extra_lock,
                    extra_wheelhouse,
                    project_root=extra_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "extra wheel",
                "extra_wheel",
            )
        )

        hash_lock, hash_wheelhouse, hash_wheels = make_case(
            negative_root / "hash", [WheelSpec("Alpha", "1.0")]
        )
        write_lock(
            hash_lock,
            [(WheelSpec("Alpha", "1.0"), hash_wheels[0])],
            hashes={"alpha": "f" * 64},
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    hash_lock,
                    hash_wheelhouse,
                    project_root=hash_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "SHA-256 does not match",
                "wheel_hash_mismatch",
            )
        )

        version_root = negative_root / "version"
        version_root.mkdir()
        write_pyproject(version_root)
        version_wheelhouse = version_root / "wheelhouse"
        version_wheel = write_wheel(version_wheelhouse, WheelSpec("Alpha", "2.0"))
        version_lock = version_root / "requirements.production.lock.txt"
        version_lock.write_text(
            f"Alpha==1.0 --hash=sha256:{sha256(version_wheel)}\n", encoding="utf-8"
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    version_lock,
                    version_wheelhouse,
                    project_root=version_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "wheel version does not match lock",
                "wheel_filename_version_mismatch",
            )
        )

        metadata_lock, metadata_wheelhouse, _ = make_case(
            negative_root / "metadata-version",
            [WheelSpec("Alpha", "1.0", metadata_version="9.9")],
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    metadata_lock,
                    metadata_wheelhouse,
                    project_root=metadata_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "METADATA version does not match lock",
                "wheel_metadata_version_mismatch",
            )
        )

        metadata_name_lock, metadata_name_wheelhouse, _ = make_case(
            negative_root / "metadata-name",
            [WheelSpec("Alpha", "1.0", metadata_name="Bravo")],
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    metadata_name_lock,
                    metadata_name_wheelhouse,
                    project_root=metadata_name_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "METADATA name does not match lock",
                "wheel_metadata_name_mismatch",
            )
        )

        traversal_lock, traversal_wheelhouse, _ = make_case(
            negative_root / "traversal",
            [WheelSpec("Alpha", "1.0", unsafe_member="../escape.txt")],
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    traversal_lock,
                    traversal_wheelhouse,
                    project_root=traversal_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "path-traversal archive member",
                "wheel_member_path_traversal",
            )
        )

        license_path_lock, license_path_wheelhouse, _ = make_case(
            negative_root / "license-path",
            [WheelSpec("Alpha", "1.0", license_file="../LICENSE.txt")],
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    license_path_lock,
                    license_path_wheelhouse,
                    project_root=license_path_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "License-File contains a path-traversal path",
                "license_file_path_traversal",
            )
        )

        duplicate_wheel_root = negative_root / "duplicate-wheel"
        duplicate_wheel_root.mkdir()
        write_pyproject(duplicate_wheel_root)
        duplicate_wheelhouse = duplicate_wheel_root / "wheelhouse"
        first_spec = WheelSpec("Alpha", "1.0")
        second_spec = WheelSpec("Alpha", "1.0", build_tag="1")
        first_wheel = write_wheel(duplicate_wheelhouse, first_spec)
        write_wheel(duplicate_wheelhouse, second_spec)
        duplicate_wheel_lock = duplicate_wheel_root / "requirements.production.lock.txt"
        write_lock(duplicate_wheel_lock, [(first_spec, first_wheel)])
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    duplicate_wheel_lock,
                    duplicate_wheelhouse,
                    project_root=duplicate_wheel_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "duplicate wheel",
                "duplicate_wheel",
            )
        )

        direct_missing_lock, direct_missing_wheelhouse, _ = make_case(
            negative_root / "direct-missing-lock",
            [WheelSpec("Bravo", "2.0")],
            direct_dependencies=("Alpha==1.0",),
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    direct_missing_lock,
                    direct_missing_wheelhouse,
                    project_root=direct_missing_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "direct dependency is missing from lock: alpha",
                "pyproject_direct_dependency_missing_from_lock",
            )
        )

        direct_version_lock, direct_version_wheelhouse, _ = make_case(
            negative_root / "direct-version-mismatch",
            [WheelSpec("Alpha", "1.0")],
            direct_dependencies=("Alpha==2.0",),
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    direct_version_lock,
                    direct_version_wheelhouse,
                    project_root=direct_version_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "locked version does not match pyproject.toml direct dependency",
                "pyproject_direct_dependency_version_mismatch",
            )
        )

        truncated_lock, truncated_wheelhouse, _ = make_case(
            negative_root / "truncated-transitive-lock",
            [WheelSpec("Alpha", "1.0", requires_dist=("Bravo>=2",))],
            direct_dependencies=("Alpha==1.0",),
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    truncated_lock,
                    truncated_wheelhouse,
                    project_root=truncated_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "applicable wheel dependency is missing from lock: alpha -> bravo",
                "truncated_transitive_lock",
            )
        )

        linux_marker_lock, linux_marker_wheelhouse, _ = make_case(
            negative_root / "linux-marker-missing",
            [
                WheelSpec(
                    "Alpha",
                    "1.0",
                    requires_dist=("LinuxOnly; sys_platform == 'linux'",),
                )
            ],
            direct_dependencies=("Alpha==1.0",),
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    linux_marker_lock,
                    linux_marker_wheelhouse,
                    project_root=linux_marker_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "applicable wheel dependency is missing from lock: alpha -> linuxonly",
                "linux_marker_dependency_missing_from_lock",
            )
        )

        non_wheel_lock, non_wheel_wheelhouse, _ = make_case(
            negative_root / "non-wheel-entry", [WheelSpec("Alpha", "1.0")]
        )
        (non_wheel_wheelhouse / "README.txt").write_text(
            "unexpected wheelhouse artifact\n", encoding="utf-8"
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    non_wheel_lock,
                    non_wheel_wheelhouse,
                    project_root=non_wheel_lock.parent,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "wheelhouse contains a non-wheel entry: README.txt",
                "wheelhouse_non_wheel_entry",
            )
        )

        missing_project_root = negative_root / "missing-pyproject"
        missing_project_root.mkdir()
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=missing_project_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "pyproject.toml is not a regular file",
                "missing_pyproject",
            )
        )

        malformed_project_root = negative_root / "malformed-pyproject"
        malformed_project_root.mkdir()
        (malformed_project_root / "pyproject.toml").write_text(
            "[project\nname = 'broken'\n", encoding="utf-8"
        )
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=malformed_project_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "pyproject.toml is not valid TOML",
                "malformed_pyproject",
            )
        )

        bool_project_root = negative_root / "bool-project-version"
        bool_project_root.mkdir()
        write_pyproject(bool_project_root, version=True)
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=bool_project_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "project version must be a string",
                "bool_project_version",
            )
        )

        rejections.append(
            expect_error(
                lambda: generator.project_identity_from_document(
                    {
                        "project": {
                            "name": APPLICATION_NAME,
                            "version": None,
                        }
                    }
                ),
                generator.SbomError,
                "project version must be a string",
                "null_project_version",
            )
        )

        invalid_version_root = negative_root / "invalid-project-version"
        invalid_version_root.mkdir()
        write_pyproject(invalid_version_root, version="1.0/escape")
        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=invalid_version_root,
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "project version is invalid",
                "invalid_project_version_format",
            )
        )

        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=zero_root,
                    application_version="0.0.0-mismatch",
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "version override does not match pyproject.toml",
                "application_version_override_mismatch",
            )
        )

        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=zero_root,
                    application_name="different-application",
                    source_date_epoch=EPOCH,
                ),
                generator.SbomError,
                "name override does not match pyproject.toml",
                "application_name_override_mismatch",
            )
        )

        rejections.append(
            expect_error(
                lambda: generator.build_sbom(
                    zero_lock,
                    zero_wheelhouse,
                    project_root=zero_root,
                    source_date_epoch=True,
                ),
                generator.SbomError,
                "non-negative integer",
                "bool_source_date_epoch",
            )
        )
        with environment_value("SOURCE_DATE_EPOCH", "not-an-integer"):
            rejections.append(
                expect_error(
                    lambda: generator.build_sbom(
                        zero_lock, zero_wheelhouse, project_root=zero_root
                    ),
                    generator.SbomError,
                    "non-negative integer",
                    "invalid_source_date_epoch_environment",
                )
            )
        with environment_value("SOURCE_DATE_EPOCH", None):
            rejections.append(
                expect_error(
                    lambda: generator.build_sbom(
                        zero_lock, zero_wheelhouse, project_root=zero_root
                    ),
                    generator.SbomError,
                    "SOURCE_DATE_EPOCH is required",
                    "missing_source_date_epoch_environment",
                )
            )

    if len(rejections) != 27 or not all(
        isinstance(item, dict) and set(item) == {"case", "message"}
        for item in rejections
    ):
        raise AssertionError("negative test collection shape is invalid")
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "passed",
        "collections": {"leaf_dependencies": 0, "one": 1, "many": 3},
        "empty_lock_rejected": True,
        "direct_dependencies_bound_to_lock": True,
        "applicable_requires_dist_closure": True,
        "non_wheel_entries_rejected": True,
        "deterministic": True,
        "independent_json_readback": True,
        "atomic_output_and_sidecar": True,
        "absolute_path_leak": False,
        "rejections": rejections,
    }
    if type(report["schema_version"]) is not int:
        raise AssertionError("test report schema_version must be an integer")
    if not isinstance(report["rejections"], list):
        raise AssertionError("test report rejections must be an array")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
