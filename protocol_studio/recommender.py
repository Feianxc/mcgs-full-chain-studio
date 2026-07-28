from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from mvp_generator.library import PROTOCOL_RESOURCES_ROOT, TemplateLibrary


EXAMPLES_ROOT = PROTOCOL_RESOURCES_ROOT / "examples"
EXAMPLE_PATHS = {
    "classic_combined": EXAMPLES_ROOT / "project-config.example.json",
    "extended_split": EXAMPLES_ROOT / "project-config.extended.example.json",
    "ab_screen_split": EXAMPLES_ROOT / "project-config.ab.example.json",
}

FAMILY_ORDER = ("classic_combined", "extended_split", "ab_screen_split")
RENDER_VARIANT_LABELS = {
    "classic_standard": "classic 标准视图",
    "classic_two_columns": "classic 单屏双列视图",
    "classic_liquidcool": "classic 液冷视图",
    "extended_standard": "extended 拆分页视图",
    "ab_screen_standard": "A/B 分屏视图",
}

PATCH_TAG_LABELS = {
    "merge_start_and_plug": "始端箱与插接箱合并页",
    "include_repeater_sheet": "含中继页",
    "include_single_cabinet_sheet": "含单机柜页",
    "hide_repeater_sheet": "不含中继页",
    "separate_start_and_plug": "始端箱 / 插接箱拆分页",
    "split_ab_screens": "A/B 分屏导出",
    "hybrid_threshold_alarm": "阈值 + 状态混合报警",
}

PROFILE_SELECTION_BUNDLE_KEYS = (
    "address_profile_id",
    "start_box_template_id",
    "plug_branch_template_id",
    "repeater_template_id",
    "single_cabinet_template_id",
)

FAMILY_ALLOWED_TOPOLOGIES = {
    "classic_combined": {
        "single_screen_one_column",
        "single_screen_two_columns",
        "single_screen_half_channel",
    },
    "extended_split": {
        "single_screen_half_channel",
        "single_screen_one_column",
        "single_screen_two_columns",
    },
    "ab_screen_split": {"dual_screens_ab_separated"},
}

LIQUIDCOOL_ADDRESS_PROFILE_ID = "classic_liquidcool_main1000_repeater5000_cabinet7000_alarm6000_32bit"
LIQUIDCOOL_EXPORT_PROFILE_ID = "classic_combined_liquidcool_default"
CLASSIC_CABINET_EXPORT_PROFILE_ID = "classic_combined_cabinet_default"
CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID = "classic_combined_two_columns_default"
LIQUIDCOOL_EXPORT_SUBTYPE = "liquidcool_hybrid"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def example_configs() -> dict[str, dict[str, Any]]:
    return {
        family: load_json(path)
        for family, path in EXAMPLE_PATHS.items()
        if path.exists()
    }


def family_of_config(config: dict[str, Any], library: TemplateLibrary) -> str | None:
    export_profile_id = config.get("profiles", {}).get("export_profile_id")
    export_profile = library.export_profile_map.get(export_profile_id)
    if export_profile:
        return export_profile.get("family")
    return config.get("export_family")


