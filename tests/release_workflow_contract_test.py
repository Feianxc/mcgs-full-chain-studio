from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-package.yml"
RUN_ALL = ROOT / "tests" / "run_all.py"
PINNED_ACTION_PATTERN = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def steps_for(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps")
    require(isinstance(steps, list) and steps, "workflow job has no steps")
    require(all(isinstance(step, dict) for step in steps), "workflow step must be an object")
    return steps


def run_text(job: dict[str, Any]) -> str:
    return "\n".join(
        str(step["run"])
        for step in steps_for(job)
        if isinstance(step.get("run"), str)
    )


def uses_values(job: dict[str, Any]) -> list[str]:
    return [
        str(step["uses"])
        for step in steps_for(job)
        if isinstance(step.get("uses"), str)
    ]


def find_action_step(job: dict[str, Any], action_prefix: str) -> dict[str, Any]:
    matches = [
        step
        for step in steps_for(job)
        if str(step.get("uses", "")).startswith(action_prefix)
    ]
    require(len(matches) == 1, f"expected exactly one {action_prefix} step")
    return matches[0]


def find_named_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in steps_for(job) if step.get("name") == name]
    require(len(matches) == 1, f"expected exactly one step named {name}")
    return matches[0]


def validate_release_test_runtime(test_job: dict[str, Any]) -> None:
    require("strategy" not in test_job, "release test job must use only target Python 3.11.6")
    job_env = test_job.get("env")
    require(isinstance(job_env, dict), "release test job has no environment contract")
    require(
        job_env.get("PYTHONDONTWRITEBYTECODE") == "1",
        "release test job must disable bytecode writes",
    )
    setup_python = find_action_step(test_job, "actions/setup-python@")
    setup_with = setup_python.get("with")
    require(isinstance(setup_with, dict), "release test Python setup has no settings")
    require(
        setup_with.get("python-version") == "3.11.6",
        "release test job must use exact target Python 3.11.6",
    )

    install_step = find_named_step(
        test_job, "Install exact production lock and constrained test dependencies"
    )
    require(install_step.get("id") == "runtime", "production runtime step must publish anchors")
    install_run = str(install_step.get("run", ""))
    for required in (
        "requirements.production.lock.txt",
        "requirements.dev.txt",
        "--require-hashes",
        "--only-binary=:all:",
        '--constraint "$PRODUCTION_CONSTRAINTS"',
        "python -I -S \"$PRODUCTION_VERIFIER\"",
        "--expected-count 17",
        "distribution.files",
        "files_sha256",
        "hash_file(resolved)",
        "relative_to(prefix)",
        "PRODUCTION_BEFORE_SHA256",
        "PRODUCTION_CONSTRAINTS_SHA256",
        'cmp --silent "$PRODUCTION_BEFORE" "$PRODUCTION_AFTER_DEV"',
        'cmp --silent "$PRODUCTION_BEFORE" "$PRODUCTION_AFTER_CHECK"',
        'echo "verifier_sha256=$PRODUCTION_VERIFIER_SHA256" >> "$GITHUB_OUTPUT"',
        'echo "fingerprint_sha256=$PRODUCTION_BEFORE_SHA256" >> "$GITHUB_OUTPUT"',
        'echo "constraints_sha256=$PRODUCTION_CONSTRAINTS_SHA256" >> "$GITHUB_OUTPUT"',
    ):
        require(required in install_run, f"release test runtime contract is missing: {required}")
    require(
        install_run.count("--expected-count 17") >= 3,
        "production set must be checked before and after development installation",
    )
    exact_lock_position = install_run.find("--requirement requirements.production.lock.txt")
    before_position = install_run.find('--output "$PRODUCTION_BEFORE"')
    dev_position = install_run.find("--requirement requirements.dev.txt")
    after_dev_position = install_run.find('--output "$PRODUCTION_AFTER_DEV"')
    after_check_position = install_run.find('--output "$PRODUCTION_AFTER_CHECK"')
    require(
        0 <= exact_lock_position < before_position < dev_position < after_dev_position < after_check_position,
        "production lock, constrained dev install, and independent readbacks are misordered",
    )
    dev_command_prefix = install_run[max(0, dev_position - 350) : dev_position]
    require(
        '--constraint "$PRODUCTION_CONSTRAINTS"' in dev_command_prefix
        and "--only-binary=:all:" in dev_command_prefix,
        "development install is not constrained to the locked production set",
    )

    gates = find_named_step(test_job, "Run release gates")
    gates_env = gates.get("env")
    require(isinstance(gates_env, dict), "release gates do not consume runtime anchors")
    require(
        gates_env
        == {
            "PRODUCTION_VERIFIER_SHA256": "${{ steps.runtime.outputs.verifier_sha256 }}",
            "PRODUCTION_FINGERPRINT_SHA256": "${{ steps.runtime.outputs.fingerprint_sha256 }}",
            "PRODUCTION_CONSTRAINTS_SHA256": "${{ steps.runtime.outputs.constraints_sha256 }}",
        },
        "release gates are not bound to the runtime step outputs",
    )
    gates_run = str(gates.get("run", ""))
    pre_position = gates_run.find(
        'verify_production_runtime "$RUNNER_TEMP/production-before-tests.json"'
    )
    tests_position = gates_run.find("python scripts/run_tests.py")
    post_position = gates_run.find(
        'verify_production_runtime "$RUNNER_TEMP/production-after-tests.json"'
    )
    require(
        0 <= pre_position < tests_position < post_position,
        "all release tests must be enclosed by production runtime fingerprints",
    )
    for required in (
        "release_test_entry_count_ok=24",
        "--expected-count 17",
        "sha256sum --check -",
        'cmp --silent "$PRODUCTION_BEFORE" "$output"',
    ):
        require(required in gates_run, f"release test gate contract is missing: {required}")
    require(
        not any(
            action.startswith("actions/upload-artifact@")
            for action in uses_values(test_job)
        ),
        "test job must not publish release artifacts",
    )


