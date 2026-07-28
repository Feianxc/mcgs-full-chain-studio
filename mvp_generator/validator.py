from __future__ import annotations

from copy import deepcopy
from typing import Any

from .library import TemplateLibrary

LIQUIDCOOL_EXPORT_PROFILE_ID = "classic_combined_liquidcool_default"
LIQUIDCOOL_ADDRESS_PROFILE_ID = "classic_liquidcool_main1000_repeater5000_cabinet7000_alarm6000_32bit"
LIQUIDCOOL_START_BOX_TEMPLATE_ID = "start_box_standard_36row_thd_energy_32bit_state"
LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_standard_30row_full_connector"
LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID = "single_cabinet_liquidcool_ia_pa_ea_ka"
CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID = "classic_combined_two_columns_default"
MEASUREMENT_LAYOUT_MODES = {"by_plug_box", "by_branch"}
VARIABLE_NUMBERING_MODES = {"per_output_contiguous", "per_board_suffix"}
DUAL_DATASET_TEMPLATE_ID = "plug_branch_dual_dataset_47row"
DUAL_OUTPUT_BOARD_TEMPLATE_ID = "board_1to6_3phase_dual"
PORTS_BY_HARDWARE = {
    "horizontal": {"A2B2", "A3B3", "A4B4"},
    "din_rail": {"A1B1", "A2B2", "A3B3"},
}
DEFAULT_ENVIRONMENT_PORT = {
    "horizontal": "A4B4",
    "din_rail": "A3B3",
}
BUS_DATA_MODES_BY_TOPOLOGY = {
    "single_screen_one_column": {"single_column_shared", "single_column_split_ab"},
    "single_screen_two_columns": {"double_column_by_column", "double_column_by_route"},
}


class ConfigError(ValueError):
    pass


