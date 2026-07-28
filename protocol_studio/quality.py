from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvp_generator.validate_rendered_workbook import validate_rendered_workbook_pair


def validate_generated_artifacts(
    canonical_json_path: Path,
    excel_path: Path,
) -> dict[str, Any]:
    canonical_json_path = Path(canonical_json_path)
    excel_path = Path(excel_path)
    try:
        json.loads(canonical_json_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "error": f"读取 canonical JSON 失败: {exc}",
            "canonical_json_path": canonical_json_path.name,
            "excel_path": excel_path.name,
        }

    try:
        validation = validate_rendered_workbook_pair(canonical_json_path, excel_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "error": str(exc),
            "canonical_json_path": canonical_json_path.name,
            "excel_path": excel_path.name,
        }

    return {
        "ok": True,
        "status": "passed",
        "family": validation["family"],
        "message": "validation_ok",
        "canonical_json_path": canonical_json_path.name,
        "excel_path": excel_path.name,
    }
