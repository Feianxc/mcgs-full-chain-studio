from __future__ import annotations

import json

from _test_support import add_repo_to_import_path, configure_process_runtime

add_repo_to_import_path()
configure_process_runtime("mcgs-pointset-contract")

from fastapi.testclient import TestClient

from protocol_studio.app import app


EXPECTED_POINTSETS = {
    "plug_branch_standard_29row_connector_temp": (29, 57, "16bit"),
    "plug_branch_compact_21row": (21, 41, "16bit"),
    "plug_branch_mid_26row_partial_connector": (26, 52, "32bit"),
    "plug_branch_dual_dataset_47row": (47, 94, "32bit"),
    "plug_branch_compact_22row_freq": (22, 43, "16bit"),
    "plug_branch_standard_30row_full_connector": (30, 60, "32bit"),
    "plug_branch_extended_load_reactive": (41, 81, "16bit"),
    "plug_branch_single_phase_triplet_30row_full_connector": (30, 60, "32bit"),
}


def main() -> int:
    client = TestClient(app)
    response = client.get("/api/bootstrap")
    assert response.status_code == 200, response.text
    payload = response.json()

    templates = payload["templates"]["plug_branch_templates"]
    assert isinstance(templates, list)
    by_id = {item["id"]: item for item in templates}
    assert set(by_id) == set(EXPECTED_POINTSETS)

    report: list[dict[str, object]] = []
    for template_id, (point_count, register_count, state_word_mode) in EXPECTED_POINTSETS.items():
        template = by_id[template_id]
        points = template["points"]

        assert isinstance(template["point_count"], int)
        assert isinstance(template["row_span"], int)
        assert isinstance(template["register_footprint"], int)
        assert isinstance(points, list)
        assert template["point_count"] == point_count
        assert template["row_span"] == point_count
        assert template["register_footprint"] == register_count
        assert template["state_word_mode"] == state_word_mode
        assert len(points) == point_count
        assert [point["index"] for point in points] == list(range(1, point_count + 1))

        for point in points:
            assert isinstance(point["index"], int)
            assert isinstance(point["prefix"], str) and point["prefix"]
            assert isinstance(point["variable_pattern"], str) and point["variable_pattern"]
            assert "{设备号}" in point["variable_pattern"]
            assert point["dataset_group"] in {None, 1, 2}
            assert isinstance(point["name"], str) and point["name"]
            assert point["unit"] is None or isinstance(point["unit"], str)
            assert isinstance(point["data_type"], str) and point["data_type"]

        report.append(
            {
                "id": template_id,
                "logical_points": point_count,
                "registers_16bit": register_count,
                "state_word_mode": state_word_mode,
            }
        )

    dual_dataset = by_id["plug_branch_dual_dataset_47row"]["points"]
    assert dual_dataset[0]["variable_pattern"] == "StateC{设备号}"
    assert dual_dataset[23]["variable_pattern"] == "E{设备号}"
    assert dual_dataset[24]["variable_pattern"] == "Ia{设备号}_2"
    assert dual_dataset[-1]["variable_pattern"] == "E{设备号}_2"
    assert [point["dataset_group"] for point in dual_dataset[:24]] == [1] * 24
    assert [point["dataset_group"] for point in dual_dataset[24:]] == [2] * 23
    dual_template = by_id["plug_branch_dual_dataset_47row"]
    assert dual_template["dataset_group_mode"] == "dual_output_board_split"
    assert dual_template["required_board_template_id"] == "board_1to6_3phase_dual"

    print(json.dumps({"status": "passed", "pointsets": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