def _require_keys(data: dict[str, Any], keys: list[str], prefix: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigError(f"{prefix} 缺少必填字段: {', '.join(missing)}")


def _validate_start_box_configs(
    devices: dict[str, Any],
    *,
    prefix: str,
    scope_label: str,
    unified_workflow: bool,
) -> None:
    start_boxes = devices.get("start_boxes")
    if not isinstance(start_boxes, dict):
        raise ConfigError(f"{prefix}.start_boxes 必须是对象")
    for route in ("A", "B"):
        route_config = start_boxes.get(route)
        if not isinstance(route_config, dict):
            raise ConfigError(f"{prefix}.start_boxes 缺少路由 {route}")
        count = route_config.get("count", 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ConfigError(
                f"{prefix}.start_boxes.{route}.count 必须为 >= 0 的整数"
            )
        if unified_workflow and count > 1:
            raise ConfigError(
                f"统一协议{scope_label}{route}路始端箱数量只能为 0 或 1；"
                "每个列位的每一路只对应一个始端箱"
            )
        instance_names = route_config.get("instance_names", [])
        if not isinstance(instance_names, list) or any(
            not isinstance(item, str) for item in instance_names
        ):
            raise ConfigError(
                f"{prefix}.start_boxes.{route}.instance_names 必须是字符串数组"
            )
        device_code_start = route_config.get("device_code_start")
        if device_code_start is not None and (
            isinstance(device_code_start, bool)
            or not isinstance(device_code_start, int)
            or device_code_start < 1
        ):
            raise ConfigError(
                f"{prefix}.start_boxes.{route}.device_code_start 必须为正整数"
            )


def _require_nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"{path} 必须为 >= 0 的整数")
    return value


def _validate_dual_dataset_layout(
    *,
    branch_template_id: str | None,
    layout_variant: dict[str, Any],
    path: str,
) -> None:
    if branch_template_id != DUAL_DATASET_TEMPLATE_ID:
        return
    board_ids = list(
        layout_variant.get("board_template_sequence")
        or layout_variant.get("board_template_ids")
        or []
    )
    if not board_ids or any(item != DUAL_OUTPUT_BOARD_TEMPLATE_ID for item in board_ids):
        raise ConfigError(
            f"{path}.branch_template_id 的双组电参只能用于全部由一拖六板卡组成的布局；"
            "一拖三板卡只能选择单组参数。"
        )


def _validate_extension_counts(
    devices: dict[str, Any],
    topology_mode: str,
) -> tuple[int, int]:
    repeater_units = devices.get("repeater_units", {})
    if not isinstance(repeater_units, dict):
        raise ConfigError("devices.repeater_units 必须是对象")
    repeater_columns = repeater_units.get("columns")
    repeater_total = 0
    if repeater_columns is not None:
        if not isinstance(repeater_columns, dict):
            raise ConfigError("devices.repeater_units.columns 必须是对象")
        allowed_column_keys = {"column_1", "column_2"}
        unknown_keys = set(repeater_columns) - allowed_column_keys
        if unknown_keys:
            raise ConfigError(
                "devices.repeater_units.columns 包含未知列："
                + ", ".join(sorted(unknown_keys))
            )
        for column_key in sorted(allowed_column_keys):
            column_cfg = repeater_columns.get(column_key, {})
            if not isinstance(column_cfg, dict):
                raise ConfigError(f"devices.repeater_units.columns.{column_key} 必须是对象")
            for route in ("A", "B"):
                repeater_total += _require_nonnegative_int(
                    column_cfg.get(f"{route}_count", 0),
                    f"devices.repeater_units.columns.{column_key}.{route}_count",
                )
        if topology_mode != "single_screen_two_columns":
            column_2 = repeater_columns.get("column_2", {})
            if any(int(column_2.get(f"{route}_count", 0) or 0) > 0 for route in ("A", "B")):
                raise ConfigError("单屏单列不能配置第二列中继数量")
    else:
        for route in ("A", "B"):
            repeater_total += _require_nonnegative_int(
                repeater_units.get(f"{route}_count", 0),
                f"devices.repeater_units.{route}_count",
            )

    cabinet_cfg = devices.get("single_cabinet_aggregation", {})
    if not isinstance(cabinet_cfg, dict):
        raise ConfigError("devices.single_cabinet_aggregation 必须是对象")
    for option_name in ("include_route_data", "include_total_power_energy"):
        option_value = cabinet_cfg.get(option_name, False)
        if not isinstance(option_value, bool):
            raise ConfigError(
                f"devices.single_cabinet_aggregation.{option_name} 必须是 boolean"
            )
    column_counts = cabinet_cfg.get("column_counts")
    if column_counts is not None:
        if not isinstance(column_counts, dict):
            raise ConfigError("devices.single_cabinet_aggregation.column_counts 必须是对象")
        column_1_count = _require_nonnegative_int(
            column_counts.get("column_1", 0),
            "devices.single_cabinet_aggregation.column_counts.column_1",
        )
        column_2_count = _require_nonnegative_int(
            column_counts.get("column_2", 0),
            "devices.single_cabinet_aggregation.column_counts.column_2",
        )
        if topology_mode != "single_screen_two_columns" and column_2_count > 0:
            raise ConfigError("单屏单列不能配置第二列单机柜数量")
        cabinet_total = column_1_count + column_2_count
    else:
        cabinet_total = _require_nonnegative_int(
            cabinet_cfg.get("cabinet_count", 0),
            "devices.single_cabinet_aggregation.cabinet_count",
        )
    return repeater_total, cabinet_total


def validate_config(config: dict[str, Any], library: TemplateLibrary) -> None:
    _require_keys(config, ["project_name", "generation_basis", "topology", "devices", "profiles"], "config")
    if config["generation_basis"] != "max_column":
        raise ConfigError("当前 MVP 仅支持 generation_basis = max_column")
    workflow = config.get("workflow")
    workflow_id = workflow.get("id") if isinstance(workflow, dict) else workflow
    is_unified_workflow = str(
        config.get("workflow_version") or workflow_id or ""
    ).strip() == "unified_protocol_v1"

    topology = config.get("topology", {})
    if not isinstance(topology, dict):
        raise ConfigError("topology 必须是对象")
    topology_mode = str(
        topology.get("screen_topology_mode") or "single_screen_one_column"
    ).strip()
    if topology_mode in BUS_DATA_MODES_BY_TOPOLOGY:
        hardware_form_factor = str(
            topology.get("hardware_form_factor") or "horizontal"
        ).strip()
        if hardware_form_factor not in PORTS_BY_HARDWARE:
            raise ConfigError("topology.hardware_form_factor 仅支持 horizontal / din_rail")
        allowed_ports = PORTS_BY_HARDWARE[hardware_form_factor]
        environment_port_value = topology.get("environment_rs485_port")
        legacy_environment_port_value = topology.get("upload_port_profile")
        environment_port = str(
            environment_port_value
            or legacy_environment_port_value
            or DEFAULT_ENVIRONMENT_PORT[hardware_form_factor]
        ).strip()
        if (
            environment_port_value not in (None, "")
            and legacy_environment_port_value not in (None, "")
            and str(environment_port_value).strip()
            != str(legacy_environment_port_value).strip()
        ):
            raise ConfigError(
                "topology.environment_rs485_port 与兼容字段 "
                "topology.upload_port_profile 不一致"
            )
        if environment_port not in allowed_ports:
            raise ConfigError(
                f"{hardware_form_factor} 设备形态不支持动环上传口 {environment_port or '空值'}"
            )
        default_data_mode = (
            "double_column_by_column"
            if topology_mode == "single_screen_two_columns"
            else "single_column_shared"
        )
        data_mode = str(
            topology.get("bus_data_port_mode") or default_data_mode
        ).strip()
        if data_mode not in BUS_DATA_MODES_BY_TOPOLOGY[topology_mode]:
            raise ConfigError(
                "topology.bus_data_port_mode 与单屏单列/单屏双列结构不匹配"
            )
        assignments = topology.get("bus_data_port_assignments")
        if assignments is None:
            available_data_ports = sorted(allowed_ports - {environment_port})
            required_count = 1 if data_mode == "single_column_shared" else 2
            if len(available_data_ports) < required_count:
                raise ConfigError("当前设备形态没有足够的母线数据接入口")
            assignments = {
                "single_column_shared": {"shared": available_data_ports[0]},
                "single_column_split_ab": {
                    "A": available_data_ports[0],
                    "B": available_data_ports[1],
                },
                "double_column_by_column": {
                    "column_1": available_data_ports[0],
                    "column_2": available_data_ports[1],
                },
                "double_column_by_route": {
                    "A": available_data_ports[0],
                    "B": available_data_ports[1],
                },
            }[data_mode]
        elif not isinstance(assignments, dict):
            raise ConfigError("topology.bus_data_port_assignments 必须是对象")
        required_assignment_keys = {
            "single_column_shared": {"shared"},
            "single_column_split_ab": {"A", "B"},
            "double_column_by_column": {"column_1", "column_2"},
            "double_column_by_route": {"A", "B"},
        }[data_mode]
        missing_assignment_keys = required_assignment_keys - set(assignments)
        if missing_assignment_keys:
            raise ConfigError(
                "topology.bus_data_port_assignments 缺少字段: "
                + ", ".join(sorted(missing_assignment_keys))
            )
        for key in required_assignment_keys:
            if assignments.get(key) not in allowed_ports:
                raise ConfigError(
                    f"母线数据接入口 {key}={assignments.get(key)} 不属于当前设备形态可用端口"
                )
            if assignments.get(key) == environment_port:
                raise ConfigError(
                    f"母线数据接入口 {key} 不能与动环 RS-485 上传口 "
                    f"{environment_port} 共用同一物理口"
                )
        if len(required_assignment_keys) > 1:
            selected_ports = [assignments[key] for key in required_assignment_keys]
            if len(set(selected_ports)) != len(selected_ports):
                raise ConfigError("当前母线数据接入方式要求使用两个不同的物理口")

    protocol_layout = config.get("protocol_layout", {})
    if not isinstance(protocol_layout, dict):
        raise ConfigError("protocol_layout 必须是对象")
    measurement_layout_mode = str(
        protocol_layout.get("measurement_layout_mode") or "by_plug_box"
    ).strip()
    if measurement_layout_mode not in MEASUREMENT_LAYOUT_MODES:
        raise ConfigError(
            "protocol_layout.measurement_layout_mode 仅支持 "
            "by_plug_box / by_branch"
        )
    for key in (
        "main_base_address",
        "downstream_base_address",
        "downstream_extension_base_address",
    ):
        value = protocol_layout.get(key)
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ConfigError(f"protocol_layout.{key} 必须为非负整数或 null")
    primary_outputs_per_route = protocol_layout.get("downstream_primary_outputs_per_route")
    if primary_outputs_per_route is not None and (
        not isinstance(primary_outputs_per_route, int) or primary_outputs_per_route < 1
    ):
        raise ConfigError(
            "protocol_layout.downstream_primary_outputs_per_route 必须为正整数或 null"
        )

    devices = config["devices"]
    _require_keys(devices, ["start_boxes", "plug_boxes"], "devices")
    repeater_total, _cabinet_total = _validate_extension_counts(devices, topology_mode)
    _validate_start_box_configs(
        devices,
        prefix="devices",
        scope_label=(
            "第一列"
            if topology_mode == "single_screen_two_columns"
            else "单列"
        ),
        unified_workflow=is_unified_workflow,
    )
    plug_boxes = devices["plug_boxes"]
    numbering = devices.get("numbering", {})
    repeater_units = devices.get("repeater_units", {})
    branch_outputs = devices.get("branch_modules") or devices.get("branch_outputs", {})
    default_branch_template_id = config.get("profiles", {}).get("plug_branch_template_id")
    if branch_outputs and not isinstance(branch_outputs, dict):
        raise ConfigError("devices.branch_modules 必须是对象")
    for route in ("A", "B"):
        if route not in plug_boxes:
            raise ConfigError(f"devices.plug_boxes 缺少路由 {route}")
        route_cfg = plug_boxes[route]
        board_number_start = route_cfg.get("board_number_start")
        if board_number_start is None:
            board_number_start = numbering.get("plug_board_start", {}).get(route)
        if board_number_start is not None and not isinstance(board_number_start, int):
            raise ConfigError(f"devices.plug_boxes.{route}.board_number_start 必须为整数")
        sequence = route_cfg.get("sequence", [])
        if not isinstance(sequence, list):
            raise ConfigError(f"devices.plug_boxes.{route}.sequence 必须是数组")
        branch_output_cfg = branch_outputs.get(route, {}) if isinstance(branch_outputs, dict) else {}
        if branch_output_cfg and not isinstance(branch_output_cfg, dict):
            raise ConfigError(f"devices.branch_outputs.{route} 必须是对象")
        legacy_module_count = branch_output_cfg.get(
            "module_count",
            branch_output_cfg.get("count"),
        )
        if legacy_module_count is not None and (
            not isinstance(legacy_module_count, int) or legacy_module_count < 0
        ):
            raise ConfigError(f"devices.branch_modules.{route}.module_count 必须为 >= 0 的整数")
        branch_output_count = int(legacy_module_count or 0)

        branches_per_module = branch_output_cfg.get("branches_per_module")
        if branches_per_module is not None and (
            not isinstance(branches_per_module, int) or branches_per_module < 1
        ):
            raise ConfigError(
                f"devices.branch_modules.{route}.branches_per_module 必须为正整数"
            )

        variable_numbering_mode = str(
            branch_output_cfg.get("variable_numbering_mode")
            or "per_board_suffix"
        ).strip()
        if variable_numbering_mode not in VARIABLE_NUMBERING_MODES:
            raise ConfigError(
                f"devices.branch_modules.{route}.variable_numbering_mode 仅支持 "
                "per_output_contiguous / per_board_suffix"
            )

        raw_module_sequence = branch_output_cfg.get("module_sequence")
        if raw_module_sequence is not None and not isinstance(raw_module_sequence, list):
            raise ConfigError(f"devices.branch_modules.{route}.module_sequence 必须是数组")
        module_sequence = raw_module_sequence or []
        if module_sequence and sequence:
            raise ConfigError(
                f"devices.branch_modules.{route}.module_sequence 与 "
                f"devices.plug_boxes.{route}.sequence 不能同时非空；"
                "请仅保留当前生成模式对应的一套拓扑配置"
            )
        explicit_module_count = 0
        explicit_branch_counts: list[int] = []
        for index, item in enumerate(module_sequence):
            prefix = f"devices.branch_modules.{route}.module_sequence[{index}]"
            if not isinstance(item, dict):
                raise ConfigError(f"{prefix} 必须是对象")
            _require_keys(item, ["type_code", "layout_pattern", "count"], prefix)
            if not isinstance(item["count"], int) or item["count"] < 1:
                raise ConfigError(f"{prefix}.count 必须为正整数")
            try:
                module_type = library.get_box_type(item["type_code"])
                layout_variant = library.get_layout_variant(
                    module_type,
                    item["layout_pattern"],
                )
            except KeyError as exc:
                raise ConfigError(str(exc)) from exc
            if (
                measurement_layout_mode == "by_branch"
                and module_type.get("phase_mode") == "single_phase_triplet"
            ):
                raise ConfigError(
                    f"{prefix} 使用了 {item['type_code']}；按监控模块模式暂不支持三个逻辑输出"
                    "共享一个聚合点集，请改用按插接箱模式。"
                )
            branch_count = sum(
                len(coverage)
                for coverage in layout_variant.get("branch_coverage", [])
            )
            explicit_module_count += int(item["count"])
            explicit_branch_counts.extend([branch_count] * int(item["count"]))
            branch_template_id = item.get("branch_template_id")
            if branch_template_id is not None and branch_template_id not in library.plug_branch_templates:
                raise ConfigError(f"未知 plug branch template: {branch_template_id}")
            _validate_dual_dataset_layout(
                branch_template_id=branch_template_id or default_branch_template_id,
                layout_variant=layout_variant,
                path=prefix,
            )

        if module_sequence:
            if branch_output_count not in (0, explicit_module_count):
                raise ConfigError(
                    f"devices.branch_modules.{route}.module_sequence 共 {explicit_module_count} 个模块，"
                    f"与旧 module_count={branch_output_count} 冲突"
                )
            if branches_per_module is not None and any(
                item != branches_per_module for item in explicit_branch_counts
            ):
                raise ConfigError(
                    f"devices.branch_modules.{route}.module_sequence 的模块分路数"
                    f"与旧 branches_per_module={branches_per_module} 冲突"
                )
        elif measurement_layout_mode == "by_branch" and branch_output_count > 0:
            if branches_per_module not in (None, 2):
                raise ConfigError(
                    f"devices.branch_modules.{route} 的旧 scalar 配置只兼容 "
                    "branches_per_module = 2；可变拓扑请改用 module_sequence"
                )
        elif measurement_layout_mode == "by_branch" and not sequence:
            raise ConfigError(
                f"按监控模块生成时，请填写 devices.branch_modules.{route}.module_sequence，"
                "或保留旧 module_count + branches_per_module=2 配置"
            )
        for key in (
            "module_number_start",
            "output_number_start",
            "branch_device_number_start",
        ):
            value = branch_output_cfg.get(key)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ConfigError(f"devices.branch_modules.{route}.{key} 必须为正整数")
        branch_names = branch_output_cfg.get("names", [])
        if branch_names and (
            not isinstance(branch_names, list)
            or any(not isinstance(item, str) for item in branch_names)
        ):
            raise ConfigError(f"devices.branch_modules.{route}.names 必须是字符串数组")
        for index, item in enumerate(sequence):
            _require_keys(item, ["type_code", "count"], f"devices.plug_boxes.{route}.sequence[{index}]")
            layout_value = item.get("layout_pattern") or item.get("layout_token")
            if not layout_value:
                raise ConfigError(f"devices.plug_boxes.{route}.sequence[{index}] 缺少 layout_pattern/layout_token")
            try:
                box_type = library.get_box_type(item["type_code"])
            except KeyError as exc:
                raise ConfigError(str(exc)) from exc
            if (
                measurement_layout_mode == "by_branch"
                and not module_sequence
                and branch_output_count <= 0
                and box_type.get("phase_mode") == "single_phase_triplet"
            ):
                raise ConfigError(
                    f"devices.plug_boxes.{route}.sequence[{index}] 使用了 {item['type_code']}；"
                    "按监控模块模式暂不支持三个逻辑输出共享一个聚合点集，请改用按插接箱模式。"
                )
            if item["count"] < 1:
                raise ConfigError(f"sequence[{index}] 的 count 必须 >= 1")
            allowed_patterns = [layout["pattern"] for layout in box_type.get("allowed_layout_patterns", [])]
            if layout_value not in allowed_patterns:
                raise ConfigError(
                    f"{item['type_code']} 不允许布局 {layout_value}，可选: {', '.join(allowed_patterns)}"
                )
            if "branch_template_id" in item:
                branch_template_id = item["branch_template_id"]
                if branch_template_id not in library.plug_branch_templates:
                    raise ConfigError(f"未知 plug branch template: {branch_template_id}")
            else:
                branch_template_id = default_branch_template_id
            try:
                layout_variant = library.get_layout_variant(box_type, layout_value)
            except KeyError as exc:
                raise ConfigError(str(exc)) from exc
            _validate_dual_dataset_layout(
                branch_template_id=branch_template_id,
                layout_variant=layout_variant,
                path=f"devices.plug_boxes.{route}.sequence[{index}]",
            )
            if "box_number" in item and not isinstance(item["box_number"], int):
                raise ConfigError(f"devices.plug_boxes.{route}.sequence[{index}].box_number 必须为整数")
            if "board_number_start" in item and not isinstance(item["board_number_start"], int):
                raise ConfigError(f"devices.plug_boxes.{route}.sequence[{index}].board_number_start 必须为整数")
            if "box_name" in item and not isinstance(item["box_name"], str):
                raise ConfigError(f"devices.plug_boxes.{route}.sequence[{index}].box_name 必须为字符串")
            if "instance_name" in item and not isinstance(item["instance_name"], str):
                raise ConfigError(f"devices.plug_boxes.{route}.sequence[{index}].instance_name 必须为字符串")

        repeater_number_start = (
            repeater_units.get("number_start", {}).get(route)
            or repeater_units.get(f"{route}_number_start")
        )
        if repeater_number_start is not None and not isinstance(repeater_number_start, int):
            raise ConfigError(f"devices.repeater_units.{route}_number_start 必须为整数")

    second_column: dict[str, Any] | None = None
    if topology_mode == "single_screen_two_columns":
        second_column = devices.get("screen_columns", {}).get("column_2")
        if is_unified_workflow and not isinstance(second_column, dict):
            raise ConfigError("单屏双列必须提供 devices.screen_columns.column_2")
        if not isinstance(second_column, dict):
            second_column = None
    if topology_mode == "single_screen_two_columns" and second_column is not None:
        _validate_start_box_configs(
            second_column,
            prefix="devices.screen_columns.column_2",
            scope_label="第二列",
            unified_workflow=is_unified_workflow,
        )
        second_column_config = deepcopy(config)
        second_column_data_port = next(
            port
            for port in sorted(PORTS_BY_HARDWARE[hardware_form_factor])
            if port != environment_port
        )
        second_column_config["topology"] = {
            **deepcopy(topology),
            "screen_topology_mode": "single_screen_one_column",
            "columns_per_screen": 1,
            "bus_data_port_mode": "single_column_shared",
            "bus_data_port_assignments": {
                "shared": second_column_data_port
            },
        }
        second_column_config["devices"] = {
            **deepcopy(second_column),
            "repeater_units": {"enabled": False, "A_count": 0, "B_count": 0},
            "single_cabinet_aggregation": {"enabled": False, "cabinet_count": 0},
        }
        validate_config(second_column_config, library)

    profiles = config["profiles"]
    _require_keys(profiles, ["address_profile_id", "device_library_id", "export_profile_id"], "profiles")
    if profiles["address_profile_id"] not in library.address_profile_map:
        raise ConfigError(f"未知 address_profile_id: {profiles['address_profile_id']}")
    if profiles["export_profile_id"] not in library.export_profile_map:
        raise ConfigError(f"未知 export_profile_id: {profiles['export_profile_id']}")
    address_profile = library.address_profile_map[profiles["address_profile_id"]]
    export_profile = library.export_profile_map[profiles["export_profile_id"]]
    if address_profile.get("family") != export_profile.get("family"):
        raise ConfigError(
            f"address_profile.family 与 export_profile.family 不一致: "
            f"{address_profile.get('family')} != {export_profile.get('family')}"
        )
    if profiles["device_library_id"] != library.device_library.get("id"):
        raise ConfigError(
            f"device_library_id 与当前加载 seed 不一致: {profiles['device_library_id']} != {library.device_library.get('id')}"
        )
    if repeater_units.get("enabled") and repeater_total > 0 and address_profile.get("repeater_base") is None:
        raise ConfigError("当前 address_profile 未配置 repeater_base，无法生成中继单元；请切换地址模板或关闭中继单元。")
    if (
        profiles["export_profile_id"] == CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID
        and repeater_units.get("enabled")
        and repeater_total > 0
    ):
        raise ConfigError("单屏双列模板当前不导出中继页；请关闭中继单元或切回经典合并模板。")
    if "start_box_template_id" in profiles and profiles["start_box_template_id"] not in library.start_box_templates:
        raise ConfigError(f"未知 start_box_template_id: {profiles['start_box_template_id']}")
    if "plug_branch_template_id" in profiles and profiles["plug_branch_template_id"] not in library.plug_branch_templates:
        raise ConfigError(f"未知 plug_branch_template_id: {profiles['plug_branch_template_id']}")
    if "repeater_template_id" in profiles:
        repeater_template_id = profiles["repeater_template_id"]
        if repeater_template_id not in library.repeater_templates:
            raise ConfigError(f"未知 repeater_template_id: {repeater_template_id}")
    if "single_cabinet_template_id" in profiles:
        template_id = profiles["single_cabinet_template_id"]
        known_ids = {item["id"] for item in library.device_library.get("single_cabinet_templates", [])}
        if template_id not in known_ids:
            raise ConfigError(f"未知 single_cabinet_template_id: {template_id}")

    if profiles["export_profile_id"] == LIQUIDCOOL_EXPORT_PROFILE_ID:
        if profiles["address_profile_id"] != LIQUIDCOOL_ADDRESS_PROFILE_ID:
            raise ConfigError(
                "classic_combined_liquidcool_default 只能搭配 "
                f"{LIQUIDCOOL_ADDRESS_PROFILE_ID}"
            )
        if profiles.get("start_box_template_id") != LIQUIDCOOL_START_BOX_TEMPLATE_ID:
            raise ConfigError(
                "classic_combined_liquidcool_default 只能搭配 "
                f"{LIQUIDCOOL_START_BOX_TEMPLATE_ID}"
            )
        if profiles.get("plug_branch_template_id") != LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID:
            raise ConfigError(
                "classic_combined_liquidcool_default 只能搭配 "
                f"{LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID}"
            )
        if profiles.get("single_cabinet_template_id") != LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID:
            raise ConfigError(
                "classic_combined_liquidcool_default 只能搭配 "
                f"{LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID}"
            )
