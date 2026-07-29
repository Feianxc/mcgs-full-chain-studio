from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "deploy-release.sh"
ROLLBACK_SCRIPT = REPO_ROOT / "deploy" / "rollback-release.sh"
RECOVERY_SCRIPT = REPO_ROOT / "deploy" / "recover-transaction.sh"
RUNTIME_FINGERPRINT = REPO_ROOT / "deploy" / "runtime_fingerprint.py"
SHELL_SCRIPTS = (DEPLOY_SCRIPT, ROLLBACK_SCRIPT, RECOVERY_SCRIPT)

SCRIPT_CONTRACTS = {
    "deploy-release.sh": {
        "guard": "transaction_exit_guard",
        "active": "TRANSACTION_ACTIVE",
        "record_temp": "DEPLOYMENT_RECORD_TEMP",
        "record": "DEPLOYMENT_RECORD",
        "archive": "COMMITTED_TRANSACTION_RECORD",
        "runtime_guard_install": 'install_transaction_runtime_guard "$SERVICE_USER"',
        "runtime_guard_remove": 'remove_transaction_runtime_guard "$SERVICE_USER"',
        "phase_transition": 'transition_transaction_status "switching" "deploy_committed_pending_activation"',
        "publication": 'publish_committed_record "$DEPLOYMENT_RECORD_TEMP" "$DEPLOYMENT_RECORD"',
    },
    "rollback-release.sh": {
        "guard": "transaction_exit_guard",
        "active": "TRANSACTION_ACTIVE",
        "record_temp": "ROLLBACK_RECORD_TEMP",
        "record": "ROLLBACK_RECORD",
        "archive": "COMMITTED_TRANSACTION_RECORD",
        "runtime_guard_install": 'install_transaction_runtime_guard "$SERVICE_USER"',
        "runtime_guard_remove": 'remove_transaction_runtime_guard "$SERVICE_USER"',
        "phase_transition": 'transition_transaction_status "rolling_back" "rollback_committed_pending_activation"',
        "publication": 'publish_committed_record "$ROLLBACK_RECORD_TEMP" "$ROLLBACK_RECORD"',
    },
    "recover-transaction.sh": {
        "guard": "recovery_exit_guard",
        "active": "RECOVERY_ACTIVE",
        "record_temp": "PENDING_RECOVERY_RECORD",
        "record": "RECOVERY_RECORD",
        "archive": "ARCHIVED_TRANSACTION_RECORD",
        "runtime_guard_install": 'ensure_transaction_runtime_guard_loaded "$PREVIOUS_SERVICE_USER"',
        "runtime_guard_remove": 'remove_transaction_runtime_guard "$PREVIOUS_SERVICE_USER"',
        "phase_transition": 'transition_transaction_status "$TX_STATUS" "recovery_committed_pending_activation"',
        "publication": 'reconcile_or_publish_committed_record "$PENDING_RECOVERY_RECORD" "$RECOVERY_RECORD"',
    },
}


def require_fragments(content: str, fragments: list[str], label: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in content]
    if missing:
        raise AssertionError(
            json.dumps({"label": label, "missing": missing}, ensure_ascii=False)
        )


def require_in_order(content: str, fragments: list[str], label: str) -> list[int]:
    positions: list[int] = []
    offset = 0
    for fragment in fragments:
        position = content.find(fragment, offset)
        if position < 0:
            raise AssertionError(
                json.dumps(
                    {
                        "label": label,
                        "missing_or_out_of_order": fragment,
                        "positions": positions,
                    },
                    ensure_ascii=False,
                )
            )
        positions.append(position)
        offset = position + len(fragment)
    return positions


def shell_function_source(content: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{{|\Z)",
        content,
    )
    if not match:
        raise AssertionError(f"shell function is missing: {name}")
    return match.group(0).rstrip()


def shell_function_body(content: str, name: str) -> str:
    source = shell_function_source(content, name)
    return source[source.find("\n") + 1 :]


def simple_shell_function_body(content: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}\s*$",
        content,
    )
    if not match:
        raise AssertionError(f"simple shell function is missing: {name}")
    return match.group("body")


def simple_shell_function_source(content: str, name: str) -> str:
    return f"{name}() {{\n{simple_shell_function_body(content, name)}}}"


