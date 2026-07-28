from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from _test_support import REPO_ROOT, add_repo_to_import_path, configure_process_runtime

add_repo_to_import_path()
configure_process_runtime("mcgs-dynamic-module")

from mvp_generator.generator import ProtocolGenerator
from mvp_generator.library import TemplateLibrary
from mvp_generator.validator import ConfigError
from protocol_studio.app import normalize_config


SCHEMA_PATH = REPO_ROOT / "resources" / "protocol" / "schemas" / "project-config.schema.json"


def build_config(
    module_sequence: list[dict],
    *,
    variable_numbering_mode: str = "per_output_contiguous",
    copy_b: bool = True,
) -> dict:
    route_a = {
        "start_boxes": {"count": 1, "instance_names": ["S1"]},
        "branch_modules": {
            "module_sequence": module_sequence,
            "module_number_start": 5,
            "output_number_start": 10,
            "branch_device_number_start": 101,
            "variable_numbering_mode": variable_numbering_mode,
        },
    }
    route_b = (
        {"copy_from_A": True}
        if copy_b
        else {
            "start_boxes": {"count": 1, "instance_names": ["S2"]},
            "branch_modules": {
                "module_sequence": module_sequence,
                "module_number_start": 1,
                "output_number_start": 1,
                "branch_device_number_start": 201,
                "variable_numbering_mode": variable_numbering_mode,
            },
        }
    )
    return {
        "workflow_version": "unified_protocol_v1",
        "project": {
            "name": "动态模块拓扑回归",
            "code": "DYNAMIC-MODULE-SEQUENCE",
            "protocol_title": "动环通讯协议",
        },
        "protocol_layout": {
            "measurement_layout_mode": "by_branch",
            "main_base_address": 1000,
            "downstream_base_address": 2000,
            "downstream_primary_outputs_per_route": 38,
            "downstream_extension_base_address": 9500,
        },
        "routes": {"A": route_a, "B": route_b},
        "extensions": {
            "single_cabinet": {"enabled": False, "cabinet_count": 0},
            "repeater": {"enabled": False, "A_count": 0, "B_count": 0},
            "alarm_state_word": {
                "enabled": False,
                "base_address": 9200,
                "word_mode": "16bit",
            },
        },
        "profiles": {},
    }


def generate(config_payload: dict) -> dict:
    library = TemplateLibrary.load()
    config = normalize_config(config_payload, library)
    return ProtocolGenerator(library).generate(config)


def module_branches(module: dict) -> list[dict]:
    return [
        branch
        for board in module["boards"]
        for branch in board["branches"]
    ]


def expect_config_error(callback: Callable[[], object], expected_text: str) -> None:
    try:
        callback()
    except ConfigError as exc:
        assert expected_text in str(exc), str(exc)
    else:
        raise AssertionError(f"预期 ConfigError: {expected_text}")


def test_explicit_mixed_module_sequence() -> None:
    model = generate(
        build_config(
            [
                {"type_code": "3P*1", "layout_pattern": "1", "count": 1},
                {"type_code": "3P*3", "layout_pattern": "2+1", "count": 1},
            ]
        )
    )
    modules = model["routes"][0]["physical_plug_boxes"]
    assert [item["module_no"] for item in modules] == [5, 6]
    assert [item["communication_alarm_slot"] for item in modules] == [5, 6]
    assert [item["module_sequence_source"] for item in modules] == [
        "explicit_module_sequence",
        "explicit_module_sequence",
    ]
    assert [board["board_template_id"] for board in modules[1]["boards"]] == [
        "board_1to6_3phase_dual",
        "board_1to3_3phase",
    ]

    first = module_branches(modules[0])
    second = module_branches(modules[1])
    assert [item["variable_device_code"] for item in first] == ["101"]
    assert [item["variable_device_code"] for item in second] == [
        "102",
        "102_2",
        "103",
    ]
    assert [item["module_local_branch_no"] for item in second] == [1, 2, 3]
    assert [item["output_no"] for item in first + second] == [10, 11, 12, 13]
    assert modules[0]["communication_variable_device_code"] == "101"
    assert modules[1]["communication_variable_device_code"] == "102"
    assert all(
        item["communication_variable_device_code"] == "102"
        and item["module_id"] == "A-M006"
        for item in second
    )


def test_per_board_suffix_numbering() -> None:
    model = generate(
        build_config(
            [{"type_code": "3P*3", "layout_pattern": "2+1", "count": 1}],
            variable_numbering_mode="per_board_suffix",
        )
    )
    module = model["routes"][0]["physical_plug_boxes"][0]
    branches = module_branches(module)
    assert [item["variable_device_code"] for item in branches] == [
        "101",
        "101_2",
        "102",
    ]
    assert module["communication_variable_device_code"] == "101"
    assert all(item["variable_numbering_mode"] == "per_board_suffix" for item in branches)