def export_profile_of_config(config: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    export_profile_id = config.get("profiles", {}).get("export_profile_id")
    return deepcopy(library.export_profile_map.get(export_profile_id, {}))


def render_variant_of_export_profile(
    export_profile: dict[str, Any],
    *,
    topology_mode: str | None = None,
) -> str | None:
    family = export_profile.get("family")
    explicit_variant = str(export_profile.get("render_variant_id") or "").strip()
    if explicit_variant:
        return explicit_variant
    if export_profile.get("id") == LIQUIDCOOL_EXPORT_PROFILE_ID or export_profile.get("subtype") == LIQUIDCOOL_EXPORT_SUBTYPE:
        return "classic_liquidcool"
    if family == "classic_combined" and (
        export_profile.get("subtype") == "single_screen_two_columns" or topology_mode == "single_screen_two_columns"
    ):
        return "classic_two_columns"
    if family == "classic_combined":
        return "classic_standard"
    return None


def export_profile_patch_flags(export_profile: dict[str, Any]) -> dict[str, Any]:
    sheet_order = list(export_profile.get("sheet_order", []))
    include_repeater_sheet = export_profile.get("include_repeater_sheet")
    if include_repeater_sheet is None:
        include_repeater_sheet = any(sheet in {"中继器", "中继单元", "连接器测温"} for sheet in sheet_order)
    return {
        "sheet_order": sheet_order,
        "include_repeater_sheet": bool(include_repeater_sheet),
        "include_single_cabinet_sheet": bool(export_profile.get("include_single_cabinet_sheet")),
        "split_ab_screens": bool(export_profile.get("split_ab_screens")),
        "merge_start_and_plug": bool(export_profile.get("merge_start_and_plug")),
    }


def export_profile_patch_labels(export_profile: dict[str, Any]) -> list[str]:
    explicit_tags = [str(item).strip() for item in export_profile.get("patch_tags", []) if str(item).strip()]
    if explicit_tags:
        return [PATCH_TAG_LABELS.get(tag, tag) for tag in explicit_tags]
    patch_flags = export_profile_patch_flags(export_profile)
    labels: list[str] = []
    if patch_flags["split_ab_screens"]:
        labels.append(PATCH_TAG_LABELS["split_ab_screens"])
    elif patch_flags["merge_start_and_plug"]:
        labels.append(PATCH_TAG_LABELS["merge_start_and_plug"])
    if patch_flags["include_repeater_sheet"]:
        labels.append(PATCH_TAG_LABELS["include_repeater_sheet"])
    if patch_flags["include_single_cabinet_sheet"]:
        labels.append(PATCH_TAG_LABELS["include_single_cabinet_sheet"])
    if patch_flags["sheet_order"]:
        labels.append(f"页面 {' / '.join(patch_flags['sheet_order'])}")
    return labels


def export_profile_baseline_bundle(export_profile: dict[str, Any]) -> dict[str, Any]:
    bundle = dict(export_profile.get("baseline_profile_bundle") or {})
    return {key: value for key, value in bundle.items() if value not in (None, "")}


def bundle_profile_ids(export_profile: dict[str, Any]) -> dict[str, Any]:
    profile_ids = {"export_profile_id": export_profile["id"]}
    for key in PROFILE_SELECTION_BUNDLE_KEYS:
        value = export_profile_baseline_bundle(export_profile).get(key)
        if value not in (None, ""):
            profile_ids[key] = value
    return profile_ids


def rank_address_profile_candidates(
    library: TemplateLibrary,
    *,
    family: str,
    alarm_word_mode: str | None = None,
    prefer_repeater: bool | None = None,
    prefer_cabinet: bool | None = None,
    prefer_plug_base: bool | None = None,
    baseline_profile_id: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    normalized_alarm_mode = str(alarm_word_mode or "").strip().lower()
    for profile in library.address_profiles.get("profiles", []):
        if profile.get("family") != family:
            continue
        score = 0
        if baseline_profile_id and profile.get("id") == baseline_profile_id:
            score += 14
        if normalized_alarm_mode:
            profile_alarm_mode = str(profile.get("alarm_word_mode") or "").strip().lower()
            if profile_alarm_mode != normalized_alarm_mode:
                continue
            score += 30

        has_repeater = profile.get("repeater_base") is not None
        has_cabinet = profile.get("cabinet_base") is not None
        has_plug_base = profile.get("plug_base") is not None

        if prefer_repeater is not None:
            score += 12 if has_repeater == prefer_repeater else -8
        if prefer_cabinet is not None:
            score += 14 if has_cabinet == prefer_cabinet else -10
        if prefer_plug_base is not None:
            score += 10 if has_plug_base == prefer_plug_base else -6

        score += len(profile.get("evidence_files", []) or [])
        candidates.append({"profile": profile, "score": score})

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def select_address_profile(
    export_profile: dict[str, Any],
    signals: dict[str, Any],
    library: TemplateLibrary,
) -> dict[str, Any] | None:
    family = str(export_profile.get("family") or "").strip()
    if not family:
        return None

    bundle = export_profile_baseline_bundle(export_profile)
    baseline_profile = library.address_profile_map.get(bundle.get("address_profile_id"), {})
    baseline_profile_id = baseline_profile.get("id")
    baseline_alarm_mode = baseline_profile.get("alarm_word_mode")
    render_variant_id = render_variant_of_export_profile(export_profile, topology_mode=signals.get("topology_mode"))

    if family != "classic_combined":
        return baseline_profile or None
    if render_variant_id in {"classic_liquidcool", "classic_two_columns"}:
        return baseline_profile or None

    prefer_cabinet = (
        bool(export_profile.get("include_single_cabinet_sheet"))
        and signals.get("single_cabinet_enabled")
        and signals.get("cabinet_count", 0) > 0
    )
    prefer_repeater = bool(signals.get("repeater_enabled")) and signals.get("repeater_count", 0) > 0

    candidates = rank_address_profile_candidates(
        library,
        family=family,
        alarm_word_mode=str(baseline_alarm_mode or "") or None,
        prefer_repeater=prefer_repeater,
        prefer_cabinet=prefer_cabinet,
        prefer_plug_base=False,
        baseline_profile_id=str(baseline_profile_id or "") or None,
    )
    if candidates:
        return candidates[0]["profile"]
    return baseline_profile or None


def _route_totals(config: dict[str, Any], library: TemplateLibrary, route: str) -> dict[str, int]:
    route_config = config.get("devices", {}).get("plug_boxes", {}).get(route, {})
    sequence = route_config.get("sequence", [])
    totals = {
        "physical_boxes": 0,
        "boards": 0,
        "branches": 0,
    }
    for item in sequence:
        count = max(0, int(item.get("count", 0) or 0))
        if count <= 0:
            continue
        type_code = item.get("type_code")
        if not type_code:
            continue
        try:
            box_type = library.get_box_type(str(type_code))
        except Exception:  # noqa: BLE001
            continue
        pattern = item.get("layout_pattern") or library.box_type_default_layout(box_type)
        layout = next(
            (candidate for candidate in box_type.get("allowed_layout_patterns", []) if candidate["pattern"] == pattern),
            None,
        )
        totals["physical_boxes"] += count
        totals["boards"] += count * int((layout or {}).get("board_count", 0))
        totals["branches"] += count * int((layout or {}).get("branch_count", 0))
    return totals


def summarize_recommendation_signals(config: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    topology = config.get("topology", {})
    devices = config.get("devices", {})
    communication = config.get("communication", {})
    profiles = config.get("profiles", {})

    repeater = devices.get("repeater_units", {})
    cabinets = devices.get("single_cabinet_aggregation", {})
    repeater_count = int(repeater.get("A_count", 0) or 0) + int(repeater.get("B_count", 0) or 0)
    cabinet_count = int(cabinets.get("cabinet_count", 0) or 0)

    route_a = _route_totals(config, library, "A")
    route_b = _route_totals(config, library, "B")
    total_boards = route_a["boards"] + route_b["boards"]
    total_branches = route_a["branches"] + route_b["branches"]
    total_boxes = route_a["physical_boxes"] + route_b["physical_boxes"]

    current_export_profile_id = profiles.get("export_profile_id")
    current_address_profile_id = profiles.get("address_profile_id")
    current_single_cabinet_template_id = profiles.get("single_cabinet_template_id")
    current_export_profile = export_profile_of_config(config, library)
    current_address_profile = library.address_profile_map.get(current_address_profile_id, {})
    current_render_variant_id = render_variant_of_export_profile(
        current_export_profile,
        topology_mode=topology.get("screen_topology_mode"),
    )
    liquidcool_bundle = export_profile_baseline_bundle(
        library.export_profile_map.get(LIQUIDCOOL_EXPORT_PROFILE_ID, {})
    )

    keyword_text = " ".join(
        str(value or "")
        for value in (
            config.get("project_name"),
            config.get("project_code"),
            config.get("protocol_title"),
            repeater.get("alias"),
        )
    ).lower()
    liquidcool_keyword_signal = "液冷" in keyword_text or "liquid" in keyword_text
    liquidcool_profile_signal = (
        current_export_profile_id == LIQUIDCOOL_EXPORT_PROFILE_ID
        or current_address_profile_id == liquidcool_bundle.get("address_profile_id")
        or current_single_cabinet_template_id == liquidcool_bundle.get("single_cabinet_template_id")
        or current_export_profile.get("subtype") == LIQUIDCOOL_EXPORT_SUBTYPE
        or (
            current_export_profile.get("family") == "classic_combined"
            and current_address_profile.get("family") == "classic_combined"
            and current_address_profile.get("repeater_base") == 5000
            and current_address_profile.get("cabinet_base") == 7000
            and current_address_profile.get("alarm_base") == 6000
            and str(current_address_profile.get("alarm_word_mode") or "").lower() == "32bit"
        )
    )
    likely_liquidcool = liquidcool_keyword_signal or liquidcool_profile_signal

    route_binding = topology.get("screen_route_binding")
    topology_mode = topology.get("screen_topology_mode")
    current_family = family_of_config(config, library)
    uses_1p3 = any(
        item.get("type_code") == "1P*3"
        for route in ("A", "B")
        for item in devices.get("plug_boxes", {}).get(route, {}).get("sequence", [])
    )

    return {
        "current_family": current_family,
        "current_export_profile_id": current_export_profile_id,
        "current_render_variant_id": current_render_variant_id,
        "current_address_profile_id": current_address_profile_id,
        "current_export_profile": current_export_profile,
        "current_patch_flags": export_profile_patch_flags(current_export_profile),
        "topology_mode": topology_mode,
        "screen_route_binding": route_binding,
        "screen_count": int(topology.get("screen_count", 1) or 1),
        "columns_per_screen": int(topology.get("columns_per_screen", 1) or 1),
        "upload_port_profile": topology.get("upload_port_profile"),
        "repeater_enabled": bool(repeater.get("enabled")),
        "repeater_count": repeater_count,
        "repeater_alias": repeater.get("alias") or "",
        "single_cabinet_enabled": bool(cabinets.get("enabled")),
        "cabinet_count": cabinet_count,
        "likely_liquidcool": likely_liquidcool,
        "liquidcool_keyword_signal": liquidcool_keyword_signal,
        "liquidcool_profile_signal": liquidcool_profile_signal,
        "total_boards": total_boards,
        "total_branches": total_branches,
        "total_physical_boxes": total_boxes,
        "uses_1p3": uses_1p3,
        "baud_rate": int(communication.get("baud_rate", 9600) or 9600),
        "route_totals": {
            "A": route_a,
            "B": route_b,
        },
    }


def rank_export_profile_candidates(signals: dict[str, Any], library: TemplateLibrary) -> list[dict[str, Any]]:
    topology_mode = signals.get("topology_mode")
    route_binding = signals.get("screen_route_binding")
    prefer_ab_screen = topology_mode == "dual_screens_ab_separated" or route_binding == "A_screen_and_B_screen_separate"
    prefer_classic_cabinet = (
        signals.get("single_cabinet_enabled")
        and signals.get("cabinet_count", 0) > 0
        and topology_mode == "single_screen_one_column"
        and not signals.get("likely_liquidcool")
        and not prefer_ab_screen
    )
    candidates: list[dict[str, Any]] = []

    for export_profile in library.export_profiles.get("profiles", []):
        export_profile_id = export_profile["id"]
        family = export_profile.get("family")
        render_variant_id = render_variant_of_export_profile(export_profile, topology_mode=topology_mode)
        patch_flags = export_profile_patch_flags(export_profile)
        score = 0
        reasons: list[str] = []

        if signals.get("current_export_profile_id") == export_profile_id:
            score += 10
            reasons.append("保留当前导出 profile 作为弱偏好。")
        if signals.get("current_render_variant_id") and signals.get("current_render_variant_id") == render_variant_id:
            score += 6
            reasons.append("保留当前渲染变体作为弱偏好。")

        if prefer_ab_screen:
            if patch_flags["split_ab_screens"]:
                score += 240
                reasons.append("检测到 A/B 分屏拓扑，优先推荐 A/B 分屏导出 profile。")
            else:
                score -= 60
        elif patch_flags["split_ab_screens"]:
            score -= 25

        if signals.get("liquidcool_profile_signal"):
            if export_profile_id == LIQUIDCOOL_EXPORT_PROFILE_ID:
                score += 260
                reasons.append("当前配置已落在 classic liquidcool 子型 profile/template 上，应保持该闭环。")
            elif family == "classic_combined":
                score += 6
        elif signals.get("likely_liquidcool"):
            if render_variant_id == "classic_liquidcool":
                score += 180
                reasons.append("项目名称/标题命中液冷关键词，优先推荐 classic 液冷视图。")
            elif family == "classic_combined":
                score += 6
        elif render_variant_id == "classic_liquidcool":
            score -= 20

        if topology_mode == "single_screen_two_columns":
            if render_variant_id == "classic_two_columns":
                score += 190
                reasons.append("单屏双列项目更接近 classic 双列视图。")
            elif family == "classic_combined" and render_variant_id == "classic_standard":
                score += 12
        elif render_variant_id == "classic_two_columns":
            score -= 16

        if topology_mode == "single_screen_one_column" and family == "classic_combined" and render_variant_id == "classic_standard":
            score += 26
            reasons.append("单屏单列是 classic 标准视图的典型场景。")

        if topology_mode == "single_screen_half_channel":
            if family == "extended_split":
                score += 26
                reasons.append("半列母线项目通常更适合使用扩展拆分页。")
            elif family == "classic_combined":
                score += 8

        if signals.get("single_cabinet_enabled") and signals.get("cabinet_count", 0) > 0:
            if patch_flags["include_single_cabinet_sheet"]:
                score += 40
                reasons.append("启用了单机柜数据，需要带单机柜页的导出 profile。")
            else:
                score -= 24
            if prefer_classic_cabinet and export_profile_id == CLASSIC_CABINET_EXPORT_PROFILE_ID:
                score += 130
                reasons.append("单屏单列 + 单机柜数据项目可直接收敛到 classic 标准视图 + 单机柜 patch。")
            elif family == "extended_split" and patch_flags["include_single_cabinet_sheet"]:
                score += 30
                reasons.append("拆分页也能较好承载单机柜工作表。")
        elif patch_flags["include_single_cabinet_sheet"]:
            score -= 6

        if signals.get("repeater_enabled") and signals.get("repeater_count", 0) > 0:
            if patch_flags["include_repeater_sheet"]:
                score += 18
                reasons.append("启用了中继/连接器测温，需要带中继页的导出 profile。")
            else:
                score -= 28
            if family == "extended_split" and patch_flags["include_repeater_sheet"]:
                score += 8
                reasons.append("extended 可将中继独立分页，更利于大项目审阅。")
        elif patch_flags["include_repeater_sheet"]:
            score -= 4

        if signals.get("repeater_alias") in {"中继单元", "连接器测温"}:
            if family == "extended_split" and patch_flags["include_repeater_sheet"]:
                score += 8
                reasons.append("中继别名更接近拆分页风格。")
            elif signals.get("repeater_alias") == "连接器测温" and family == "classic_combined" and patch_flags["include_repeater_sheet"]:
                score += 8
                reasons.append("连接器测温仍可放入 classic 的中继页，兼容标准单页模板。")

        if signals.get("total_boards", 0) >= 12 or signals.get("total_physical_boxes", 0) >= 10:
            if family == "extended_split":
                score += 12
                reasons.append("板卡/物理箱数量较多，拆分页更利于审阅和导出。")
            elif family == "classic_combined":
                score += 3
        elif family == "classic_combined":
            score += 8
            reasons.append("项目规模较轻，classic 合并页更紧凑。")

        if signals.get("screen_count", 1) >= 2 and signals.get("columns_per_screen", 1) >= 2 and patch_flags["split_ab_screens"]:
            score += 18
            reasons.append("多屏 + 每屏两列的结构更接近 A/B 分屏样式。")

        candidates.append(
            {
                "family": family,
                "export_profile_id": export_profile_id,
                "display_label": export_profile.get("display_label", export_profile_id),
                "render_variant_id": render_variant_id,
                "render_variant_label": RENDER_VARIANT_LABELS.get(render_variant_id, render_variant_id),
                "patch_flags": patch_flags,
                "patch_labels": export_profile_patch_labels(export_profile),
                "score": score,
                "reasons": reasons,
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def rank_family_candidates(signals: dict[str, Any], export_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_family: dict[str, dict[str, Any]] = {}
    for candidate in export_candidates:
        family = candidate["family"]
        current = best_by_family.get(family)
        if current is None or candidate["score"] > current["score"]:
            best_by_family[family] = candidate

    candidates: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        best = best_by_family.get(family)
        if best is None:
            continue
        reasons = [f"族内最佳导出视图为“{best['display_label']}”。", *best["reasons"]]
        candidates.append(
            {
                "family": family,
                "score": best["score"],
                "reasons": reasons,
                "export_profile_id": best["export_profile_id"],
                "render_variant_id": best.get("render_variant_id"),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def recommendation_confidence(candidates: list[dict[str, Any]]) -> str:
    if len(candidates) < 2:
        return "high"
    gap = candidates[0]["score"] - candidates[1]["score"]
    if gap >= 50:
        return "high"
    if gap >= 20:
        return "medium"
    return "low"


def _profile_ids_from_example(family: str) -> dict[str, Any]:
    config = example_configs()[family]
    return deepcopy(config.get("profiles", {}))


def recommend_profile_ids(
    export_profile_id: str,
    signals: dict[str, Any],
    library: TemplateLibrary,
) -> tuple[dict[str, Any], list[str]]:
    export_profile = library.export_profile_map[export_profile_id]
    family = str(export_profile.get("family"))
    profile_ids = {
        key: value
        for key, value in _profile_ids_from_example(family).items()
        if key not in PROFILE_SELECTION_BUNDLE_KEYS
    }
    profile_ids.update(bundle_profile_ids(export_profile))
    reasons: list[str] = []
    render_variant_id = render_variant_of_export_profile(export_profile, topology_mode=signals.get("topology_mode"))
    address_profile = select_address_profile(export_profile, signals, library)
    bundle = export_profile_baseline_bundle(export_profile)
    baseline_address_id = str(bundle.get("address_profile_id") or "").strip()
    if address_profile:
        profile_ids["address_profile_id"] = address_profile["id"]

    if render_variant_id == "classic_liquidcool":
        reasons.append("液冷项目优先沿用 classic liquidcool 视图的 baseline bundle。")
    elif render_variant_id == "classic_two_columns":
        reasons.append("单屏双列项目优先沿用双列表头视图的 baseline bundle。")
    elif export_profile_id == CLASSIC_CABINET_EXPORT_PROFILE_ID:
        reasons.append("启用单机柜数据时，推荐带单机柜页的 classic 标准 patch。")
    elif family == "extended_split":
        reasons.append("扩展拆分页优先沿用拆分页标准 bundle。")
    elif family == "ab_screen_split":
        reasons.append("A/B 分屏当前沿用分屏标准 bundle。")
    else:
        reasons.append("当前导出 profile 其余模板沿用该视图的 baseline bundle。")

    if address_profile and address_profile["id"] != baseline_address_id:
        if address_profile.get("cabinet_base") is not None:
            reasons.append("按单机柜数据场景，地址 profile 自动切到含 cabinet_base 的方案。")
        elif address_profile.get("repeater_base") is not None:
            reasons.append("按中继/连接器测温场景，地址 profile 自动切到含 repeater_base 的方案。")
        else:
            reasons.append("当前无中继页需求，地址 profile 收敛到精简主/报警方案。")

    return profile_ids, reasons


def build_recommended_config(
    config: dict[str, Any],
    family: str,
    profile_ids: dict[str, Any],
) -> dict[str, Any]:
    base = deepcopy(example_configs()[family])
    current = deepcopy(config)

    base["project_name"] = current.get("project_name") or base.get("project_name")
    base["project_code"] = current.get("project_code") or base.get("project_code")
    base["protocol_title"] = current.get("protocol_title") or base.get("protocol_title")
    base["communication"] = deepcopy(current.get("communication", base.get("communication", {})))
    base["devices"] = deepcopy(current.get("devices", base.get("devices", {})))
    base["topology"] = deepcopy(base.get("topology", {}))
    base["topology"]["canonical_column_id"] = current.get("topology", {}).get(
        "canonical_column_id",
        base["topology"].get("canonical_column_id"),
    )
    base["topology"]["upload_port_profile"] = current.get("topology", {}).get(
        "upload_port_profile",
        base["topology"].get("upload_port_profile"),
    )

    current_mode = current.get("topology", {}).get("screen_topology_mode")
    if family == "ab_screen_split":
        base["topology"]["screen_topology_mode"] = "dual_screens_ab_separated"
        base["topology"]["screen_route_binding"] = "A_screen_and_B_screen_separate"
        base["topology"]["screen_count"] = max(2, int(current.get("topology", {}).get("screen_count", 2) or 2))
        base["topology"]["columns_per_screen"] = max(2, int(current.get("topology", {}).get("columns_per_screen", 2) or 2))
    else:
        if current_mode in FAMILY_ALLOWED_TOPOLOGIES[family]:
            base["topology"]["screen_topology_mode"] = current_mode
        base["topology"]["screen_route_binding"] = "both_routes_in_one_screen"
        base["topology"]["screen_count"] = max(1, int(current.get("topology", {}).get("screen_count", 1) or 1))
        base["topology"]["columns_per_screen"] = max(1, int(current.get("topology", {}).get("columns_per_screen", 1) or 1))
        if current_mode == "single_screen_two_columns":
            base["topology"]["columns_per_screen"] = max(2, base["topology"]["columns_per_screen"])
            if not base["topology"].get("upload_port_profile") or base["topology"]["upload_port_profile"] == "A4B4":
                base["topology"]["upload_port_profile"] = "A3B3"

    base["export_family"] = family
    base["profiles"] = deepcopy(profile_ids)
    base["profiles"]["device_library_id"] = current.get("profiles", {}).get(
        "device_library_id",
        base["profiles"].get("device_library_id"),
    )
    return base


def diff_profile_selection(current_config: dict[str, Any], recommended_config: dict[str, Any]) -> list[dict[str, Any]]:
    current_profiles = current_config.get("profiles", {})
    next_profiles = recommended_config.get("profiles", {})
    diff: list[dict[str, Any]] = []
    keys = (
        "export_profile_id",
        "address_profile_id",
        "start_box_template_id",
        "plug_branch_template_id",
        "repeater_template_id",
        "single_cabinet_template_id",
    )
    for key in keys:
        before = current_profiles.get(key)
        after = next_profiles.get(key)
        if before != after:
            diff.append(
                {
                    "field": key,
                    "from": before,
                    "to": after,
                }
            )
    current_family = current_config.get("export_family")
    next_family = recommended_config.get("export_family")
    if current_family != next_family:
        diff.insert(
            0,
            {
                "field": "export_family",
                "from": current_family,
                "to": next_family,
            },
        )
    return diff


def recommend_protocol_config(config: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    signals = summarize_recommendation_signals(config, library)
    export_candidates = rank_export_profile_candidates(signals, library)
    best_export = export_candidates[0]
    candidates = rank_family_candidates(signals, export_candidates)
    family = best_export["family"]
    profile_ids, profile_reasons = recommend_profile_ids(best_export["export_profile_id"], signals, library)
    recommended_config = build_recommended_config(config, family, profile_ids)
    changes = diff_profile_selection(config, recommended_config)
    current_patch_flags = signals.get("current_patch_flags", {})
    recommended_patch_flags = best_export.get("patch_flags", {})
    current_profile = signals.get("current_export_profile", {})

    return {
        "current_family": signals.get("current_family"),
        "recommended_family": family,
        "current_export_profile_id": signals.get("current_export_profile_id"),
        "recommended_export_profile_id": best_export["export_profile_id"],
        "current_render_variant_id": signals.get("current_render_variant_id"),
        "recommended_render_variant_id": best_export.get("render_variant_id"),
        "confidence": recommendation_confidence(export_candidates),
        "summary": (
            f"推荐 {family} / {best_export['display_label']}"
            f"{'（' + best_export['render_variant_label'] + '）' if best_export.get('render_variant_label') else ''}"
            f"，原因：{'；'.join(best_export['reasons'][:2]) or '基于当前拓扑与设备规模。'}"
        ),
        "reasons": best_export["reasons"] + profile_reasons,
        "signals": signals,
        "candidates": candidates,
        "export_candidates": export_candidates,
        "recommended_profile_ids": profile_ids,
        "recommended_config": recommended_config,
        "current_template_plan": {
            "family": signals.get("current_family"),
            "export_profile_id": signals.get("current_export_profile_id"),
            "render_variant_id": signals.get("current_render_variant_id"),
            "patch_flags": current_patch_flags,
            "patch_labels": export_profile_patch_labels(current_profile),
        },
        "recommended_template_plan": {
            "family": family,
            "export_profile_id": best_export["export_profile_id"],
            "render_variant_id": best_export.get("render_variant_id"),
            "patch_flags": recommended_patch_flags,
            "patch_labels": best_export.get("patch_labels", []),
        },
        "changes": changes,
    }
