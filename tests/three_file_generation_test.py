from __future__ import annotations

import csv
import gc
import io
import json
import os
import re
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException
from fastapi.testclient import TestClient


def synthetic_config() -> dict:
    return {
        "workflow_version": "unified_protocol_v1",
        "project": {
            "name": "合成三文件回归",
            "code": "SYNTH-BUNDLE-001",
            "protocol_title": "动环通讯协议",
        },
        "routes": {
            "A": {
                "start_boxes": {"count": 1, "instance_names": ["S1"]},
                "plug_boxes": {
                    "board_number_start": 101,
                    "sequence": [
                        {"type_code": "3P*1", "count": 2, "layout_pattern": "1"},
                    ],
                },
            },
            "B": {"copy_from_A": True},
        },
        "extensions": {
            "single_cabinet": {"enabled": False, "cabinet_count": 0},
            "repeater": {"enabled": False, "A_count": 0, "B_count": 0},
            "alarm_state_word": {
                "enabled": True,
                "base_address": 6100,
                "word_mode": "16bit",
            },
        },
        "program_upload": {
            "device_name": "fixture-upload",
            "driver_component_name": "合成Modbus上传驱动",
            "driver_component_version": "1.0-test",
            "encoding": "gb18030",
        },
        "profiles": {},
    }