def test_full_device_library_topology_matrix() -> None:
    """One route may mix modules with 1/2/4 outputs and different board layouts."""
    model = generate(
        build_config(
            [
                {"type_code": "3P*1", "layout_pattern": "1", "count": 1},
                {"type_code": "3P*2", "layout_pattern": "1+1", "count": 1},
                {"type_code": "3P*4", "layout_pattern": "2+1+1", "count": 1},
                {"type_code": "3P*4", "layout_pattern": "1+1+1+1", "count": 1},
            ]
        )
    )
    modules = model["routes"][0]["physical_plug_boxes"]
    assert len(modules) == 4
    assert sum(len(module["boards"]) for module in modules) == 10
    assert [len(module_branches(module)) for module in modules] == [1, 2, 4, 4]
    assert sum(len(module_branches(module)) for module in modules) == 11
    assert [module["module_no"] for module in modules] == [5, 6, 7, 8]
    assert [
        branch["module_no"]
        for module in modules
        for branch in module_branches(module)
    ] == [5, 6, 6, 7, 7, 7, 7, 8, 8, 8, 8]


def test_single_board_dual_output_and_ab_heterogeneous() -> None:
    payload = build_config(
        [{"type_code": "3P*2", "layout_pattern": "2", "count": 1}],
        variable_numbering_mode="per_board_suffix",
        copy_b=False,
    )
    payload["routes"]["B"]["branch_modules"].update(
        {
            "module_sequence": [
                {"type_code": "3P*4", "layout_pattern": "2+2", "count": 1}
            ],
            "variable_numbering_mode": "per_board_suffix",
        }
    )
    model = generate(payload)
    route_a_modules = model["routes"][0]["physical_plug_boxes"]
    route_b_modules = model["routes"][1]["physical_plug_boxes"]
    assert len(route_a_modules) == 1 and len(route_a_modules[0]["boards"]) == 1
    assert [
        branch["variable_device_code"]
        for branch in module_branches(route_a_modules[0])
    ] == ["101", "101_2"]
    assert len(route_b_modules) == 1 and len(route_b_modules[0]["boards"]) == 2
    assert [
        branch["variable_device_code"]
        for branch in module_branches(route_b_modules[0])
    ] == ["201", "201_2", "202", "202_2"]


def test_legacy_scalar_compatibility() -> None:
    payload = build_config([])
    for route, start in (("A", 101), ("B", 201)):
        route_payload = payload["routes"].setdefault(route, {})
        if route == "B":
            route_payload.clear()
            route_payload["copy_from_A"] = True
            continue
        route_payload["branch_modules"] = {
            "module_count": 2,
            "branches_per_module": 2,
            "module_number_start": 1,
            "output_number_start": 1,
            "branch_device_number_start": start,
        }
    model = generate(payload)
    modules = model["routes"][0]["physical_plug_boxes"]
    assert len(modules) == 2
    assert all(item["module_sequence_source"] == "legacy_scalar_two_output" for item in modules)
    assert [
        branch["variable_device_code"]
        for module in modules
        for branch in module_branches(module)
    ] == ["101", "102", "103", "104"]


def test_conflicting_scalar_rejected() -> None:
    payload = build_config(
        [{"type_code": "3P*3", "layout_pattern": "2+1", "count": 1}]
    )
    payload["routes"]["A"]["branch_modules"]["module_count"] = 3
    expect_config_error(lambda: generate(payload), "与旧 module_count=3 冲突")


def test_conflicting_plug_box_sequence_rejected() -> None:
    payload = build_config(
        [{"type_code": "3P*3", "layout_pattern": "2+1", "count": 1}]
    )
    payload["routes"]["A"]["plug_boxes"] = {
        "board_number_start": 101,
        "sequence": [
            {"type_code": "3P*1", "layout_pattern": "1", "count": 1}
        ],
    }
    expect_config_error(
        lambda: generate(payload),
        "module_sequence 与 devices.plug_boxes.A.sequence 不能同时非空",
    )


def test_single_phase_shared_dataset_rejected() -> None:
    payload = build_config(
        [{"type_code": "1P*3", "layout_pattern": "1", "count": 1}]
    )
    expect_config_error(lambda: generate(payload), "共享一个聚合点集")


def test_global_variable_name_collision_rejected() -> None:
    sequence = [{"type_code": "3P*1", "layout_pattern": "1", "count": 1}]
    payload = build_config(sequence, copy_b=False)
    payload["routes"]["B"]["branch_modules"]["branch_device_number_start"] = 101
    expect_config_error(lambda: generate(payload), "变量名重复")


def test_schema_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    contract = schema["$defs"]["branchModules"]
    assert "module_sequence" in contract["properties"]
    assert contract["properties"]["variable_numbering_mode"]["enum"] == [
        "per_output_contiguous",
        "per_board_suffix",
    ]
    assert (
        contract["properties"]["variable_numbering_mode"]["default"]
        == "per_board_suffix"
    )
    assert contract["properties"]["module_sequence"]["items"]["required"] == [
        "type_code",
        "layout_pattern",
        "count",
    ]


def main() -> int:
    test_explicit_mixed_module_sequence()
    test_per_board_suffix_numbering()
    test_full_device_library_topology_matrix()
    test_single_board_dual_output_and_ab_heterogeneous()
    test_legacy_scalar_compatibility()
    test_conflicting_scalar_rejected()
    test_conflicting_plug_box_sequence_rejected()
    test_single_phase_shared_dataset_rejected()
    test_global_variable_name_collision_rejected()
    test_schema_contract()
    print("protocol_studio_dynamic_module_sequence_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
