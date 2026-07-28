from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROTOCOL_RESOURCES_ROOT = PROJECT_ROOT / "resources" / "protocol"


def resolve_protocol_resources_root() -> Path:
    """Return the versioned protocol resources shipped with this project.

    ``PROTOCOL_STUDIO_RESOURCES_ROOT`` is intentionally optional.  It supports
    read-only packaged deployments without re-introducing a dependency on a
    neighbouring development repository.
    """

    configured = os.environ.get("PROTOCOL_STUDIO_RESOURCES_ROOT", "").strip()
    root = Path(configured).expanduser() if configured else DEFAULT_PROTOCOL_RESOURCES_ROOT
    return root.resolve()


PROTOCOL_RESOURCES_ROOT = resolve_protocol_resources_root()
LIBRARIES_ROOT = PROTOCOL_RESOURCES_ROOT / "libraries"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"协议资源不存在: {path.name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"协议资源根节点必须是 JSON object: {path.name}")
    return payload


@dataclass
class TemplateLibrary:
    device_library: dict[str, Any]
    address_profiles: dict[str, Any]
    export_profiles: dict[str, Any]

    @classmethod
    def load(
        cls,
        device_library_path: Path | None = None,
        address_profiles_path: Path | None = None,
        export_profiles_path: Path | None = None,
    ) -> "TemplateLibrary":
        device_library_path = device_library_path or LIBRARIES_ROOT / "device-library.seed.json"
        address_profiles_path = address_profiles_path or LIBRARIES_ROOT / "address-profiles.seed.json"
        export_profiles_path = export_profiles_path or LIBRARIES_ROOT / "export-profiles.seed.json"
        return cls(
            device_library=load_json(device_library_path),
            address_profiles=load_json(address_profiles_path),
            export_profiles=load_json(export_profiles_path),
        )

    @property
    def plug_branch_templates(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.device_library.get("plug_branch_templates", [])}

    @property
    def start_box_templates(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.device_library.get("start_box_templates", [])}

    @property
    def repeater_templates(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.device_library.get("repeater_templates", [])}

    @property
    def board_templates(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.device_library.get("board_templates", [])}

    @property
    def single_cabinet_templates(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.device_library.get("single_cabinet_templates", [])}

    @property
    def plug_box_types(self) -> dict[str, dict[str, Any]]:
        return {item["type_code"]: item for item in self.device_library.get("plug_box_physical_types", [])}

    @property
    def plug_box_type_aliases(self) -> dict[str, str]:
        aliases = self.device_library.get("entity_aliases", {}).get("plug_box_type_aliases", {})
        return {str(key): str(value) for key, value in aliases.items()}

    @property
    def address_profile_map(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.address_profiles.get("profiles", [])}

    @property
    def export_profile_map(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.export_profiles.get("profiles", [])}

    def first_start_box_template_id(self) -> str:
        return self.device_library["start_box_templates"][0]["id"]

    def first_repeater_template_id(self) -> str | None:
        items = self.device_library.get("repeater_templates", [])
        return items[0]["id"] if items else None

    def normalize_box_type_code(self, type_code: str) -> str:
        normalized = self.plug_box_type_aliases.get(type_code, type_code)
        if normalized not in self.plug_box_types:
            raise KeyError(f"未知插接箱类型: {type_code}")
        return normalized

    def get_box_type(self, type_code: str) -> dict[str, Any]:
        return self.plug_box_types[self.normalize_box_type_code(type_code)]

    def box_type_allowed_layout_tokens(self, box_type: dict[str, Any]) -> list[str]:
        tokens = [item["pattern"] for item in box_type.get("allowed_layout_patterns", [])]
        if box_type.get("phase_mode") == "single_phase_triplet" and "1P3" not in tokens:
            tokens.append("1P3")
        return tokens

    def box_type_default_layout(self, box_type: dict[str, Any]) -> str | None:
        if box_type.get("phase_mode") == "single_phase_triplet":
            return "1P3"
        return box_type.get("default_layout_pattern")

    def box_type_default_branch_template(self, box_type: dict[str, Any]) -> str | None:
        return box_type.get("conservative_default_branch_template")

    def get_layout_variant(self, box_type: dict[str, Any], layout_token: str) -> dict[str, Any]:
        normalized_token = "1" if box_type.get("phase_mode") == "single_phase_triplet" and layout_token == "1P3" else layout_token
        for item in box_type.get("allowed_layout_patterns", []):
            if item["pattern"] == normalized_token:
                return {
                    "pattern": item["pattern"],
                    "layout_token": layout_token,
                    "board_template_sequence": item["board_template_ids"],
                    "branch_coverage": self._derive_branch_coverage(
                        phase_mode=box_type["phase_mode"],
                        board_template_ids=item["board_template_ids"],
                    ),
                }
        raise KeyError(f"未找到布局 {box_type['type_code']}::{layout_token}")

    def _derive_branch_coverage(self, phase_mode: str, board_template_ids: list[str]) -> list[list[int | str]]:
        if phase_mode == "single_phase_triplet":
            return [["A", "B", "C"]]

        coverage: list[list[int]] = []
        next_branch = 1
        for board_template_id in board_template_ids:
            board_template = self.board_templates[board_template_id]
            capacity = int(board_template["branch_capacity"])
            coverage.append(list(range(next_branch, next_branch + capacity)))
            next_branch += capacity
        return coverage