def assert_openxml(payload: bytes) -> None:
    assert len(payload) > 1024
    assert payload.startswith(b"PK")
    with ZipFile(BytesIO(payload)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert "xl/workbook.xml" in names
        assert any(name.startswith("xl/worksheets/sheet") for name in names)


def assert_gb18030_csv(payload: bytes, point_count: int) -> None:
    assert payload
    decoded = payload.decode("gb18030")
    assert decoded.encode("gb18030") == payload
    rows = list(csv.reader(io.StringIO(decoded)))
    assert point_count > 0
    assert len(rows) == point_count + 5
    assert rows[4][:4] == ["通道号", "变量名", "变量类型", "通道名称"]
    assert any(row and "组态设备名称" in row[0] for row in rows[:4])
    assert all(any(cell.strip() for cell in row) for row in rows)


def assert_runtime_root_not_exposed(payload: object, runtime_root: Path) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    absolute_markers = {
        str(runtime_root.resolve()),
        str(runtime_root.resolve()).replace("\\", "/"),
    }
    assert not any(marker and marker in serialized for marker in absolute_markers)


def assert_traversal_is_rejected(
    app_module: object,
    client: TestClient,
    runtime_root: Path,
) -> None:
    outside_run = runtime_root / "outside-run"
    outside_run.mkdir()
    canary = outside_run / "delivery-summary.json"
    canary.write_text('{"sentinel":"outside-runs-root"}\n', encoding="utf-8")
    (outside_run / "manifest.json").write_text(
        json.dumps(
            {
                "sentinel": "outside-runs-root",
                "artifacts": {"delivery_path": str(canary.resolve())},
            }
        ),
        encoding="utf-8",
    )

    direct_checks = (
        lambda: app_module.api_run_manifest("../outside-run"),
        lambda: app_module.resolve_run_artifact("../outside-run", "delivery"),
    )
    for check in direct_checks:
        try:
            check()
        except HTTPException as exc:
            assert exc.status_code in {400, 404, 422}
        else:
            raise AssertionError("run_id traversal was accepted by a run artifact resolver")

    escaped = "%2E%2E%5Coutside-run"
    traversal_requests = [
        ("GET", f"/api/runs/{escaped}/manifest"),
        ("GET", f"/api/runs/{escaped}/canonical"),
        ("GET", f"/api/runs/{escaped}/validation"),
        ("GET", f"/api/runs/{escaped}/quality"),
        ("GET", f"/api/runs/{escaped}/compare"),
        ("GET", f"/api/runs/{escaped}/download/delivery"),
        ("DELETE", f"/api/runs/{escaped}"),
    ]
    for method, encoded_path in traversal_requests:
        response = client.request(method, encoded_path, follow_redirects=False)
        assert response.status_code == 404, (method, encoded_path, response.status_code)
        assert response.json() == {"detail": "未找到生成记录"}

    valid_run = Path(app_module.RUNS_ROOT) / "fixture-malicious"
    valid_run.mkdir()
    malicious_manifest = valid_run / "manifest.json"
    for malicious_reference in (
        str(canary.resolve()),
        "../outside-run/delivery-summary.json",
    ):
        malicious_manifest.write_text(
            json.dumps({"artifacts": {"delivery_path": malicious_reference}}),
            encoding="utf-8",
        )
        response = client.get("/api/runs/fixture-malicious/download/delivery")
        assert response.status_code == 404
        assert response.json() == {"detail": "delivery 文件不存在或已被移除"}

    assert canary.read_text(encoding="utf-8") == '{"sentinel":"outside-runs-root"}\n'


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mcgs-three-file-generation-") as temp_dir:
        runtime_root = Path(temp_dir)
        runs_root = runtime_root / "external-runs"
        os.environ.update(
            {
                "PROTOCOL_STUDIO_AUTH_ENABLED": "false",
                "MCGS_FULL_CHAIN_RUNS_ROOT": str(runs_root),
                "PROTOCOL_STUDIO_RUNS_ROOT": str(runs_root),
                "PROTOCOL_STUDIO_SECURITY_DB": str(runtime_root / "unused-security.sqlite3"),
            }
        )

        import protocol_studio.app as app_module

        assert app_module.RUNS_ROOT.resolve() == runs_root.resolve()
        with TestClient(app_module.app, base_url="http://testserver") as client:
            response = client.post("/api/generate", json={"config": synthetic_config()})
            assert response.status_code == 200, response.text
            result = response.json()
            assert_runtime_root_not_exposed(result, runtime_root)

            run_id = result["run_id"]
            assert isinstance(run_id, str)
            assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", run_id)
            assert result["validation"]["status"] == "passed"
            assert result["validation"]["ok"] is True
            assert result["source_compare"]["verdict"] == "skipped"
            assert result["delivery_status"]["status"] == "deliverable"
            bundle = result["delivery_bundle"]
            assert bundle["required_keys"] == ["excel", "alarm_code", "program_upload"]
            assert bundle["status"] == "complete"
            assert bundle["files"]["excel"]["status"] == "generated"
            assert bundle["files"]["alarm_code"]["status"] == "generated"
            assert bundle["files"]["program_upload"]["status"] == "generated"

            downloads = result["downloads"]
            excel = client.get(downloads["excel"])
            alarm = client.get(downloads["alarm_code"])
            program_upload = client.get(downloads["program_upload"])
            delivery = client.get(downloads["delivery"])
            for artifact_response in (excel, alarm, program_upload, delivery):
                assert artifact_response.status_code == 200
                assert artifact_response.content

            assert_openxml(excel.content)
            alarm_text = alarm.content.decode("utf-8")
            assert len(alarm_text.strip()) > 20 and "!GetAlmValue" in alarm_text
            upload_contract = result["program_upload"]
            assert upload_contract["encoding"].lower() == "gb18030"
            assert type(upload_contract["point_count"]) is int
            assert_gb18030_csv(program_upload.content, upload_contract["point_count"])

            delivery_payload = json.loads(delivery.content.decode("utf-8"))
            assert_runtime_root_not_exposed(delivery_payload, runtime_root)
            assert delivery_payload["run_id"] == run_id
            assert delivery_payload["delivery_bundle"]["status"] == "complete"
            assert delivery_payload["delivery_bundle"]["required_keys"] == [
                "excel",
                "alarm_code",
                "program_upload",
            ]

            run_dir = (runs_root / run_id).resolve()
            assert run_dir.is_dir()
            assert run_dir.is_relative_to(runs_root.resolve())
            for key in ("excel_path", "alarm_code_path", "program_upload_path", "delivery_path"):
                public_path = Path(result["artifacts"][key])
                assert not public_path.is_absolute()
                assert ".." not in public_path.parts

            generated_files = {
                "excel": next(run_dir.glob("*.xlsx")),
                "alarm_code": next(run_dir.glob("*报警状态字上传代码.txt")),
                "program_upload": next(run_dir.glob("*.csv")),
                "delivery": run_dir / "delivery-summary.json",
            }
            for artifact_path in generated_files.values():
                assert artifact_path.is_file()
                assert artifact_path.stat().st_size > 0
                assert artifact_path.resolve().is_relative_to(run_dir)

            manifest = client.get(f"/api/runs/{run_id}/manifest")
            assert manifest.status_code == 200
            assert manifest.json()["run_id"] == run_id
            assert_runtime_root_not_exposed(manifest.json(), runtime_root)
            for endpoint in ("canonical", "validation", "quality", "compare"):
                json_response = client.get(f"/api/runs/{run_id}/{endpoint}")
                assert json_response.status_code == 200, endpoint
                assert isinstance(json_response.json(), dict)
                assert_runtime_root_not_exposed(json_response.json(), runtime_root)
            assert len([item for item in runs_root.iterdir() if item.is_dir()]) == 1

            assert_traversal_is_rejected(app_module, client, runtime_root)
        gc.collect()

    print(json.dumps({"status": "passed", "suite": "three_file_generation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