def assert_transaction_exit_guard_ownership(
    bash: str, contents: dict[str, str]
) -> dict[str, object]:
    contracts = {
        "deploy-release.sh": {
            "handler": "rollback_to_previous",
            "running": "ROLLBACK_RUNNING",
            "failure_prefix": "SWITCH FAILED:",
            "unexpected_prefix": "deployment transaction exited unexpectedly with status",
            "marker_status": "switching",
        },
        "rollback-release.sh": {
            "handler": "restore_previous",
            "running": "ROLLBACK_RECOVERY_RUNNING",
            "failure_prefix": "ROLLBACK TARGET FAILED:",
            "unexpected_prefix": "rollback transaction exited unexpectedly with status",
            "marker_status": "rolling_back",
        },
    }
    baseline_case_specs = (
        {
            "name": "explicit_fallback",
            "trigger_status": 1,
            "explicit_reason": "explicit fallback",
            "entry": "explicit",
        },
        {
            "name": "unexpected_false",
            "trigger_status": 1,
            "explicit_reason": None,
            "entry": "false",
        },
        {
            "name": "unexpected_exit_42",
            "trigger_status": 42,
            "explicit_reason": None,
            "entry": "exit_42",
        },
    )
    signal_case_specs = (
        ("TERM", "signal_mask", 130, None),
        ("INT", "running_assignment", 1, "signal INT before running_assignment"),
        ("HUP", "exit_trap_clear", 1, "signal HUP before exit_trap_clear"),
        ("TERM", "errexit_disable", 1, "signal TERM before errexit_disable"),
        (
            "INT",
            "first_systemctl_show",
            1,
            "signal INT before first_systemctl_show",
        ),
    )
    guard_signal_case_specs = (
        ("TERM", "false"),
        ("HUP", "exit_42"),
    )
    failure_modes = (
        "disable",
        "fsync_enablement",
        "stop_verify",
        "reset_failed",
        "enablement_probe",
        "state_readback",
        "marker_acl",
        "persistent_assertion",
    )
    expected_state = {
        "enabled": False,
        "active_state": "inactive",
        "sub_state": "dead",
        "main_pid": 0,
    }
    completed_cases = 0
    completed_signal_cases = 0
    completed_guard_signal_cases = 0
    completed_failure_cases = 0
    signal_delivery_mode = "trap_state_probe" if os.name == "nt" else "real_signal"

    with tempfile.TemporaryDirectory(prefix="transaction-exit-guard-") as temporary:
        root = Path(temporary)
        for script_index, (label, contract) in enumerate(contracts.items(), start=1):
            content = contents[label]
            handler = str(contract["handler"])
            running = str(contract["running"])
            marker_payload = (
                json.dumps(
                    {"schema_version": 3, "status": contract["marker_status"]},
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            handler_source = simple_shell_function_source(content, handler)
            guard_source = simple_shell_function_source(content, "transaction_exit_guard")
            signal_guard_source = simple_shell_function_source(
                content, "transaction_signal_guard"
            )
            signal_trap_source = "trap transaction_signal_guard INT TERM HUP"
            first_systemctl_show = next(
                line.strip()
                for line in handler_source.splitlines()
                if line.lstrip().startswith(
                    'original_pid="$(systemctl show "$SERVICE" '
                )
            )
            require_in_order(
                handler_source,
                [
                    "trap '' INT TERM HUP",
                    f'{running}="true"',
                    "trap - EXIT",
                    "set +e",
                ],
                f"{label}-compensation-handler-blocks-signals-before-owning-exit",
            )
            require_in_order(
                guard_source,
                [
                    'local status="${1:-$?}"',
                    "trap '' INT TERM HUP",
                    "trap - EXIT",
                ],
                f"{label}-exit-guard-blocks-signals-before-compensation",
            )
            require_in_order(
                signal_guard_source,
                ["trap '' INT TERM HUP", "transaction_exit_guard 130"],
                f"{label}-signal-guard-blocks-signals-before-explicit-exit-guard",
            )
            if content.count(signal_trap_source) != 1:
                raise AssertionError(
                    f"{label}: signal guard trap must be installed exactly once"
                )

            injection_targets = {
                "signal_mask": "trap '' INT TERM HUP",
                "running_assignment": f'{running}="true"',
                "exit_trap_clear": "trap - EXIT",
                "errexit_disable": "set +e",
                "first_systemctl_show": first_systemctl_show.replace(
                    "2>/dev/null", "2> /dev/null"
                ),
            }
            case_specs = [
                {
                    **spec,
                    "failure_mode": "none",
                    "inject_signal": "none",
                    "inject_step": "none",
                    "inject_before": "none",
                    "expect_confirmed": True,
                }
                for spec in baseline_case_specs
            ]
            case_specs.extend(
                {
                    "name": f"signal_{signal.lower()}_before_{step}",
                    "trigger_status": trigger_status,
                    "explicit_reason": explicit_reason,
                    "entry": "explicit",
                    "failure_mode": "none",
                    "inject_signal": signal,
                    "inject_step": step,
                    "inject_before": injection_targets[step],
                    "expect_confirmed": True,
                }
                for signal, step, trigger_status, explicit_reason in signal_case_specs
            )
            case_specs.extend(
                {
                    "name": f"unexpected_{entry}_signal_{signal.lower()}_in_guard",
                    "trigger_status": 130,
                    "explicit_reason": None,
                    "entry": entry,
                    "failure_mode": "none",
                    "inject_signal": signal,
                    "inject_step": "guard_signal_mask",
                    "inject_before": "trap '' INT TERM HUP",
                    "expect_confirmed": True,
                }
                for signal, entry in guard_signal_case_specs
            )
            case_specs.extend(
                {
                    "name": f"failure_{failure_mode}",
                    "trigger_status": 1,
                    "explicit_reason": f"failure branch {failure_mode}",
                    "entry": "explicit",
                    "failure_mode": failure_mode,
                    "inject_signal": "none",
                    "inject_step": "none",
                    "inject_before": "none",
                    "expect_confirmed": False,
                }
                for failure_mode in failure_modes
            )

            for case_index, case_spec in enumerate(case_specs, start=1):
                case_name = str(case_spec["name"])
                trigger_status = int(case_spec["trigger_status"])
                explicit_reason = case_spec["explicit_reason"]
                failure_mode = str(case_spec["failure_mode"])
                inject_signal = str(case_spec["inject_signal"])
                inject_step = str(case_spec["inject_step"])
                inject_before = str(case_spec["inject_before"])
                expect_confirmed = bool(case_spec["expect_confirmed"])
                case_root = root / f"{script_index}-{case_index}-{case_name}"
                case_root.mkdir()
                marker = case_root / "transaction.json"
                state = case_root / "systemd-state.json"
                trace = case_root / "systemd-trace.txt"
                signal_trace = case_root / "signal-trace.txt"
                marker.write_bytes(marker_payload)
                entry = str(case_spec["entry"])
                if entry == "explicit":
                    explicit_command = f'false || {handler} "{explicit_reason}"'
                elif entry == "false":
                    explicit_command = "false"
                elif entry == "exit_42":
                    explicit_command = "exit 42"
                else:
                    raise AssertionError(f"unsupported exit-guard test entry: {entry}")
                harness = f"""\
set -Eeuo pipefail
TRANSACTION_FILE="$1"
SYSTEMD_STATE_FILE="$2"
SYSTEMD_TRACE_FILE="$3"
FAILURE_MODE="$4"
INJECT_SIGNAL="$5"
INJECT_STEP="$6"
SIGNAL_TRACE_FILE="$7"
SIGNAL_DELIVERY_MODE="$8"
SERVICE="protocol-studio.service"
SERVICE_USER="protocol-studio"
TRANSACTION_ACTIVE="true"
TRANSACTION_COMMITTED="false"
{running}="false"
DEBUG_FIRED="false"
INJECT_BEFORE="none"

case "$INJECT_STEP" in
  guard_signal_mask) INJECT_BEFORE="trap '' INT TERM HUP" ;;
  signal_mask) INJECT_BEFORE="trap '' INT TERM HUP" ;;
  running_assignment) INJECT_BEFORE='{running}="true"' ;;
  exit_trap_clear) INJECT_BEFORE="trap - EXIT" ;;
  errexit_disable) INJECT_BEFORE="set +e" ;;
  first_systemctl_show)
    # BASH_COMMAND renders the redirection with a separating space.
    INJECT_BEFORE='{injection_targets["first_systemctl_show"]}'
    ;;
  none) ;;
  *) exit 64 ;;
esac

trap() {{
  local caller="${{FUNCNAME[1]:-}}"
  if [[ "$DEBUG_FIRED" == "false" \
    && "$INJECT_STEP" == "guard_signal_mask" \
    && "$caller" == "transaction_exit_guard" \
    && "${{1-}}" == "" && "${{2-}}" == "INT" \
    && "${{3-}}" == "TERM" && "${{4-}}" == "HUP" ]]; then
    DEBUG_FIRED="true"
    printf '%s\t%s\t%s\n' \
      "$INJECT_SIGNAL" "$INJECT_BEFORE" "$SIGNAL_DELIVERY_MODE" \
      > "$SIGNAL_TRACE_FILE"
    if [[ "$SIGNAL_DELIVERY_MODE" == "real_signal" ]]; then
      kill -s "$INJECT_SIGNAL" "$BASHPID"
    elif [[ "$SIGNAL_DELIVERY_MODE" == "trap_state_probe" ]]; then
      transaction_signal_guard
    else
      exit 64
    fi
  fi
  builtin trap "$@"
}}

debug_injector() {{
  local pending_command="$BASH_COMMAND"
  if [[ "$DEBUG_FIRED" == "false" && "$pending_command" == "$INJECT_BEFORE" ]]; then
    DEBUG_FIRED="true"
    printf '%s\\t%s\\t%s\\n' \
      "$INJECT_SIGNAL" "$pending_command" "$SIGNAL_DELIVERY_MODE" \
      > "$SIGNAL_TRACE_FILE"
    if [[ "$SIGNAL_DELIVERY_MODE" == "real_signal" ]]; then
      kill -s "$INJECT_SIGNAL" "$BASHPID"
    elif [[ "$SIGNAL_DELIVERY_MODE" == "trap_state_probe" ]]; then
      if [[ "$INJECT_STEP" == "guard_signal_mask" \
        || "$INJECT_STEP" == "signal_mask" ]]; then
        transaction_signal_guard
      fi
      local trap_state
      trap_state="$(trap -p "$INJECT_SIGNAL")"
      if [[ "$trap_state" != "trap -- '' SIG$INJECT_SIGNAL" ]]; then
        printf '%s\\t%s\\n' "PROBE_FAILURE" "$trap_state" >> "$SIGNAL_TRACE_FILE"
        exit 70
      fi
    else
      exit 64
    fi
  fi
}}

write_systemd_state() {{
  printf 'enabled=%s\\nactive_state=%s\\nsub_state=%s\\nmain_pid=%s\\n' \
    "$1" "$2" "$3" "$4" > "$SYSTEMD_STATE_FILE"
}}

read_systemd_state() {{
  local requested="$1"
  local key
  local value
  while IFS='=' read -r key value; do
    if [[ "$key" == "$requested" ]]; then
      printf '%s\\n' "$value"
      return 0
    fi
  done < "$SYSTEMD_STATE_FILE"
  return 1
}}

systemctl() {{
  local enabled
  local active_state
  local sub_state
  local main_pid
  case "$1" in
    disable)
      printf '%s\\n' "disable" >> "$SYSTEMD_TRACE_FILE"
      if [[ "$FAILURE_MODE" == "disable" ]]; then
        return 1
      fi
      active_state="$(read_systemd_state active_state)"
      sub_state="$(read_systemd_state sub_state)"
      main_pid="$(read_systemd_state main_pid)"
      write_systemd_state false "$active_state" "$sub_state" "$main_pid"
      ;;
    reset-failed)
      printf '%s\\n' "reset-failed" >> "$SYSTEMD_TRACE_FILE"
      [[ "$FAILURE_MODE" != "reset_failed" ]]
      ;;
    show)
      if [[ "$FAILURE_MODE" == "state_readback" \
        && "$*" == *"--property=ActiveState --value"* ]]; then
        enabled="$(read_systemd_state enabled)"
        write_systemd_state "$enabled" active running 99999999
      fi
      case "$*" in
        *"--property=ActiveState --value"*)
          printf '%s\\n' "show-active" >> "$SYSTEMD_TRACE_FILE"
          read_systemd_state active_state
          ;;
        *"--property=SubState --value"*)
          printf '%s\\n' "show-sub" >> "$SYSTEMD_TRACE_FILE"
          read_systemd_state sub_state
          ;;
        *"--property=MainPID --value"*)
          printf '%s\\n' "show-main-pid" >> "$SYSTEMD_TRACE_FILE"
          read_systemd_state main_pid
          ;;
        *)
          return 64
          ;;
      esac
      ;;
    *)
      return 64
      ;;
  esac
}}

stat() {{
  if [[ "$#" -eq 4 && "$1" == "-c" && "$2" == "%u:%g:%a" \
    && "$3" == "--" && "$4" == "$TRANSACTION_FILE" ]]; then
    printf '%s\\n' "0:0:600"
    return 0
  fi
  command stat "$@"
}}

fsync_systemd_enablement_state() {{
  printf '%s\\n' "fsync-enablement" >> "$SYSTEMD_TRACE_FILE"
  [[ "$FAILURE_MODE" != "fsync_enablement" ]]
}}
stop_service_and_verify() {{
  local enabled
  printf '%s\\n' "stop-verify" >> "$SYSTEMD_TRACE_FILE"
  if [[ "$FAILURE_MODE" == "stop_verify" ]]; then
    return 1
  fi
  enabled="$(read_systemd_state enabled)"
  write_systemd_state "$enabled" inactive dead 0
}}
probe_service_enablement() {{
  printf '%s\\n' "probe-enablement" >> "$SYSTEMD_TRACE_FILE"
  if [[ "$FAILURE_MODE" == "enablement_probe" || "$FAILURE_MODE" == "disable" ]]; then
    SERVICE_ENABLE_STDOUT="enabled"
    SERVICE_ENABLE_EXIT="0"
  else
    SERVICE_ENABLE_STDOUT="disabled"
    SERVICE_ENABLE_EXIT="1"
  fi
}}
acl_is_minimal() {{
  printf '%s\\n' "acl-minimal" >> "$SYSTEMD_TRACE_FILE"
  [[ "$FAILURE_MODE" != "marker_acl" ]]
}}
assert_service_persistently_disabled() {{
  printf '%s\\n' "assert-persistent-disabled" >> "$SYSTEMD_TRACE_FILE"
  if [[ "$FAILURE_MODE" == "persistent_assertion" ]]; then
    return 1
  fi
  [[ "$(read_systemd_state enabled)" == "false" \
    && "$(read_systemd_state active_state)" == "inactive" \
    && "$(read_systemd_state sub_state)" == "dead" \
    && "$(read_systemd_state main_pid)" == "0" ]]
}}
cleanup_candidate() {{
  printf '%s\\n' "cleanup-candidate" >> "$SYSTEMD_TRACE_FILE"
  return 0
}}

write_systemd_state true active running 99999999

{handler_source}

{guard_source}

{signal_guard_source}

trap transaction_exit_guard EXIT
{signal_trap_source}
if [[ "$INJECT_SIGNAL" != "none" ]]; then
  set -T
  trap debug_injector DEBUG
fi
{explicit_command}
"""
                harness_path = case_root / "harness.sh"
                harness_path.write_text(harness, encoding="utf-8", newline="\n")
                completed = subprocess.run(
                    [
                        bash,
                        harness_path.as_posix(),
                        marker.as_posix(),
                        state.as_posix(),
                        trace.as_posix(),
                        failure_mode,
                        inject_signal,
                        inject_step,
                        signal_trace.as_posix(),
                        signal_delivery_mode,
                    ],
                    cwd=REPO_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                    ),
                )
                if completed.returncode != 1:
                    raise AssertionError(
                        f"{label}/{case_name}: compensation must terminate with status 1, "
                        f"got {completed.returncode}"
                    )
                if completed.stdout:
                    raise AssertionError(
                        f"{label}/{case_name}: compensation leaked stdout: "
                        f"{completed.stdout!r}"
                    )
                stderr = completed.stderr
                expected_reason = (
                    explicit_reason
                    if explicit_reason is not None
                    else f"{contract['unexpected_prefix']} {trigger_status}"
                )
                message_counts = {
                    "failure_prefix": stderr.count(str(contract["failure_prefix"])),
                    "reason": stderr.count(expected_reason),
                    "confirmed": stderr.count("FAIL-CLOSED CONFIRMED:"),
                    "not_confirmed": stderr.count(
                        "CRITICAL: FAIL-CLOSED NOT CONFIRMED"
                    ),
                    "recursive": stderr.count("recursive transaction failure"),
                    "do_not_reboot": stderr.count("DO NOT REBOOT"),
                }
                if expect_confirmed:
                    expected_counts = {
                        "failure_prefix": 1,
                        "reason": 1,
                        "confirmed": 1,
                        "not_confirmed": 0,
                        "recursive": 0,
                        "do_not_reboot": 0,
                    }
                else:
                    expected_counts = {
                        "failure_prefix": 1,
                        "reason": 1,
                        "confirmed": 0,
                        "not_confirmed": 1,
                        "recursive": 0,
                        "do_not_reboot": 1,
                    }
                if message_counts != expected_counts:
                    raise AssertionError(
                        f"{label}/{case_name}: contradictory compensation messages: "
                        f"counts={message_counts!r} stderr={stderr!r}"
                    )
                if marker.read_bytes() != marker_payload:
                    raise AssertionError(
                        f"{label}/{case_name}: active transaction marker was modified"
                    )
                if inject_signal != "none":
                    expected_signal_trace = (
                        f"{inject_signal}\t{inject_before}\t{signal_delivery_mode}"
                    )
                    if (
                        not signal_trace.is_file()
                        or signal_trace.read_text(encoding="utf-8").splitlines()
                        != [expected_signal_trace]
                    ):
                        actual_signal_trace = (
                            signal_trace.read_text(encoding="utf-8")
                            if signal_trace.exists()
                            else None
                        )
                        raise AssertionError(
                            f"{label}/{case_name}: DEBUG signal injection did not fire "
                            f"exactly once at the requested command: "
                            f"{actual_signal_trace!r}"
                        )
                    completed_signal_cases += 1
                    if inject_step == "guard_signal_mask":
                        completed_guard_signal_cases += 1
                elif signal_trace.exists():
                    raise AssertionError(
                        f"{label}/{case_name}: unexpected signal trace was written"
                    )

                raw_systemd_state: dict[str, str] = {}
                for line in state.read_text(encoding="utf-8").splitlines():
                    key, separator, value = line.partition("=")
                    if not separator or key in raw_systemd_state:
                        raise AssertionError(
                            f"{label}/{case_name}: malformed systemd state line: "
                            f"{line!r}"
                        )
                    raw_systemd_state[key] = value
                if raw_systemd_state.get("enabled") not in {"true", "false"}:
                    raise AssertionError(
                        f"{label}/{case_name}: invalid systemd enabled state"
                    )
                try:
                    main_pid = int(raw_systemd_state["main_pid"])
                except (KeyError, ValueError) as error:
                    raise AssertionError(
                        f"{label}/{case_name}: invalid systemd MainPID state"
                    ) from error
                systemd_state = {
                    "enabled": raw_systemd_state["enabled"] == "true",
                    "active_state": raw_systemd_state.get("active_state"),
                    "sub_state": raw_systemd_state.get("sub_state"),
                    "main_pid": main_pid,
                }
                if (
                    type(systemd_state.get("enabled")) is not bool
                    or type(systemd_state.get("active_state")) is not str
                    or type(systemd_state.get("sub_state")) is not str
                    or type(systemd_state.get("main_pid")) is not int
                    or (expect_confirmed and systemd_state != expected_state)
                ):
                    raise AssertionError(
                        f"{label}/{case_name}: fail-closed systemd state drifted: "
                        f"{systemd_state!r}"
                    )
                trace_lines = trace.read_text(encoding="utf-8").splitlines()
                expected_trace_counts = {
                    "disable": 1,
                    "reset-failed": 1,
                    "show-active": 1,
                    "show-sub": 1,
                    "show-main-pid": 2,
                    "fsync-enablement": 1,
                    "stop-verify": 1,
                    "probe-enablement": 1,
                    "acl-minimal": 1,
                    "assert-persistent-disabled": 1,
                    "cleanup-candidate": 1 if label == "deploy-release.sh" else 0,
                }
                trace_counts = {
                    name: trace_lines.count(name) for name in expected_trace_counts
                }
                if trace_counts != expected_trace_counts:
                    raise AssertionError(
                        f"{label}/{case_name}: systemd compensation trace drifted: "
                        f"{trace_counts!r}"
                    )
                if failure_mode != "none":
                    completed_failure_cases += 1
                completed_cases += 1

    return {
        "scripts": len(contracts),
        "cases": completed_cases,
        "baseline_cases": len(contracts) * len(baseline_case_specs),
        "signal_injection_cases": completed_signal_cases,
        "guard_entry_signal_cases": completed_guard_signal_cases,
        "failure_branch_cases": completed_failure_cases,
        "signals": sorted(
            {spec[0] for spec in signal_case_specs}
            | {spec[0] for spec in guard_signal_case_specs}
        ),
        "signal_delivery_mode": signal_delivery_mode,
        "real_signal_injection_executed": signal_delivery_mode == "real_signal",
        "failure_modes": list(failure_modes),
        "trigger_statuses": [
            int(spec["trigger_status"]) for spec in baseline_case_specs
        ],
        "terminal_status": 1,
        "marker_retained": True,
        "systemd_fail_closed_state": expected_state,
        "mutually_exclusive_verdict": True,
    }


def content_after(content: str, fragment: str, label: str) -> str:
    position = content.find(fragment)
    if position < 0:
        raise AssertionError(f"{label}: missing anchor: {fragment}")
    return content[position:]


def assert_runtime_fingerprint_schema() -> int:
    helper = RUNTIME_FINGERPRINT.read_text(encoding="utf-8")
    if len(re.findall(r"(?m)^SCHEMA_VERSION = 2$", helper)) != 1:
        raise AssertionError("runtime fingerprint helper must declare schema 2 exactly once")
    require_fragments(
        helper,
        [
            "BASELINE_SCHEMA_VERSION = 1",
            '"runtime_guard_helper_sha256"',
            'baseline["runtime_guard_helper_sha256"] != helper_sha256',
            'fail_verification("runtime guard helper digest mismatch")',
            '"runtime_guard_helper_sha256": helper_sha256',
        ],
        "runtime-helper-baseline-binding",
    )

    with tempfile.TemporaryDirectory(prefix="runtime-schema-contract-") as temporary:
        root = Path(temporary)
        runtime = root / "runtime"
        interpreter = runtime / "bin" / "python"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_bytes(b"synthetic interpreter\n")
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                os.fspath(RUNTIME_FINGERPRINT),
                "--runtime-root",
                os.fspath(runtime),
                "--python",
                os.fspath(interpreter),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(
                "runtime fingerprint schema probe failed: "
                f"exit={completed.returncode} stderr={completed.stderr!r}"
            )
        report = json.loads(completed.stdout)
        if type(report.get("schema_version")) is not int:
            raise AssertionError("runtime fingerprint schema_version must be a JSON integer")
        if report["schema_version"] != 2:
            raise AssertionError("runtime fingerprint output must use schema 2")
        if not isinstance(report.get("distributions"), list):
            raise AssertionError("runtime fingerprint distributions must remain an array")
        return report["schema_version"]


def assert_atomic_probe_only(content: str, label: str) -> None:
    body = shell_function_body(content, "verify_atomic_rename_boundary")
    require_fragments(
        body,
        [
            '[python, "-I", helper, "probe", "--source-dir", source_dir, "--target-dir", target_dir]',
            'type(report["schema_version"]) is not int',
            'type(report["error_number"]) is not int',
            'type(report[name]) is not bool',
        ],
        f"{label}-atomic-probe-strict-json",
    )
    modes = re.findall(r'\bhelper,\s*["\']([a-z][a-z0-9_-]*)["\']', body)
    if modes != ["probe"]:
        raise AssertionError(f"{label}: atomic helper modes must be exactly ['probe']: {modes}")
    if content.count('"$SCRIPT_DIR/atomic_rename.py"') != 2:
        raise AssertionError(
            f"{label}: atomic helper must appear only in the trust list and probe wrapper"
        )
    if content.count("verify_atomic_rename_boundary") != 2:
        raise AssertionError(f"{label}: atomic boundary probe must be defined and called once")
    direct_replace = re.search(
        r'atomic_rename\.py["\']?(?:\s*\\\r?\n\s*|\s+)["\']?replace\b',
        content,
    )
    if direct_replace or re.search(r'\bhelper,\s*["\']replace["\']', content):
        raise AssertionError(f"{label}: atomic helper replace mode is forbidden")


def assert_no_overwrite_publication(
    content: str,
    label: str,
    record_temp: str,
    record: str,
) -> str:
    body = shell_function_body(content, "publish_committed_record")
    require_in_order(
        body,
        [
            '[[ ! -e "$final" && ! -L "$final" ]] || return 1',
            'ln -T -- "$temporary" "$final" || return 1',
            '"$(stat -c \'%d:%i\' -- "$temporary")" == "$(stat -c \'%d:%i\' -- "$final")"',
            'fsync_directory "$DEPLOYMENT_DIR" || return 1',
            "rm " + '-f -- "$temporary" || return 1',
            '[[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1',
            'fsync_directory "$DEPLOYMENT_DIR"',
        ],
        f"{label}-no-overwrite-publication-function",
    )
    if re.search(r"(?m)^\s*(?:mv|cp|install)\b", body) or "ln -f" in body:
        raise AssertionError(f"{label}: passed-record publication contains overwrite semantics")
    direct_call = f'publish_committed_record "${record_temp}" "${record}"'
    reconcile_call = f'reconcile_or_publish_committed_record "${record_temp}" "${record}"'
    direct_line_count = len(
        re.findall(rf'(?m)^\s*{re.escape(direct_call)}(?:\s|$)', content)
    )
    reconcile_line_count = len(
        re.findall(rf'(?m)^\s*{re.escape(reconcile_call)}(?:\s|$)', content)
    )
    if direct_line_count + reconcile_line_count != 1:
        raise AssertionError(
            f"{label}: passed-record publication/reconciliation call must occur exactly once"
        )
    overwrite_pattern = re.compile(
        rf'(?m)^\s*mv\s+[^\n]*"\${re.escape(record_temp)}"\s+"\${re.escape(record)}"'
    )
    if overwrite_pattern.search(content):
        raise AssertionError(f"{label}: passed record is still published with mv overwrite")
    return shell_function_source(content, "publish_committed_record")


def run_publication_harness(bash: str, function_source: str, root: Path) -> None:
    harness = f"""set -u
DEPLOYMENT_DIR=.
fsync_directory() {{ return 0; }}
stat() {{
  if [[ "$1" == "-c" && "$2" == "%u:%g:%a" ]]; then
    printf '0:0:640\\n'
  else
    command stat "$@"
  fi
}}
{function_source}
publish_committed_record "$1" "$2"
"""

    pending = root / "pending.json"
    final = root / "passed.json"
    pending.write_bytes(b"first\n")
    first = subprocess.run(
        [bash, "-c", harness, "transaction-publication", pending.name, final.name],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if first.returncode != 0:
        raise AssertionError(
            "no-overwrite publication harness rejected an unused destination: "
            f"exit={first.returncode} stdout={first.stdout!r} stderr={first.stderr!r}"
        )
    if pending.exists() or final.read_bytes() != b"first\n":
        raise AssertionError("successful publication did not move one immutable payload")

    second = root / "second.json"
    second.write_bytes(b"second\n")
    rejected = subprocess.run(
        [bash, "-c", harness, "transaction-publication", second.name, final.name],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if rejected.returncode == 0:
        raise AssertionError("existing passed-record destination was overwritten")
    if second.read_bytes() != b"second\n" or final.read_bytes() != b"first\n":
        raise AssertionError("rejected publication mutated the source or existing record")


def assert_reconcile_durability_contract(recovery: str) -> tuple[str, str]:
    body = shell_function_body(recovery, "reconcile_or_publish_committed_record")
    both_branch = body.split('elif [[ -e "$final" || -L "$final" ]]', 1)[0]
    require_in_order(
        both_branch,
        [
            'assert_trusted_record_file "$pending" "pending committed operation evidence"',
            'assert_trusted_record_file "$final" "published committed operation evidence"',
            '"$(stat -c \'%d:%i\' -- "$pending")" == "$(stat -c \'%d:%i\' -- "$final")"',
            'cmp -s "$pending" "$final"',
            'fsync_file "$final"',
            'fsync_directory "$DEPLOYMENT_DIR"',
            'rm ' + '-f -- "$pending"',
            '[[ ! -e "$pending" && ! -L "$pending" ]]',
            'fsync_directory "$DEPLOYMENT_DIR"',
        ],
        "recovery-both-exist-reconciliation-durability",
    )
    final_only_match = re.search(
        r'(?ms)elif \[\[ -e "\$final" \|\| -L "\$final" \]\]; then\n'
        r'(?P<body>.*?)\n  elif \[\[ -e "\$pending"',
        body,
    )
    if not final_only_match:
        raise AssertionError("recovery final-only reconciliation branch is missing")
    require_in_order(
        final_only_match.group("body"),
        [
            'assert_trusted_record_file "$final" "published committed operation evidence"',
            'fsync_file "$final"',
            'fsync_directory "$DEPLOYMENT_DIR"',
        ],
        "recovery-final-only-reconciliation-durability",
    )
    return (
        shell_function_source(recovery, "publish_committed_record"),
        shell_function_source(recovery, "reconcile_or_publish_committed_record"),
    )


def run_reconcile_interruption_harness(
    bash: str,
    publish_source: str,
    reconcile_source: str,
    root: Path,
) -> int:
    harness = f"""set -u
DEPLOYMENT_DIR=.
TRACE="$4"
INJECT="${{5:-}}"
FSYNC_DIRECTORY_CALLS=0
assert_trusted_record_file() {{
  [[ -f "$1" && ! -L "$1" ]]
}}
fsync_file() {{
  printf 'file:%s\n' "$1" >>"$TRACE"
  if [[ "$INJECT" == "fsync_file" ]]; then
    kill -9 "$BASHPID"
  fi
  return 0
}}
fsync_directory() {{
  FSYNC_DIRECTORY_CALLS=$((FSYNC_DIRECTORY_CALLS + 1))
  printf 'directory:%s:%s\n' "$1" "$FSYNC_DIRECTORY_CALLS" >>"$TRACE"
  if [[ "$INJECT" == "fsync_directory" && "$FSYNC_DIRECTORY_CALLS" == "1" ]]; then
    kill -9 "$BASHPID"
  fi
  return 0
}}
stat() {{
  if [[ "$1" == "-c" && "$2" == "%u:%g:%a" ]]; then
    printf '0:0:640\n'
  else
    command stat "$@"
  fi
}}
ln() {{
  if [[ "$INJECT" == "link" ]]; then
    kill -9 "$BASHPID"
  fi
  command ln "$@"
}}
rm() {{
  if [[ "$INJECT" == "unlink" ]]; then
    kill -9 "$BASHPID"
  fi
  command rm "$@"
}}
{publish_source}
{reconcile_source}
case "$1" in
  publish) publish_committed_record "$2" "$3" ;;
  reconcile) reconcile_or_publish_committed_record "$2" "$3" ;;
  *) exit 64 ;;
esac
"""

    completed_cases = 0
    for injection in ("link", "fsync_directory", "fsync_file", "unlink"):
        case_root = root / injection
        case_root.mkdir()
        pending = case_root / "pending.json"
        final = case_root / "passed.json"
        trace = case_root / "trace.log"
        pending.write_bytes(b"immutable-payload\n")
        mode = "publish"
        if injection == "fsync_file":
            os.link(pending, final)
            mode = "reconcile"
        interrupted = subprocess.run(
            [
                bash,
                "-c",
                harness,
                "reconcile-interruption",
                mode,
                pending.name,
                final.name,
                trace.name,
                injection,
            ],
            cwd=case_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if interrupted.returncode == 0:
            raise AssertionError(f"{injection}: interruption injection did not terminate")
        if not pending.exists():
            raise AssertionError(f"{injection}: interrupted publication lost pending evidence")
        if injection == "link":
            if final.exists():
                raise AssertionError("link interruption unexpectedly created final evidence")
        else:
            if not final.exists() or not os.path.samefile(pending, final):
                raise AssertionError(
                    f"{injection}: interrupted publication did not retain one hard-linked inode"
                )

        retry_trace = case_root / "retry.log"
        retried = subprocess.run(
            [
                bash,
                "-c",
                harness,
                "reconcile-retry",
                "reconcile",
                pending.name,
                final.name,
                retry_trace.name,
                "",
            ],
            cwd=case_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if retried.returncode != 0:
            raise AssertionError(
                f"{injection}: retry failed: exit={retried.returncode} "
                f"stdout={retried.stdout!r} stderr={retried.stderr!r}"
            )
        if pending.exists() or final.read_bytes() != b"immutable-payload\n":
            raise AssertionError(f"{injection}: retry did not preserve exactly one final payload")

        final_only_trace = case_root / "final-only.log"
        final_only = subprocess.run(
            [
                bash,
                "-c",
                harness,
                "reconcile-final-only",
                "reconcile",
                pending.name,
                final.name,
                final_only_trace.name,
                "",
            ],
            cwd=case_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if final_only.returncode != 0:
            raise AssertionError(f"{injection}: final-only retry was not idempotent")
        trace_text = final_only_trace.read_text(encoding="utf-8")
        if "file:passed.json\n" not in trace_text or "directory:.:1\n" not in trace_text:
            raise AssertionError(
                f"{injection}: final-only retry omitted file/directory durability: {trace_text!r}"
            )
        completed_cases += 1

    collision_root = root / "no-overwrite"
    collision_root.mkdir()
    pending = collision_root / "pending.json"
    final = collision_root / "passed.json"
    trace = collision_root / "trace.log"
    pending.write_bytes(b"new\n")
    final.write_bytes(b"existing\n")
    collision = subprocess.run(
        [
            bash,
            "-c",
            harness,
            "reconcile-no-overwrite",
            "reconcile",
            pending.name,
            final.name,
            trace.name,
            "",
        ],
        cwd=collision_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if collision.returncode == 0:
        raise AssertionError("reconciliation accepted different pending/final inodes")
    if pending.read_bytes() != b"new\n" or final.read_bytes() != b"existing\n":
        raise AssertionError("no-overwrite reconciliation mutated ambiguous evidence")
    return completed_cases + 1


def assert_enablement_alias_contract(content: str, label: str) -> str:
    collector = shell_function_source(content, "collect_service_enablement_links")
    require_fragments(
        collector,
        [
            '"$PYTHON_BIN" -I - "$SYSTEMD_CONFIG_DIR" "$SYSTEMD_UNIT_FILE"',
            'directory.name.endswith((".wants", ".requires"))',
            "entry.is_symlink()",
            "entry.resolve(strict=True)",
            "resolved == target_resolved",
            "for value in sorted(matches)",
        ],
        f"{label}-canonical-enable-alias-scan",
    )
    disabled = shell_function_body(content, "assert_service_persistently_disabled")
    enabled = shell_function_body(content, "assert_standard_enabled_topology")
    for body_name, body in (("disabled", disabled), ("enabled", enabled)):
        if '-name "$SERVICE"' in body:
            raise AssertionError(f"{label}: {body_name} topology still filters by basename")
        require_fragments(
            body,
            [
                "collect_service_enablement_links",
                'enablement_links=("${SERVICE_ENABLEMENT_LINKS[@]}")',
            ],
            f"{label}-{body_name}-canonical-alias-consumer",
        )
    require_fragments(
        disabled,
        ['((${#enablement_links[@]} == 0)) || return 1'],
        f"{label}-disabled-rejects-any-alias",
    )
    require_fragments(
        enabled,
        [
            '[[ "${#enablement_links[@]}" == "1"',
            '"${enablement_links[0]}" == "$wants_link"',
        ],
        f"{label}-enabled-requires-unique-standard-link",
    )
    return collector


def run_enablement_alias_harness(bash: str, collector: str, root: Path) -> int:
    target = root / "sample.service"
    target.write_text("[Service]\n", encoding="utf-8")
    wants = root / "multi-user.target.wants"
    requires = root / "graphical.target.requires"
    wants.mkdir()
    requires.mkdir()
    unrelated = root / "unrelated.service"
    unrelated.write_text("[Service]\n", encoding="utf-8")

    harness = f"""set -u
PYTHON_BIN=python
SYSTEMD_CONFIG_DIR="$1"
SERVICE=sample.service
SYSTEMD_UNIT_FILE="$SYSTEMD_CONFIG_DIR/$SERVICE"
{collector}
collect_service_enablement_links
for value in "${{SERVICE_ENABLEMENT_LINKS[@]}}"; do
  printf '%s\\0' "$value"
done
"""

    def collect() -> set[Path]:
        completed = subprocess.run(
            [bash, "-c", harness, "enablement-alias", os.fspath(root)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(
                "enablement alias harness failed: "
                f"exit={completed.returncode} stderr={completed.stderr.decode('utf-8', 'replace')!r}"
            )
        values = [value for value in completed.stdout.split(b"\0") if value]
        return {Path(value.decode("utf-8")) for value in values}

    if collect():
        raise AssertionError("empty enablement tree produced a managed link")
    standard = wants / "sample.service"
    standard.symlink_to(target)
    if {path.resolve() for path in collect()} != {standard.resolve()}:
        raise AssertionError("standard enablement link was not detected")
    alias = requires / "different-name.service"
    alias.symlink_to(target)
    if len(collect()) != 2:
        raise AssertionError("different-basename alias pointing to the unit was not detected")
    unrelated_alias = wants / "unrelated-alias.service"
    unrelated_alias.symlink_to(unrelated)
    if len(collect()) != 2:
        raise AssertionError("unrelated systemd symlink polluted managed topology")
    standard.unlink()
    if collect() != {alias}:
        raise AssertionError("requires alias was not retained after removing the standard link")
    return 4


def assert_runtime_systemd_guard_contract(content: str, label: str) -> None:
    require_fragments(
        content,
        [
            'RUNTIME_SYSTEMD_DIR="/run/systemd/system"',
            'TRANSACTION_RUNTIME_GUARD_DIR="$RUNTIME_SYSTEMD_DIR/$SERVICE.d"',
            'TRANSACTION_RUNTIME_GUARD="$TRANSACTION_RUNTIME_GUARD_DIR/99-transaction-runtime-guard.conf"',
            "assert_transaction_runtime_guard_file()",
            "assert_transaction_runtime_guard_loaded()",
            "install_transaction_runtime_guard()",
            "ensure_transaction_runtime_guard_loaded()",
            "remove_transaction_runtime_guard()",
            "transition_transaction_status()",
            "payload = b\"[Service]\\nRestart=no\\nRuntimeMaxSec=300s\\n\"",
        ],
        f"{label}-runtime-systemd-guard-surface",
    )

    file_check = shell_function_body(content, "assert_transaction_runtime_guard_file")
    require_fragments(
        file_check,
        [
            '"$(stat -c \'%u:%g:%a\' -- "$TRANSACTION_RUNTIME_GUARD")" == "0:0:644"',
            'assert_no_extended_acl "$TRANSACTION_RUNTIME_GUARD"',
            "printf '[Service]\\nRestart=no\\nRuntimeMaxSec=300s\\n'",
        ],
        f"{label}-runtime-guard-file-identity",
    )

    loaded = shell_function_body(content, "assert_transaction_runtime_guard_loaded")
    require_in_order(
        loaded,
        [
            "assert_transaction_runtime_guard_file",
            "--property=Restart --value",
            '== "no"',
            "--property=RuntimeMaxUSec --value",
            '== "5min"',
            "--property=NeedDaemonReload --value",
            "--property=DropInPaths --value",
            "assert_dropin_paths_exact",
        ],
        f"{label}-runtime-guard-loaded-readback",
    )

    installed = shell_function_body(content, "install_transaction_runtime_guard")
    require_in_order(
        installed,
        [
            '[[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]]',
            "os.O_EXCL",
            "os.fchmod(descriptor, 0o644)",
            "os.fchown(descriptor, 0, 0)",
            "os.fsync(handle.fileno())",
            "if os.path.lexists(final):",
            "os.rename(temporary, final)",
            "os.fsync(directory_fd)",
            "assert_transaction_runtime_guard_file",
            "systemctl daemon-reload",
            "assert_transaction_runtime_guard_loaded",
        ],
        f"{label}-runtime-guard-exclusive-install",
    )

    removed = shell_function_body(content, "remove_transaction_runtime_guard")
    require_in_order(
        removed,
        [
            "assert_transaction_runtime_guard_file",
            "rm " + '-f -- "$TRANSACTION_RUNTIME_GUARD"',
            '[[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]]',
            'fsync_directory "$TRANSACTION_RUNTIME_GUARD_DIR"',
            "systemctl daemon-reload",
            "--property=Restart --value",
            '== "on-failure"',
            "--property=RuntimeMaxUSec --value",
            '== "infinity"',
            "--property=NeedDaemonReload --value",
            "--property=DropInPaths --value",
            "assert_dropin_paths_exact",
        ],
        f"{label}-runtime-guard-removal-readback",
    )

    transition = shell_function_body(content, "transition_transaction_status")
    require_fragments(
        transition,
        [
            'type(record.get("schema_version")) is not int',
            'record.get("schema_version") != 3',
            'record.get("status") != expected',
            'record["status"] = new',
            "os.O_EXCL",
            "os.rename(temporary, marker)",
            "os.fsync(directory_fd)",
            '== "$new_status"',
        ],
        f"{label}-schema3-phase-transition",
    )


def assert_guard_and_commit_order(content: str, label: str, contract: dict[str, str]) -> None:
    guard = contract["guard"]
    active = contract["active"]
    record_temp = contract["record_temp"]
    record = contract["record"]
    archive = contract["archive"]
    runtime_guard_install = contract["runtime_guard_install"]
    runtime_guard_remove = contract["runtime_guard_remove"]
    phase_transition = contract["phase_transition"]
    publication = contract["publication"]

    guard_install = f"trap {guard} EXIT"
    main = content_after(content, guard_install, f"{label}-guard-install")
    active_true = f'{active}="true"'
    active_position = content.find(active_true)
    disable_position = content.find('systemctl disable "$SERVICE"', content.find(guard_install))
    if active_position < 0 or disable_position < 0 or active_position > disable_position:
        raise AssertionError(f"{label}: exit guard is not active before the first switch action")
    require_in_order(
        main,
        [
            guard_install,
            'systemctl disable "$SERVICE"',
            runtime_guard_install,
            "stop_service_and_verify",
            f'fsync_file "${record_temp}"',
            phase_transition,
            runtime_guard_remove,
            'systemctl --no-block start "$SERVICE"',
            'systemctl enable "$SERVICE"',
            "assert_standard_enabled_topology",
            'fsync_systemd_enablement_state',
            "assert_standard_enabled_topology",
            'systemctl is-active --quiet "$SERVICE"',
            'process_exec_argv',
            'process_working_directory',
            publication,
            f'mv -T -- "$TRANSACTION_FILE" "${archive}"',
            f'{active}="false"',
            f'fsync_file "${archive}"',
            'fsync_directory "$DEPLOYMENT_DIR"',
            'fsync_directory "$APP_ROOT"',
            'trap - EXIT INT TERM HUP',
        ],
        f"{label}-pending-activation-enable-archive-publication-order",
    )

    phase_position = main.find(phase_transition)
    enable_position = main.find('systemctl enable "$SERVICE"', phase_position)
    archive_fragment = f'mv -T -- "$TRANSACTION_FILE" "${archive}"'
    publication_position = main.find(publication, enable_position)
    archive_position = main.find(archive_fragment, publication_position)
    if (
        phase_position < 0
        or enable_position < 0
        or publication_position < 0
        or archive_position < 0
    ):
        raise AssertionError(f"{label}: pending-activation state machine is incomplete")
    precommit = main[:phase_position]
    if 'systemctl enable "$SERVICE"' in precommit:
        raise AssertionError(f"{label}: precommit marker path must never enable the service")
    marker_retention_window = main[phase_position:publication_position]
    if archive_fragment in marker_retention_window or f'{active}="false"' in marker_retention_window:
        raise AssertionError(
            f"{label}: active marker/exit guard was cleared before passed evidence publication"
        )

    post_enable = main[main.find('systemctl enable "$SERVICE"') :]
    post_enable_publication = post_enable.find(publication)
    if post_enable_publication < 0:
        raise AssertionError(f"{label}: passed evidence was not published after enablement")
    require_fragments(
        post_enable[:post_enable_publication],
        [
            "assert_standard_enabled_topology",
            "fsync_systemd_enablement_state",
            'systemctl is-active --quiet "$SERVICE"',
            '--property=MainPID --value',
            "--property=Restart --value",
            "--property=RuntimeMaxUSec --value",
            "--property=ExecStart --value",
            "--property=WorkingDirectory --value",
            "--property=DropInPaths --value",
            "process_exec_argv",
            "process_working_directory",
        ],
        f"{label}-pre-publication-real-state-readback",
    )
    publication_to_archive = main[publication_position:archive_position]
    if f'{active}="false"' in publication_to_archive:
        raise AssertionError(
            f"{label}: active marker was cleared between evidence publication and archival"
        )
    guard_body = simple_shell_function_body(content, guard)
    if f'[[ "${active}" == "true" ]]' not in guard_body:
        raise AssertionError(f"{label}: exit guard is not gated by the live transaction flag")


def extract_recovery_marker_parser(recovery: str) -> str:
    anchor = "mapfile -d '' -t TX_FIELDS"
    start = recovery.find(anchor)
    if start < 0:
        raise AssertionError("recovery marker parser invocation is missing")
    opener = recovery.find("<<'PY'\n", start)
    if opener < 0:
        raise AssertionError("recovery marker parser heredoc opener is missing")
    code_start = opener + len("<<'PY'\n")
    code_end = recovery.find("\nPY\n)", code_start)
    if code_end < 0:
        raise AssertionError("recovery marker parser heredoc closer is missing")
    return recovery[code_start:code_end]


def database_backup_fixture() -> dict[str, object]:
    return {
        "basename": "security-20260728.sqlite3",
        "sha256": "a" * 64,
        "size_bytes": 4096,
        "integrity_check": "ok",
        "page_count": 1,
        "page_size": 4096,
        "user_version": 0,
        "schema_version": 1,
        "application_id": 0,
        "schema_sha256": "b" * 64,
    }


def marker_fixture(managed_dropin: str) -> dict[str, object]:
    return {
        "schema_version": 3,
        "status": "switching",
        "release_id": "v0.1.1",
        "previous_release_id": "v0.1.0",
        "previous_target": "/srv/apps/protocol-studio/releases/v0.1.0",
        "fragment_path": "/etc/systemd/system/protocol-studio.service",
        "fragment_sha256": "c" * 64,
        "dropin_paths_before": [managed_dropin],
        "managed_dropin_sha256_before": "d" * 64,
        "fragment_backup": "protocol-studio.service.20260728",
        "managed_dropin_backup": "90-release-runtime.conf.20260728",
        "previous_exec_path": "/srv/apps/protocol-studio/current/.venv/bin/python",
        "previous_exec_argv": "/srv/apps/protocol-studio/current/.venv/bin/python -m uvicorn",
        "previous_working_directory": "/srv/apps/protocol-studio/current",
        "previous_service_user": "protocol-studio",
        "previous_service_group": "protocol-studio",
        "previous_environment_files": "/etc/protocol-studio/protocol-studio.env",
        "previous_read_write_paths": "/srv/apps/protocol-studio/shared",
        "previous_umask": "0077",
        "environment_file_sha256": "e" * 64,
        "public_origin": "https://protocol.feian.online",
        "public_host": "protocol.feian.online",
        "database_backup": database_backup_fixture(),
        "prepared_release_durable": True,
        "service_enabled_before_switch": True,
        "known_good_health_before_switch": True,
        "started_at": "2026-07-28T12:00:00Z",
    }


def run_marker_parser(
    parser: str,
    marker: dict[str, object],
    managed_dropin: str,
    root: Path,
    case_name: str,
) -> subprocess.CompletedProcess[bytes]:
    marker_path = root / f"{case_name}.json"
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", parser, os.fspath(marker_path), managed_dropin],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )


def assert_recovery_marker_types(recovery: str) -> tuple[int, int, int]:
    parser = extract_recovery_marker_parser(recovery)
    compile(parser, "recover-transaction.sh:marker-parser", "exec")
    if "from urllib.parse import urlsplit" not in parser:
        raise AssertionError("recovery marker parser does not import its origin parser")
    transition = shell_function_body(recovery, "transition_transaction_status")
    require_in_order(
        transition,
        [
            'local recovery_activation_id="${3:-}"',
            'local recovery_activation_mode="${4:-}"',
            'if new == "recovery_committed_pending_activation":',
            'record["recovery_activation_release_id"] = activation_id',
            'record["recovery_activation_runtime_mode"] = activation_mode',
        ],
        "recovery-transition-persists-activation-direction",
    )
    require_fragments(
        recovery,
        [
            'switching|rolling_back)',
            'ACTIVATION_ID="$MARKER_PREVIOUS_ID"',
            'ACTIVATION_MODE="$MARKER_PREVIOUS_RUNTIME_MODE"',
            'recovery_committed_pending_activation)',
            '"$TX_TARGET_ID" == "$MARKER_PREVIOUS_ID"',
            'deploy_committed_pending_activation)',
            'ACTIVATION_ID="$TX_TARGET_ID"',
            'rollback_committed_pending_activation)',
            'transition_transaction_status "$TX_STATUS" "recovery_committed_pending_activation"',
            '"$ACTIVATION_ID" "$ACTIVATION_MODE"',
        ],
        "recovery-directional-reentry-selection",
    )
    managed = "/etc/systemd/system/protocol-studio.service.d/90-release-runtime.conf"
    valid_marker = marker_fixture(managed)

    with tempfile.TemporaryDirectory(prefix="recovery-marker-contract-") as temporary:
        root = Path(temporary)
        valid_cases: dict[str, tuple[dict[str, object], tuple[str, str, str]]] = {}
        valid_cases["switching"] = (
            copy.deepcopy(valid_marker),
            ("deploy", "v0.1.1", "release"),
        )
        deploy_pending = copy.deepcopy(valid_marker)
        deploy_pending["status"] = "deploy_committed_pending_activation"
        valid_cases["deploy_pending"] = (
            deploy_pending,
            ("deploy", "v0.1.1", "release"),
        )
        rollback = copy.deepcopy(valid_marker)
        rollback["status"] = "rolling_back"
        rollback.pop("release_id")
        rollback["target_release_id"] = "v0.0.9"
        rollback["target_runtime_mode"] = "release"
        valid_cases["rolling_back"] = (
            rollback,
            ("rollback", "v0.0.9", "release"),
        )
        rollback_pending = copy.deepcopy(rollback)
        rollback_pending["status"] = "rollback_committed_pending_activation"
        valid_cases["rollback_pending"] = (
            rollback_pending,
            ("rollback", "v0.0.9", "release"),
        )
        recovery_deploy = copy.deepcopy(valid_marker)
        recovery_deploy["status"] = "recovery_committed_pending_activation"
        recovery_deploy["recovery_activation_release_id"] = "v0.1.0"
        recovery_deploy["recovery_activation_runtime_mode"] = "release"
        valid_cases["recovery_pending_from_deploy"] = (
            recovery_deploy,
            ("deploy", "v0.1.0", "release"),
        )
        recovery_rollback = copy.deepcopy(rollback)
        recovery_rollback["status"] = "recovery_committed_pending_activation"
        recovery_rollback["recovery_activation_release_id"] = "v0.1.0"
        recovery_rollback["recovery_activation_runtime_mode"] = "release"
        valid_cases["recovery_pending_from_rollback"] = (
            recovery_rollback,
            ("rollback", "v0.1.0", "release"),
        )

        directional_reentry_cases = {
            "deploy_pending",
            "rollback_pending",
            "recovery_pending_from_deploy",
        }
        reentry_count = 0
        for case_name, (marker, expected_activation) in valid_cases.items():
            valid = run_marker_parser(parser, marker, managed, root, case_name)
            if valid.returncode != 0 or valid.stderr:
                raise AssertionError(
                    f"valid recovery marker was rejected ({case_name}): "
                    f"exit={valid.returncode} "
                    f"stderr={valid.stderr.decode('utf-8', 'replace')!r}"
                )
            fields = valid.stdout.split(b"\0")
            if not fields or fields[-1] != b"":
                raise AssertionError("recovery marker parser output is not NUL terminated")
            fields = fields[:-1]
            if len(fields) != 26:
                raise AssertionError(
                    f"recovery marker parser emitted {len(fields)} fields, expected 26"
                )
            backup = marker["database_backup"]
            if not isinstance(backup, dict):
                raise AssertionError("test fixture database_backup shape changed")
            if fields[18].decode("utf-8") != marker["public_origin"]:
                raise AssertionError("recovery marker field 18 changed public origin")
            if fields[19].decode("utf-8") != marker["public_host"]:
                raise AssertionError("recovery marker field 19 changed public host")
            if fields[20].decode("utf-8") != backup["basename"]:
                raise AssertionError(
                    "recovery marker field 20 is not the database backup basename"
                )
            parsed_backup = json.loads(fields[21].decode("utf-8"))
            if parsed_backup != backup:
                raise AssertionError(
                    "recovery marker field 21 changed database backup metadata"
                )
            activation = tuple(field.decode("utf-8") for field in fields[22:25])
            if activation != expected_activation:
                raise AssertionError(
                    f"{case_name}: activation fields changed: {activation!r}"
                )
            if fields[25].decode("utf-8") != marker["started_at"]:
                raise AssertionError(
                    f"{case_name}: deterministic evidence timestamp changed"
                )
            if case_name in directional_reentry_cases:
                retry = run_marker_parser(
                    parser, marker, managed, root, f"{case_name}-reentry"
                )
                if (
                    retry.returncode != 0
                    or retry.stderr
                    or retry.stdout != valid.stdout
                ):
                    raise AssertionError(
                        f"{case_name}: interrupted recovery retry changed activation direction"
                    )
                reentry_count += 1

        invalid_cases: dict[str, dict[str, object]] = {}
        schema_bool = copy.deepcopy(valid_marker)
        schema_bool["schema_version"] = True
        invalid_cases["marker_schema_boolean"] = schema_bool
        schema_float = copy.deepcopy(valid_marker)
        schema_float["schema_version"] = 3.0
        invalid_cases["marker_schema_float"] = schema_float
        legacy_schema = copy.deepcopy(valid_marker)
        legacy_schema["schema_version"] = 2
        invalid_cases["legacy_active_marker_schema_2"] = legacy_schema
        wrong_origin = copy.deepcopy(valid_marker)
        wrong_origin["public_origin"] = "https://other.example"
        invalid_cases["public_origin_host_mismatch"] = wrong_origin
        trailing_origin = copy.deepcopy(valid_marker)
        trailing_origin["public_origin"] = "https://protocol.feian.online/"
        invalid_cases["public_origin_not_canonical"] = trailing_origin
        uppercase_host = copy.deepcopy(valid_marker)
        uppercase_host["public_host"] = "Protocol.Feian.Online"
        invalid_cases["public_host_not_canonical"] = uppercase_host
        generic_wrong_target = copy.deepcopy(recovery_deploy)
        generic_wrong_target["recovery_activation_release_id"] = "v0.1.1"
        invalid_cases["generic_recovery_direction_drift"] = generic_wrong_target
        generic_missing_identity = copy.deepcopy(recovery_deploy)
        generic_missing_identity.pop("recovery_activation_release_id")
        invalid_cases["generic_recovery_identity_missing"] = generic_missing_identity
        for key in (
            "prepared_release_durable",
            "service_enabled_before_switch",
            "known_good_health_before_switch",
        ):
            mutated = copy.deepcopy(valid_marker)
            mutated[key] = 1
            invalid_cases[f"boolean_gate_number_{key}"] = mutated
        for key in (
            "size_bytes",
            "page_count",
            "page_size",
            "user_version",
            "schema_version",
            "application_id",
        ):
            mutated = copy.deepcopy(valid_marker)
            backup = mutated["database_backup"]
            if not isinstance(backup, dict):
                raise AssertionError("test fixture database_backup shape changed")
            backup[key] = True
            invalid_cases[f"database_integer_boolean_{key}"] = mutated
            float_mutated = copy.deepcopy(valid_marker)
            float_backup = float_mutated["database_backup"]
            if not isinstance(float_backup, dict):
                raise AssertionError("test fixture database_backup shape changed")
            float_backup[key] = float(float_backup[key])
            invalid_cases[f"database_integer_float_{key}"] = float_mutated

        for case_name, marker in invalid_cases.items():
            rejected = run_marker_parser(parser, marker, managed, root, case_name)
            if rejected.returncode == 0:
                raise AssertionError(f"recovery marker parser accepted invalid case: {case_name}")
            if rejected.stdout:
                raise AssertionError(
                    f"rejected recovery marker leaked partial fields: {case_name}"
                )
        if reentry_count != 3:
            raise AssertionError(
                f"directional recovery reentry cases changed: {reentry_count}"
            )
        return len(invalid_cases), len(valid_cases), reentry_count


def assert_recovery_guard_reports_actual_state(recovery: str) -> None:
    body = simple_shell_function_body(recovery, "recovery_exit_guard")
    for forbidden in (
        "service left disabled/stopped",
        "service remains disabled/stopped",
    ):
        if forbidden in body:
            raise AssertionError(
                "recovery exit guard unconditionally claims a disabled/stopped state"
            )
    positions = require_in_order(
        body,
        [
            'systemctl disable "$SERVICE"',
            '( trap - EXIT; stop_service_and_verify )',
            "probe_service_enablement",
            "--property=ActiveState --value",
            "--property=SubState --value",
            "--property=MainPID --value",
            'if [[ "$fail_closed" == "true" ]]',
            "FAIL-CLOSED CONFIRMED:",
            "else",
            "CRITICAL: FAIL-CLOSED NOT CONFIRMED",
        ],
        "recovery-exit-guard-actual-state-readback",
    )
    state_readback = body[positions[2] : positions[6]]
    require_fragments(
        state_readback,
        [
            '"$SERVICE_ENABLE_STDOUT" == "disabled"',
            '"$SERVICE_ENABLE_EXIT" == "1"',
            '"$active_state" == "inactive"',
            '"$sub_state" == "dead"',
            '"$main_pid" == "0"',
            '"$process_gone" == "true"',
            '"$marker_retained" == "true"',
            "assert_service_persistently_disabled",
        ],
        "recovery-exit-guard-confirmation-gates",
    )
    if re.search(r'(?m)^\s*(?:rm|mv)\b[^\n]*"?\$TRANSACTION_FILE\b', body):
        raise AssertionError("recovery exit guard must retain the transaction marker")


def assert_active_marker_gates_normal_entry(content: str, label: str) -> None:
    guard = '[[ ! -e "$TRANSACTION_FILE" && ! -L "$TRANSACTION_FILE" ]]'
    guard_position = content.find(guard)
    if guard_position < 0:
        raise AssertionError(f"{label}: normal entry does not reject an active marker")
    if label == "deploy-release.sh":
        consumer_position = content.find('DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/', guard_position)
    else:
        consumer_position = content.find("validate_passed_release_record ", guard_position)
    if consumer_position < 0 or guard_position > consumer_position:
        raise AssertionError(
            f"{label}: passed evidence may be consumed before the active-marker gate"
        )


def first_python_heredoc_after(content: str, anchor: str, label: str) -> str:
    anchor_position = content.find(anchor)
    if anchor_position < 0:
        raise AssertionError(f"{label}: parser anchor is missing")
    opener = content.find("<<'PY'\n", anchor_position)
    if opener < 0:
        raise AssertionError(f"{label}: parser heredoc opener is missing")
    start = opener + len("<<'PY'\n")
    end = content.find("\nPY\n", start)
    if end < 0:
        raise AssertionError(f"{label}: parser heredoc terminator is missing")
    return content[start:end]


def valid_schema5_deployment_record(
    release_id: str,
    baseline_path: str,
    exec_start_pre_argvs: list[str],
) -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": 5,
        "status": "passed",
        "release_id": release_id,
        "version": "0.1.1",
        "previous_release_id": "previous-release",
        "archive_sha256": digest,
        "release_manifest_sha256": digest,
        "deployed_at": "2026-07-29T00:00:00Z",
        "systemd": {
            "fragment_sha256_before": digest,
            "dropin_paths_before": [],
            "managed_dropin_sha256_before": None,
            "managed_dropin_sha256_after": digest,
            "fragment_backup": "protocol-studio.service-before-v011",
            "managed_dropin_backup": None,
            "runtime_mode": "release-local-venv-dropin",
            "environment_file_sha256": digest,
            "exec_start_pre_argvs": exec_start_pre_argvs,
        },
        "public_origin": "https://protocol.feian.online",
        "public_host": "protocol.feian.online",
        "runtime_fingerprint": {
            "schema_version": 2,
            "release_root_sha256": digest,
        },
        "database_backup": {
            "basename": "security-v011.sqlite3",
            "sha256": digest,
            "size_bytes": 4096,
            "integrity_check": "ok",
            "page_count": 1,
            "page_size": 4096,
            "user_version": 0,
            "schema_version": 0,
            "application_id": 0,
            "schema_sha256": digest,
        },
        "runtime_baseline_path": baseline_path,
        "runtime_baseline_sha256": digest,
        "runtime_fingerprint_sha256": digest,
        "runtime_guard_helper_sha256": digest,
        "checks": {
            "archive_manifest": True,
            "prepared_release_durable": True,
            "release_permissions_normalized": True,
            "release_tree_immutable": True,
            "service_user_import": True,
            "isolated_service_user_preflight": True,
            "security_database_backup": True,
            "known_good_health_before_switch": True,
            "service_disabled_during_switch": True,
            "service_stopped_before_switch": True,
            "atomic_symlink": True,
            "managed_systemd_dropin": True,
            "effective_runtime": True,
            "running_process_runtime": True,
            "systemd_active": True,
            "local_health": True,
            "public_health": True,
            "public_login_redirect": True,
            "production_environment_validated_three_phases": True,
            "final_publication_configuration_gate": True,
            "ordinary_restart_environment_gate": True,
            "ordinary_restart_integrity_gate": True,
            "service_enabled_after_health": True,
        },
    }


def run_passed_record_parser(
    source: str,
    payload: bytes,
    case_root: Path,
    *,
    release_id: str,
    baseline_path: str,
    managed_dropin: str,
    exec_start_pre_argvs: list[str],
) -> subprocess.CompletedProcess[str]:
    record = case_root / "record.json"
    record.write_bytes(payload)
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            os.fspath(record),
            release_id,
            "https://protocol.feian.online",
            "protocol.feian.online",
            json.dumps(exec_start_pre_argvs, separators=(",", ":")),
            baseline_path,
            managed_dropin,
        ],
        cwd=REPO_ROOT,
        input=source,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def assert_historical_activation_boundary(
    bash: str,
    contents: dict[str, str],
) -> dict[str, int]:
    deploy = contents[DEPLOY_SCRIPT.name]
    legacy_definition = (
        'LEGACY_RELEASE_ID="${PROTOCOL_STUDIO_LEGACY_RELEASE_ID:-'
        '20260722-114300-620b1bcf9aa9}"'
    )
    if deploy.count(legacy_definition) != 1:
        raise AssertionError("deploy legacy release id must have one canonical definition")

    early_audit_source = shell_function_source(
        deploy, "audit_current_activation_schema"
    )
    early_parser_source = first_python_heredoc_after(
        early_audit_source,
        "audit_current_activation_schema()",
        "deploy-early-activation-schema-audit",
    )
    require_fragments(
        early_audit_source,
        [
            '[[ -L "$CURRENT_LINK" ]]',
            'current_target="$(readlink -f -- "$CURRENT_LINK")"',
            '"$RELEASES_DIR"/*)',
            'if [[ "$current_id" == "$LEGACY_RELEASE_ID" ]]; then',
            '[[ ! -e "$current_target/.venv" && ! -L "$current_target/.venv" ]]',
            'record="$DEPLOYMENT_DIR/$current_id.json"',
            'assert_trusted_record_file "$record"',
            "object_pairs_hook=strict_object",
            "parse_constant=",
            "type(schema) is not int",
            "schema not in {2, 3, 4, 5}",
            'require_activatable_passed_record_schema "$schema"',
        ],
        "deploy-early-activation-schema-audit",
    )
    forbidden_early_mutations = [
        fragment
        for fragment in (
            "systemctl ",
            "systemd-run ",
            "install ",
            "mv ",
            "rm ",
            "sqlite_backup.py",
            "install_runtime_guard_helper",
            "create_runtime_baseline",
        )
        if fragment in early_audit_source
    ]
    if forbidden_early_mutations:
        raise AssertionError(
            "deploy early activation audit contains mutation-capable operations: "
            f"{forbidden_early_mutations}"
        )

    entry_match = re.search(
        r'(?m)^if \[\[ "\$MODE" == "switch" \]\]; then\n'
        r'  audit_current_activation_schema\nfi$',
        deploy,
    )
    if entry_match is None:
        raise AssertionError("deploy switch-only early activation audit is missing")
    entry_block = entry_match.group(0)
    side_effect_anchors = [
        "verify_atomic_rename_boundary \\",
        'TRUSTED_ARCHIVE="$CONTROL_DIR/.archive-$RELEASE_ID-$$.tar.gz"',
        'PREFLIGHT_ROOT="$APP_ROOT/.preflight-$RELEASE_ID-$$"',
        'backup --source "$SECURITY_DB" --destination "$PREFLIGHT_DB"',
        'systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT"',
        'DROPIN_CANDIDATE="$LOG_DIR/.runtime-dropin-$RELEASE_ID-$$"',
        'UNIT_BACKUP="$BACKUP_DIR/$SERVICE-$BACKUP_STAMP-before-$RELEASE_ID"',
        'DROPIN_BACKUP="$BACKUP_DIR/$SERVICE-runtime-$BACKUP_STAMP-before-$RELEASE_ID.conf"',
        "install_runtime_guard_helper \\",
        "create_runtime_baseline \\",
        'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
        'systemctl disable "$SERVICE"',
    ]
    require_in_order(
        deploy[entry_match.start() :],
        [entry_block, *side_effect_anchors],
        "deploy-historical-current-rejected-before-all-activation-side-effects",
    )

    gate_sources: dict[str, str] = {}
    parser_sources: dict[str, str] = {}
    anchors = {
        DEPLOY_SCRIPT.name: "mapfile -t PREVIOUS_RECORD_FIELDS",
        ROLLBACK_SCRIPT.name: "validate_passed_release_record()",
        RECOVERY_SCRIPT.name: "validate_passed_release_record()",
    }
    for label, content in contents.items():
        gate_sources[label] = shell_function_source(
            content, "require_activatable_passed_record_schema"
        )
        parser_sources[label] = first_python_heredoc_after(
            content, anchors[label], label
        )
        require_fragments(
            parser_sources[label],
            [
                "type(schema) is not int",
                "schema not in {2, 3, 4, 5}",
                "if schema != 5:",
                "set(record) != expected_keys",
                'record.get("runtime_baseline_path") != sys.argv[6]',
                'systemd.get("exec_start_pre_argvs") != json.loads(sys.argv[5])',
                "object_pairs_hook=strict_object",
                "parse_constant=",
            ],
            f"{label}-strict-schema5-parser",
        )

    require_in_order(
        deploy,
        [
            'require_activatable_passed_record_schema "$PREVIOUS_RECORD_SCHEMA"',
            'cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN"',
            'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
            'systemctl disable "$SERVICE"',
        ],
        "deploy-schema4-current-rejected-before-new-dropin-and-systemd",
    )
    rollback_validator = shell_function_source(
        contents[ROLLBACK_SCRIPT.name], "validate_passed_release_record"
    )
    require_in_order(
        rollback_validator,
        [
            'require_activatable_passed_record_schema "${fields[0]}"',
            'sha256sum "$RUNTIME_BASELINE_DIR/$release_id.json"',
            "verify_release_runtime_baseline",
        ],
        "rollback-schema2-through-4-rejected-before-baseline-consumption",
    )
    require_in_order(
        contents[ROLLBACK_SCRIPT.name],
        [
            'validate_passed_release_record "$TARGET_DEPLOYMENT_RECORD"',
            'DATABASE_BACKUP="$BACKUP_DIR/',
            'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
            'systemctl disable "$SERVICE"',
        ],
        "rollback-historical-target-rejected-before-backup-marker-systemd",
    )
    recovery_validator = shell_function_source(
        contents[RECOVERY_SCRIPT.name], "validate_passed_release_record"
    )
    require_in_order(
        recovery_validator,
        [
            'require_activatable_passed_record_schema "$PREVIOUS_RECORD_SCHEMA"',
            'sha256sum "$RUNTIME_BASELINE_DIR/$PREVIOUS_ID.json"',
            "verify_release_runtime_baseline",
        ],
        "recovery-schema2-through-4-rejected-before-baseline-consumption",
    )
    require_in_order(
        contents[RECOVERY_SCRIPT.name],
        [
            'cmp -s "$DROPIN_BACKUP" <(canonical_managed_dropin_content)',
            'systemctl disable "$SERVICE"',
        ],
        "recovery-precommit-single-gate-backup-rejected-before-systemd",
    )

    gate_cases = 0
    parser_cases = 0
    early_parser_cases = 0
    early_historical_rejections = 0
    with tempfile.TemporaryDirectory(prefix="historical-activation-boundary-") as temporary:
        root = Path(temporary)
        gate_scripts: dict[str, Path] = {}
        for label, gate_source in gate_sources.items():
            gate_script = root / f"{label}.gate.sh"
            gate_script.write_text(
                "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
                "fail() { printf '%s\\n' \"$*\" >&2; return 97; }\n"
                + gate_source
                + "\nrequire_activatable_passed_record_schema \"$1\"\n",
                encoding="utf-8",
            )
            gate_scripts[label] = gate_script
            for schema in ("2", "3", "4", "5", "5.0", "true", "5-string", "null"):
                completed = subprocess.run(
                    [bash, os.fspath(gate_script), schema],
                    cwd=REPO_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                expected_success = schema == "5"
                if (completed.returncode == 0) != expected_success:
                    raise AssertionError(
                        f"{label}: schema gate decision drifted for {schema!r}: "
                        f"exit={completed.returncode} stderr={completed.stderr!r}"
                    )
                gate_cases += 1

        early_root = root / "deploy-early-parser"
        early_root.mkdir()

        def probe_early(payload: bytes) -> subprocess.CompletedProcess[str]:
            nonlocal early_parser_cases
            early_parser_cases += 1
            record = early_root / "record.json"
            record.write_bytes(payload)
            return subprocess.run(
                [sys.executable, "-I", "-", os.fspath(record)],
                cwd=REPO_ROOT,
                input=early_parser_source,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        deploy_gate_script = gate_scripts[DEPLOY_SCRIPT.name]
        for schema in (2, 3, 4, 5):
            parsed = probe_early(
                (json.dumps({"schema_version": schema}, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            if parsed.returncode != 0 or parsed.stdout.splitlines() != [str(schema)]:
                raise AssertionError(
                    f"deploy early parser did not identify strict schema {schema}: "
                    f"exit={parsed.returncode} stderr={parsed.stderr!r}"
                )
            gated = subprocess.run(
                [bash, os.fspath(deploy_gate_script), parsed.stdout.strip()],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if schema == 5:
                if gated.returncode != 0:
                    raise AssertionError("deploy early schema 5 parser output was not activatable")
            else:
                if gated.returncode == 0 or "audit-only" not in gated.stderr:
                    raise AssertionError(
                        f"deploy early historical schema {schema} did not fail closed"
                    )
                early_historical_rejections += 1

        for value in (5.0, True, "5", None):
            result = probe_early(
                (json.dumps({"schema_version": value}, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            if result.returncode == 0 or result.stdout:
                raise AssertionError(
                    f"deploy early parser accepted invalid schema type: {value!r}"
                )
        for payload in (
            b'{"schema_version":5,"schema_version":5}\n',
            b'{"schema_version":NaN}\n',
        ):
            result = probe_early(payload)
            if result.returncode == 0 or result.stdout:
                raise AssertionError(
                    "deploy early parser accepted duplicate-key or non-finite JSON"
                )

        release_id = "v0.1.1"
        baseline_path = f"/srv/apps/protocol-studio/runtime-guard/baselines/{release_id}.json"
        managed_dropin = "/etc/systemd/system/protocol-studio.service.d/90-release-runtime.conf"
        pre_argvs = ["runtime-guard", "environment-validator"]
        valid = valid_schema5_deployment_record(release_id, baseline_path, pre_argvs)
        for label, parser_source in parser_sources.items():
            case_root = root / label
            case_root.mkdir()

            def probe(payload: bytes) -> subprocess.CompletedProcess[str]:
                nonlocal parser_cases
                parser_cases += 1
                return run_passed_record_parser(
                    parser_source,
                    payload,
                    case_root,
                    release_id=release_id,
                    baseline_path=baseline_path,
                    managed_dropin=managed_dropin,
                    exec_start_pre_argvs=pre_argvs,
                )

            valid_result = probe(
                (json.dumps(valid, separators=(",", ":")) + "\n").encode("utf-8")
            )
            if valid_result.returncode != 0 or valid_result.stdout.splitlines()[:1] != ["5"]:
                raise AssertionError(
                    f"{label}: strict schema 5 fixture was rejected: "
                    f"exit={valid_result.returncode} stderr={valid_result.stderr!r}"
                )
            if len(valid_result.stdout.splitlines()) != 8:
                raise AssertionError(f"{label}: schema 5 parser field count drifted")

            for historical_schema in (2, 3, 4):
                historical = {
                    "schema_version": historical_schema,
                    "systemd": {
                        "runtime_mode": "release-local-venv-dropin",
                        "exec_start_pre_argv": "historical-single-environment-gate",
                    },
                }
                result = probe(
                    (json.dumps(historical, separators=(",", ":")) + "\n").encode("utf-8")
                )
                if result.returncode != 0 or result.stdout.splitlines() != [str(historical_schema)]:
                    raise AssertionError(
                        f"{label}: historical schema {historical_schema} was not audit-identified"
                    )

            invalid_schema_values: tuple[object, ...] = (5.0, True, "5", None)
            for value in invalid_schema_values:
                result = probe(
                    (json.dumps({"schema_version": value}, separators=(",", ":")) + "\n").encode("utf-8")
                )
                if result.returncode == 0 or result.stdout:
                    raise AssertionError(f"{label}: invalid schema type was accepted: {value!r}")

            raw_invalid = (
                b'{"schema_version":5,"schema_version":5}\n',
                b'{"schema_version":NaN}\n',
            )
            for payload in raw_invalid:
                result = probe(payload)
                if result.returncode == 0:
                    raise AssertionError(f"{label}: duplicate/non-finite JSON was accepted")

            invalid_records: list[dict[str, object]] = []
            extra = copy.deepcopy(valid)
            extra["unexpected"] = None
            invalid_records.append(extra)
            missing = copy.deepcopy(valid)
            missing.pop("archive_sha256")
            invalid_records.append(missing)
            wrong_archive = copy.deepcopy(valid)
            wrong_archive["archive_sha256"] = "A" * 64
            invalid_records.append(wrong_archive)
            wrong_path = copy.deepcopy(valid)
            wrong_path["runtime_baseline_path"] = baseline_path + ".other"
            invalid_records.append(wrong_path)
            reversed_pre = copy.deepcopy(valid)
            reversed_pre["systemd"]["exec_start_pre_argvs"] = list(reversed(pre_argvs))
            invalid_records.append(reversed_pre)
            float_fingerprint_schema = copy.deepcopy(valid)
            float_fingerprint_schema["runtime_fingerprint"]["schema_version"] = 2.0
            invalid_records.append(float_fingerprint_schema)
            uppercase_helper = copy.deepcopy(valid)
            uppercase_helper["runtime_guard_helper_sha256"] = "A" * 64
            invalid_records.append(uppercase_helper)
            for record in invalid_records:
                result = probe(
                    (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
                )
                if result.returncode == 0 or result.stdout.splitlines() != ["5"]:
                    raise AssertionError(f"{label}: malformed schema 5 record was accepted")

    return {
        "gate_cases": gate_cases,
        "parser_cases": parser_cases,
        "deploy_early_parser_cases": early_parser_cases,
        "deploy_early_historical_rejections": early_historical_rejections,
        "deploy_early_side_effect_anchors": len(side_effect_anchors),
    }


def main() -> int:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash is required for transaction contract tests")
    contents = {path.name: path.read_text(encoding="utf-8") for path in SHELL_SCRIPTS}

    exit_guard_contract = assert_transaction_exit_guard_ownership(bash, contents)
    runtime_schema = assert_runtime_fingerprint_schema()
    publication_sources: dict[str, str] = {}
    enablement_collectors: dict[str, str] = {}
    for label, content in contents.items():
        contract = SCRIPT_CONTRACTS[label]
        require_fragments(
            content,
            [
                'type(record["runtime_fingerprint"].get("schema_version")) is not int',
                'flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL',
            ],
            f"{label}-schema-and-exclusive-temp",
        )
        assert_atomic_probe_only(content, label)
        assert_runtime_systemd_guard_contract(content, label)
        enablement_collectors[label] = assert_enablement_alias_contract(content, label)
        publication_sources[label] = assert_no_overwrite_publication(
            content,
            label,
            contract["record_temp"],
            contract["record"],
        )
        assert_guard_and_commit_order(content, label, contract)
        require_fragments(
            content,
            [
                '"schema_version": 5',
                '"ordinary_restart_integrity_gate"',
                '"exec_start_pre_argvs"',
                "process_environment_matches()",
                'Path(f"/proc/{pid}/environ").read_bytes()',
                "StartLimitIntervalSec=60s",
                "StartLimitBurst=3",
                '"runtime_guard_helper_sha256"',
                'sha256sum "$RUNTIME_GUARD_HELPER"',
            ],
            f"{label}-schema5-ordinary-restart-and-process-environment-contract",
        )

    deploy = contents[DEPLOY_SCRIPT.name]
    require_in_order(
        deploy,
        [
            "install_runtime_guard_helper",
            "create_runtime_baseline",
            'mv -T -- "$CANDIDATE_DIR" "$RELEASE_DIR"',
            "publish_runtime_baseline",
            'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
            "verify_release_runtime_baseline",
            'TRANSACTION_ACTIVE="true"',
            'systemctl disable "$SERVICE"',
        ],
        "deploy-runtime-baseline-durable-before-active-marker-and-systemd",
    )
    require_fragments(
        deploy,
        [
            'RUNTIME_BASELINE_TEMP="$RUNTIME_BASELINE_DIR/.pending-$RELEASE_ID.json"',
            'os.O_WRONLY | os.O_CREAT | os.O_EXCL',
            'ln -T -- "$RUNTIME_BASELINE_TEMP" "$RUNTIME_BASELINE"',
            'fsync_file "$RUNTIME_BASELINE"',
            'fsync_directory "$RUNTIME_BASELINE_DIR"',
            'rm -f -- "$RUNTIME_BASELINE_TEMP"',
            "automatic helper upgrades are intentionally blocked",
            '"runtime_guard_helper_sha256": sys.argv[7]',
            '"$RUNTIME_GUARD_HELPER_SHA256"',
            '"runtime_guard_helper_sha256",',
        ],
        "deploy-exclusive-baseline-publication-and-helper-upgrade-fail-closed",
    )
    if re.search(r'(?m)^\s*rm\s+-[^\n]*\$RUNTIME_BASELINE(?:["\s]|$)', deploy):
        raise AssertionError("published runtime baselines must never be automatically deleted")
    for label in (ROLLBACK_SCRIPT.name, RECOVERY_SCRIPT.name):
        require_fragments(
            contents[label],
            [
                "verify_release_runtime_baseline()",
                "require_activatable_passed_record_schema()",
                "type(schema) is not int",
                "schema not in {2, 3, 4, 5}",
                "if schema != 5:",
                'record.get("runtime_baseline_path") != sys.argv[6]',
                'systemd.get("exec_start_pre_argvs") != json.loads(sys.argv[5])',
                "runtime_baseline_verification_matches_record()",
            ],
            f"{label}-schema5-activation-and-historical-audit-boundary",
        )

    assert_active_marker_gates_normal_entry(contents[DEPLOY_SCRIPT.name], DEPLOY_SCRIPT.name)
    assert_active_marker_gates_normal_entry(contents[ROLLBACK_SCRIPT.name], ROLLBACK_SCRIPT.name)

    with tempfile.TemporaryDirectory(prefix="passed-record-publication-") as temporary:
        root = Path(temporary)
        for index, (label, source) in enumerate(publication_sources.items(), start=1):
            case_root = root / f"{index}-{label}"
            case_root.mkdir()
            run_publication_harness(bash, source, case_root)

    recovery = contents[RECOVERY_SCRIPT.name]
    historical_activation = assert_historical_activation_boundary(bash, contents)
    publish_source, reconcile_source = assert_reconcile_durability_contract(recovery)
    with tempfile.TemporaryDirectory(prefix="record-reconciliation-") as temporary:
        reconciliation_cases = run_reconcile_interruption_harness(
            bash,
            publish_source,
            reconcile_source,
            Path(temporary),
        )
    with tempfile.TemporaryDirectory(prefix="enablement-alias-") as temporary:
        alias_cases = 0
        alias_root = Path(temporary)
        for index, (label, collector) in enumerate(enablement_collectors.items(), start=1):
            case_root = alias_root / f"{index}-{label}"
            case_root.mkdir()
            alias_cases += run_enablement_alias_harness(bash, collector, case_root)
    (
        invalid_marker_cases,
        valid_marker_statuses,
        directional_reentry_cases,
    ) = assert_recovery_marker_types(recovery)
    assert_recovery_guard_reports_actual_state(recovery)

    not_proven = ["real systemd behavior", "power-loss atomicity", "production recovery"]
    if not exit_guard_contract["real_signal_injection_executed"]:
        not_proven.insert(
            0,
            "real POSIX guard-active signal delivery (Windows trap-state probe only)",
        )

    report = {
        "status": "passed",
        "suite": "release_transaction_contract",
        "scope": (
            "static shell contracts plus isolated exit-guard, marker, "
            "and publication unit probes"
        ),
        "checks": {
            "transaction_exit_guard_scripts": exit_guard_contract["scripts"],
            "transaction_exit_guard_dynamic_cases": exit_guard_contract["cases"],
            "transaction_exit_guard_baseline_cases": exit_guard_contract[
                "baseline_cases"
            ],
            "transaction_exit_guard_signal_injection_cases": exit_guard_contract[
                "signal_injection_cases"
            ],
            "transaction_exit_guard_guard_entry_signal_cases": exit_guard_contract[
                "guard_entry_signal_cases"
            ],
            "transaction_exit_guard_failure_branch_cases": exit_guard_contract[
                "failure_branch_cases"
            ],
            "transaction_exit_guard_signals": exit_guard_contract["signals"],
            "transaction_exit_guard_signal_delivery_mode": exit_guard_contract[
                "signal_delivery_mode"
            ],
            "transaction_exit_guard_real_signal_injection_executed": (
                exit_guard_contract["real_signal_injection_executed"]
            ),
            "transaction_exit_guard_failure_modes": exit_guard_contract[
                "failure_modes"
            ],
            "transaction_exit_guard_trigger_statuses": exit_guard_contract[
                "trigger_statuses"
            ],
            "transaction_exit_guard_terminal_status": exit_guard_contract[
                "terminal_status"
            ],
            "transaction_exit_guard_marker_retained": exit_guard_contract[
                "marker_retained"
            ],
            "transaction_exit_guard_systemd_fail_closed_state": exit_guard_contract[
                "systemd_fail_closed_state"
            ],
            "transaction_exit_guard_mutually_exclusive_verdict": exit_guard_contract[
                "mutually_exclusive_verdict"
            ],
            "runtime_fingerprint_schema": runtime_schema,
            "runtime_helper_baseline_binding": True,
            "atomic_probe_script_count": len(contents),
            "atomic_replace_call_count": 0,
            "recovery_marker_schema_version": 3,
            "recovery_marker_public_identity_bound": True,
            "recovery_parser_internal_field_count": 26,
            "recovery_parser_valid_status_shapes": valid_marker_statuses,
            "recovery_directional_reentry_cases": directional_reentry_cases,
            "strict_type_negative_cases": invalid_marker_cases,
            "passed_record_no_overwrite_scripts": len(publication_sources),
            "publication_interruption_retry_cases": reconciliation_cases,
            "canonical_enablement_alias_cases": alias_cases,
            "runtime_systemd_guard_install_remove_and_state_readback": True,
            "pending_activation_marker_retained_through_enable": True,
            "passed_record_publication_before_marker_archive": True,
            "normal_entry_rejects_active_marker_before_evidence_consumption": True,
            "recovery_guard_actual_state_reporting": True,
            "passed_evidence_schema_version": 5,
            "runtime_baseline_durable_before_marker": True,
            "published_runtime_baseline_never_auto_deleted": True,
            "historical_passed_evidence_schema_2_through_4_audit_only": True,
            "historical_activation_gate_cases": historical_activation["gate_cases"],
            "strict_passed_record_parser_cases": historical_activation["parser_cases"],
            "deploy_early_activation_parser_cases": historical_activation[
                "deploy_early_parser_cases"
            ],
            "deploy_early_historical_schema_rejections": historical_activation[
                "deploy_early_historical_rejections"
            ],
            "deploy_early_activation_side_effect_anchors": historical_activation[
                "deploy_early_side_effect_anchors"
            ],
            "process_environment_provenance_bound": True,
        },
        "not_proven": not_proven,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