def expect_runtime_rejection(
    test_job: dict[str, Any], label: str, mutate: Any
) -> str:
    candidate = copy.deepcopy(test_job)
    mutate(candidate)
    try:
        validate_release_test_runtime(candidate)
    except AssertionError:
        return label
    raise AssertionError(f"negative runtime mutation was accepted: {label}")


def read_run_all_entries() -> list[str]:
    tree = ast.parse(RUN_ALL.read_text(encoding="utf-8"), filename=str(RUN_ALL))
    values: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in {
            "JAVASCRIPT_TESTS",
            "PYTHON_TESTS",
        }:
            value = ast.literal_eval(node.value)
            require(isinstance(value, list), f"{target.id} must be a list")
            values[target.id] = value
    require(set(values) == {"JAVASCRIPT_TESTS", "PYTHON_TESTS"}, "run_all lists are missing")
    return values["JAVASCRIPT_TESTS"] + values["PYTHON_TESTS"]


def main() -> int:
    raw = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.load(raw, Loader=yaml.BaseLoader)
    require(isinstance(document, dict), "workflow root must be an object")
    require("workflow_dispatch" not in raw, "release workflow must not allow manual dispatch")
    require(
        document.get("on") == {"push": {"tags": ["v*"]}},
        "release workflow must run only for version tags",
    )
    require(
        document.get("permissions") == {"contents": "read"},
        "default workflow permissions must be contents: read only",
    )

    jobs = document.get("jobs")
    require(isinstance(jobs, dict), "workflow jobs must be an object")
    require({"test", "package", "attest"} <= set(jobs), "required release jobs are missing")
    test_job = jobs["test"]
    package_job = jobs["package"]
    attest_job = jobs["attest"]
    require(all(isinstance(job, dict) for job in (test_job, package_job, attest_job)), "job must be an object")

    require(package_job.get("needs") == "test", "clean package job must depend on test")
    require(attest_job.get("needs") == "package", "attest job must depend on package")
    require("permissions" not in test_job, "test job must not elevate permissions")
    require("permissions" not in package_job, "package job must not elevate permissions")
    require(
        attest_job.get("permissions")
        == {"contents": "read", "id-token": "write", "attestations": "write"},
        "only attest job may receive provenance permissions",
    )

    for job_name, job in jobs.items():
        require(isinstance(job, dict), f"{job_name} job must be an object")
        for action in uses_values(job):
            require(
                PINNED_ACTION_PATTERN.fullmatch(action) is not None,
                f"{job_name} action is not pinned to a full commit: {action}",
            )

    for job_name, job in (("test", test_job), ("package", package_job)):
        checkout = find_action_step(job, "actions/checkout@")
        checkout_with = checkout.get("with")
        require(isinstance(checkout_with, dict), f"{job_name} checkout has no settings")
        require(checkout_with.get("fetch-depth") == "0", f"{job_name} checkout must fetch history")
        require(
            checkout_with.get("persist-credentials") == "false",
            f"{job_name} checkout must not persist credentials",
        )
        require(checkout_with.get("clean") == "true", f"{job_name} checkout must clean the tree")

    validate_release_test_runtime(test_job)
    negative_rejections = [
        expect_runtime_rejection(
            test_job,
            "missing_constraints",
            lambda job: find_named_step(
                job, "Install exact production lock and constrained test dependencies"
            ).update(
                {
                    "run": str(
                        find_named_step(
                            job,
                            "Install exact production lock and constrained test dependencies",
                        )["run"]
                    ).replace(
                        '--constraint "$PRODUCTION_CONSTRAINTS"',
                        '--constraint "$UNCONTROLLED_CONSTRAINTS"',
                        1,
                    )
                }
            ),
        ),
        expect_runtime_rejection(
            test_job,
            "missing_distribution_file_fingerprint",
            lambda job: find_named_step(
                job, "Install exact production lock and constrained test dependencies"
            ).update(
                {
                    "run": str(
                        find_named_step(
                            job,
                            "Install exact production lock and constrained test dependencies",
                        )["run"]
                    ).replace("files_sha256", "files_unchecked", 1)
                }
            ),
        ),
        expect_runtime_rejection(
            test_job,
            "missing_after_dev_compare",
            lambda job: find_named_step(
                job, "Install exact production lock and constrained test dependencies"
            ).update(
                {
                    "run": str(
                        find_named_step(
                            job,
                            "Install exact production lock and constrained test dependencies",
                        )["run"]
                    ).replace(
                        'cmp --silent "$PRODUCTION_BEFORE" "$PRODUCTION_AFTER_DEV"',
                        ": # comparison removed",
                        1,
                    )
                }
            ),
        ),
        expect_runtime_rejection(
            test_job,
            "missing_post_test_fingerprint",
            lambda job: find_named_step(job, "Run release gates").update(
                {
                    "run": str(find_named_step(job, "Run release gates")["run"]).replace(
                        'verify_production_runtime "$RUNNER_TEMP/production-after-tests.json"',
                        ": # post-test fingerprint removed",
                        1,
                    )
                }
            ),
        ),
        expect_runtime_rejection(
            test_job,
            "bytecode_writes_enabled",
            lambda job: job["env"].update({"PYTHONDONTWRITEBYTECODE": "0"}),
        ),
        expect_runtime_rejection(
            test_job,
            "release_matrix_added",
            lambda job: job.update(
                {"strategy": {"matrix": {"python-version": ["3.11", "3.12"]}}}
            ),
        ),
        expect_runtime_rejection(
            test_job,
            "wrong_target_python",
            lambda job: find_action_step(job, "actions/setup-python@")["with"].update(
                {"python-version": "3.12"}
            ),
        ),
    ]

    run_all_entries = read_run_all_entries()
    require(len(run_all_entries) == 24, "release run_all test entry count must be 24")
    require(len(run_all_entries) == len(set(run_all_entries)), "release test entries must be unique")
    require(
        all((ROOT / value).is_file() for value in run_all_entries),
        "release run_all contains a missing test entry",
    )

    package_runs = run_text(package_job)
    package_actions = uses_values(package_job)

    for forbidden in (
        "requirements.dev.txt",
        "scripts/run_tests.py",
        "needs.test.outputs",
    ):
        require(forbidden not in package_runs, f"package job contains forbidden test input: {forbidden}")
    require(
        not any(action.startswith("actions/setup-node@") for action in package_actions),
        "package job must not install the test Node runtime",
    )
    require(
        not any(action.startswith("actions/download-artifact@") for action in package_actions),
        "package job must not consume artifacts from the dependency-installing test job",
    )

    download_position = package_runs.find("pip --isolated --disable-pip-version-check download")
    archive_position = package_runs.find("packaging/build_release.py")
    require(archive_position >= 0, "clean package job no longer builds the release archive")
    require(download_position > archive_position, "network wheel download must occur after source archive build")
    for required in (
        "python -I -m pip --isolated --disable-pip-version-check download",
        "--no-cache-dir",
        "--only-binary=:all:",
        "--require-hashes",
        "python -I -m venv",
        "--no-index",
        "--find-links \"$WHEELHOUSE\"",
        "production_dependency_smoke_ok",
        "requirements.production.lock.txt",
        "$RUNNER_TEMP/wheelhouse-v${RELEASE_VERSION}",
        "$RUNNER_TEMP/release-assets",
        "git diff --cached --exit-code -- .",
        "git status --porcelain=v1 --untracked-files=all",
        "steps.archive.outputs.sha256",
        "python -I packaging/verify_release.py",
        "python -I packaging/generate_sbom.py",
    ):
        require(required in package_runs, f"clean package contract is missing: {required}")
    offline_steps = [
        step
        for step in steps_for(package_job)
        if step.get("name") == "Verify exact production lock offline"
    ]
    require(len(offline_steps) == 1, "package job must have one exact-lock offline verification step")
    offline_run = str(offline_steps[0].get("run", ""))
    for required in (
        'VERIFY_WORK="$VERIFY_ROOT/work"',
        'cd "$VERIFY_WORK"',
        '"$VERIFY_VENV/bin/python" -I -m pip',
        "--no-index",
        '--find-links "$WHEELHOUSE"',
        "--only-binary=:all:",
        "--require-hashes",
        "requirements.production.lock.txt",
        "production_dependency_smoke_ok",
        "git diff --cached --exit-code -- .",
        "steps.archive.outputs.sha256",
    ):
        require(required in offline_run, f"offline production verification is missing: {required}")
    require(
        len(re.findall(r"(?m)^\s*install\s+\\$", offline_run)) == 1,
        "package job must perform exactly one controlled offline production install",
    )
    require(
        len(re.findall(r"(?m)^\s*check\s*$", offline_run)) == 1,
        "offline production environment must run pip check exactly once",
    )
    require(
        offline_run.count("git diff --cached --exit-code -- .") >= 2
        and offline_run.count("steps.archive.outputs.sha256") >= 2,
        "offline production install must be enclosed by source and archive integrity gates",
    )
    require(
        package_runs.count("git status --porcelain=v1 --untracked-files=all") >= 6,
        "clean package job must check source cleanliness before and after network processing",
    )
    require(
        package_runs.count("steps.archive.outputs.sha256") >= 4,
        "pre-network archive digest must be rechecked after network processing",
    )

    upload = find_action_step(package_job, "actions/upload-artifact@")
    upload_with = upload.get("with")
    require(isinstance(upload_with, dict), "release upload step has no settings")
    upload_paths = str(upload_with.get("path", "")).splitlines()
    upload_paths = [value.strip() for value in upload_paths if value.strip()]
    require(len(upload_paths) == 4, "release upload must contain exactly four assets")
    require(
        all(value.startswith("${{ runner.temp }}/release-assets/") for value in upload_paths),
        "release assets must be built outside the writable checkout",
    )
    require(not any("wheelhouse" in value.casefold() for value in upload_paths), "wheelhouse must not be uploaded")
    require(
        {value.rsplit("/", 1)[-1].split("${{ steps.version.outputs.value }}", 1)[-1] for value in upload_paths}
        == {".tar.gz", ".tar.gz.sha256", ".cdx.json", ".cdx.json.sha256"},
        "release upload asset names do not match the four-file contract",
    )

    print(
        "release_workflow_contract_ok "
        f"negative_rejections={len(negative_rejections)} test_entries={len(run_all_entries)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
