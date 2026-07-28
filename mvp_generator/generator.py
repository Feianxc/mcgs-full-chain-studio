from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .excel_renderer import ClassicCombinedRenderer, LIQUIDCOOL_THRESHOLD_ROWS
from .library import TemplateLibrary
from .split_renderers import AbScreenSplitRenderer, ExtendedSplitRenderer
from .validator import ConfigError, validate_config


DEFAULT_NUMBERING = {
    "physical_box_start": {"A": 101, "B": 201},
    "start_box_start": {"A": 1, "B": 2},
    "repeater_start": {"A": 101, "B": 201},
}
DERIVED_ADDRESS_BLOCK = 1000
EXTENDED_REPEATER_ROUTE_GAP = 100
MEASUREMENT_LAYOUT_BY_PLUG_BOX = "by_plug_box"
MEASUREMENT_LAYOUT_BY_BRANCH = "by_branch"
MEASUREMENT_LAYOUT_MODES = {
    MEASUREMENT_LAYOUT_BY_PLUG_BOX,
    MEASUREMENT_LAYOUT_BY_BRANCH,
}
VARIABLE_NUMBERING_PER_OUTPUT = "per_output_contiguous"
VARIABLE_NUMBERING_PER_BOARD = "per_board_suffix"
VARIABLE_NUMBERING_MODES = {
    VARIABLE_NUMBERING_PER_OUTPUT,
    VARIABLE_NUMBERING_PER_BOARD,
}
DUAL_DATASET_TEMPLATE_ID = "plug_branch_dual_dataset_47row"
DUAL_OUTPUT_BOARD_TEMPLATE_ID = "board_1to6_3phase_dual"


@dataclass
class AddressCursor:
    current: int
    step: int

    def next_address(self) -> int:
        value = self.current
        self.current += self.step
        return value


class ProtocolGenerator:
    def __init__(self, library: TemplateLibrary):
        self.library = library

    @classmethod
    def with_default_assets(cls) -> "ProtocolGenerator":
        return cls(TemplateLibrary.load())

    def load_config(self, config_path: Path) -> dict[str, Any]:
        return json.loads(config_path.read_text(encoding="utf-8"))

    def generate_from_path(self, config_path: Path) -> dict[str, Any]:
        config = self.load_config(config_path)
        return self.generate(config)

    def generate(self, config: dict[str, Any]) -> dict[str, Any]:
        config = self._normalize_route_copy_artifacts(deepcopy(config))
        validate_config(config, self.library)
        address_profile = self.library.address_profile_map[config["profiles"]["address_profile_id"]]
        export_profile = self.library.export_profile_map[config["profiles"]["export_profile_id"]]
        selected_start_box_template_id = config["profiles"].get("start_box_template_id")
        selected_branch_template_id = config["profiles"].get("plug_branch_template_id")
        selected_repeater_template_id = config["profiles"].get("repeater_template_id")
        selected_cabinet_template_id = config["profiles"].get("single_cabinet_template_id")
        export_family = export_profile["family"]
        register_step = address_profile.get("register_step", 2)
        protocol_layout = self._protocol_layout(config)

        model = {
            "project": {
                "project_name": config["project_name"],
                "project_code": config.get("project_code"),
                "protocol_title": config.get("protocol_title", "上位机通讯协议"),
                "generation_basis": config["generation_basis"],
                "topology": deepcopy(config["topology"]),
            },
            "communication": deepcopy(config.get("communication", {})),
            "protocol_layout": protocol_layout,
            "profiles": {
                "address_profile": deepcopy(address_profile),
                "export_profile": deepcopy(export_profile),
                "device_library_id": config["profiles"]["device_library_id"],
                "start_box_template_id": selected_start_box_template_id,
                "plug_branch_template_id": selected_branch_template_id,
                "repeater_template_id": selected_repeater_template_id,
                "single_cabinet_template_id": selected_cabinet_template_id,
            },
            "modeling_principle": self.library.device_library.get("modeling_principle"),
            "routes": [],
            "single_cabinet_rows": [],
            "warnings": [],
        }

        main_cursor = AddressCursor(address_profile["main_base"], register_step)
        plug_base = address_profile.get("plug_base")
        plug_cursor = AddressCursor(plug_base, register_step) if plug_base is not None else main_cursor
        repeater_base = address_profile.get("repeater_base")
        repeater_cursor = AddressCursor(repeater_base, register_step) if repeater_base is not None else None
        cabinet_base = address_profile.get("cabinet_base")
        cabinet_cursor = AddressCursor(cabinet_base, register_step) if cabinet_base is not None else None
        route_address_summary: dict[str, dict[str, int | None]] = {}
        repeater_cfg = config.get("devices", {}).get("repeater_units", {})
        repeater_enabled = bool(repeater_cfg.get("enabled")) and self._repeater_total_count(repeater_cfg) > 0
        cabinet_cfg = config.get("devices", {}).get("single_cabinet_aggregation", {})
        cabinet_enabled = bool(cabinet_cfg.get("enabled")) and self._single_cabinet_total_count(cabinet_cfg) > 0
        alarm_enabled = (
            config.get("extensions", {}).get("alarm_state_word", {}).get("enabled", True)
            is not False
        )

        column_device_groups = self._screen_column_device_groups(config)
        for route in ("A", "B"):
            route_main_cursor = main_cursor
            route_plug_cursor = plug_cursor
            route_repeater_cursor = repeater_cursor
            if export_family == "ab_screen_split":
                route_main_cursor = AddressCursor(address_profile["main_base"], register_step)
                route_plug_cursor = route_main_cursor if plug_base is None else AddressCursor(plug_base, register_step)
                route_repeater_cursor = AddressCursor(repeater_base, register_step) if repeater_base is not None else None
            elif export_family == "extended_split" and repeater_base is not None:
                route_repeater_base = repeater_base if route == "A" else repeater_base + EXTENDED_REPEATER_ROUTE_GAP
                route_repeater_cursor = AddressCursor(route_repeater_base, register_step)
            route_model = {
                "route": route,
                "start_boxes": [],
                "physical_plug_boxes": [],
                "repeater_units": [],
            }
            next_module_number: int | None = None
            next_output_number: int | None = None
            for screen_column, column_devices in column_device_groups:
                column_config = deepcopy(config)
                column_config["devices"] = deepcopy(column_devices)
                if (
                    protocol_layout.get("measurement_layout_mode")
                    == MEASUREMENT_LAYOUT_BY_BRANCH
                ):
                    branch_module_config = (
                        column_config["devices"]
                        .setdefault("branch_modules", {})
                        .setdefault(route, {})
                    )
                    branch_module_config.setdefault(
                        "display_module_number_start",
                        int(branch_module_config.get("module_number_start", 1) or 1),
                    )
                    if screen_column > 1 and next_module_number is not None:
                        branch_module_config["module_number_start"] = next_module_number
                    if screen_column > 1 and next_output_number is not None:
                        branch_module_config["output_number_start"] = next_output_number
                column_config["devices"]["repeater_units"] = self._repeater_config_for_column(
                    config.get("devices", {}).get("repeater_units", {}),
                    screen_column,
                )
                column_route_model, route_main_cursor, route_plug_cursor, route_repeater_cursor = self._build_route(
                    route=route,
                    config=column_config,
                    main_cursor=route_main_cursor,
                    plug_cursor=route_plug_cursor,
                    repeater_cursor=route_repeater_cursor,
                    selected_start_box_template_id=selected_start_box_template_id,
                    selected_branch_template_id=selected_branch_template_id,
                    selected_repeater_template_id=selected_repeater_template_id,
                    screen_column=screen_column,
                )
                model["warnings"].extend(column_route_model.pop("_warnings"))
                route_model["start_boxes"].extend(column_route_model["start_boxes"])
                route_model["physical_plug_boxes"].extend(
                    column_route_model["physical_plug_boxes"]
                )
                route_model["repeater_units"].extend(column_route_model["repeater_units"])
                if protocol_layout.get("measurement_layout_mode") == MEASUREMENT_LAYOUT_BY_BRANCH:
                    column_modules = column_route_model["physical_plug_boxes"]
                    module_numbers = [
                        int(module["module_no"])
                        for module in column_modules
                        if module.get("module_no") is not None
                    ]
                    output_numbers = [
                        int(branch["output_no"])
                        for module in column_modules
                        for board in module.get("boards", [])
                        for branch in board.get("branches", [])
                        if branch.get("output_no") is not None
                    ]
                    if module_numbers:
                        next_module_number = max(module_numbers) + 1
                    if output_numbers:
                        next_output_number = max(output_numbers) + 1
            model["routes"].append(route_model)
            route_address_summary[route] = {
                "main_next_address": route_main_cursor.current,
                "plug_next_address": route_plug_cursor.current if plug_base is not None else None,
                "repeater_next_address": route_repeater_cursor.current if route_repeater_cursor and repeater_enabled else None,
            }
            if export_family != "ab_screen_split":
                main_cursor = route_main_cursor
                plug_cursor = route_plug_cursor
                repeater_cursor = route_repeater_cursor

        if cabinet_enabled and cabinet_cursor is None:
            cabinet_base = self._derive_cabinet_base(
                model=model,
                route_address_summary=route_address_summary,
                main_next_address=main_cursor.current,
                plug_next_address=plug_cursor.current if plug_base is not None else None,
                repeater_next_address=repeater_cursor.current if repeater_cursor is not None else None,
                register_step=register_step,
            )
            model["profiles"]["address_profile"]["cabinet_base"] = cabinet_base
            model["warnings"].append(f"当前 address profile 未配置 cabinet_base，已自动推导单机柜起始地址 {cabinet_base}。")
            cabinet_cursor = AddressCursor(cabinet_base, register_step)

        if cabinet_cursor is not None:
            (
                model["single_cabinet_rows"],
                cabinet_cursor,
                cabinet_warnings,
            ) = self._build_single_cabinet_rows(
                config=config,
                address_cursor=cabinet_cursor,
                selected_template_id=selected_cabinet_template_id,
            )
            model["warnings"].extend(cabinet_warnings)

        main_next_address, plug_next_address, repeater_next_address = self._resequence_addresses(
            model,
            main_next_address=main_cursor.current,
            plug_next_address=plug_cursor.current if plug_cursor is not main_cursor else None,
            repeater_next_address=repeater_cursor.current if repeater_cursor else None,
            route_address_summary=route_address_summary,
        )
        model["address_summary"] = {
            "main_next_address": None if export_family == "ab_screen_split" else main_next_address,
            "plug_next_address": None if export_family == "ab_screen_split" or plug_base is None else plug_next_address,
            "repeater_next_address": None if export_family == "ab_screen_split" or not repeater_enabled else repeater_next_address,
            "cabinet_start_address": model["profiles"]["address_profile"].get("cabinet_base") if cabinet_enabled else None,
            "cabinet_next_address": cabinet_cursor.current if cabinet_cursor and cabinet_enabled else None,
            "alarm_base": address_profile.get("alarm_base"),
            "alarm_word_mode": address_profile.get("alarm_word_mode"),
            "alarm_generation_status": "configured" if alarm_enabled else "disabled",
        }
        if route_address_summary:
            model["address_summary"]["routes"] = route_address_summary
        if model.get("downstream_address_segments"):
            model["address_summary"]["downstream_segments"] = deepcopy(
                model["downstream_address_segments"]
            )
        self._validate_global_variable_names(model, config)
        self._validate_unified_address_usage(model, config)
        return model

    def _screen_column_device_groups(
        self,
        config: dict[str, Any],
    ) -> list[tuple[int, dict[str, Any]]]:
        devices = config.get("devices", {})
        groups: list[tuple[int, dict[str, Any]]] = [(1, devices)]
        topology_mode = str(
            config.get("topology", {}).get("screen_topology_mode") or ""
        )
        if topology_mode != "single_screen_two_columns":
            return groups
        second_column = devices.get("screen_columns", {}).get("column_2")
        if isinstance(second_column, dict):
            groups.append((2, second_column))
        return groups

    def _repeater_config_for_column(
        self,
        repeater_cfg: dict[str, Any],
        screen_column: int,
    ) -> dict[str, Any]:
        """Return the repeater settings for one physical screen column.

        The legacy A_count/B_count fields remain a single-column compatibility
        layer.  New two-column payloads use columns.column_1/column_2 so all four
        groups (column 1 A/B and column 2 A/B) are independent.
        """

        result = deepcopy(repeater_cfg) if isinstance(repeater_cfg, dict) else {}
        columns = result.get("columns") if isinstance(result.get("columns"), dict) else {}
        column_key = f"column_{screen_column}"
        column_cfg = columns.get(column_key) if isinstance(columns.get(column_key), dict) else None
        if column_cfg is not None:
            result.update(deepcopy(column_cfg))
        elif screen_column > 1:
            result.update({"A_count": 0, "B_count": 0})

        if screen_column > 1:
            for key in ("number_start", "A_number_start", "B_number_start"):
                if column_cfg is None or key not in column_cfg:
                    result.pop(key, None)

        result["enabled"] = bool(repeater_cfg.get("enabled"))
        result["A_count"] = max(0, int(result.get("A_count", 0) or 0))
        result["B_count"] = max(0, int(result.get("B_count", 0) or 0))
        result.pop("columns", None)
        return result

    def _repeater_total_count(self, repeater_cfg: dict[str, Any]) -> int:
        if not isinstance(repeater_cfg, dict):
            return 0
        columns = repeater_cfg.get("columns")
        if isinstance(columns, dict) and columns:
            return sum(
                max(0, int(column_cfg.get(f"{route}_count", 0) or 0))
                for column_cfg in columns.values()
                if isinstance(column_cfg, dict)
                for route in ("A", "B")
            )
        return sum(max(0, int(repeater_cfg.get(f"{route}_count", 0) or 0)) for route in ("A", "B"))

    def _single_cabinet_column_counts(self, aggregation_cfg: dict[str, Any]) -> tuple[int, int]:
        raw_counts = aggregation_cfg.get("column_counts")
        if isinstance(raw_counts, dict):
            return (
                max(0, int(raw_counts.get("column_1", 0) or 0)),
                max(0, int(raw_counts.get("column_2", 0) or 0)),
            )
        return max(0, int(aggregation_cfg.get("cabinet_count", 0) or 0)), 0

    def _single_cabinet_total_count(self, aggregation_cfg: dict[str, Any]) -> int:
        return sum(self._single_cabinet_column_counts(aggregation_cfg))

    def _validate_global_variable_names(
        self,
        model: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        """Reject duplicate exported variable names before any artifact is written."""

        render_variant_id = str(
            model.get("profiles", {}).get("export_profile", {}).get("render_variant_id")
            or ""
        )
        if render_variant_id != "unified_master":
            return

        seen: dict[str, str] = {}

        def register(var_name: Any, path: str) -> None:
            name = str(var_name or "").strip()
            if not name:
                return
            previous = seen.get(name)
            if previous is not None:
                raise ConfigError(
                    f"变量名重复：{name} 同时出现在 {previous} 与 {path}；"
                    "请调整 A/B 路变量设备号、板卡编号或模块编号。"
                )
            seen[name] = path

        for route_model in model.get("routes", []):
            route = str(route_model.get("route") or "?")
            for start_index, start_box in enumerate(route_model.get("start_boxes", []), start=1):
                for point_index, point in enumerate(start_box.get("points", []), start=1):
                    register(point.get("var_name"), f"{route}路始端箱{start_index}.points[{point_index}]")
            for module_index, physical_box in enumerate(
                route_model.get("physical_plug_boxes", []),
                start=1,
            ):
                entity_label = (
                    f"模块{physical_box.get('module_no') or module_index}"
                    if physical_box.get("entity_kind") == "monitor_module"
                    else f"插接箱{physical_box.get('physical_box_no') or module_index}"
                )
                for board_index, board in enumerate(physical_box.get("boards", []), start=1):
                    for branch_index, branch in enumerate(board.get("branches", []), start=1):
                        for point_index, point in enumerate(branch.get("points", []), start=1):
                            register(
                                point.get("var_name"),
                                f"{route}路{entity_label}.boards[{board_index}]."
                                f"branches[{branch_index}].points[{point_index}]",
                            )
            for repeater_index, repeater in enumerate(route_model.get("repeater_units", []), start=1):
                for point_index, point in enumerate(repeater.get("points", []), start=1):
                    register(
                        point.get("var_name"),
                        f"{route}路中继[{repeater_index}].points[{point_index}]",
                    )

        for row_index, item in enumerate(model.get("single_cabinet_rows", []), start=1):
            register(item.get("var_name"), f"single_cabinet_rows[{row_index}]")

        alarm_config = config.get("extensions", {}).get("alarm_state_word", {})
        if alarm_config.get("enabled") is not False:
            for row_index, row in enumerate(ClassicCombinedRenderer(model)._build_alarm_rows(), start=1):
                register(row.var_name, f"alarm_rows[{row_index}]")

    def _validate_unified_address_usage(
        self,
        model: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        """Reject overlapping register ranges in the parameterized master flow."""

        render_variant_id = str(
            model.get("profiles", {}).get("export_profile", {}).get("render_variant_id")
            or ""
        )
        if render_variant_id != "unified_master":
            return

        occupied: dict[int, str] = {}

        def reserve(start: int, size: int, label: str) -> None:
            for address in range(start, start + size):
                previous = occupied.get(address)
                if previous is not None:
                    raise ConfigError(
                        f"寄存器地址冲突：{label} 与 {previous} 同时占用地址 {address}；"
                        "请调整主数据、下游分路、中继、单机柜或报警状态字的起始地址。"
                    )
                occupied[address] = label

        def collect_points(node: Any, path: str) -> None:
            if isinstance(node, dict):
                address = node.get("address")
                register_size = node.get("register_size")
                if isinstance(address, int) and isinstance(register_size, int) and register_size > 0:
                    point_label = str(
                        node.get("var_name")
                        or node.get("variable_name")
                        or node.get("measurement_name")
                        or path
                    )
                    reserve(address, register_size, f"遥测点 {point_label}")
                    return
                for key, value in node.items():
                    collect_points(value, f"{path}.{key}")
                return
            if isinstance(node, list):
                for index, value in enumerate(node):
                    collect_points(value, f"{path}[{index}]")

        collect_points(model.get("routes", []), "routes")
        collect_points(model.get("single_cabinet_rows", []), "single_cabinet_rows")

        alarm_config = config.get("extensions", {}).get("alarm_state_word", {})
        if alarm_config.get("enabled") is False:
            return
        alarm_register_size = (
            2
            if model.get("profiles", {})
            .get("address_profile", {})
            .get("alarm_word_mode")
            == "32bit"
            else 1
        )
        for row in ClassicCombinedRenderer(model)._build_alarm_rows():
            reserve(
                int(row.register_address),
                alarm_register_size,
                f"报警状态字 {row.var_name}",
            )

    def _protocol_layout(self, config: dict[str, Any]) -> dict[str, Any]:
        layout = deepcopy(config.get("protocol_layout") or {})
        measurement_layout_mode = str(
            layout.get("measurement_layout_mode") or MEASUREMENT_LAYOUT_BY_PLUG_BOX
        ).strip()
        if measurement_layout_mode not in MEASUREMENT_LAYOUT_MODES:
            measurement_layout_mode = MEASUREMENT_LAYOUT_BY_PLUG_BOX
        layout.update(
            {
                "measurement_layout_mode": measurement_layout_mode,
                "base_sheet_name": "始端箱和插接箱",
                "embed_single_cabinet_in_base_sheet": layout.get(
                    "embed_single_cabinet_in_base_sheet",
                    True,
                )
                is not False,
                "alarm_start_box_first": layout.get("alarm_start_box_first", True) is not False,
            }
        )
        return layout

    def _normalize_route_copy_artifacts(self, config: dict[str, Any]) -> dict[str, Any]:
        devices = config.get("devices", {})
        start_boxes_cfg = devices.get("start_boxes", {})
        plug_boxes_cfg = devices.get("plug_boxes", {})
        topology_mode = config.get("topology", {}).get("screen_topology_mode")

        route_b_start_cfg = start_boxes_cfg.get("B")
        if isinstance(route_b_start_cfg, dict):
            count = int(route_b_start_cfg.get("count", 0) or 0)
            instance_names = [str(item).strip() for item in (route_b_start_cfg.get("instance_names") or []) if str(item).strip()]
            normalized_count = max(count, len(instance_names))
            a_default_names = self._default_start_box_names("A", normalized_count, topology_mode)
            copied_a_defaults = bool(instance_names) and instance_names == a_default_names[: len(instance_names)]
            if copied_a_defaults:
                route_b_start_cfg["instance_names"] = self._default_start_box_names("B", normalized_count, topology_mode)

        route_b_plug_cfg = plug_boxes_cfg.get("B")
        if isinstance(route_b_plug_cfg, dict):
            if route_b_plug_cfg.get("board_number_start") == DEFAULT_NUMBERING["physical_box_start"]["A"]:
                route_b_plug_cfg["board_number_start"] = DEFAULT_NUMBERING["physical_box_start"]["B"]
            for index, item in enumerate(route_b_plug_cfg.get("sequence") or []):
                expected_a = DEFAULT_NUMBERING["physical_box_start"]["A"] + index
                expected_b = DEFAULT_NUMBERING["physical_box_start"]["B"] + index
                if item.get("box_number") == expected_a:
                    item["box_number"] = expected_b
                if item.get("board_number_start") == expected_a:
                    item["board_number_start"] = expected_b
                for name_key in ("box_name", "instance_name"):
                    if item.get(name_key) == str(expected_a):
                        item[name_key] = str(expected_b)

        numbering_cfg = devices.get("numbering", {}).get("plug_board_start")
        if isinstance(numbering_cfg, dict):
            if numbering_cfg.get("B") == DEFAULT_NUMBERING["physical_box_start"]["A"]:
                numbering_cfg["B"] = DEFAULT_NUMBERING["physical_box_start"]["B"]

        return config

    def _default_start_box_names(self, route: str, count: int, topology_mode: str | None) -> list[str]:
        total = max(0, int(count or 0))
        start = DEFAULT_NUMBERING["start_box_start"][route]
        step = 2 if topology_mode == "single_screen_two_columns" else 1
        return [f"S{start + index * step}" for index in range(total)]

    def _derive_cabinet_base(
        self,
        model: dict[str, Any],
        route_address_summary: dict[str, dict[str, int | None]],
        main_next_address: int | None,
        plug_next_address: int | None,
        repeater_next_address: int | None,
        register_step: int,
    ) -> int:
        address_profile = model["profiles"]["address_profile"]
        candidates: list[int] = []

        for value in (
            address_profile.get("main_base"),
            address_profile.get("plug_base"),
            address_profile.get("repeater_base"),
            address_profile.get("alarm_base"),
            main_next_address,
            plug_next_address,
            repeater_next_address,
            self._estimate_alarm_next_address(model),
        ):
            if value is not None:
                candidates.append(int(value))

        for summary in route_address_summary.values():
            for value in summary.values():
                if value is not None:
                    candidates.append(int(value))

        anchor = max(candidates) if candidates else DERIVED_ADDRESS_BLOCK
        derived = ((anchor // DERIVED_ADDRESS_BLOCK) + 1) * DERIVED_ADDRESS_BLOCK
        if derived % register_step != 0:
            derived += register_step - (derived % register_step)
        return derived

    def _estimate_alarm_next_address(self, model: dict[str, Any]) -> int | None:
        address_profile = model["profiles"]["address_profile"]
        alarm_base = address_profile.get("alarm_base")
        if alarm_base is None:
            return None

        family = model["profiles"]["export_profile"]["family"]
        if family == "classic_combined":
            renderer = ClassicCombinedRenderer(model)
            if renderer._is_liquidcool_profile():
                threshold_next = int(alarm_base) + len(LIQUIDCOOL_THRESHOLD_ROWS) * 2
                rows = renderer._build_liquidcool_state_alarm_rows()
                if not rows:
                    return threshold_next
                return max(threshold_next, *(row.register_address + self._alarm_row_register_size(row) for row in rows))
            rows = renderer._build_alarm_rows()
        elif family == "extended_split":
            rows = ExtendedSplitRenderer(model)._build_alarm_rows()
        elif family == "ab_screen_split":
            renderer = AbScreenSplitRenderer(model)
            rows = []
            for route in ("A", "B"):
                rows.extend(renderer._build_screen_alarm_rows(renderer._route_model(route)))
        else:
            rows = []

        if rows:
            return max(row.register_address + self._alarm_row_register_size(row) for row in rows)
        return int(alarm_base) + (2 if address_profile.get("alarm_word_mode") == "32bit" else 1)

    def _alarm_row_register_size(self, row: Any) -> int:
        data_type_label = str(getattr(row, "data_type_label", "") or "")
        return 2 if "32位" in data_type_label else 1

    def _build_route(
        self,
        route: str,
        config: dict[str, Any],
        main_cursor: AddressCursor,
        plug_cursor: AddressCursor,
        repeater_cursor: AddressCursor | None,
        selected_start_box_template_id: str | None,
        selected_branch_template_id: str | None,
        selected_repeater_template_id: str | None,
        screen_column: int = 1,
    ) -> tuple[dict[str, Any], AddressCursor, AddressCursor, AddressCursor | None]:
        route_model = {
            "route": route,
            "screen_column": screen_column,
            "start_boxes": [],
            "physical_plug_boxes": [],
            "repeater_units": [],
            "_warnings": [],
        }

        start_boxes_cfg = config["devices"]["start_boxes"].get(route, {})
        start_box_template_id = selected_start_box_template_id or self.library.first_start_box_template_id()
        start_box_template = self.library.start_box_templates[start_box_template_id]
        start_seq = int(
            start_boxes_cfg.get("device_code_start")
            or DEFAULT_NUMBERING["start_box_start"][route]
        )
        for index in range(start_boxes_cfg.get("count", 0)):
            instance_names = start_boxes_cfg.get("instance_names") or []
            device_code = start_seq + index
            instance_name = instance_names[index] if index < len(instance_names) else f"S{device_code}"
            points, main_cursor = self._allocate_template_points(
                template=start_box_template,
                variable_device_suffix=str(device_code),
                address_cursor=main_cursor,
            )
            route_model["start_boxes"].append(
                {
                    "instance_name": instance_name,
                    "device_code": device_code,
                    "screen_column": screen_column,
                    "template_id": start_box_template_id,
                    "point_count": len(points),
                    "points": points,
                }
            )

        route_cfg = config["devices"]["plug_boxes"][route]
        branch_output_cfg = (
            config.get("devices", {}).get("branch_modules", {}).get(route, {})
            or config.get("devices", {}).get("branch_outputs", {}).get(route, {})
        )
        measurement_layout_mode = str(
            config.get("protocol_layout", {}).get("measurement_layout_mode")
            or MEASUREMENT_LAYOUT_BY_PLUG_BOX
        )
        module_sequence_source = "plug_box_sequence"
        if measurement_layout_mode == MEASUREMENT_LAYOUT_BY_BRANCH:
            explicit_module_sequence = branch_output_cfg.get("module_sequence")
            requested_module_count = int(
                branch_output_cfg.get("module_count")
                or branch_output_cfg.get("count")
                or 0
            )
            if isinstance(explicit_module_sequence, list) and explicit_module_sequence:
                module_sequence_source = "explicit_module_sequence"
                route_cfg = {
                    "board_number_start": int(
                        branch_output_cfg.get("branch_device_number_start")
                        or branch_output_cfg.get("device_number_start")
                        or route_cfg.get("board_number_start")
                        or DEFAULT_NUMBERING["physical_box_start"][route]
                    ),
                    "sequence": deepcopy(explicit_module_sequence),
                }
            elif requested_module_count > 0:
                # unified_protocol_v1 compatibility: Malaysia-style scalar input
                # means one monitor module with two independent one-output boards.
                module_sequence_source = "legacy_scalar_two_output"
                route_cfg = {
                    "board_number_start": int(
                        branch_output_cfg.get("branch_device_number_start")
                        or branch_output_cfg.get("device_number_start")
                        or route_cfg.get("board_number_start")
                        or DEFAULT_NUMBERING["physical_box_start"][route]
                    ),
                    "sequence": [
                        {
                            "type_code": "3P*2",
                            "count": requested_module_count,
                            "layout_pattern": "1+1",
                        }
                    ],
                }
        physical_box_no = int(
            route_cfg.get("box_number_start")
            or route_cfg.get("board_number_start")
            or DEFAULT_NUMBERING["physical_box_start"][route]
        )
        board_device_no = route_cfg.get("board_number_start")
        if board_device_no is None:
            board_device_no = config.get("devices", {}).get("numbering", {}).get("plug_board_start", {}).get(route)
        if board_device_no is None:
            first_item = (route_cfg.get("sequence") or [{}])[0]
            board_device_no = first_item.get("board_number_start") or first_item.get("box_number")
        if board_device_no is None:
            board_device_no = DEFAULT_NUMBERING["physical_box_start"][route]
        for item in route_cfg.get("sequence", []):
            box_type = self.library.get_box_type(item["type_code"])
            layout_pattern = item.get("layout_pattern") or item.get("layout_token") or self.library.box_type_default_layout(box_type)
            layout_variant = self.library.get_layout_variant(box_type, layout_pattern)
            branch_template_id = (
                item.get("branch_template_id")
                or selected_branch_template_id
                or self.library.box_type_default_branch_template(box_type)
            )
            explicit_box_number = item.get("box_number")
            explicit_board_number = item.get("board_number_start")
            explicit_box_name = str(item.get("box_name") or item.get("instance_name") or "").strip() or None
            for repeat_index in range(item["count"]):
                current_physical_box_no = physical_box_no
                current_board_device_no = board_device_no
                current_box_name = explicit_box_name if repeat_index == 0 else None
                if explicit_box_number is not None and repeat_index == 0:
                    current_physical_box_no = int(explicit_box_number)
                if explicit_board_number is not None and repeat_index == 0:
                    current_board_device_no = int(explicit_board_number)
                elif explicit_box_number is not None and repeat_index == 0:
                    current_board_device_no = int(explicit_box_number)

                box_model, physical_box_no, board_device_no, plug_cursor = self._build_physical_box(
                    route=route,
                    physical_box_no=current_physical_box_no,
                    board_device_no=current_board_device_no,
                    box_type=box_type,
                    layout_variant=layout_variant,
                    branch_template_id=branch_template_id,
                    plug_cursor=plug_cursor,
                    route_warnings=route_model["_warnings"],
                    box_name=current_box_name,
                    screen_column=screen_column,
                )
                route_model["physical_plug_boxes"].append(box_model)

        output_number = int(
            branch_output_cfg.get("output_number_start")
            or branch_output_cfg.get("number_start")
            or 1
        )
        output_names = [
            str(item).strip()
            for item in (branch_output_cfg.get("names") or [])
            if str(item).strip()
        ]
        is_two_column = (
            config.get("topology", {}).get("screen_topology_mode")
            == "single_screen_two_columns"
        )
        route_output_prefix = (
            f"{'第一列' if screen_column == 1 else '第二列'}{route}路"
            if is_two_column
            else f"{route}路"
        )
        if measurement_layout_mode == MEASUREMENT_LAYOUT_BY_BRANCH:
            variable_numbering_mode = str(
                branch_output_cfg.get("variable_numbering_mode")
                or VARIABLE_NUMBERING_PER_BOARD
            ).strip()
            if str(config.get("workflow_version") or "").strip() == "unified_protocol_v1":
                # The unified product contract is board based: one-to-three
                # boards consume one number and one-to-six boards expose the
                # second output as <board>_2.  A saved legacy draft must not be
                # allowed to silently rewrite 102_2 into 103.
                variable_numbering_mode = VARIABLE_NUMBERING_PER_BOARD
            variable_device_number = int(
                branch_output_cfg.get("branch_device_number_start")
                or branch_output_cfg.get("device_number_start")
                or DEFAULT_NUMBERING["physical_box_start"][route]
            )
            module_number = int(branch_output_cfg.get("module_number_start", 1) or 1)
            display_module_number = int(
                branch_output_cfg.get("display_module_number_start")
                or branch_output_cfg.get("module_number_start")
                or 1
            )
            output_index = 0
            for physical_box in route_model["physical_plug_boxes"]:
                module_id = (
                    f"{route}-M{module_number:03d}"
                    if screen_column == 1
                    else f"C{screen_column}-{route}-M{module_number:03d}"
                )
                physical_box.update(
                    {
                        "entity_kind": "monitor_module",
                        "module_id": module_id,
                        "module_no": module_number,
                        "display_module_no": display_module_number,
                        "communication_alarm_slot": module_number,
                        "module_sequence_source": module_sequence_source,
                        "variable_numbering_mode": variable_numbering_mode,
                    }
                )
                module_local_branch_no = 1
                module_branches: list[dict[str, Any]] = []
                for board in physical_box["boards"]:
                    board["module_id"] = module_id
                    board["module_no"] = module_number
                    for branch in board["branches"]:
                        if branch.get("branch_kind") == "single_phase_triplet_aggregate":
                            raise ConfigError(
                                "按监控模块模式暂不支持 1P*3 / 3*1P 的三个逻辑输出共享一个聚合点集；"
                                "请改用 by_plug_box，或等待共享数据集 canonical 支持。"
                            )
                        if variable_numbering_mode == VARIABLE_NUMBERING_PER_OUTPUT:
                            self._rewrite_branch_variable_device_code(
                                branch,
                                str(variable_device_number),
                            )
                            variable_device_number += 1
                        branch.update(
                            {
                                "module_id": module_id,
                                "module_no": module_number,
                                "display_module_no": display_module_number,
                                "module_local_branch_no": module_local_branch_no,
                                "output_no": output_number,
                                "output_name": (
                                    output_names[output_index]
                                    if output_index < len(output_names)
                                    else f"{route_output_prefix}输出分路{output_number}"
                                ),
                                "variable_numbering_mode": variable_numbering_mode,
                                "communication_alarm_slot": module_number,
                            }
                        )
                        module_branches.append(branch)
                        module_local_branch_no += 1
                        output_number += 1
                        output_index += 1
                if not module_branches:
                    raise ConfigError(f"{route}路监控模块 {module_number} 未展开出任何输出分路")
                communication_variable_device_code = str(
                    module_branches[0]["variable_device_code"]
                )
                physical_box["communication_variable_device_code"] = (
                    communication_variable_device_code
                )
                physical_box["module_branch_count"] = len(module_branches)
                for branch in module_branches:
                    branch["communication_variable_device_code"] = (
                        communication_variable_device_code
                    )
                module_number += 1
                display_module_number += 1
        else:
            output_index = 0
            for physical_box in route_model["physical_plug_boxes"]:
                for board in physical_box["boards"]:
                    for branch in board["branches"]:
                        branch["output_no"] = output_number
                        branch["output_name"] = (
                            output_names[output_index]
                            if output_index < len(output_names)
                            else f"{route_output_prefix}输出分路{output_number}"
                        )
                        output_number += 1
                        output_index += 1

        repeater_cfg = config["devices"].get("repeater_units", {})
        if repeater_cfg.get("enabled") and repeater_cursor is not None:
            repeater_template_id = selected_repeater_template_id or self.library.first_repeater_template_id()
            if repeater_template_id:
                repeater_template = self.library.repeater_templates[repeater_template_id]
                repeater_seq = (
                    repeater_cfg.get("number_start", {}).get(route)
                    or repeater_cfg.get(f"{route}_number_start")
                    or DEFAULT_NUMBERING["repeater_start"][route] + (screen_column - 1) * 200
                )
                repeater_count = repeater_cfg.get(f"{route}_count", 0)
                for index in range(repeater_count):
                    device_code = repeater_seq + index
                    points, repeater_cursor = self._allocate_template_points(
                        template=repeater_template,
                        variable_device_suffix=str(device_code),
                        address_cursor=repeater_cursor,
                    )
                    route_model["repeater_units"].append(
                        {
                            "device_code": device_code,
                            "screen_column": screen_column,
                            "alias": repeater_cfg.get("alias", "中继器"),
                            "template_id": repeater_template_id,
                            "point_count": len(points),
                            "points": points,
                        }
                    )

        return route_model, main_cursor, plug_cursor, repeater_cursor

    def _rewrite_branch_variable_device_code(
        self,
        branch: dict[str, Any],
        variable_device_code: str,
    ) -> None:
        branch["variable_suffix"] = ""
        branch["variable_device_code"] = variable_device_code
        for point in branch.get("points", []):
            point["var_name"] = f"{point['prefix']}{variable_device_code}"

    def _build_physical_box(
        self,
        route: str,
        physical_box_no: int,
        board_device_no: int,
        box_type: dict[str, Any],
        layout_variant: dict[str, Any],
        branch_template_id: str | None,
        plug_cursor: AddressCursor,
        route_warnings: list[str],
        box_name: str | None = None,
        screen_column: int = 1,
    ) -> tuple[dict[str, Any], int, int, AddressCursor]:
        instance_name = str(box_name).strip() if box_name else str(physical_box_no)
        box_model = {
            "route": route,
            "screen_column": screen_column,
            "physical_box_no": physical_box_no,
            "instance_name": instance_name,
            "type_code": box_type["type_code"],
            "aliases": box_type.get("aliases", []),
            "phase_mode": box_type["phase_mode"],
            "branch_count": box_type.get("branch_count"),
            "layout_pattern": layout_variant.get("pattern", layout_variant.get("layout_token")),
            "boards": [],
        }

        board_sequence = layout_variant.get("board_template_sequence") or layout_variant.get("board_template_ids") or []
        branch_coverages = layout_variant.get("branch_coverage") or self._derive_branch_coverage(board_sequence)
        for board_index, board_template_id in enumerate(board_sequence, start=1):
            board_template = self.library.board_templates[board_template_id]
            covered_branches = branch_coverages[board_index - 1]
            board_model = {
                "board_sequence_index": board_index,
                "board_device_no": board_device_no,
                "board_template_id": board_template_id,
                "board_phase_mode": board_template["phase_mode"],
                "board_branch_capacity": board_template["branch_capacity"],
                "logical_output_count": len(covered_branches),
                "logical_output_labels": list(covered_branches),
                "branches": [],
            }

            if board_template["phase_mode"] == "single_phase_triplet":
                if not branch_template_id:
                    raise ValueError(f"{box_type['type_code']} 缺少 branch template 绑定")
                branch_template = self.library.plug_branch_templates[branch_template_id]
                points, plug_cursor = self._allocate_template_points(
                    template=branch_template,
                    variable_device_suffix=str(board_device_no),
                    address_cursor=plug_cursor,
                )
                board_model["branches"].append(
                    {
                        "physical_branch_index": 1,
                        "phase_label": "A/B/C",
                        "variable_suffix": "",
                        "variable_device_code": str(board_device_no),
                        "logical_output_count": len(covered_branches),
                        "logical_output_labels": list(covered_branches),
                        "branch_kind": "single_phase_triplet_aggregate",
                        "description": f"插接箱{physical_box_no}",
                        "display_label": f"插接箱{physical_box_no}",
                        "point_template_id": branch_template_id,
                        "point_count": len(points),
                        "points": points,
                    }
                )
            else:
                if not branch_template_id:
                    raise ValueError(f"{box_type['type_code']} 缺少 branch template 绑定")
                branch_template = self.library.plug_branch_templates[branch_template_id]
                if branch_template_id == DUAL_DATASET_TEMPLATE_ID:
                    if board_template_id != DUAL_OUTPUT_BOARD_TEMPLATE_ID or len(covered_branches) != 2:
                        raise ConfigError("双组电参只能用于一拖六板卡（单板双三相输出）。")
                    prefix_groups = self._dual_dataset_prefix_groups(branch_template)
                else:
                    prefix_groups = [list(branch_template["point_prefix_sequence"])] * len(covered_branches)

                for branch_offset, physical_branch_index in enumerate(covered_branches, start=1):
                    variable_suffix = "" if branch_offset == 1 else "_2"
                    variable_device_code = f"{board_device_no}{variable_suffix}"
                    points, plug_cursor = self._allocate_template_prefixes(
                        template=branch_template,
                        prefixes=prefix_groups[branch_offset - 1],
                        variable_device_suffix=variable_device_code,
                        address_cursor=plug_cursor,
                        dataset_group=branch_offset if branch_template_id == DUAL_DATASET_TEMPLATE_ID else None,
                    )
                    board_model["branches"].append(
                        {
                            "physical_branch_index": physical_branch_index,
                            "variable_suffix": variable_suffix,
                            "variable_device_code": variable_device_code,
                            "description": f"插接箱{physical_box_no}分路{physical_branch_index}",
                            "point_template_id": branch_template_id,
                            "point_count": len(points),
                            "points": points,
                        }
                    )

            box_model["boards"].append(board_model)
            board_device_no += 1

        return box_model, physical_box_no + 1, board_device_no, plug_cursor

    def _derive_branch_coverage(self, board_template_ids: list[str]) -> list[list[Any]]:
        coverage: list[list[Any]] = []
        branch_index = 1
        for board_template_id in board_template_ids:
            board_template = self.library.board_templates[board_template_id]
            if board_template["phase_mode"] == "single_phase_triplet":
                coverage.append(board_template.get("output_phase_sequence", ["A", "B", "C"]))
                continue
            capacity = board_template["branch_capacity"]
            coverage.append(list(range(branch_index, branch_index + capacity)))
            branch_index += capacity
        return coverage

    def _allocate_template_points(
        self,
        template: dict[str, Any],
        variable_device_suffix: str,
        address_cursor: AddressCursor,
    ) -> tuple[list[dict[str, Any]], AddressCursor]:
        return self._allocate_template_prefixes(
            template=template,
            prefixes=list(template["point_prefix_sequence"]),
            variable_device_suffix=variable_device_suffix,
            address_cursor=address_cursor,
        )

    def _allocate_template_prefixes(
        self,
        template: dict[str, Any],
        prefixes: list[str],
        variable_device_suffix: str,
        address_cursor: AddressCursor,
        dataset_group: int | None = None,
    ) -> tuple[list[dict[str, Any]], AddressCursor]:
        points = []
        for prefix in prefixes:
            register_size, data_type_label = self._point_register_size_and_type(prefix, template)
            point = {
                "prefix": prefix,
                "var_name": f"{prefix}{variable_device_suffix}",
                "address": address_cursor.current,
                "register_size": register_size,
                "data_type_label": data_type_label,
            }
            if dataset_group is not None:
                point["dataset_group"] = dataset_group
            points.append(point)
            address_cursor.current += register_size
        return points, address_cursor

    def _dual_dataset_prefix_groups(self, template: dict[str, Any]) -> list[list[str]]:
        prefixes = [str(item) for item in template.get("point_prefix_sequence", [])]
        split_index = int(template.get("dataset_group_split_index", 24) or 24)
        strip_token = str(template.get("secondary_prefix_strip_token", "101_") or "101_")
        if split_index <= 0 or split_index >= len(prefixes):
            raise ConfigError("双组电参模板缺少有效的数据组分界。")
        first_group = prefixes[:split_index]
        second_group = [
            prefix[: -len(strip_token)]
            if strip_token and prefix.endswith(strip_token)
            else prefix
            for prefix in prefixes[split_index:]
        ]
        if not second_group or any(not prefix for prefix in second_group):
            raise ConfigError("双组电参模板的第二组变量前缀无效。")
        return [first_group, second_group]

    def _point_register_size_and_type(self, prefix: str, template: dict[str, Any]) -> tuple[int, str]:
        state_mode = template.get("state_word_mode", "16bit")
        if prefix.startswith("State"):
            if state_mode == "32bit":
                return 2, "32位 无符号二进制"
            return 1, "16位 无符号二进制"
        return 2, "32位 浮点数"

    def _resequence_addresses(
        self,
        model: dict[str, Any],
        main_next_address: int,
        plug_next_address: int | None,
        repeater_next_address: int | None,
        route_address_summary: dict[str, dict[str, int | None]],
    ) -> tuple[int, int | None, int | None]:
        address_profile = model["profiles"]["address_profile"]
        export_profile = model["profiles"]["export_profile"]
        family = export_profile["family"]
        is_liquidcool_profile = (
            export_profile.get("id") == "classic_combined_liquidcool_default"
            or export_profile.get("subtype") == "liquidcool_hybrid"
        )

        repeater_base = address_profile.get("repeater_base")
        if family == "extended_split" and repeater_base is not None:
            register_step = address_profile.get("register_step", 2)
            route_models_by_name = {route_model["route"]: route_model for route_model in model["routes"]}
            route_nexts: list[int] = []
            for route_name, route_base in (("A", repeater_base), ("B", repeater_base + 100)):
                route_model = route_models_by_name.get(route_name)
                if not route_model or not route_model.get("repeater_units"):
                    continue
                route_cursor = AddressCursor(route_base, register_step)
                for repeater in route_model["repeater_units"]:
                    self._reassign_points(repeater["points"], route_cursor)
                route_nexts.append(route_cursor.current)
                if route_name in route_address_summary:
                    route_address_summary[route_name]["repeater_next_address"] = route_cursor.current
            if route_nexts:
                return main_next_address, plug_next_address, max(route_nexts)

        if family != "classic_combined":
            return main_next_address, plug_next_address, repeater_next_address

        main_cursor = AddressCursor(address_profile["main_base"], address_profile.get("register_step", 2))
        separate_plug_base = address_profile.get("plug_base")
        plug_cursor = (
            AddressCursor(separate_plug_base, address_profile.get("register_step", 2))
            if separate_plug_base is not None
            else main_cursor
        )
        measurement_layout_mode = str(
            model.get("protocol_layout", {}).get("measurement_layout_mode") or "by_plug_box"
        )
        primary_outputs_per_route = model.get("protocol_layout", {}).get(
            "downstream_primary_outputs_per_route"
        )
        extension_base = model.get("protocol_layout", {}).get(
            "downstream_extension_base_address"
        )
        segmented_branch_addresses = (
            measurement_layout_mode == "by_branch"
            and separate_plug_base is not None
            and primary_outputs_per_route is not None
            and extension_base is not None
        )
        extension_cursor = (
            AddressCursor(int(extension_base), address_profile.get("register_step", 2))
            if segmented_branch_addresses
            else None
        )
        repeater_cursor = AddressCursor(repeater_base, address_profile.get("register_step", 2)) if repeater_base is not None else None

        for route_model in model["routes"]:
            for start_box in route_model["start_boxes"]:
                self._reassign_points(start_box["points"], main_cursor)

        for route_model in model["routes"]:
            route_output_index = 0
            for physical_box in route_model["physical_plug_boxes"]:
                for board in physical_box["boards"]:
                    for branch in board["branches"]:
                        points = branch.get("points", [])
                        if points:
                            route_output_index += 1
                            target_cursor = (
                                extension_cursor
                                if segmented_branch_addresses
                                and extension_cursor is not None
                                and route_output_index > int(primary_outputs_per_route)
                                else plug_cursor
                            )
                            self._reassign_points(points, target_cursor)
            route_name = route_model.get("route")
            if route_name in route_address_summary and separate_plug_base is not None:
                route_address_summary[route_name]["plug_next_address"] = plug_cursor.current
                if extension_cursor is not None:
                    route_address_summary[route_name]["plug_extension_next_address"] = extension_cursor.current

        if repeater_cursor is not None:
            if is_liquidcool_profile:
                route_models_by_name = {route_model["route"]: route_model for route_model in model["routes"]}
                max_repeater_count = max((len(route_model["repeater_units"]) for route_model in model["routes"]), default=0)
                repeater_entries = []
                for slot_index in range(max_repeater_count):
                    for route_name in ("A", "B"):
                        route_model = route_models_by_name.get(route_name)
                        if not route_model or slot_index >= len(route_model["repeater_units"]):
                            continue
                        repeater_entries.append(route_model["repeater_units"][slot_index])
            else:
                repeater_entries = [
                    repeater
                    for route_model in model["routes"]
                    for repeater in route_model["repeater_units"]
                ]
            for repeater in repeater_entries:
                self._reassign_points(repeater["points"], repeater_cursor)

        if extension_cursor is not None:
            model["downstream_address_segments"] = {
                "primary_base": int(separate_plug_base),
                "primary_next_address": plug_cursor.current,
                "primary_outputs_per_route": int(primary_outputs_per_route),
                "extension_base": int(extension_base),
                "extension_next_address": extension_cursor.current,
            }

        return (
            main_cursor.current,
            plug_cursor.current if separate_plug_base is not None else None,
            repeater_cursor.current if repeater_cursor is not None else None,
        )

    def _build_single_cabinet_rows(
        self,
        config: dict[str, Any],
        address_cursor: AddressCursor,
        selected_template_id: str | None,
    ) -> tuple[list[dict[str, Any]], AddressCursor, list[str]]:
        aggregation_cfg = config.get("devices", {}).get("single_cabinet_aggregation", {})
        if not aggregation_cfg.get("enabled"):
            return [], address_cursor, []

        column_1_count, column_2_count = self._single_cabinet_column_counts(aggregation_cfg)
        cabinet_count = column_1_count + column_2_count
        if cabinet_count <= 0:
            return [], address_cursor, []

        template_id = selected_template_id
        if template_id is None:
            templates = self.library.device_library.get("single_cabinet_templates", [])
            template_id = templates[0]["id"] if templates else None

        template_map = {item["id"]: item for item in self.library.device_library.get("single_cabinet_templates", [])}
        template = template_map.get(template_id) if template_id else None
        metric_sequence = list((template or {}).get("metric_sequence") or [])
        metric_definitions = dict((template or {}).get("metric_definitions") or {})

        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        metric_base_addresses = aggregation_cfg.get("metric_base_addresses", {})
        metric_next_addresses: list[int] = []
        include_route_data = aggregation_cfg.get("include_route_data") is True
        include_total_power_energy = (
            aggregation_cfg.get("include_total_power_energy") is True
        )
        route_split_metric_codes = {"IA", "PA", "EA"}

        if not metric_sequence:
            metric_sequence = ["IA"]
        if not metric_definitions:
            metric_definitions = {
                "IA": {
                    "register_size": 2,
                    "data_type_label": "32位 浮点数",
                    "description_suffix": "总电流",
                    "unit": "A",
                }
            }

        def cabinet_variable_metric_code(metric_code: str, screen_column: int) -> str:
            if screen_column == 2 and metric_code.endswith("A"):
                return f"{metric_code[:-1]}B"
            return metric_code

        def append_cabinet_row(
            *,
            cabinet_index: int,
            display_cabinet_index: int,
            screen_column: int,
            metric_code: str,
            variable_metric_code: str,
            data_scope: str,
            route: str | None,
            address: int,
            register_size: int,
            data_type_label: str,
            channel_name: str,
            description_suffix: str,
            unit: str | None,
        ) -> None:
            column_label = "第一列" if screen_column == 1 else "第二列"
            cabinet_prefix = (
                f"{column_label}{display_cabinet_index}#机柜"
                if column_2_count > 0
                else f"{cabinet_index}#机柜"
            )
            if route:
                route_suffix = (
                    description_suffix[1:]
                    if description_suffix.startswith("总")
                    else description_suffix
                )
                description = f"{cabinet_prefix}{route}路{route_suffix}"
            else:
                description = f"{cabinet_prefix}{description_suffix}"
            rows.append(
                {
                    "cabinet_index": cabinet_index,
                    "display_cabinet_index": display_cabinet_index,
                    "screen_column": screen_column,
                    "metric_code": metric_code,
                    "variable_metric_code": variable_metric_code,
                    "template_id": template_id,
                    "var_name": f"{variable_metric_code}{display_cabinet_index:02d}",
                    "address": address,
                    "register_size": register_size,
                    "data_type_label": data_type_label,
                    "channel_name": channel_name,
                    "description": description,
                    "unit": unit,
                    "data_scope": data_scope,
                    "route": route,
                }
            )

        for metric_code in metric_sequence:
            metric_meta = metric_definitions.get(metric_code, {})
            register_size = int(metric_meta.get("register_size", 2))
            data_type_label = str(metric_meta.get("data_type_label", "32位 浮点数"))
            channel_name = metric_meta.get("channel_name", "只读4DF")
            description_suffix = str(metric_meta.get("description_suffix", metric_code))
            unit = metric_meta.get("unit")
            configured_metric_base = (
                metric_base_addresses.get(metric_code)
                if isinstance(metric_base_addresses, dict)
                else None
            )
            if configured_metric_base is not None:
                requested_metric_base = int(configured_metric_base)
                occupied_next_address = max(
                    address_cursor.current,
                    *metric_next_addresses,
                ) if metric_next_addresses else address_cursor.current
                effective_metric_base = max(
                    requested_metric_base,
                    occupied_next_address,
                )
                if effective_metric_base != requested_metric_base:
                    warnings.append(
                        f"单机柜 {metric_code} 基址 {requested_metric_base} 与前序数据重叠，"
                        f"已顺延至 {effective_metric_base}。"
                    )
                metric_cursor = AddressCursor(
                    effective_metric_base,
                    address_cursor.step,
                )
            else:
                metric_cursor = address_cursor
            for cabinet_index in range(1, cabinet_count + 1):
                screen_column = 1 if cabinet_index <= column_1_count else 2
                display_cabinet_index = (
                    cabinet_index
                    if screen_column == 1
                    else cabinet_index - column_1_count
                )
                total_metric_code = cabinet_variable_metric_code(
                    metric_code,
                    screen_column,
                )
                append_cabinet_row(
                    cabinet_index=cabinet_index,
                    display_cabinet_index=display_cabinet_index,
                    screen_column=screen_column,
                    metric_code=metric_code,
                    variable_metric_code=total_metric_code,
                    data_scope="total",
                    route=None,
                    address=metric_cursor.current,
                    register_size=register_size,
                    data_type_label=data_type_label,
                    channel_name=channel_name,
                    description_suffix=description_suffix,
                    unit=unit,
                )
                metric_cursor.current += register_size
                if include_route_data and metric_code in route_split_metric_codes:
                    for route in ("A", "B"):
                        append_cabinet_row(
                            cabinet_index=cabinet_index,
                            display_cabinet_index=display_cabinet_index,
                            screen_column=screen_column,
                            metric_code=metric_code,
                            variable_metric_code=f"{total_metric_code}{route}",
                            data_scope=f"route_{route}",
                            route=route,
                            address=metric_cursor.current,
                            register_size=register_size,
                            data_type_label=data_type_label,
                            channel_name=channel_name,
                            description_suffix=description_suffix,
                            unit=unit,
                        )
                        metric_cursor.current += register_size
            if configured_metric_base is not None:
                metric_next_addresses.append(metric_cursor.current)
            else:
                address_cursor = metric_cursor
        if metric_next_addresses:
            address_cursor.current = max(address_cursor.current, *metric_next_addresses)

        if include_total_power_energy:
            screen_total_rows = (
                ("P", "总功率", "KW"),
                ("E", "总电能", "KWH"),
            )
            for variable_name, description, unit in screen_total_rows:
                rows.append(
                    {
                        "cabinet_index": None,
                        "display_cabinet_index": None,
                        "screen_column": None,
                        "metric_code": variable_name,
                        "variable_metric_code": variable_name,
                        "template_id": template_id,
                        "var_name": variable_name,
                        "address": address_cursor.current,
                        "register_size": 2,
                        "data_type_label": "32位 浮点数",
                        "channel_name": "只读4DF",
                        "description": f"整屏{description}",
                        "unit": unit,
                        "data_scope": "screen_total",
                        "route": None,
                    }
                )
                address_cursor.current += 2

        return rows, address_cursor, warnings

    def _reassign_points(self, points: list[dict[str, Any]], cursor: AddressCursor) -> None:
        for point in points:
            point["address"] = cursor.current
            register_size = point.get("register_size")
            if register_size is None:
                register_size = 1 if point.get("data_type_label") == "16位 无符号二进制" else 2
                point["register_size"] = register_size
            cursor.current += register_size
