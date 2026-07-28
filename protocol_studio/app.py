from __future__ import annotations

import json
import hmac
import os
import re
import secrets
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mvp_generator.excel_renderer import ClassicCombinedRenderer, PREFIX_META
from mvp_generator.generator import ProtocolGenerator
from mvp_generator.library import PROTOCOL_RESOURCES_ROOT, TemplateLibrary
from mvp_generator.split_renderers import AbScreenSplitRenderer, ExtendedSplitRenderer
from protocol_studio.alarm_codegen import AlarmCodegenUnsupportedError, generate_alarm_code_from_workbook
from protocol_studio.program_upload import write_program_upload_csv_from_config
from protocol_studio.quality import validate_generated_artifacts
from protocol_studio.recommender import recommend_protocol_config
from protocol_studio.security import (
    LOGIN_CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthSession,
    SecurityManager,
    SecuritySettings,
)
from protocol_studio.source_compare import compare_generated_excel_to_source


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = APP_ROOT / "templates"
STATIC_ROOT = APP_ROOT / "static"
ASSEMBLY_ROOT = WORKSPACE_ROOT / "assembly_studio"
ASSEMBLY_TEMPLATES_ROOT = ASSEMBLY_ROOT / "templates"
ASSEMBLY_STATIC_ROOT = ASSEMBLY_ROOT / "static"
ASSEMBLY_INDEX_PATH = ASSEMBLY_TEMPLATES_ROOT / "index.html"
SECURITY_SETTINGS = SecuritySettings.from_env(WORKSPACE_ROOT)
SECURITY_MANAGER = SecurityManager(SECURITY_SETTINGS)


def resolve_runs_root() -> Path:
    """Keep portable-build output outside PyInstaller's bundled resources."""

    for variable_name in (
        "MCGS_FULL_CHAIN_RUNS_ROOT",
        "PROTOCOL_STUDIO_RUNS_ROOT",
    ):
        configured_root = os.environ.get(variable_name, "").strip()
        if configured_root:
            return Path(configured_root).expanduser().resolve()
    return (APP_ROOT / "runs").resolve()


RUNS_ROOT = resolve_runs_root()
STATIC_ASSET_PATHS = [
    STATIC_ROOT / "studio.css",
    STATIC_ROOT / "workspace-refine.css",
    STATIC_ROOT / "protocol-studio-v2.css",
    STATIC_ROOT / "protocol-studio-precision.css",
    STATIC_ROOT / "protocol-studio-quiet.css",
    STATIC_ROOT / "security.css",
    STATIC_ROOT / "login.css",
    STATIC_ROOT / "app.js",
    STATIC_ROOT / "security.js",
    STATIC_ROOT / "login.js",
    STATIC_ROOT / "favicon.svg",
    STATIC_ROOT / "assets" / "din-rail.svg",
    STATIC_ROOT / "vendor" / "lucide" / "lucide.min.js",
    TEMPLATES_ROOT / "index.html",
    TEMPLATES_ROOT / "login.html",
    ASSEMBLY_INDEX_PATH,
    *ASSEMBLY_STATIC_ROOT.glob("*"),
]
RUNS_ROOT.mkdir(parents=True, exist_ok=True)

EXAMPLES_ROOT = PROTOCOL_RESOURCES_ROOT / "examples"
EXAMPLE_PATHS = {
    "classic_combined": EXAMPLES_ROOT / "project-config.example.json",
    "classic_combined_two_columns": EXAMPLES_ROOT / "project-config.two-columns.example.json",
    "extended_split": EXAMPLES_ROOT / "project-config.extended.example.json",
    "ab_screen_split": EXAMPLES_ROOT / "project-config.ab.example.json",
}
CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID = "classic_combined_two_columns_default"
CLASSIC_DEFAULT_EXPORT_PROFILE_ID = "classic_combined_default"
CLASSIC_CABINET_EXPORT_PROFILE_ID = "classic_combined_cabinet_default"
CLASSIC_DEFAULT_ADDRESS_PROFILE_ID = "classic_with_repeater5500_alarm6000_16bit"
CLASSIC_CABINET_ADDRESS_PROFILE_ID = "classic_with_repeater5500_cabinet7000_alarm6000_16bit"
CLASSIC_DEFAULT_START_BOX_TEMPLATE_ID = "start_box_standard_36row_thd_energy"
CLASSIC_DEFAULT_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_standard_29row_connector_temp"
BRANCH_MODE_START_BOX_TEMPLATE_ID = "start_box_extended_load_unbalance_reactive"
BRANCH_MODE_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_extended_load_reactive"
CLASSIC_DEFAULT_SINGLE_CABINET_TEMPLATE_ID = "single_cabinet_standard_ia_pa_ea"
CLASSIC_TWO_COLUMNS_ADDRESS_PROFILE_ID = "classic_main1000_alarm6000_16bit"
CLASSIC_TWO_COLUMNS_START_BOX_TEMPLATE_ID = "start_box_compact_31row_inlet_temp"
CLASSIC_TWO_COLUMNS_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_compact_21row"
UNIFIED_WORKFLOW_ID = "unified_protocol_v1"
UNIFIED_WORKFLOW_VERSION = "1.0"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

FAMILY_META = {
    "classic_combined": {
        "label": "标准单页",
        "tagline": "始端箱 / 插接箱合并出表，适合常规项目",
        "topology_modes": [
            "single_screen_one_column",
            "single_screen_two_columns",
            "single_screen_half_channel",
        ],
    },
    "extended_split": {
        "label": "扩展分页",
        "tagline": "始端箱 / 插接箱 / 单机柜 / 中继分开出表",
        "topology_modes": [
            "single_screen_half_channel",
            "single_screen_one_column",
            "single_screen_two_columns",
        ],
    },
    "ab_screen_split": {
        "label": "A/B 分屏",
        "tagline": "A 路与 B 路独立数据页和报警页",
        "topology_modes": ["dual_screens_ab_separated"],
    },
}

SCENARIO_OPTIONS = [
    {
        "id": "classic_standard",
        "label": "标准单列（含中继页）",
        "family": "classic_combined",
        "example_key": "classic_combined",
        "topology_mode": "single_screen_one_column",
        "usage_hint": "适合常见单屏项目；A/B 共屏，默认带中继页和统一报警页。",
        "meta": "常规项目首选",
    },
    {
        "id": "classic_two_columns",
        "label": "单屏双列（两列均含 A/B 路）",
        "family": "classic_combined",
        "example_key": "classic_combined_two_columns",
        "topology_mode": "single_screen_two_columns",
        "usage_hint": (
            "适合一台监控屏管理两列机柜；第一列与第二列的 A/B 路分别配置，"
            "动环上传口和母线数据接入口由设备形态及现场接线决定。"
        ),
        "meta": "四组设备独立配置",
    },
    {
        "id": "extended_split",
        "label": "扩展分页（含单机柜 / 中继页）",
        "family": "extended_split",
        "example_key": "extended_split",
        "topology_mode": "single_screen_half_channel",
        "usage_hint": "适合需要把始端箱、插接箱、单机柜和中继分开出表的项目。",
        "meta": "分页更完整",
    },
    {
        "id": "ab_screen_split",
        "label": "A/B 分屏（独立数据页 + 报警页）",
        "family": "ab_screen_split",
        "example_key": "ab_screen_split",
        "topology_mode": "dual_screens_ab_separated",
        "usage_hint": "适合 A 路与 B 路分屏显示、分表导出的项目。",
        "meta": "双屏独立导出",
    },
]

SCREEN_TOPOLOGY_OPTIONS = [
    {"value": "single_screen_one_column", "label": "单屏单列", "help_text": "一列机柜，包含 A 路和 B 路。"},
    {"value": "single_screen_two_columns", "label": "单屏双列", "help_text": "第一列和第二列分别包含 A 路、B 路。"},
    {"value": "single_screen_half_channel", "label": "单屏半列（扩展分页常用）", "help_text": "常用于扩展分页或单机柜项目。"},
    {"value": "dual_screens_ab_separated", "label": "A/B 双屏（分屏导出）", "help_text": "A 路与 B 路独立成页。"},
]

SCREEN_BINDING_OPTIONS = [
    {"value": "both_routes_in_one_screen", "label": "A/B 共屏", "help_text": "A 路和 B 路显示在同一屏。"},
    {"value": "A_screen_and_B_screen_separate", "label": "A/B 分屏", "help_text": "A 路和 B 路分开显示。"},
]

UPLOAD_PORT_OPTIONS = [
    {"value": "A1B1", "label": "A1B1", "short_label": "A1B1"},
    {"value": "A2B2", "label": "A2B2", "short_label": "A2B2"},
    {"value": "A3B3", "label": "A3B3", "short_label": "A3B3"},
    {"value": "A4B4", "label": "A4B4", "short_label": "A4B4"},
]

HARDWARE_FORM_FACTOR_OPTIONS = [
    {
        "value": "horizontal",
        "label": "卧式屏",
        "help_text": "屏后可用 A2B2、A3B3、A4B4；动环上传口默认 A4B4。",
        "available_ports": ["A2B2", "A3B3", "A4B4"],
        "default_environment_port": "A4B4",
    },
    {
        "value": "din_rail",
        "label": "滑轨式屏",
        "help_text": "屏后可用 A1B1、A2B2、A3B3；动环上传口默认 A3B3。",
        "available_ports": ["A1B1", "A2B2", "A3B3"],
        "default_environment_port": "A3B3",
    },
]

BUS_DATA_PORT_MODE_OPTIONS = {
    "single_screen_one_column": [
        {
            "value": "single_column_shared",
            "label": "A/B 两路共用一个口",
            "help_text": "单列的 A 路与 B 路母线数据接入同一个物理口。",
        },
        {
            "value": "single_column_split_ab",
            "label": "A/B 两路分开接两个口",
            "help_text": "单列的 A 路与 B 路分别占用一个物理口。",
        },
    ],
    "single_screen_two_columns": [
        {
            "value": "double_column_by_column",
            "label": "每列共用一个口",
            "help_text": "第一列 A/B 共用一个口，第二列 A/B 共用另一个口。",
        },
        {
            "value": "double_column_by_route",
            "label": "两列按 A/B 路分口",
            "help_text": "两列 A 路共用一个口，两列 B 路共用另一个口。",
        },
    ],
}

PORTS_BY_HARDWARE = {
    item["value"]: tuple(item["available_ports"])
    for item in HARDWARE_FORM_FACTOR_OPTIONS
}
DEFAULT_ENVIRONMENT_PORT = {
    item["value"]: item["default_environment_port"]
    for item in HARDWARE_FORM_FACTOR_OPTIONS
}

LIQUIDCOOL_EXPORT_PROFILE_ID = "classic_combined_liquidcool_default"
LIQUIDCOOL_ADDRESS_PROFILE_ID = "classic_liquidcool_main1000_repeater5000_cabinet7000_alarm6000_32bit"
LIQUIDCOOL_START_BOX_TEMPLATE_ID = "start_box_standard_36row_thd_energy_32bit_state"
LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_standard_30row_full_connector"
LIQUIDCOOL_REPEATER_TEMPLATE_ID = "repeater_abcn_temp_4row"
LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID = "single_cabinet_liquidcool_ia_pa_ea_ka"
LEGACY_EXTENDED_DEMO_PROJECT_CODE = "DEMO-MCGS-EXT-001"
LEGACY_EXTENDED_DEMO_CABINET_COUNT = 152
LEGACY_EXTENDED_DEMO_TEMPLATE_ID = "single_cabinet_current_sum_ia_only"


class GenerateRequest(BaseModel):
    config: dict[str, Any] = Field(..., description="项目配置 JSON")


class RecommendRequest(BaseModel):
    config: dict[str, Any] = Field(..., description="待推荐的项目配置 JSON")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=512)
    csrf_token: str = Field(..., min_length=16, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=1, max_length=512)


app = FastAPI(
    title="MCGS Full Chain Studio",
    version="1.0.0",
    docs_url=None if SECURITY_SETTINGS.enabled else "/docs",
    redoc_url=None if SECURITY_SETTINGS.enabled else "/redoc",
)
if SECURITY_SETTINGS.enabled:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(SECURITY_SETTINGS.allowed_hosts),
    )
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.mount(
    "/assembly-static",
    StaticFiles(directory=ASSEMBLY_STATIC_ROOT),
    name="assembly-static",
)
templates = Jinja2Templates(directory=TEMPLATES_ROOT)
assembly_templates = Jinja2Templates(directory=ASSEMBLY_TEMPLATES_ROOT)

PUBLIC_AUTH_PATHS = {
    "/login",
    "/api/health",
    "/api/auth/login",
}
PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/",
    "/protocol",
    "/protocol/",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/auth/change-password",
}
UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def request_client_ip(request: Request) -> str:
    peer_ip = request.client.host if request.client else "unknown"
    if peer_ip in {"127.0.0.1", "::1"}:
        cloudflare_ip = request.headers.get("cf-connecting-ip", "").strip()
        if cloudflare_ip:
            return cloudflare_ip[:96]
    return str(peer_ip or "unknown")[:96]


def request_session(request: Request) -> AuthSession | None:
    value = getattr(request.state, "auth_session", None)
    return value if isinstance(value, AuthSession) else None


def auth_error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code},
    )


def add_security_headers(response: Any) -> Any:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data: blob:; "
        "media-src 'self'; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "worker-src 'self' blob:"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if SECURITY_SETTINGS.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def security_boundary(request: Request, call_next: Any) -> Any:
    request.state.auth_session = None
    if not SECURITY_SETTINGS.enabled:
        return add_security_headers(await call_next(request))

    path = request.url.path
    is_static = path.startswith(("/static/", "/assembly-static/"))
    is_public = path in PUBLIC_AUTH_PATHS or is_static
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    session = SECURITY_MANAGER.get_session(token) if token else None
    request.state.auth_session = session

    if not is_public and session is None:
        if path.startswith("/api/"):
            return add_security_headers(
                auth_error(401, "auth_required", "登录状态已失效，请重新登录")
            )
        login_url = request.url_for("login_page").include_query_params(reason="session_expired")
        return add_security_headers(RedirectResponse(str(login_url), status_code=303))

    if (
        session is not None
        and request.method.upper() in UNSAFE_HTTP_METHODS
        and path != "/api/auth/login"
    ):
        csrf_token = request.headers.get("x-csrf-token", "")
        if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
            return add_security_headers(
                auth_error(403, "csrf_invalid", "安全校验已失效，请刷新页面后重试")
            )

    if (
        session is not None
        and session.must_change_password
        and not is_static
        and path not in PASSWORD_CHANGE_ALLOWED_PATHS
        and path not in PUBLIC_AUTH_PATHS
    ):
        return add_security_headers(
            auth_error(403, "password_change_required", "首次登录需要先修改密码")
        )

    response = await call_next(request)
    if path == "/login" or path.startswith("/api/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return add_security_headers(response)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_unified_workflow(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    workflow = config.get("workflow")
    workflow_id = workflow.get("id") if isinstance(workflow, dict) else workflow
    return str(config.get("workflow_version") or workflow_id or "").strip() == UNIFIED_WORKFLOW_ID


def route_number_defaults(route: str, screen_column: int) -> dict[str, int]:
    column_offset = max(0, int(screen_column) - 1)
    return {
        "start_box_code": (1 if route == "A" else 2) + column_offset * 2,
        "device_number": (101 if route == "A" else 201) + column_offset * 200,
    }


def build_empty_column_devices(screen_column: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "start_boxes": {},
        "plug_boxes": {},
        "branch_modules": {},
    }
    for route in ("A", "B"):
        defaults = route_number_defaults(route, screen_column)
        result["start_boxes"][route] = {
            "count": 0,
            "instance_names": [],
            "device_code_start": defaults["start_box_code"],
        }
        result["plug_boxes"][route] = {
            "box_number_start": defaults["device_number"],
            "board_number_start": defaults["device_number"],
            "sequence": [],
        }
        result["branch_modules"][route] = {
            "module_sequence": [],
            "module_number_start": 1,
            "output_number_start": 1,
            "branch_device_number_start": defaults["device_number"],
            "variable_numbering_mode": "per_board_suffix",
            "names": [],
        }
    return result


def normalize_screen_column_devices(raw_devices: Any, screen_column: int) -> dict[str, Any]:
    defaults = build_empty_column_devices(screen_column)
    devices = deepcopy(raw_devices) if isinstance(raw_devices, dict) else {}
    for group_name in ("start_boxes", "plug_boxes", "branch_modules"):
        group = devices.get(group_name)
        group = deepcopy(group) if isinstance(group, dict) else {}
        for route in ("A", "B"):
            route_config = group.get(route)
            route_config = deepcopy(route_config) if isinstance(route_config, dict) else {}
            group[route] = {**deepcopy(defaults[group_name][route]), **route_config}
        devices[group_name] = group
    return devices


def normalize_unified_topology(raw_topology: Any) -> dict[str, Any]:
    topology = deepcopy(raw_topology) if isinstance(raw_topology, dict) else {}
    topology_mode = str(
        topology.get("screen_topology_mode") or "single_screen_one_column"
    ).strip()
    if topology_mode not in {"single_screen_one_column", "single_screen_two_columns"}:
        topology_mode = "single_screen_one_column"

    hardware_form_factor = str(
        topology.get("hardware_form_factor") or "horizontal"
    ).strip()
    effective_hardware_form_factor = (
        hardware_form_factor
        if hardware_form_factor in PORTS_BY_HARDWARE
        else "horizontal"
    )
    allowed_ports = list(PORTS_BY_HARDWARE[effective_hardware_form_factor])

    raw_environment_port = topology.get("environment_rs485_port")
    raw_legacy_environment_port = topology.get("upload_port_profile")
    environment_port = str(
        raw_environment_port
        or raw_legacy_environment_port
        or DEFAULT_ENVIRONMENT_PORT[effective_hardware_form_factor]
    ).strip()
    legacy_environment_port = str(
        raw_legacy_environment_port or environment_port
    ).strip()

    available_data_ports = [port for port in allowed_ports if port != environment_port]
    if not available_data_ports:
        available_data_ports = list(allowed_ports)

    allowed_modes = [
        item["value"] for item in BUS_DATA_PORT_MODE_OPTIONS[topology_mode]
    ]
    data_mode = str(topology.get("bus_data_port_mode") or allowed_modes[0]).strip()
    effective_data_mode = data_mode if data_mode in allowed_modes else allowed_modes[0]

    assignment_keys = {
        "single_column_shared": ("shared",),
        "single_column_split_ab": ("A", "B"),
        "double_column_by_column": ("column_1", "column_2"),
        "double_column_by_route": ("A", "B"),
    }[effective_data_mode]
    raw_assignments = topology.get("bus_data_port_assignments")
    raw_assignments = raw_assignments if isinstance(raw_assignments, dict) else {}
    assignments: dict[str, str] = {}
    for index, key in enumerate(assignment_keys):
        requested = str(raw_assignments.get(key) or "").strip()
        if not requested:
            requested = available_data_ports[min(index, len(available_data_ports) - 1)]
        if (
            key not in raw_assignments
            and requested in assignments.values()
            and len(assignment_keys) > 1
        ):
            alternative = next(
                (
                    port
                    for port in available_data_ports
                    if port not in assignments.values()
                ),
                requested,
            )
            requested = alternative
        assignments[key] = requested

    topology.update(
        {
            "screen_topology_mode": topology_mode,
            "screen_route_binding": "both_routes_in_one_screen",
            "screen_count": 1,
            "columns_per_screen": 2 if topology_mode == "single_screen_two_columns" else 1,
            "route_mode": "AB_dual_route",
            "hardware_form_factor": hardware_form_factor,
            "environment_rs485_port": environment_port,
            "upload_port_profile": legacy_environment_port,
            "bus_data_port_mode": data_mode,
            "bus_data_port_assignments": assignments,
            "canonical_column_id": topology.get("canonical_column_id") or "J01",
        }
    )
    return topology


def normalize_single_cabinet_columns(
    config: dict[str, Any],
    *,
    two_columns: bool,
) -> dict[str, Any]:
    result = deepcopy(config) if isinstance(config, dict) else {}
    raw_counts = result.get("column_counts")
    raw_counts = raw_counts if isinstance(raw_counts, dict) else {}
    legacy_count = max(0, int(result.get("cabinet_count", 0) or 0))
    column_1 = max(0, int(raw_counts.get("column_1", legacy_count) or 0))
    column_2 = (
        max(0, int(raw_counts.get("column_2", 0) or 0))
        if two_columns
        else 0
    )
    result["column_counts"] = {
        "column_1": column_1,
        "column_2": column_2,
    }
    result["cabinet_count"] = column_1 + column_2
    result["include_route_data"] = result.get("include_route_data") is True
    result["include_total_power_energy"] = (
        result.get("include_total_power_energy") is True
    )
    return result


def normalize_repeater_columns(
    config: dict[str, Any],
    *,
    two_columns: bool,
) -> dict[str, Any]:
    result = deepcopy(config) if isinstance(config, dict) else {}
    raw_columns = result.get("columns")
    raw_columns = raw_columns if isinstance(raw_columns, dict) else {}
    legacy_a = max(0, int(result.get("A_count", 0) or 0))
    legacy_b = max(0, int(result.get("B_count", 0) or 0))

    normalized_columns: dict[str, dict[str, Any]] = {}
    for column_index in (1, 2):
        key = f"column_{column_index}"
        raw_column = raw_columns.get(key)
        raw_column = deepcopy(raw_column) if isinstance(raw_column, dict) else {}
        fallback_a = legacy_a if column_index == 1 else 0
        fallback_b = legacy_b if column_index == 1 else 0
        if column_index == 2 and not two_columns:
            a_count = 0
            b_count = 0
        else:
            a_count = max(0, int(raw_column.get("A_count", fallback_a) or 0))
            b_count = max(0, int(raw_column.get("B_count", fallback_b) or 0))
        normalized_columns[key] = {
            **raw_column,
            "A_count": a_count,
            "B_count": b_count,
        }

    result["columns"] = normalized_columns
    result["A_count"] = sum(item["A_count"] for item in normalized_columns.values())
    result["B_count"] = sum(item["B_count"] for item in normalized_columns.values())
    return result


def normalize_unified_workflow_input(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Map the business workflow payload onto the existing generator contract.

    Legacy payloads intentionally pass through untouched.  The protocol engine can
    therefore keep accepting historical examples while the product UI talks in
    project/routes/extensions terms instead of template/profile ids.
    """

    config = deepcopy(raw_config)
    if not is_unified_workflow(config):
        return config

    config["workflow_version"] = UNIFIED_WORKFLOW_ID
    config["generation_basis"] = "max_column"

    project = config.get("project")
    if isinstance(project, dict):
        config.setdefault("project_name", project.get("name") or project.get("project_name") or "")
        config.setdefault("project_code", project.get("code") or project.get("project_code") or "")
        config.setdefault(
            "protocol_title",
            project.get("protocol_title") or project.get("title") or "上位机通讯协议",
        )

    config.setdefault("project_name", "")
    config.setdefault("project_code", "")
    config.setdefault("protocol_title", "上位机通讯协议")
    config["topology"] = normalize_unified_topology(config.get("topology"))
    two_columns = (
        config["topology"].get("screen_topology_mode")
        == "single_screen_two_columns"
    )
    config.setdefault("devices", {})
    devices = config["devices"]
    devices.setdefault("start_boxes", {})
    devices.setdefault("plug_boxes", {})
    devices.setdefault("branch_modules", {})
    protocol_layout = config.get("protocol_layout")
    protocol_layout = deepcopy(protocol_layout) if isinstance(protocol_layout, dict) else {}
    measurement_layout_mode = str(
        protocol_layout.get("measurement_layout_mode") or "by_plug_box"
    ).strip()
    if measurement_layout_mode not in {"by_plug_box", "by_branch"}:
        measurement_layout_mode = "by_plug_box"
    protocol_layout.update(
        {
            "measurement_layout_mode": measurement_layout_mode,
            "base_sheet_name": "始端箱和插接箱",
            "main_base_address": int(protocol_layout.get("main_base_address", 1000) or 1000),
            "downstream_base_address": (
                int(protocol_layout.get("downstream_base_address"))
                if protocol_layout.get("downstream_base_address") is not None
                else (2000 if measurement_layout_mode == "by_branch" else None)
            ),
            "downstream_primary_outputs_per_route": (
                int(protocol_layout.get("downstream_primary_outputs_per_route", 38) or 38)
                if measurement_layout_mode == "by_branch"
                else None
            ),
            "downstream_extension_base_address": (
                int(protocol_layout.get("downstream_extension_base_address", 9500) or 9500)
                if measurement_layout_mode == "by_branch"
                else None
            ),
            "embed_single_cabinet_in_base_sheet": protocol_layout.get(
                "embed_single_cabinet_in_base_sheet",
                True,
            )
            is not False,
            "alarm_start_box_first": protocol_layout.get("alarm_start_box_first", True) is not False,
        }
    )
    config["protocol_layout"] = protocol_layout

    routes = config.get("routes")
    routes = routes if isinstance(routes, dict) else {}
    for route in ("A", "B"):
        route_config = routes.get(route)
        if not isinstance(route_config, dict):
            continue
        start_config = route_config.get("start_boxes") or route_config.get("start_box")
        plug_config = route_config.get("plug_boxes") or route_config.get("plug_box")
        branch_output_config = (
            route_config.get("branch_modules")
            or route_config.get("monitor_modules")
            or route_config.get("branch_outputs")
            or route_config.get("output_branches")
        )
        if isinstance(start_config, dict):
            devices["start_boxes"][route] = deepcopy(start_config)
        if isinstance(plug_config, dict):
            devices["plug_boxes"][route] = deepcopy(plug_config)
        if isinstance(branch_output_config, dict):
            devices["branch_modules"][route] = deepcopy(branch_output_config)

    route_b = routes.get("B") if isinstance(routes.get("B"), dict) else {}
    if route_b.get("copy_from_A"):
        devices["start_boxes"].setdefault("B", deepcopy(devices["start_boxes"].get("A", {})))
        devices["plug_boxes"].setdefault("B", deepcopy(devices["plug_boxes"].get("A", {})))
        devices["branch_modules"].setdefault("B", deepcopy(devices["branch_modules"].get("A", {})))
        if isinstance(devices["branch_modules"].get("B"), dict):
            devices["branch_modules"]["B"]["branch_device_number_start"] = 201
            devices["branch_modules"]["B"]["module_number_start"] = 1
            devices["branch_modules"]["B"]["output_number_start"] = 1
            devices["branch_modules"]["B"]["names"] = []

    extensions = config.get("extensions")
    extensions = deepcopy(extensions) if isinstance(extensions, dict) else {}
    single_cabinet = (
        extensions.get("single_cabinet")
        or extensions.get("single_cabinet_data")
        or devices.get("single_cabinet_aggregation")
        or {}
    )
    repeater = extensions.get("repeater") or devices.get("repeater_units") or {}
    alarm_state_word = (
        extensions.get("alarm_state_word")
        or extensions.get("alarm_status_word")
        or {}
    )
    single_cabinet = deepcopy(single_cabinet) if isinstance(single_cabinet, dict) else {}
    repeater = deepcopy(repeater) if isinstance(repeater, dict) else {}
    alarm_state_word = deepcopy(alarm_state_word) if isinstance(alarm_state_word, dict) else {}

    single_cabinet.setdefault("enabled", False)
    single_cabinet.setdefault("cabinet_count", 0)
    single_cabinet.setdefault("include_route_data", False)
    single_cabinet.setdefault("include_total_power_energy", False)
    single_cabinet.setdefault("base_address", 8200 if measurement_layout_mode == "by_branch" else 7000)
    single_cabinet.setdefault(
        "metric_base_addresses",
        {"IA": 8200, "PA": 8400, "EA": 8600, "KA": 8800}
        if measurement_layout_mode == "by_branch"
        else {},
    )
    repeater.setdefault("enabled", False)
    repeater.setdefault("A_count", 0)
    repeater.setdefault("B_count", 0)
    repeater.setdefault("base_address", 9000 if measurement_layout_mode == "by_branch" else 5500)
    alarm_state_word.setdefault("enabled", True)
    alarm_state_word.setdefault("base_address", 6000)
    alarm_state_word.setdefault("word_mode", "16bit")
    alarm_state_word["legacy_slide_rail_order"] = (
        alarm_state_word.get("legacy_slide_rail_order") is True
    )
    single_cabinet = normalize_single_cabinet_columns(
        single_cabinet,
        two_columns=two_columns,
    )
    repeater = normalize_repeater_columns(
        repeater,
        two_columns=two_columns,
    )

    extensions = {
        **extensions,
        "single_cabinet": single_cabinet,
        "repeater": repeater,
        "alarm_state_word": alarm_state_word,
    }
    config["extensions"] = extensions
    devices["single_cabinet_aggregation"] = deepcopy(single_cabinet)
    devices["repeater_units"] = deepcopy(repeater)
    devices = normalize_screen_column_devices(devices, 1)
    screen_columns = devices.get("screen_columns")
    screen_columns = deepcopy(screen_columns) if isinstance(screen_columns, dict) else {}
    screen_columns["column_2"] = normalize_screen_column_devices(
        screen_columns.get("column_2"),
        2,
    )
    devices["screen_columns"] = screen_columns
    config["devices"] = devices
    for route, default_device_start in (("A", 101), ("B", 201)):
        branch_output = devices["branch_modules"].setdefault(route, {})
        module_sequence = branch_output.get("module_sequence")
        has_explicit_module_sequence = bool(
            isinstance(module_sequence, list) and module_sequence
        )
        if not has_explicit_module_sequence:
            branch_output.setdefault("module_count", 0)
            branch_output.setdefault("branches_per_module", 2)
        branch_output.setdefault("module_number_start", 1)
        branch_output.setdefault("output_number_start", 1)
        branch_output.setdefault("branch_device_number_start", default_device_start)
        branch_output["variable_numbering_mode"] = "per_board_suffix"
        branch_output.setdefault("names", [])

    return config


def canonical_alarm_word_mode(value: Any) -> str:
    normalized = str(value or "16bit").strip().lower().replace("-", "")
    return "32bit" if normalized in {"32", "32bit", "dword"} else "16bit"


def install_unified_internal_profiles(
    config: dict[str, Any],
    library: TemplateLibrary,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a request-local adaptive profile hidden from the product UI."""

    devices = config.get("devices", {})
    repeater = devices.get("repeater_units", {})
    single_cabinet = devices.get("single_cabinet_aggregation", {})
    repeater_enabled = bool(repeater.get("enabled")) and sum(
        int(repeater.get(f"{route}_count", 0) or 0) for route in ("A", "B")
    ) > 0
    cabinet_enabled = bool(single_cabinet.get("enabled")) and int(single_cabinet.get("cabinet_count", 0) or 0) > 0

    base_export_id = CLASSIC_CABINET_EXPORT_PROFILE_ID if cabinet_enabled else CLASSIC_DEFAULT_EXPORT_PROFILE_ID
    base_export_profile = deepcopy(library.export_profile_map[base_export_id])
    baseline_bundle = deepcopy(base_export_profile.get("baseline_profile_bundle") or {})
    base_address_profile = deepcopy(library.address_profile_map[baseline_bundle["address_profile_id"]])

    alarm_config = config.get("extensions", {}).get("alarm_state_word", {})
    alarm_enabled = alarm_config.get("enabled") is not False
    alarm_base = int(alarm_config.get("base_address", base_address_profile.get("alarm_base", 6000)) or 6000)
    alarm_word_mode = canonical_alarm_word_mode(alarm_config.get("word_mode"))
    protocol_layout = config.get("protocol_layout", {})
    main_base = int(protocol_layout.get("main_base_address", base_address_profile.get("main_base", 1000)) or 1000)
    downstream_base = protocol_layout.get("downstream_base_address")
    downstream_base = int(downstream_base) if downstream_base is not None else None
    repeater_base = repeater.get("base_address")
    repeater_base = int(repeater_base) if repeater_enabled and repeater_base is not None else base_address_profile.get("repeater_base")
    cabinet_base = single_cabinet.get("base_address")
    cabinet_base = int(cabinet_base) if cabinet_enabled and cabinet_base is not None else base_address_profile.get("cabinet_base")
    address_profile_id = (
        f"unified_internal_main{main_base}_down{downstream_base or 0}_"
        f"r{repeater_base or 0}_c{cabinet_base or 0}_alarm{alarm_base}_{alarm_word_mode}"
    )
    base_address_profile.update(
        {
            "id": address_profile_id,
            "family": "classic_combined",
            "display_label": "项目协议地址方案",
            "description": "按当前项目参数自动推导。",
            "alarm_base": alarm_base,
            "alarm_word_mode": alarm_word_mode,
            "main_base": main_base,
            "plug_base": downstream_base,
            "repeater_base": repeater_base,
            "cabinet_base": cabinet_base,
        }
    )
    if address_profile_id not in library.address_profile_map:
        library.address_profiles.setdefault("profiles", []).append(base_address_profile)

    measurement_layout_mode = str(
        config.get("protocol_layout", {}).get("measurement_layout_mode") or "by_plug_box"
    )
    base_sheet_name = "始端箱和插接箱"
    export_profile_id = (
        f"unified_master_{measurement_layout_mode}_main{main_base}_down{downstream_base or 0}_"
        f"r{repeater_base or 0}_c{cabinet_base or 0}_alarm{alarm_base}_{alarm_word_mode}"
    )
    baseline_bundle["address_profile_id"] = address_profile_id
    if measurement_layout_mode == "by_branch":
        baseline_bundle["start_box_template_id"] = BRANCH_MODE_START_BOX_TEMPLATE_ID
        baseline_bundle["plug_branch_template_id"] = BRANCH_MODE_PLUG_BRANCH_TEMPLATE_ID
        baseline_bundle["single_cabinet_template_id"] = LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID
    sheet_order = [base_sheet_name]
    if repeater_enabled:
        sheet_order.append("中继器")
    if alarm_enabled:
        sheet_order.append("报警状态")
    base_export_profile.update(
        {
            "id": export_profile_id,
            "family": "classic_combined",
            "render_variant_id": "unified_master",
            "is_family_baseline": False,
            "baseline_profile_bundle": baseline_bundle,
            "display_label": "统一参数化协议",
            "description": "由 A/B 路和扩展项参数自动编译；历史模板仅作为内部规则来源。",
            "sheet_order": sheet_order,
            "base_sheet_name": base_sheet_name,
            "include_repeater_sheet": repeater_enabled,
            "include_single_cabinet_sheet": False,
            "embed_single_cabinet_in_base_sheet": cabinet_enabled,
            "include_alarm_sheet": alarm_enabled,
            "merge_start_and_plug": True,
            "split_ab_screens": False,
        }
    )
    if export_profile_id not in library.export_profile_map:
        library.export_profiles.setdefault("profiles", []).append(base_export_profile)
    return base_export_profile, baseline_bundle


def template_asset_version() -> str:
    latest_mtime = max(path.stat().st_mtime for path in STATIC_ASSET_PATHS if path.exists())
    return str(int(latest_mtime))


TEMPLATE_LIBRARY_KEYS = {
    "start": "start_box_templates",
    "plug": "plug_branch_templates",
    "repeater": "repeater_templates",
    "cabinet": "single_cabinet_templates",
}

PREFERRED_TEMPLATE_BASELINE_IDS = {
    "start": CLASSIC_DEFAULT_START_BOX_TEMPLATE_ID,
    "plug": CLASSIC_DEFAULT_PLUG_BRANCH_TEMPLATE_ID,
}

STANDARD_TEMPLATE_IDS = {
    "start": CLASSIC_DEFAULT_START_BOX_TEMPLATE_ID,
    "plug": CLASSIC_DEFAULT_PLUG_BRANCH_TEMPLATE_ID,
    "repeater": LIQUIDCOOL_REPEATER_TEMPLATE_ID,
    "cabinet": CLASSIC_DEFAULT_SINGLE_CABINET_TEMPLATE_ID,
}

TEMPLATE_TYPE_LABELS = {
    "start": "始端箱",
    "plug": "插接箱",
    "repeater": "中继",
    "cabinet": "单机柜",
}

SINGLE_CABINET_METRIC_LABELS = {
    "IA": "总电流",
    "PA": "总功率",
    "EA": "总电能",
    "KA": "状态字",
}

FEATURE_ORDER = [
    "频率",
    "入/出线温度",
    "入线温度",
    "出线温度",
    "连接点温度",
    "谐波",
    "电量",
    "负载率",
    "不平衡",
    "无功功率",
    "视在功率",
    "32 位状态字",
    "16 位状态字",
    "总电流",
    "总功率",
    "总电能",
    "状态字",
    "A/B/C/N 温度",
]


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def feature_sort_key(label: str) -> tuple[int, str]:
    try:
        return (FEATURE_ORDER.index(label), label)
    except ValueError:
        return (len(FEATURE_ORDER), label)


def normalize_feature_labels(features: list[str]) -> list[str]:
    normalized = unique_preserve_order(features)
    if "入线温度" in normalized and "出线温度" in normalized:
        normalized = [item for item in normalized if item not in {"入线温度", "出线温度"}]
        normalized.insert(1 if normalized else 0, "入/出线温度")
    return sorted(normalized, key=feature_sort_key)


def join_cn(items: list[str]) -> str:
    return "、".join([item for item in items if item])


def humanize_alarm_word_mode(mode: str | None) -> str:
    if str(mode or "16bit").lower() == "32bit":
        return "32 位报警字"
    return "16 位报警字"


def template_lookup_map(library: TemplateLibrary, template_type: str) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in library.device_library.get(TEMPLATE_LIBRARY_KEYS[template_type], [])
    }


def template_feature_footprint(template: dict[str, Any], template_type: str) -> int:
    if template_type == "cabinet":
        return len(template.get("metric_sequence") or [])
    return len(template.get("point_prefix_sequence") or [])


def baseline_template_for(library: TemplateLibrary, template_type: str) -> dict[str, Any] | None:
    template_map = template_lookup_map(library, template_type)
    preferred_id = PREFERRED_TEMPLATE_BASELINE_IDS.get(template_type)
    if preferred_id and preferred_id in template_map:
        return template_map[preferred_id]

    candidates = list(template_map.values())
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: (
            len(item.get("evidence_files", []) or []),
            template_feature_footprint(item, template_type),
            int(item.get("row_span") or 0),
            str(item.get("id") or ""),
        ),
    )


def baseline_profile_ids_for_selection(
    library: TemplateLibrary,
    export_profile_id: str | None,
    family: str | None = None,
) -> dict[str, Any]:
    baseline_export_profile = resolve_baseline_export_profile(
        library,
        family,
        {"export_profile_id": export_profile_id} if export_profile_id else {},
    )
    bundle = export_profile_baseline_bundle(baseline_export_profile)
    if bundle:
        return bundle
    return {}


def resolve_profile_baselines(
    library: TemplateLibrary,
    profiles: dict[str, Any],
) -> dict[str, dict[str, Any] | None]:
    export_profile = library.export_profile_map.get(profiles.get("export_profile_id"))
    family = export_profile.get("family") if export_profile else None
    baseline_ids = baseline_profile_ids_for_selection(library, profiles.get("export_profile_id"), family)
    start_templates = template_lookup_map(library, "start")
    plug_templates = template_lookup_map(library, "plug")
    repeater_templates = template_lookup_map(library, "repeater")
    cabinet_templates = template_lookup_map(library, "cabinet")
    return {
        "address_profile": library.address_profile_map.get(baseline_ids.get("address_profile_id")),
        "start_box_template": start_templates.get(baseline_ids.get("start_box_template_id")),
        "plug_branch_template": plug_templates.get(baseline_ids.get("plug_branch_template_id")),
        "repeater_template": repeater_templates.get(baseline_ids.get("repeater_template_id")),
        "single_cabinet_template": cabinet_templates.get(baseline_ids.get("single_cabinet_template_id")),
    }


def extract_template_features(template: dict[str, Any]) -> list[str]:
    if not template:
        return []

    if template.get("metric_sequence"):
        features = [SINGLE_CABINET_METRIC_LABELS.get(metric, metric) for metric in template.get("metric_sequence", [])]
        return normalize_feature_labels(features)

    prefixes = [str(item) for item in template.get("point_prefix_sequence", [])]
    prefix_set = set(prefixes)
    features: list[str] = []

    if "F" in prefix_set:
        features.append("频率")
    if {"Ta", "Tb", "Tc", "Tn"} & prefix_set:
        features.append("入线温度")
    if {"TaO", "TbO", "TcO", "TnO"} & prefix_set:
        features.append("出线温度")
    if {"TaD", "TbD", "TcD", "TnD"} & prefix_set:
        features.append("连接点温度")
    if any(item.startswith("THD") for item in prefixes):
        features.append("谐波")
    if {"Ea", "Eb", "Ec", "E"} & prefix_set:
        features.append("电量")
    if "LoadS" in prefix_set:
        features.append("负载率")
    if "UBS" in prefix_set:
        features.append("不平衡")
    if {"Qa", "Qb", "Qc", "Q"} & prefix_set:
        features.append("无功功率")
    if {"Sa", "Sb", "Sc", "S_"} & prefix_set:
        features.append("视在功率")
    if {"TaZ", "TbZ", "TcZ", "TnZ"} & prefix_set:
        features.append("A/B/C/N 温度")
    if any(item.startswith("State") for item in prefixes):
        features.append("32 位状态字" if template.get("state_word_mode") == "32bit" else "16 位状态字")

    return normalize_feature_labels(features)


def template_variant_name(template: dict[str, Any], template_type: str) -> str:
    template_id = str(template.get("id", ""))
    base = TEMPLATE_TYPE_LABELS[template_type]

    if template_type == "start":
        if template_id == STANDARD_TEMPLATE_IDS["start"]:
            return "标准始端箱"
        if "extended" in template_id:
            return "扩展始端箱"
        if "compact" in template_id:
            return "紧凑始端箱"
        if "outlet" in template_id:
            return "出线温度版始端箱"
        if "inlet" in template_id:
            return "入口温度版始端箱"
    elif template_type == "plug":
        if template_id == STANDARD_TEMPLATE_IDS["plug"]:
            return "标准插接箱"
        if "compact" in template_id:
            return "紧凑插接箱"
        if "full_connector" in template_id or template.get("state_word_mode") == "32bit":
            return "全量插接箱"
    elif template_type == "repeater":
        return "标准中继"
    elif template_type == "cabinet":
        if "liquidcool" in template_id:
            return "液冷单机柜"
        return "单机柜模板"

    return f"{base}模板"


def build_template_descriptor(
    template: dict[str, Any],
    template_type: str,
    baseline_template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = extract_template_features(template)
    baseline_features = extract_template_features(baseline_template or {})
    feature_set = set(features)
    baseline_set = set(baseline_features)
    added = [item for item in features if item not in baseline_set]
    removed = [item for item in baseline_features if item not in feature_set]
    variant_name = template_variant_name(template, template_type)
    is_standard = bool(baseline_template) and baseline_template.get("id") == template.get("id")

    if is_standard:
        label = f"{variant_name}（含{join_cn([item for item in features if item != '16 位状态字']) or join_cn(features)}）"
        diff_summary = "当前场景标准模板"
    else:
        diff_parts: list[str] = []
        if added:
            diff_parts.append(f"比当前标准多：{join_cn(added)}")
        if removed:
            diff_parts.append(f"比当前标准少：{join_cn(removed)}")
        if not diff_parts and features:
            diff_parts.append(f"监测项：{join_cn(features)}")
        label = f"{variant_name}（{'；'.join(diff_parts)}）" if diff_parts else variant_name
        diff_summary = "；".join(diff_parts) if diff_parts else "与当前标准模板接近"

    help_parts: list[str] = []
    if features:
        help_parts.append(f"监测项：{join_cn(features)}")
    if template_type != "cabinet" and template.get("state_word_mode") == "32bit":
        help_parts.append("状态字按 32 位展开")
    evidence = template.get("evidence_files", [])
    if evidence:
        help_parts.append(f"参考 {len(evidence)} 份历史协议")

    return {
        "label": label,
        "short_label": variant_name,
        "help_text": "；".join(help_parts),
        "diff_summary": diff_summary,
        "features": features,
        "is_standard": is_standard,
    }


def address_variant_name(profile: dict[str, Any]) -> str:
    profile_id = str(profile.get("id", ""))
    family = profile.get("family")
    if profile_id == CLASSIC_DEFAULT_ADDRESS_PROFILE_ID:
        return "标准地址方案"
    if profile_id == CLASSIC_TWO_COLUMNS_ADDRESS_PROFILE_ID:
        return "双列精简地址方案"
    if profile_id == LIQUIDCOOL_ADDRESS_PROFILE_ID:
        return "液冷地址方案"
    if family == "extended_split":
        return "扩展分页地址方案"
    if family == "ab_screen_split":
        return "A/B 分屏地址方案"
    if profile.get("alarm_word_mode") == "32bit":
        return "32 位报警地址方案"
    return "地址方案"


def build_address_descriptor(
    profile: dict[str, Any],
    baseline_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    segments = [f"主 {profile['main_base']}"]
    if profile.get("plug_base") is not None:
        segments.append(f"插接箱 {profile['plug_base']}")
    if profile.get("cabinet_base") is not None:
        segments.append(f"单机柜 {profile['cabinet_base']}")
    if profile.get("repeater_base") is not None:
        segments.append(f"中继 {profile['repeater_base']}")
    segments.append(f"报警 {profile['alarm_base']}")
    segments.append(humanize_alarm_word_mode(profile.get("alarm_word_mode")))

    notes: list[str] = []
    if profile.get("repeater_base") is not None:
        notes.append("含中继地址段")
    else:
        notes.append("不含中继地址段")
    if profile.get("cabinet_base") is not None:
        notes.append("含单机柜地址段")
    if profile.get("plug_base") is not None:
        notes.append("插接箱独立地址段")

    diff_parts: list[str] = []
    if baseline_profile:
        if baseline_profile.get("main_base") != profile.get("main_base"):
            diff_parts.append(f"主地址起始改为 {profile.get('main_base')}")
        if baseline_profile.get("plug_base") is None and profile.get("plug_base") is not None:
            diff_parts.append(f"比当前标准多插接箱地址段（{profile.get('plug_base')} 起）")
        elif baseline_profile.get("plug_base") is not None and profile.get("plug_base") is None:
            diff_parts.append("比当前标准少插接箱地址段")
        elif baseline_profile.get("plug_base") != profile.get("plug_base"):
            diff_parts.append(f"插接箱地址起始改为 {profile.get('plug_base')}")
        if baseline_profile.get("repeater_base") is not None and profile.get("repeater_base") is None:
            diff_parts.append("比当前标准少中继地址段")
        elif baseline_profile.get("repeater_base") is None and profile.get("repeater_base") is not None:
            diff_parts.append(f"比当前标准多中继地址段（{profile.get('repeater_base')} 起）")
        elif baseline_profile.get("repeater_base") != profile.get("repeater_base"):
            diff_parts.append(f"中继地址起始改为 {profile.get('repeater_base')}")
        if baseline_profile.get("cabinet_base") is None and profile.get("cabinet_base") is not None:
            diff_parts.append(f"比当前标准多单机柜地址段（{profile.get('cabinet_base')} 起）")
        elif baseline_profile.get("cabinet_base") is not None and profile.get("cabinet_base") is None:
            diff_parts.append("比当前标准少单机柜地址段")
        elif baseline_profile.get("cabinet_base") != profile.get("cabinet_base"):
            diff_parts.append(f"单机柜地址起始改为 {profile.get('cabinet_base')}")
        if baseline_profile.get("alarm_base") != profile.get("alarm_base"):
            diff_parts.append(f"报警地址起始改为 {profile.get('alarm_base')}")
        if baseline_profile.get("alarm_word_mode") != profile.get("alarm_word_mode"):
            diff_parts.append(f"报警字改为{humanize_alarm_word_mode(profile.get('alarm_word_mode'))}")

    label = f"{address_variant_name(profile)}（{' / '.join(segments)}）"
    return {
        "label": label,
        "short_label": address_variant_name(profile),
        "help_text": "；".join(notes),
        "diff_summary": "；".join(diff_parts) if diff_parts else ("与当前标准地址方案一致" if baseline_profile else "与标准地址方案一致"),
        "segments": segments,
    }


EXPORT_RENDER_VARIANT_LABELS = {
    "classic_standard": "classic 标准视图",
    "classic_two_columns": "classic 单屏双列视图",
    "classic_liquidcool": "classic 液冷视图",
    "extended_standard": "extended 拆分页视图",
    "ab_screen_standard": "A/B 分屏视图",
}

EXPORT_PATCH_TAG_LABELS = {
    "merge_start_and_plug": "始端箱与插接箱合并页",
    "include_repeater_sheet": "含中继页",
    "include_single_cabinet_sheet": "含单机柜页",
    "hide_repeater_sheet": "不含中继页",
    "separate_start_and_plug": "始端箱 / 插接箱拆分页",
    "split_ab_screens": "A/B 分屏导出",
    "hybrid_threshold_alarm": "阈值 + 状态混合报警",
}

EXPORT_ACTIVE_ZONE_LABELS = {
    "intro_block": "说明区",
    "combined_main_sheet": "始端箱与插接箱主数据页",
    "repeater_sheet": "中继 / 连接器页",
    "single_cabinet_sheet": "单机柜页",
    "alarm_sheet": "报警页",
    "two_column_header": "双列表头区",
    "wiring_layout_aux_columns": "接线布局活动区",
    "liquidcool_threshold_block": "液冷阈值区",
    "split_start_sheet": "始端箱独立页",
    "split_plug_sheet": "插接箱独立页",
    "route_a_data": "A路屏数据页",
    "route_a_alarm": "A路屏报警页",
    "route_b_data": "B路屏数据页",
    "route_b_alarm": "B路屏报警页",
}

SHEET_NAME_TO_ACTIVE_ZONE = {
    "始端箱和插接箱": "combined_main_sheet",
    "中继器": "repeater_sheet",
    "中继单元": "repeater_sheet",
    "连接器测温": "repeater_sheet",
    "报警状态": "alarm_sheet",
    "单机柜数据": "single_cabinet_sheet",
    "始端箱": "split_start_sheet",
    "插接箱": "split_plug_sheet",
    "A路屏数据": "route_a_data",
    "A路屏报警": "route_a_alarm",
    "B路屏数据": "route_b_data",
    "B路屏报警": "route_b_alarm",
}


def export_profile_render_variant_id(profile: dict[str, Any] | None) -> str | None:
    if not profile:
        return None
    explicit = str(profile.get("render_variant_id") or "").strip()
    if explicit:
        return explicit
    profile_id = str(profile.get("id") or "").strip()
    family = str(profile.get("family") or "").strip()
    if profile_id == LIQUIDCOOL_EXPORT_PROFILE_ID or profile.get("subtype") == "liquidcool_hybrid":
        return "classic_liquidcool"
    if family == "classic_combined" and (
        profile.get("subtype") == "single_screen_two_columns"
        or profile.get("topology_mode") == "single_screen_two_columns"
    ):
        return "classic_two_columns"
    if family == "classic_combined":
        return "classic_standard"
    if family == "extended_split":
        return "extended_standard"
    if family == "ab_screen_split":
        return "ab_screen_standard"
    return None


def export_profile_render_variant_label(profile: dict[str, Any] | None) -> str | None:
    variant_id = export_profile_render_variant_id(profile)
    if not variant_id:
        return None
    return EXPORT_RENDER_VARIANT_LABELS.get(variant_id, variant_id)


def export_profile_patch_tags(profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return []
    explicit_tags = [str(item).strip() for item in profile.get("patch_tags", []) if str(item).strip()]
    if explicit_tags:
        return unique_preserve_order(explicit_tags)

    sheet_order = [str(item).strip() for item in profile.get("sheet_order", []) if str(item).strip()]
    tags: list[str] = []
    if profile.get("split_ab_screens"):
        tags.append("split_ab_screens")
    elif profile.get("merge_start_and_plug"):
        tags.append("merge_start_and_plug")
    elif not profile.get("merge_start_and_plug") and any(item in {"始端箱", "插接箱"} for item in sheet_order):
        tags.append("separate_start_and_plug")
    include_repeater_sheet = profile.get("include_repeater_sheet")
    if include_repeater_sheet is None:
        include_repeater_sheet = any(item in {"中继器", "中继单元", "连接器测温"} for item in sheet_order)
    if include_repeater_sheet:
        tags.append("include_repeater_sheet")
    elif export_profile_render_variant_id(profile) == "classic_two_columns":
        tags.append("hide_repeater_sheet")
    if profile.get("include_single_cabinet_sheet"):
        tags.append("include_single_cabinet_sheet")
    if profile.get("alarm_mode") == "hybrid_threshold_and_state":
        tags.append("hybrid_threshold_alarm")
    return unique_preserve_order(tags)


def export_profile_patch_labels(profile: dict[str, Any] | None) -> list[str]:
    return [
        EXPORT_PATCH_TAG_LABELS.get(tag, tag)
        for tag in export_profile_patch_tags(profile)
    ]


def export_profile_active_zones(profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return []
    explicit_zones = [str(item).strip() for item in profile.get("active_zones", []) if str(item).strip()]
    if explicit_zones:
        return unique_preserve_order(explicit_zones)

    zones: list[str] = []
    sheet_order = [str(item).strip() for item in profile.get("sheet_order", []) if str(item).strip()]
    if profile.get("description"):
        zones.append("intro_block")
    for item in sheet_order:
        zone = SHEET_NAME_TO_ACTIVE_ZONE.get(item)
        if zone:
            zones.append(zone)
    if export_profile_render_variant_id(profile) == "classic_two_columns":
        zones.append("two_column_header")
    if export_profile_render_variant_id(profile) == "classic_liquidcool":
        zones.extend(["liquidcool_threshold_block", "wiring_layout_aux_columns"])
    return unique_preserve_order(zones)


def export_profile_active_zone_labels(profile: dict[str, Any] | None) -> list[str]:
    return [
        EXPORT_ACTIVE_ZONE_LABELS.get(zone, zone)
        for zone in export_profile_active_zones(profile)
    ]


def template_plan_label(
    render_variant_label: str | None,
    export_label: str | None,
    patch_labels: list[str] | None = None,
    *,
    fallback: str = "当前方案",
) -> str:
    base = str(render_variant_label or export_label or fallback).strip()
    normalized_patch_labels = [str(item).strip() for item in (patch_labels or []) if str(item).strip()]
    concise_patch_labels = [item for item in normalized_patch_labels if not item.startswith("页面 ")]
    if concise_patch_labels:
        return f"{base}（{join_cn(concise_patch_labels[:3])}）"
    export_text = str(export_label or "").strip()
    if export_text and export_text != base:
        return f"{base}（{export_text}）"
    return base


def export_profile_baseline_bundle(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    bundle = dict(profile.get("baseline_profile_bundle") or {})
    return {key: value for key, value in bundle.items() if value not in (None, "")}


PROFILE_SELECTION_BUNDLE_KEYS = (
    "address_profile_id",
    "start_box_template_id",
    "plug_branch_template_id",
    "repeater_template_id",
    "single_cabinet_template_id",
)


def family_default_export_profile_id(library: TemplateLibrary, family: str | None) -> str:
    family_key = str(family or "").strip()
    for item in library.export_profiles.get("profiles", []):
        if item.get("family") == family_key and item.get("is_family_baseline"):
            return str(item.get("id"))
    return CLASSIC_DEFAULT_EXPORT_PROFILE_ID


def resolve_baseline_export_profile(
    library: TemplateLibrary,
    family: str | None,
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profiles = profiles or {}
    export_profile_id = profiles.get("export_profile_id")
    if export_profile_id and export_profile_id in library.export_profile_map:
        return library.export_profile_map[export_profile_id]
    default_export_profile_id = family_default_export_profile_id(library, family)
    if default_export_profile_id in library.export_profile_map:
        return library.export_profile_map[default_export_profile_id]
    return library.export_profile_map.get(CLASSIC_DEFAULT_EXPORT_PROFILE_ID, {})


def family_hint_for_topology(topology_mode: str | None, explicit_family: str | None = None) -> str:
    family = str(explicit_family or "").strip()
    if family:
        return family
    if topology_mode == "dual_screens_ab_separated":
        return "ab_screen_split"
    return "classic_combined"


def baseline_export_profile_for_family(library: TemplateLibrary, family: str | None) -> dict[str, Any]:
    family_key = str(family or "").strip()
    if not family_key:
        return {}
    default_export_profile_id = family_default_export_profile_id(library, family_key)
    return dict(library.export_profile_map.get(default_export_profile_id) or {})


def resolve_export_profile_for_config(
    library: TemplateLibrary,
    profiles: dict[str, Any] | None,
    *,
    family_hint: str | None = None,
) -> dict[str, Any]:
    profile_map = library.export_profile_map
    export_profile_id = str((profiles or {}).get("export_profile_id") or "").strip()
    if export_profile_id and export_profile_id in profile_map:
        return profile_map[export_profile_id]
    return resolve_baseline_export_profile(library, family_hint, profiles)


def find_export_profile(
    library: TemplateLibrary,
    *,
    family: str | None = None,
    render_variant_id: str | None = None,
    topology_mode: str | None = None,
    subtype: str | None = None,
    include_single_cabinet_sheet: bool | None = None,
    split_ab_screens: bool | None = None,
) -> dict[str, Any] | None:
    family_key = str(family or "").strip()
    variant_key = str(render_variant_id or "").strip()
    topology_key = str(topology_mode or "").strip()
    subtype_key = str(subtype or "").strip()
    best_match: dict[str, Any] | None = None
    best_score = -1

    for item in library.export_profiles.get("profiles", []):
        if family_key and item.get("family") != family_key:
            continue

        score = 0
        item_variant = export_profile_render_variant_id(item)
        if variant_key:
            if item_variant != variant_key:
                continue
            score += 50
        if topology_key:
            item_topology = str(item.get("topology_mode") or "").strip()
            if item_topology == topology_key:
                score += 20
            elif item_topology:
                continue
        if subtype_key:
            item_subtype = str(item.get("subtype") or "").strip()
            if item_subtype == subtype_key:
                score += 20
            elif item_subtype:
                continue
        if include_single_cabinet_sheet is not None:
            if bool(item.get("include_single_cabinet_sheet")) != include_single_cabinet_sheet:
                continue
            score += 12
        if split_ab_screens is not None:
            if bool(item.get("split_ab_screens")) != split_ab_screens:
                continue
            score += 8
        if item.get("is_family_baseline"):
            score += 4
        score += len(export_profile_baseline_bundle(item))

        if score > best_score:
            best_match = item
            best_score = score

    return best_match


def build_migratable_profile_defaults(
    library: TemplateLibrary,
    *,
    family: str | None,
    source_export_profile: dict[str, Any] | None = None,
    legacy_values: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    migratable: dict[str, set[str]] = {key: set() for key in PROFILE_SELECTION_BUNDLE_KEYS}
    source_profiles = [
        source_export_profile or {},
        baseline_export_profile_for_family(library, family),
    ]
    for profile in source_profiles:
        for key, value in export_profile_baseline_bundle(profile).items():
            if key not in migratable:
                continue
            normalized = str(value or "").strip()
            if normalized:
                migratable[key].add(normalized)
    for key, values in (legacy_values or {}).items():
        if key not in migratable:
            continue
        migratable[key].update(str(item).strip() for item in values if str(item).strip())
    return migratable


def apply_export_profile_bundle_defaults(
    profiles: dict[str, Any],
    target_bundle: dict[str, Any],
    *,
    migratable_defaults: dict[str, set[str]] | None = None,
    force_keys: set[str] | None = None,
) -> None:
    migratable_defaults = migratable_defaults or {}
    forced = {str(item).strip() for item in (force_keys or set()) if str(item).strip()}
    for key in PROFILE_SELECTION_BUNDLE_KEYS:
        target_value = target_bundle.get(key)
        normalized_target = str(target_value or "").strip()
        if not normalized_target:
            continue
        current_value = profiles.get(key)
        normalized_current = str(current_value or "").strip()
        if key in forced or not normalized_current or normalized_current in migratable_defaults.get(key, set()):
            profiles[key] = target_value


def export_profile_display_label(profile: dict[str, Any] | None) -> str | None:
    if not profile:
        return None
    label = profile.get("display_label")
    if label:
        return label
    sheet_order = [str(item).strip() for item in profile.get("sheet_order", []) if str(item).strip()]
    if sheet_order:
        return " / ".join(sheet_order)
    family = str(profile.get("family") or "").strip()
    return FAMILY_META.get(family, {}).get("label") or family or None


def build_export_profile_descriptor(
    profile: dict[str, Any],
    baseline_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label = export_profile_display_label(profile) or "Excel 页面结构"
    sheet_order = [str(item).strip() for item in profile.get("sheet_order", []) if str(item).strip()]
    baseline_order = [
        str(item).strip()
        for item in (baseline_profile or {}).get("sheet_order", [])
        if str(item).strip()
    ]
    render_variant_id = export_profile_render_variant_id(profile)
    render_variant_label = export_profile_render_variant_label(profile)
    baseline_render_variant_id = export_profile_render_variant_id(baseline_profile or {})
    patch_tags = export_profile_patch_tags(profile)
    patch_labels = export_profile_patch_labels(profile)
    active_zones = export_profile_active_zones(profile)
    active_zone_labels = export_profile_active_zone_labels(profile)
    baseline_active_zones = export_profile_active_zones(baseline_profile or {})
    is_standard = bool(baseline_profile) and baseline_profile.get("id") == profile.get("id")

    diff_parts: list[str] = []
    variant_diff_summary = ""
    active_zone_diff_summary = ""
    if is_standard:
        diff_summary = "当前场景标准 Excel 页面结构"
    else:
        added = [item for item in sheet_order if item not in baseline_order]
        removed = [item for item in baseline_order if item not in sheet_order]
        if render_variant_id and render_variant_id != baseline_render_variant_id and render_variant_label:
            variant_diff_summary = f"渲染视图切换为：{render_variant_label}"
            diff_parts.append(variant_diff_summary)
        added_zones = [
            EXPORT_ACTIVE_ZONE_LABELS.get(zone, zone)
            for zone in active_zones
            if zone not in baseline_active_zones
        ]
        removed_zones = [
            EXPORT_ACTIVE_ZONE_LABELS.get(zone, zone)
            for zone in baseline_active_zones
            if zone not in active_zones
        ]
        zone_diff_parts: list[str] = []
        if added_zones:
            zone_diff_parts.append(f"活动区增加：{join_cn(added_zones)}")
        if removed_zones:
            zone_diff_parts.append(f"活动区移除：{join_cn(removed_zones)}")
        active_zone_diff_summary = "；".join(zone_diff_parts)
        if active_zone_diff_summary:
            diff_parts.append(active_zone_diff_summary)
        if added:
            diff_parts.append(f"比当前标准多：{join_cn(added)}")
        if removed:
            diff_parts.append(f"比当前标准少：{join_cn(removed)}")
        if baseline_order and sheet_order and baseline_order != sheet_order and not added and not removed:
            diff_parts.append(f"Excel 页面顺序调整为：{' / '.join(sheet_order)}")
        diff_summary = "；".join(diff_parts) if diff_parts else "与当前标准 Excel 页面结构接近"

    help_parts = []
    if profile.get("description"):
        help_parts.append(str(profile.get("description")))
    if render_variant_label:
        help_parts.append(f"渲染视图：{render_variant_label}")
    if patch_labels:
        help_parts.append(f"patch：{join_cn(patch_labels)}")
    if active_zone_labels:
        help_parts.append(f"活动区：{join_cn(active_zone_labels)}")
    if sheet_order:
        help_parts.append(f"导出页：{' / '.join(sheet_order)}")

    return {
        "label": label,
        "short_label": label,
        "help_text": "；".join(help_parts),
        "diff_summary": diff_summary,
        "render_variant_id": render_variant_id,
        "render_variant_label": render_variant_label,
        "patch_tags": patch_tags,
        "patch_labels": patch_labels,
        "active_zones": active_zones,
        "active_zone_labels": active_zone_labels,
        "variant_diff_summary": variant_diff_summary,
        "active_zone_diff_summary": active_zone_diff_summary,
        "sheet_order": sheet_order,
        "is_standard": is_standard,
    }


def humanize_source_compare_text(text: str | None) -> str:
    if not text:
        return ""
    value = str(text)
    replacements = {
        "merge ranges": "合并单元格范围",
        "merge pattern": "合并区模式",
        "freeze panes": "冻结窗格",
        "top merges": "顶部合并区",
        "anchor_texts": "固定文案锚点",
        "fill_positions": "填充位置",
        "column_widths": "列宽",
        "row_heights": "行高",
        "exact_data_merges": "精确合并单元格范围",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def customerize_compare_copy(text: str | None) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    replacements = {
        "exact_data_merges": "合并区范围",
        "top_merges": "顶部说明区",
        "anchor_texts": "固定标题文案",
        "fill_positions": "颜色标记位置",
        "freeze_panes": "冻结窗格",
        "column_widths": "列宽",
        "row_heights": "行高",
        "fonts": "字体",
        "alignments": "对齐",
        "borders": "边框",
        "merge ranges": "合并单元格范围",
        "merge pattern": "合并区模式",
        "freeze panes": "冻结窗格",
        "fill positions": "颜色标记位置",
        "anchor texts": "固定文案锚点",
        "精确 merge ranges": "合并区范围",
    }
    for source, target in replacements.items():
        content = content.replace(source, target)
    return content


def customerize_major_difference(text: str | None) -> str:
    content = humanize_source_compare_text(text).strip()
    if not content:
        return ""
    replacements = {
        "顶部合并区块与源模板不一致": "页头标题区还没完全贴齐",
        "数据区的组标签 / 状态字合并模式不一致": "数据区分组和状态字说明排布还有差异",
        "精确 merge ranges 仍与源模板不一致": "部分合并单元格起止范围还没贴齐",
        "列宽贴源度不足": "列宽还没完全贴齐",
        "行高贴源度不足": "行高还没完全贴齐",
        "填充坐标位置与源模板不一致": "底色与重点标注位置还有偏差",
        "颜色与填充策略差异较大": "颜色和填充策略还有明显差异",
        "字体样式分布与源模板不一致": "字体样式还没完全贴齐",
        "对齐 / 换行设置与源模板不一致": "对齐和换行设置还有差异",
        "边框样式与源模板不一致": "边框样式还有差异",
        "冻结窗格 与源模板不一致": "冻结窗格位置还没贴齐",
        "freeze panes 与源模板不一致": "冻结窗格位置还没贴齐",
        "固定文案锚点与关键标签位置存在偏差": "固定说明文案的位置还有偏差",
        "intro / 说明区文案没有完全贴源": "说明区文案还没完全贴齐",
        "表头文本或辅助列标题存在偏差": "部分表头文字和辅助标题还有偏差",
    }
    for source, target in replacements.items():
        content = content.replace(source, target)
    return content


def canonical_sheet_label(name: str | None) -> str:
    mapping = {
        "combined": "始端箱和插接箱",
        "repeater": "中继器",
        "alarm": "报警状态",
        "start": "始端箱",
        "plug": "插接箱",
        "cabinet": "单机柜数据",
        "route_a_data": "A路屏数据",
        "route_a_alarm": "A路屏报警",
        "route_b_data": "B路屏数据",
        "route_b_alarm": "B路屏报警",
    }
    value = str(name or "").strip()
    return mapping.get(value, value or "工作表")


def build_source_protocol_summary(source_compare: dict[str, Any] | None) -> dict[str, Any]:
    source_compare = source_compare or {}
    if source_compare.get("skipped_for_unified_workflow"):
        customer_message = "协议按当前项目参数和业务规则生成，不执行历史模板相似度对比。"
        return {
            "source_file": "",
            "reference_basis_label": "项目业务规则",
            "overview": customer_message,
            "customer_message": customer_message,
            "protocol_items": [],
            "layout_items": [],
            "qa_items": [],
            "structure_status": "not_applicable",
            "format_status": "not_applicable",
            "verdict": "skipped",
            "structure_label": "不适用",
            "format_label": "不适用",
        }
    if not source_compare:
        return {
            "source_file": "",
            "reference_basis_label": "当前场景参考口径",
            "overview": "生成后会补充与参考源文件的差异摘要。",
            "customer_message": "生成后会补充与参考源文件的差异摘要。",
            "protocol_items": [],
            "layout_items": [],
            "qa_items": [],
            "structure_status": "unknown",
            "format_status": "unknown",
            "verdict": "unknown",
            "structure_label": "未对照",
            "format_label": "未对照",
        }
    if source_compare.get("source_compare_unavailable"):
        reason = str(source_compare.get("error") or source_compare.get("source_compare_unavailable_reason") or "").strip()
        customer_message = "当前软件包未随附历史源协议，已跳过源文件贴合度对照；Excel 结构校验和生成结果仍可正常使用。"
        if reason:
            customer_message += f" 原因：{reason}"
        return {
            "source_file": "",
            "reference_basis_label": "当前场景参考口径",
            "overview": customer_message,
            "customer_message": customer_message,
            "protocol_items": ["未随软件包提供历史源协议，无法执行源文件点表对照。"],
            "layout_items": ["未随软件包提供历史源协议，无法执行源文件版式对照。"],
            "qa_items": ["交付前按项目实际要求抽查关键地址、报警页和下载文件。"],
            "structure_status": "unknown",
            "format_status": "unknown",
            "verdict": "not_checked",
            "structure_label": "未对照",
            "format_label": "未对照",
        }
    source_file = (
        source_compare.get("source_workbook", {}).get("file_name")
        or source_compare.get("representative_source", {}).get("file_name")
        or ""
    )
    structure_status = str(source_compare.get("structure_status") or "unknown")
    format_status = str(source_compare.get("format_status") or "unknown")
    verdict = str(source_compare.get("verdict") or source_compare.get("overall_status") or "unknown")
    protocol_items: list[str] = []
    layout_items: list[str] = []
    qa_items: list[str] = []

    if source_compare.get("sheet_order_match") is False:
        protocol_items.append("导出页面顺序与参考源文件不一致")

    missing_categories = [
        canonical_sheet_label(item) for item in source_compare.get("missing_categories", []) if str(item).strip()
    ]
    if missing_categories:
        protocol_items.append(f"当前仍缺参考源文件中的页面：{join_cn(missing_categories)}")

    for sheet in source_compare.get("sheets", []):
        sheet_name = (
            str(sheet.get("sheet_name") or "").strip()
            or str(sheet.get("generated_sheet") or "").strip()
            or str(sheet.get("source_sheet") or "").strip()
            or canonical_sheet_label(sheet.get("canonical_name"))
        )
        if structure_status != "match" and str(sheet.get("structure_status") or "unknown") not in {"match", "unknown"}:
            protocol_items.append(f"{sheet_name}：点表结构仍需按参考源文件复核")
            continue
        if str(sheet.get("format_status") or "unknown") == "diverged":
            major_differences = [customerize_major_difference(item) for item in sheet.get("major_differences", []) if str(item).strip()]
            if major_differences:
                layout_items.append(f"{sheet_name}：{major_differences[0]}")

    if structure_status == "match" and not protocol_items:
        protocol_items.append("点表结构与参考源文件一致，当前主要差异不在协议含义。")

    worst_sheet = source_compare.get("score_summary", {}).get("worst_sheet", {})
    if worst_sheet.get("sheet_name") and format_status in {"close", "diverged"}:
        layout_items.insert(0, f"{worst_sheet['sheet_name']}：当前与参考源文件的表头 / 排版差异最集中")

    for item in source_compare.get("top_priority_fixes", [])[:3]:
        sheet_name = item.get("sheet") or "重点页"
        label = customerize_compare_copy(item.get("metric") or item.get("label") or "重点项")
        qa_items.append(f"{sheet_name}：先核对{label}")

    if format_status == "match" and not layout_items and not qa_items:
        layout_items.append("表头 / 排版也已基本贴齐参考源文件。")

    if structure_status == "match" and format_status == "match":
        customer_message = "相对参考源文件，点表结构和表头 / 排版都已基本贴齐。"
    elif structure_status == "match" and format_status in {"close", "diverged"}:
        customer_message = "相对参考源文件，点表结构已对齐，当前主要差异集中在表头 / 排版。"
    else:
        customer_message = "相对参考源文件，仍有结构或关键页面需要人工复核。"

    overview = customer_message
    if verdict == "match":
        overview = f"{customer_message} 当前整体对照状态为一致。"
    elif verdict == "close":
        overview = f"{customer_message} 当前整体对照状态为接近。"
    elif verdict == "diverged":
        overview = f"{customer_message} 当前整体对照状态为差异较大。"

    status_labels = {
        "match": "一致",
        "close": "接近",
        "diverged": "差异较大",
        "unknown": "未对照",
    }
    return {
        "source_file": source_file,
        "reference_basis_label": "当前场景参考口径",
        "overview": overview,
        "customer_message": customer_message,
        "protocol_items": unique_preserve_order(protocol_items),
        "layout_items": unique_preserve_order(layout_items),
        "qa_items": unique_preserve_order(qa_items),
        "structure_status": structure_status,
        "format_status": format_status,
        "verdict": verdict,
        "structure_label": status_labels.get(structure_status, structure_status or "未对照"),
        "format_label": status_labels.get(format_status, format_status or "未对照"),
    }


def build_reference_basis_label(selected_profiles: dict[str, Any] | None) -> str:
    selected_profiles = selected_profiles or {}
    baseline = selected_profiles.get("baseline_context") or {}
    export_profile = selected_profiles.get("export_profile") or {}
    baseline_label = str(baseline.get("reference_label") or baseline.get("label") or "").strip()
    export_variant_label = str(export_profile.get("render_variant_label") or "").strip()
    export_label = str(export_profile.get("short_label") or export_profile.get("label") or "").strip()
    if baseline_label:
        return f"{baseline_label} 参考口径"
    if export_variant_label:
        return f"{export_variant_label} 参考口径"
    if export_label:
        return f"{export_label} 参考口径"
    return "当前场景参考口径"


def build_baseline_context_details(
    library: TemplateLibrary,
    family: str | None,
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    export_profile = resolve_baseline_export_profile(library, family, profiles)
    baseline_bundle = export_profile_baseline_bundle(export_profile)
    export_descriptor = (
        build_export_profile_descriptor(export_profile, export_profile)
        if export_profile
        else {}
    )
    render_variant_id = export_descriptor.get("render_variant_id")
    render_variant_label = export_descriptor.get("render_variant_label")
    patch_labels = list(export_descriptor.get("patch_labels", []) or [])
    active_zone_labels = list(export_descriptor.get("active_zone_labels", []) or [])
    display_label = str(export_descriptor.get("label") or "").strip()
    reference_label = template_plan_label(
        render_variant_label,
        display_label,
        patch_labels,
        fallback=str(display_label or family or "当前标准方案"),
    )
    key = str(export_profile.get("id") or family or CLASSIC_DEFAULT_EXPORT_PROFILE_ID)
    return {
        "key": key,
        "family": export_profile.get("family") or family,
        "export_profile_id": export_profile.get("id"),
        "address_profile_id": baseline_bundle.get("address_profile_id"),
        "start_box_template_id": baseline_bundle.get("start_box_template_id"),
        "plug_branch_template_id": baseline_bundle.get("plug_branch_template_id"),
        "repeater_template_id": baseline_bundle.get("repeater_template_id"),
        "single_cabinet_template_id": baseline_bundle.get("single_cabinet_template_id"),
        "label": reference_label or display_label,
        "display_label": display_label or reference_label,
        "export_profile_label": display_label or reference_label,
        "render_variant_id": render_variant_id,
        "render_variant_label": render_variant_label,
        "patch_labels": patch_labels,
        "active_zone_labels": active_zone_labels,
        "reference_label": reference_label,
    }


def board_layout_variant_label(pattern: str) -> str:
    parts = [item for item in str(pattern).split("+") if item]
    if not parts:
        return pattern
    single_count = parts.count("1")
    dual_count = parts.count("2")
    labels: list[str] = []
    if dual_count:
        labels.append(f"{dual_count} 块双回路板")
    if single_count:
        labels.append(f"{single_count} 块单回路板")
    if not labels:
        labels.append(f"{len(parts)} 块板卡")
    return f"{' + '.join(labels)}（{pattern}）"


def box_type_label(box_type: dict[str, Any]) -> str:
    type_code = box_type["type_code"]
    if box_type.get("phase_mode") == "single_phase_triplet":
        return f"单相 {box_type.get('branch_count', 0)} 回路（{type_code}）"
    return f"三相 {box_type.get('branch_count', 0)} 回路（{type_code}）"


def humanize_address_profile(profile: dict[str, Any]) -> str:
    return build_address_descriptor(profile)["label"]


def humanize_template(template: dict[str, Any], template_type: str) -> str:
    return build_template_descriptor(template, template_type)["label"]


def template_register_footprint(template: dict[str, Any]) -> int:
    state_word_mode = template.get("state_word_mode", "16bit")
    total = 0
    for prefix in template.get("point_prefix_sequence", []):
        if str(prefix).startswith("State"):
            total += 2 if state_word_mode == "32bit" else 1
        else:
            total += 2
    return total


def point_prefix_meta(prefix: Any) -> tuple[str, str | None]:
    raw_prefix = str(prefix or "").strip()
    if raw_prefix in PREFIX_META:
        return PREFIX_META[raw_prefix]
    base_prefix = re.sub(r"\d+_?$", "", raw_prefix)
    if base_prefix in PREFIX_META:
        return PREFIX_META[base_prefix]
    return raw_prefix or "未命名点位", None


def build_point_preview(template: dict[str, Any]) -> list[dict[str, Any]]:
    state_word_mode = str(template.get("state_word_mode") or "16bit")
    dual_dataset = template.get("dataset_group_mode") == "dual_output_board_split"
    split_index = int(template.get("dataset_group_split_index", 24) or 24)
    strip_token = str(template.get("secondary_prefix_strip_token", "101_") or "101_")
    points: list[dict[str, Any]] = []
    for index, raw_prefix in enumerate(template.get("point_prefix_sequence") or [], start=1):
        prefix = str(raw_prefix)
        dataset_group = 2 if dual_dataset and index > split_index else 1
        if dataset_group == 2 and strip_token and prefix.endswith(strip_token):
            prefix = prefix[: -len(strip_token)]
        name, unit = point_prefix_meta(prefix)
        is_state_word = prefix.startswith("State")
        data_type = (
            "32位 无符号二进制"
            if is_state_word and state_word_mode == "32bit"
            else "16位 无符号二进制"
            if is_state_word
            else "32位 浮点数"
        )
        points.append(
            {
                "index": index,
                "prefix": prefix,
                "variable_pattern": (
                    f"{prefix}{{设备号}}_2"
                    if dual_dataset and dataset_group == 2
                    else f"{prefix}{{设备号}}"
                ),
                "dataset_group": dataset_group if dual_dataset else None,
                "name": name,
                "unit": unit,
                "data_type": data_type,
            }
        )
    return points


def single_cabinet_register_footprint(template: dict[str, Any]) -> int:
    metric_sequence = list(template.get("metric_sequence") or [])
    metric_definitions = dict(template.get("metric_definitions") or {})
    if not metric_sequence:
        metric_sequence = ["IA"]
    if not metric_definitions:
        metric_definitions = {
            "IA": {
                "register_size": 2,
            }
        }
    return sum(int(metric_definitions.get(metric_code, {}).get("register_size", 2)) for metric_code in metric_sequence)


def layout_branch_allocation_count(library: TemplateLibrary, layout_variant: dict[str, Any]) -> int:
    board_sequence = layout_variant.get("board_template_sequence") or layout_variant.get("board_template_ids") or []
    total = 0
    for board_template_id in board_sequence:
        board_template = library.board_templates.get(board_template_id, {})
        if board_template.get("phase_mode") == "single_phase_triplet":
            total += 1
        else:
            total += int(board_template.get("branch_capacity", 0) or 0)
    return total


def normalize_config(raw_config: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    config = normalize_unified_workflow_input(raw_config)
    unified_workflow = is_unified_workflow(config)
    config.setdefault("profiles", {})
    config.setdefault("topology", {})
    config.setdefault("communication", {})
    config.setdefault("devices", {})
    requested_export_profile_id = "" if unified_workflow else str(config["profiles"].get("export_profile_id") or "").strip()
    requested_export_profile = library.export_profile_map.get(requested_export_profile_id)
    family_hint = family_hint_for_topology(
        config["topology"].get("screen_topology_mode"),
        "classic_combined"
        if unified_workflow
        else (requested_export_profile.get("family") if requested_export_profile else config.get("export_family")),
    )
    topology_mode = config["topology"].get("screen_topology_mode")
    config["topology"]["screen_count"] = max(1, int(config["topology"].get("screen_count", 1) or 1))
    config["topology"]["columns_per_screen"] = max(1, int(config["topology"].get("columns_per_screen", 1) or 1))
    if topology_mode == "single_screen_two_columns":
        config["topology"]["screen_route_binding"] = "both_routes_in_one_screen"
        config["topology"]["columns_per_screen"] = 2
    elif topology_mode in {"single_screen_one_column", "single_screen_half_channel"}:
        config["topology"]["screen_route_binding"] = "both_routes_in_one_screen"
        config["topology"]["columns_per_screen"] = 1
    elif topology_mode == "dual_screens_ab_separated":
        config["topology"]["screen_route_binding"] = "A_screen_and_B_screen_separate"
        config["topology"]["screen_count"] = max(2, int(config["topology"].get("screen_count", 2) or 2))
        config["topology"]["columns_per_screen"] = 1
    config.setdefault("protocol_title", "上位机通讯协议")
    config.setdefault("project_code", "")
    config["communication"].setdefault("protocol", "Modbus RTU")
    config["communication"].setdefault("baud_rate", 9600)
    config["communication"].setdefault("parity", "N")
    config["communication"].setdefault("data_bits", 8)
    config["communication"].setdefault("stop_bits", 1)
    config["communication"].setdefault("default_screen_address", 1)
    config["devices"].setdefault("repeater_units", {"enabled": False, "A_count": 0, "B_count": 0})
    config["devices"].setdefault("single_cabinet_aggregation", {"enabled": False, "cabinet_count": 0})
    config["devices"].setdefault(
        "start_boxes",
        {
            "A": {"count": 1, "instance_names": ["S1"]},
            "B": {"count": 1, "instance_names": ["S2"]},
        },
    )
    config["devices"].setdefault("plug_boxes", {"A": {"board_number_start": 101, "sequence": []}, "B": {"board_number_start": 201, "sequence": []}})

    if unified_workflow:
        export_profile, unified_profile_bundle = install_unified_internal_profiles(config, library)
    else:
        export_profile = resolve_export_profile_for_config(library, config["profiles"], family_hint=family_hint)
        unified_profile_bundle = {}
    if export_profile:
        config["profiles"]["export_profile_id"] = export_profile["id"]

    source_export_profile = requested_export_profile or baseline_export_profile_for_family(
        library,
        export_profile.get("family") if export_profile else family_hint,
    )

    if not unified_workflow and topology_mode == "single_screen_two_columns":
        if config["topology"].get("upload_port_profile") in (None, "", "A4B4"):
            config["topology"]["upload_port_profile"] = "A3B3"
        if requested_export_profile is None or bool(source_export_profile.get("is_family_baseline")):
            two_column_profile = find_export_profile(
                library,
                family="classic_combined",
                render_variant_id="classic_two_columns",
                topology_mode="single_screen_two_columns",
            )
            if two_column_profile:
                export_profile = two_column_profile
                config["profiles"]["export_profile_id"] = two_column_profile["id"]
    elif not unified_workflow and export_profile and export_profile_render_variant_id(export_profile) == "classic_two_columns":
        fallback_profile = baseline_export_profile_for_family(library, export_profile.get("family") or family_hint)
        if fallback_profile:
            export_profile = fallback_profile
            config["profiles"]["export_profile_id"] = fallback_profile["id"]

    single_cabinet_cfg = config["devices"].get("single_cabinet_aggregation", {})
    single_cabinet_enabled = bool(single_cabinet_cfg.get("enabled")) and int(single_cabinet_cfg.get("cabinet_count") or 0) > 0
    if (
        not unified_workflow
        and export_profile.get("family") == "classic_combined"
        and export_profile_render_variant_id(export_profile) not in {"classic_liquidcool", "classic_two_columns"}
        and single_cabinet_enabled
        and (requested_export_profile is None or bool(export_profile.get("is_family_baseline")))
    ):
        cabinet_profile = find_export_profile(
            library,
            family="classic_combined",
            render_variant_id="classic_standard",
            include_single_cabinet_sheet=True,
            split_ab_screens=False,
        )
        if cabinet_profile:
            export_profile = cabinet_profile
            config["profiles"]["export_profile_id"] = cabinet_profile["id"]

    if export_profile:
        migratable_defaults = build_migratable_profile_defaults(
            library,
            family=export_profile.get("family"),
            source_export_profile=source_export_profile,
            legacy_values={"single_cabinet_template_id": {LEGACY_EXTENDED_DEMO_TEMPLATE_ID}},
        )
        apply_export_profile_bundle_defaults(
            config["profiles"],
            export_profile_baseline_bundle(export_profile),
            migratable_defaults=migratable_defaults,
        )
        if unified_workflow:
            # Unified workflow parameters, not client-supplied template ids,
            # are the source of truth for all internal profile selection.
            config["profiles"].update(unified_profile_bundle)
            config["profiles"]["export_profile_id"] = export_profile["id"]
            config["profiles"]["device_library_id"] = library.device_library.get("id")
        config["export_family"] = export_profile["family"]

    if (
        export_profile.get("family") == "extended_split"
        and config.get("project_code") == LEGACY_EXTENDED_DEMO_PROJECT_CODE
        and bool(single_cabinet_cfg.get("enabled"))
        and int(single_cabinet_cfg.get("cabinet_count") or 0) == LEGACY_EXTENDED_DEMO_CABINET_COUNT
        and config["profiles"].get("single_cabinet_template_id") == LEGACY_EXTENDED_DEMO_TEMPLATE_ID
    ):
        single_cabinet_cfg["cabinet_count"] = 38
        config["profiles"]["single_cabinet_template_id"] = LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID

    return config


def build_box_type_options(library: TemplateLibrary) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for box_type in library.device_library.get("plug_box_physical_types", []):
        layout_variants = []
        for item in box_type.get("allowed_layout_patterns", []):
            layout_variants.append(
                {
                    "pattern": item["pattern"],
                    "value": item["pattern"],
                    "label": board_layout_variant_label(item["pattern"]),
                    "short_label": item["pattern"],
                    "help_text": f"{item['board_count']} 块板卡，合计 {item['branch_count']} 回路",
                    "board_count": item["board_count"],
                    "branch_count": item["branch_count"],
                    "board_template_ids": item["board_template_ids"],
                    "branch_allocation_count": layout_branch_allocation_count(library, item),
                }
            )
        options.append(
            {
                "type_code": box_type["type_code"],
                "label": box_type_label(box_type),
                "short_label": box_type["type_code"],
                "aliases": box_type.get("aliases", []),
                "phase_mode": box_type["phase_mode"],
                "branch_count": box_type["branch_count"],
                "default_layout_pattern": box_type.get("default_layout_pattern"),
                "allowed_layout_patterns": layout_variants,
                "notes": box_type.get("notes", ""),
                "help_text": box_type.get("notes", ""),
            }
        )
    return options


def build_template_options(library: TemplateLibrary) -> dict[str, list[dict[str, Any]]]:
    device_library = library.device_library
    baseline_start = baseline_template_for(library, "start")
    baseline_plug = baseline_template_for(library, "plug")
    baseline_repeater = baseline_template_for(library, "repeater")
    baseline_cabinet = baseline_template_for(library, "cabinet")
    return {
        "start_box_templates": [
            {
                "id": item["id"],
                **build_template_descriptor(
                    item,
                    "start",
                    baseline_start,
                ),
                "row_span": item.get("row_span"),
                "point_count": len(item.get("point_prefix_sequence", [])),
                "points": build_point_preview(item),
                "state_word_mode": item.get("state_word_mode", "16bit"),
                "register_footprint": template_register_footprint(item),
            }
            for item in device_library.get("start_box_templates", [])
        ],
        "plug_branch_templates": [
            {
                "id": item["id"],
                **build_template_descriptor(
                    item,
                    "plug",
                    baseline_plug,
                ),
                "row_span": item.get("row_span"),
                "point_count": len(item.get("point_prefix_sequence", [])),
                "points": build_point_preview(item),
                "state_word_mode": item.get("state_word_mode", "16bit"),
                "register_footprint": template_register_footprint(item),
                "dataset_group_mode": item.get("dataset_group_mode"),
                "required_board_template_id": item.get("required_board_template_id"),
            }
            for item in device_library.get("plug_branch_templates", [])
        ],
        "repeater_templates": [
            {
                "id": item["id"],
                **build_template_descriptor(
                    item,
                    "repeater",
                    baseline_repeater,
                ),
                "row_span": item.get("row_span"),
                "point_count": len(item.get("point_prefix_sequence", [])),
                "state_word_mode": item.get("state_word_mode", "16bit"),
                "register_footprint": template_register_footprint(item),
            }
            for item in device_library.get("repeater_templates", [])
        ],
        "single_cabinet_templates": [
            {
                "id": item["id"],
                **build_template_descriptor(
                    item,
                    "cabinet",
                    baseline_cabinet,
                ),
                "row_span": item.get("row_span"),
                "point_count": len(item.get("point_prefix_sequence", [])),
                "register_footprint_per_cabinet": single_cabinet_register_footprint(item),
                "metric_count": len(item.get("metric_sequence") or []),
                "route_split_register_footprint_per_cabinet": sum(
                    int((item.get("metric_definitions") or {}).get(metric_code, {}).get("register_size", 2))
                    for metric_code in (item.get("metric_sequence") or [])
                    if metric_code in {"IA", "PA", "EA"}
                ),
            }
            for item in device_library.get("single_cabinet_templates", [])
        ],
    }


def build_family_profiles(library: TemplateLibrary) -> dict[str, dict[str, Any]]:
    family_profiles: dict[str, dict[str, Any]] = {}
    for family, meta in FAMILY_META.items():
        baseline_context = build_baseline_context_details(
            library,
            family,
            {"export_profile_id": family_default_export_profile_id(library, family)},
        )
        baseline_address = library.address_profile_map.get(baseline_context.get("address_profile_id"))
        baseline_export = library.export_profile_map.get(baseline_context.get("export_profile_id"))
        address_profiles = [
            {
                "id": item["id"],
                **build_address_descriptor(item, baseline_address),
                "family": item["family"],
                "main_base": item["main_base"],
                "plug_base": item.get("plug_base"),
                "cabinet_base": item.get("cabinet_base"),
                "repeater_base": item.get("repeater_base"),
                "alarm_base": item["alarm_base"],
                "alarm_word_mode": item.get("alarm_word_mode"),
                "register_step": item.get("register_step", 2),
            }
            for item in library.address_profiles.get("profiles", [])
            if item.get("family") == family
        ]
        export_profiles = [
            {
                "id": item["id"],
                **build_export_profile_descriptor(item, baseline_export),
                "family": item["family"],
                "sheet_order": item.get("sheet_order", []),
                "description": item.get("description"),
            }
            for item in library.export_profiles.get("profiles", [])
            if item.get("family") == family
        ]
        family_profiles[family] = {
            "family": family,
            "label": meta["label"],
            "tagline": meta["tagline"],
            "address_profiles": address_profiles,
            "export_profiles": export_profiles,
            "topology_modes": meta["topology_modes"],
        }
    return family_profiles


def build_example_configs(library: TemplateLibrary) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for family, path in EXAMPLE_PATHS.items():
        if path.exists():
            result[family] = normalize_config(load_json(path), library)
    return result


def build_scenario_options(examples: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in SCENARIO_OPTIONS:
        example_key = item["example_key"]
        if example_key not in examples:
            continue
        result.append(
            {
                **item,
                "example_key": example_key,
                "config": examples[example_key],
            }
        )
    return result


def build_bootstrap_payload() -> dict[str, Any]:
    library = TemplateLibrary.load()
    examples = build_example_configs(library)
    family_profiles = build_family_profiles(library)
    defaults = {
        family: {
            "address_profile_id": example["profiles"]["address_profile_id"],
            "export_profile_id": example["profiles"]["export_profile_id"],
            "start_box_template_id": example["profiles"].get("start_box_template_id"),
            "plug_branch_template_id": example["profiles"].get("plug_branch_template_id"),
            "repeater_template_id": example["profiles"].get("repeater_template_id"),
            "single_cabinet_template_id": example["profiles"].get("single_cabinet_template_id"),
        }
        for family, example in examples.items()
    }
    export_profiles_flat = [
        item for family in family_profiles.values() for item in family["export_profiles"]
    ]
    address_profiles_flat = [
        item for family in family_profiles.values() for item in family["address_profiles"]
    ]
    family_defaults = {
        family: {"config": example, "profiles": defaults[family]}
        for family, example in examples.items()
    }
    workflow = {
        "id": UNIFIED_WORKFLOW_ID,
        "version": UNIFIED_WORKFLOW_VERSION,
        "label": "统一动环协议生成流程",
        "product_model": "parameterized_protocol_compiler",
        "generation_basis": "max_column",
        "template_strategy": "internal_rules_only",
        "template_selection_exposed": False,
        "steps": [
            {"id": "project", "label": "项目信息", "order": 1},
            {"id": "route_a", "label": "A 路最大设备", "order": 2},
            {"id": "route_b", "label": "B 路最大设备", "order": 3, "supports_copy_from": "route_a"},
            {"id": "extensions", "label": "扩展项", "order": 4},
            {"id": "review", "label": "整体参数总览", "order": 5},
            {"id": "generate", "label": "生成与下载", "order": 6},
        ],
        "extensions": [
            {
                "id": "single_cabinet",
                "label": "单机柜数据",
                "default_enabled": False,
                "parameter_keys": ["cabinet_count"],
            },
            {
                "id": "repeater",
                "label": "中继",
                "default_enabled": False,
                "parameter_keys": ["A_count", "B_count", "alias"],
            },
            {
                "id": "alarm_state_word",
                "label": "报警状态字",
                "default_enabled": True,
                "parameter_keys": ["base_address", "word_mode", "legacy_slide_rail_order"],
                "word_mode_options": ["16bit", "32bit"],
            },
        ],
        "internal_profile_selection": {
            "mode": "automatic",
            "visible_to_user": False,
            "description": "系统按 A/B 路、扩展项和地址参数自动编译最终表结构。",
        },
    }
    delivery_bundle = {
        "id": "protocol_delivery_bundle_v1",
        "required_keys": ["excel", "alarm_code", "program_upload"],
        "items": [
            {
                "key": "excel",
                "label": "动环通讯协议",
                "extension": ".xlsx",
                "file_name_suffix": "动环通讯协议.xlsx",
                "required": True,
            },
            {
                "key": "alarm_code",
                "label": "报警状态字上传代码",
                "extension": ".txt",
                "file_name_suffix": "报警状态字上传代码.txt",
                "required": True,
            },
            {
                "key": "program_upload",
                "label": "MCGS 动环上传设备导入表",
                "extension": ".csv",
                "file_name_suffix": "MCGS动环上传设备导入.csv",
                "required": True,
            },
        ],
    }
    return {
        "app": {
            "name": "动环协议出表工作台",
            "device_library_id": library.device_library.get("id"),
        },
        "meta": {
            "app_name": "动环协议出表工作台",
            "app_subtitle": "面向协议编写师的单任务出表工具",
            "device_library_id": library.device_library.get("id"),
        },
        "families": family_profiles,
        "defaults": defaults,
        "templates": build_template_options(library),
        "box_types": build_box_type_options(library),
        "examples": examples,
        "profiles": {
            "families": list(FAMILY_META.keys()),
            "export_profiles": export_profiles_flat,
            "address_profiles": address_profiles_flat,
        },
        "family_defaults": family_defaults,
        "scenarios": build_scenario_options(examples),
        "workflow": workflow,
        "delivery_bundle": delivery_bundle,
        "options": {
            "screen_topology_modes": SCREEN_TOPOLOGY_OPTIONS,
            "screen_route_bindings": SCREEN_BINDING_OPTIONS,
            "upload_port_profiles": UPLOAD_PORT_OPTIONS,
            "physical_ports": UPLOAD_PORT_OPTIONS,
            "hardware_form_factors": HARDWARE_FORM_FACTOR_OPTIONS,
            "bus_data_port_modes": BUS_DATA_PORT_MODE_OPTIONS,
        },
        "capabilities": {
            "validation": True,
            "source_compare": True,
            "recent_runs": True,
            "recommendation": True,
            "unified_workflow": True,
            "automatic_internal_profiles": True,
            "three_file_delivery": True,
        },
        "recent_runs": list_recent_runs(),
        "topology_options": {
            "screen_topology_mode": SCREEN_TOPOLOGY_OPTIONS,
            "screen_route_binding": SCREEN_BINDING_OPTIONS,
        },
    }


def sanitize_file_stem(text: str) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text)
    compact = "_".join(segment for segment in safe.split("_") if segment)
    return compact[:80] or "protocol"


def excel_suffix_for_family(family: str) -> str:
    return {
        "classic_combined": "classic",
        "extended_split": "extended",
        "ab_screen_split": "ab",
    }[family]


def render_excel(output: dict[str, Any], excel_path: Path) -> None:
    family = output["profiles"]["export_profile"]["family"]
    if family == "classic_combined":
        renderer = ClassicCombinedRenderer(output)
    elif family == "extended_split":
        renderer = ExtendedSplitRenderer(output)
    elif family == "ab_screen_split":
        renderer = AbScreenSplitRenderer(output)
    else:
        raise NotImplementedError(f"未支持的导出 family: {family}")
    renderer.render_to_path(excel_path)


def compute_route_summary(route_model: dict[str, Any]) -> dict[str, Any]:
    start_count = len(route_model.get("start_boxes", []))
    physical_boxes = route_model.get("physical_plug_boxes", [])
    repeater_count = len(route_model.get("repeater_units", []))
    board_count = sum(len(box.get("boards", [])) for box in physical_boxes)
    branch_count = 0
    point_count = 0
    structure_only_count = 0

    for start_box in route_model.get("start_boxes", []):
        point_count += len(start_box.get("points", []))
    for repeater in route_model.get("repeater_units", []):
        point_count += len(repeater.get("points", []))
    for physical_box in physical_boxes:
        has_real_points = False
        for board in physical_box.get("boards", []):
            for branch in board.get("branches", []):
                branch_count += int(branch.get("logical_output_count") or 1)
                branch_points = branch.get("points", [])
                point_count += len(branch_points)
                if branch_points:
                    has_real_points = True
        if not has_real_points:
            structure_only_count += 1

    return {
        "route": route_model["route"],
        "start_box_count": start_count,
        "physical_box_count": len(physical_boxes),
        "board_count": board_count,
        "branch_count": branch_count,
        "repeater_count": repeater_count,
        "point_count": point_count,
        "structure_only_box_count": structure_only_count,
    }


def build_selected_profile_snapshot(library: TemplateLibrary, config: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    start_templates = template_lookup_map(library, "start")
    plug_templates = template_lookup_map(library, "plug")
    repeater_templates = template_lookup_map(library, "repeater")
    cabinet_templates = template_lookup_map(library, "cabinet")

    start_template = start_templates.get(profiles.get("start_box_template_id"))
    plug_template = plug_templates.get(profiles.get("plug_branch_template_id"))
    repeater_template = repeater_templates.get(profiles.get("repeater_template_id"))
    cabinet_template = cabinet_templates.get(profiles.get("single_cabinet_template_id"))
    address_profile = library.address_profile_map.get(profiles.get("address_profile_id"))
    export_profile = library.export_profile_map.get(profiles.get("export_profile_id"))

    baseline_profiles = resolve_profile_baselines(library, profiles)
    baseline_address = baseline_profiles.get("address_profile")
    baseline_context = build_baseline_context_details(
        library,
        export_profile.get("family") if export_profile else None,
        profiles,
    )
    baseline_export = library.export_profile_map.get(baseline_context.get("export_profile_id"))

    return {
        "baseline_context": {
            "key": baseline_context.get("key"),
            "label": baseline_context.get("label"),
            "reference_label": baseline_context.get("reference_label"),
            "display_label": baseline_context.get("display_label"),
            "family": baseline_context.get("family"),
            "export_profile_id": baseline_context.get("export_profile_id"),
            "render_variant_id": baseline_context.get("render_variant_id"),
            "render_variant_label": baseline_context.get("render_variant_label"),
            "patch_labels": baseline_context.get("patch_labels", []),
            "active_zone_labels": baseline_context.get("active_zone_labels", []),
        },
        "export_profile": {
            "id": export_profile.get("id") if export_profile else None,
            **(build_export_profile_descriptor(export_profile, baseline_export) if export_profile else {}),
        },
        "address_profile": {
            "id": address_profile.get("id") if address_profile else None,
            **(build_address_descriptor(address_profile, baseline_address) if address_profile else {}),
        },
        "start_box_template": {
            "id": start_template.get("id") if start_template else None,
            **(
                build_template_descriptor(
                    start_template,
                    "start",
                    baseline_profiles.get("start_box_template"),
                )
                if start_template
                else {}
            ),
        },
        "plug_branch_template": {
            "id": plug_template.get("id") if plug_template else None,
            **(
                build_template_descriptor(
                    plug_template,
                    "plug",
                    baseline_profiles.get("plug_branch_template"),
                )
                if plug_template
                else {}
            ),
        },
        "repeater_template": {
            "id": repeater_template.get("id") if repeater_template else None,
            **(
                build_template_descriptor(
                    repeater_template,
                    "repeater",
                    baseline_profiles.get("repeater_template"),
                )
                if repeater_template
                else {}
            ),
        },
        "single_cabinet_template": {
            "id": cabinet_template.get("id") if cabinet_template else None,
            **(
                build_template_descriptor(
                    cabinet_template,
                    "cabinet",
                    baseline_profiles.get("single_cabinet_template"),
                )
                if cabinet_template
                else {}
            ),
        },
    }


def build_address_cards(summary: dict[str, Any], output: dict[str, Any]) -> list[dict[str, Any]]:
    address_summary = dict(summary.get("address_summary", {}))
    profile = output.get("profiles", {}).get("address_profile", {})
    route_addresses = dict(address_summary.get("routes", {}))
    cards: list[dict[str, Any]] = []
    if route_addresses:
        for route in ("A", "B"):
            route_summary = route_addresses.get(route) or {}
            if route_summary.get("main_next_address") is not None:
                cards.append(
                    {
                        "label": f"{route} 路主数据尾地址后一个地址",
                        "value": route_summary.get("main_next_address"),
                        "note": f"{route} 路主数据从 {profile.get('main_base', '-')} 起排",
                    }
                )
            if route_summary.get("plug_next_address") is not None:
                cards.append(
                    {
                        "label": f"{route} 路插接箱地址段尾地址后一个地址",
                        "value": route_summary.get("plug_next_address"),
                        "note": f"{route} 路插接箱地址从 {profile.get('plug_base', '-')} 起排",
                    }
                )
    else:
        cards.append(
            {
                "label": "主数据尾地址后一个地址",
                "value": address_summary.get("main_next_address"),
                "note": f"主数据从 {profile.get('main_base', '-')} 起排",
            }
        )
        if profile.get("plug_base") is not None or address_summary.get("plug_next_address") is not None:
            cards.append(
                {
                    "label": "插接箱地址段尾地址后一个地址",
                    "value": address_summary.get("plug_next_address") or profile.get("plug_base"),
                    "note": f"插接箱地址从 {profile.get('plug_base', '-')} 起排",
                }
            )
    cards.append(
        {
            "label": "报警页起始地址",
            "value": address_summary.get("alarm_base"),
            "note": humanize_alarm_word_mode(address_summary.get("alarm_word_mode")),
        }
    )
    if profile.get("repeater_base") is not None or address_summary.get("repeater_next_address") is not None:
        cards.append(
            {
                "label": "中继地址段",
                "value": address_summary.get("repeater_next_address") or profile.get("repeater_base"),
                "note": f"起始 {profile.get('repeater_base', '-')}",
            }
        )
    if address_summary.get("cabinet_start_address") is not None:
        cards.append(
            {
                "label": "单机柜地址段",
                "value": address_summary.get("cabinet_start_address"),
                "note": (
                    f"下一地址 {address_summary.get('cabinet_next_address')}"
                    if address_summary.get("cabinet_next_address") is not None
                    else "按模板/数量自动推导"
                ),
            }
        )
    return cards


def build_protocol_diff_summary(
    library: TemplateLibrary,
    config: dict[str, Any],
    output: dict[str, Any],
    summary: dict[str, Any],
    selected_profiles: dict[str, Any],
    delivery_status: dict[str, Any] | None = None,
    source_compare: dict[str, Any] | None = None,
) -> dict[str, Any]:
    export_profile = selected_profiles.get("export_profile", {})
    address_profile = selected_profiles.get("address_profile", {})
    sheet_order = export_profile.get("sheet_order", []) or summary.get("sheet_order", [])
    family = summary.get("family")
    totals = summary.get("totals", {})
    baseline_context = selected_profiles.get("baseline_context") or build_baseline_context_details(
        library,
        family,
        config.get("profiles", {}),
    )
    baseline_export_id = baseline_context.get("export_profile_id") or family_default_export_profile_id(library, family)
    baseline_sheet_order = []
    if baseline_export_id and output.get("profiles", {}).get("export_profile", {}).get("family") == family:
        baseline_sheet_order = library.export_profile_map.get(baseline_export_id, {}).get("sheet_order", [])

    added_sheets = [item for item in sheet_order if item not in baseline_sheet_order]
    removed_sheets = [item for item in baseline_sheet_order if item not in sheet_order]
    sheet_changes: list[str] = []
    if added_sheets:
        sheet_changes.append(f"比当前标准 Excel 页面结构多：{join_cn(added_sheets)}")
    if removed_sheets:
        sheet_changes.append(f"比当前标准 Excel 页面结构少：{join_cn(removed_sheets)}")
    if baseline_sheet_order and sheet_order and baseline_sheet_order != sheet_order and not added_sheets and not removed_sheets:
        sheet_changes.append(f"Excel 页面顺序调整为：{' / '.join(sheet_order)}")
    variant_changes: list[str] = []
    if export_profile.get("variant_diff_summary"):
        variant_changes.append(str(export_profile.get("variant_diff_summary")))
    if export_profile.get("active_zone_diff_summary"):
        variant_changes.append(str(export_profile.get("active_zone_diff_summary")))

    template_changes: list[str] = []
    for key, title in (
        ("start_box_template", "始端箱"),
        ("plug_branch_template", "插接箱"),
        ("repeater_template", "中继"),
        ("single_cabinet_template", "单机柜"),
    ):
        detail = selected_profiles.get(key) or {}
        if not detail.get("id"):
            continue
        if key == "repeater_template" and "中继器" not in sheet_order and not totals.get("repeater_count"):
            continue
        if key == "single_cabinet_template" and not totals.get("single_cabinet_count"):
            continue
        if detail.get("diff_summary") and detail.get("diff_summary") not in {"标准模板", "当前场景标准模板"}:
            template_changes.append(f"{title}：{detail['diff_summary']}")

    address_changes: list[str] = []
    if address_profile.get("diff_summary") and address_profile.get("diff_summary") not in {"与标准地址方案一致", "与当前标准地址方案一致"}:
        address_changes.append(address_profile["diff_summary"])
    route_addresses = dict(summary.get("address_summary", {}).get("routes", {}))
    if route_addresses and family == "ab_screen_split":
        for route in ("A", "B"):
            route_summary = route_addresses.get(route) or {}
            if route_summary.get("main_next_address") is not None:
                address_changes.append(f"{route} 路主数据尾地址后一个地址：{route_summary.get('main_next_address')}")

    alarm_changes = [f"报警采用 {humanize_alarm_word_mode(summary.get('address_summary', {}).get('alarm_word_mode'))}"]
    if family == "ab_screen_split":
        alarm_changes.append("A 路 / B 路报警独立分页导出")
    elif "报警状态" in sheet_order:
        alarm_changes.append("报警统一输出在“报警状态”页")

    review_items = list(summary.get("warnings", []))
    blocking_items: list[str] = []
    if delivery_status:
        review_items.extend(delivery_status.get("review_items", []))
        blocking_items.extend(delivery_status.get("blockers", []))

    focus_items: list[str] = []
    worst_sheet = (source_compare or {}).get("score_summary", {}).get("worst_sheet", {})
    if worst_sheet.get("sheet_name"):
        worst_score = worst_sheet.get("overall_score")
        worst_score_text = f"{float(worst_score):.1f}" if worst_score is not None else "-"
        focus_items.append(
            f"优先核对 {worst_sheet['sheet_name']} 页，当前贴源分约 {worst_score_text}"
        )

    scenario_label = export_profile.get("label") or summary.get("family") or "当前方案"
    render_variant_label = export_profile.get("render_variant_label")
    active_zone_labels = list(export_profile.get("active_zone_labels", []) or [])
    baseline_label = baseline_context.get("reference_label") or baseline_context.get("label") or "当前标准方案"
    scenario_descriptor = render_variant_label or scenario_label
    if render_variant_label and scenario_label and render_variant_label != scenario_label:
        scenario_descriptor = f"{render_variant_label}（{scenario_label}）"
    overview = (
        f"相对 {baseline_label}，当前采用 {scenario_descriptor}：共 {totals.get('board_count', 0)} 板、"
        f"{totals.get('branch_count', 0)} 回路、{len(sheet_order)} 个工作表。"
    )
    if active_zone_labels:
        overview += f" 活动区包括：{join_cn(active_zone_labels)}。"

    return {
        "overview": overview,
        "variant_changes": unique_preserve_order(variant_changes),
        "sheet_changes": unique_preserve_order(sheet_changes),
        "template_changes": unique_preserve_order(template_changes),
        "address_changes": unique_preserve_order(address_changes),
        "alarm_changes": unique_preserve_order(alarm_changes),
        "review_items": unique_preserve_order(review_items),
        "blocking_items": unique_preserve_order(blocking_items),
        "focus_items": unique_preserve_order(focus_items),
    }


def compute_result_summary(config: dict[str, Any], output: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    raw_route_summaries = [compute_route_summary(route_model) for route_model in output.get("routes", [])]
    measurement_layout_mode = str(
        output.get("protocol_layout", {}).get("measurement_layout_mode") or "by_plug_box"
    )
    route_summaries = [
        {
            "route": item["route"],
            "start_boxes": item["start_box_count"],
            "start_box_count": item["start_box_count"],
            "physical_boxes": item["physical_box_count"],
            "physical_box_count": item["physical_box_count"],
            "boards": item["board_count"],
            "board_count": item["board_count"],
            "branches": item["branch_count"],
            "branch_count": item["branch_count"],
            "repeaters": item["repeater_count"],
            "repeater_count": item["repeater_count"],
            "point_count": item["point_count"],
            "structure_only_boxes": item["structure_only_box_count"],
            "structure_only_box_count": item["structure_only_box_count"],
            "monitor_modules": item["physical_box_count"] if measurement_layout_mode == "by_branch" else 0,
            "monitor_module_count": item["physical_box_count"] if measurement_layout_mode == "by_branch" else 0,
        }
        for item in raw_route_summaries
    ]
    totals = {
        "start_box_count": sum(item["start_boxes"] for item in route_summaries),
        "physical_box_count": sum(item["physical_boxes"] for item in route_summaries),
        "board_count": sum(item["boards"] for item in route_summaries),
        "branch_count": sum(item["branches"] for item in route_summaries),
        "repeater_count": sum(item["repeaters"] for item in route_summaries),
        "point_count": sum(item["point_count"] for item in route_summaries) + len(output.get("single_cabinet_rows", [])),
        "single_cabinet_count": len(output.get("single_cabinet_rows", [])),
        "warning_count": len(output.get("warnings", [])),
    }
    family = output["profiles"]["export_profile"]["family"]
    single_cabinet_start_address = (
        (output.get("single_cabinet_rows") or [{}])[0].get("address")
        if output.get("single_cabinet_rows")
        else output["profiles"]["address_profile"].get("cabinet_base")
    )
    address_summary = dict(output.get("address_summary", {}))
    address_summary["cabinet_start_address"] = single_cabinet_start_address
    selected_profiles = build_selected_profile_snapshot(library, config)
    export_profile_summary = selected_profiles.get("export_profile", {})
    baseline_profile_summary = selected_profiles.get("baseline_context", {})
    return {
        "project_name": config.get("project_name"),
        "project_code": config.get("project_code"),
        "protocol_title": config.get("protocol_title"),
        "family": family,
        "export_family": family,
        "sheet_order": output["profiles"]["export_profile"].get("sheet_order", []),
        "protocol_layout": deepcopy(output.get("protocol_layout", {})),
        "measurement_layout_mode": measurement_layout_mode,
        "measurement_layout_label": (
            "按监控模块（监控模块 → 板卡 → 数据驱动输出分路）"
            if measurement_layout_mode == "by_branch"
            else "按插接箱"
        ),
        "profile_selection": {
            "export_profile_id": config.get("profiles", {}).get("export_profile_id"),
            "render_variant_id": export_profile_summary.get("render_variant_id"),
            "address_profile_id": config.get("profiles", {}).get("address_profile_id"),
            "start_box_template_id": config.get("profiles", {}).get("start_box_template_id"),
            "plug_branch_template_id": config.get("profiles", {}).get("plug_branch_template_id"),
            "repeater_template_id": config.get("profiles", {}).get("repeater_template_id"),
            "single_cabinet_template_id": config.get("profiles", {}).get("single_cabinet_template_id"),
        },
        "template_plan": {
            "export_profile_id": config.get("profiles", {}).get("export_profile_id"),
            "render_variant_id": export_profile_summary.get("render_variant_id"),
            "render_variant_label": export_profile_summary.get("render_variant_label"),
            "patch_labels": export_profile_summary.get("patch_labels", []),
            "active_zone_labels": export_profile_summary.get("active_zone_labels", []),
        },
        "baseline_template_plan": {
            "export_profile_id": baseline_profile_summary.get("export_profile_id"),
            "render_variant_id": baseline_profile_summary.get("render_variant_id"),
            "render_variant_label": baseline_profile_summary.get("render_variant_label"),
            "patch_labels": baseline_profile_summary.get("patch_labels", []),
            "active_zone_labels": baseline_profile_summary.get("active_zone_labels", []),
            "reference_label": baseline_profile_summary.get("reference_label") or baseline_profile_summary.get("label"),
        },
        "routes": route_summaries,
        "route_summaries": route_summaries,
        "totals": totals,
        "single_cabinet_rows": len(output.get("single_cabinet_rows", [])),
        "warnings": output.get("warnings", []),
        "address_summary": address_summary,
        "address_cards": build_address_cards(
            {
                "address_summary": address_summary,
            },
            output,
        ),
        "single_cabinet_start_address": single_cabinet_start_address,
        "selected_profiles": selected_profiles,
        "variant_label": export_profile_summary.get("render_variant_label") or export_profile_summary.get("label"),
    }


def run_validation_report(canonical_path: Path, excel_path: Path) -> dict[str, Any]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    payload = validate_generated_artifacts(canonical_path, excel_path)
    if not payload.get("ok"):
        return {
            "status": "failed",
            "checked_at": checked_at,
            "message": payload.get("error", "validation_failed"),
            "canonical_path": canonical_path.name,
            "excel_path": excel_path.name,
            **payload,
        }
    return {
        "status": "passed",
        "checked_at": checked_at,
        "message": "validation_ok",
        **payload,
    }


def run_source_compare_report(
    excel_path: Path,
    family: str,
    export_profile_id: str | None = None,
    address_profile_id: str | None = None,
) -> dict[str, Any]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        report = compare_generated_excel_to_source(
            excel_path,
            family=family,
            export_profile_id=export_profile_id,
            address_profile_id=address_profile_id,
        )
    except FileNotFoundError as exc:
        return {
            "checked_at": checked_at,
            "family": family,
            "overall_status": "not_checked",
            "verdict": "not_checked",
            "structure_status": "unknown",
            "format_status": "unknown",
            "source_compare_unavailable": True,
            "source_compare_unavailable_reason": str(exc),
            "error": str(exc),
            "generated_workbook": {
                "path": excel_path.name,
                "file_name": excel_path.name,
            },
            "sheets": [],
            "missing_categories": [],
            "top_priority_fixes": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "checked_at": checked_at,
            "family": family,
            "overall_status": "diverged",
            "verdict": "diverged",
            "error": str(exc),
            "generated_workbook": {
                "path": excel_path.name,
                "file_name": excel_path.name,
            },
        }
    report["checked_at"] = checked_at
    return report


def build_quality_summary(validation: dict[str, Any], source_compare: dict[str, Any]) -> dict[str, Any]:
    return {
        "validation_status": validation.get("status"),
        "validation_ok": validation.get("ok", False),
        "source_compare_status": source_compare.get("overall_status"),
        "source_compare_verdict": source_compare.get("verdict", source_compare.get("overall_status")),
        "source_compare_source_file": source_compare.get("source_workbook", {}).get("file_name"),
        "source_compare_sheet_order_match": source_compare.get("sheet_order_match"),
        "structure_status": source_compare.get("structure_status"),
        "format_status": source_compare.get("format_status"),
        "overall_score": source_compare.get("overall_score"),
        "structure_score": source_compare.get("structure_score"),
        "format_score": source_compare.get("format_score"),
        "worst_sheet": source_compare.get("score_summary", {}).get("worst_sheet"),
    }


def delivery_check(status: str, label: str, detail: str) -> dict[str, Any]:
    return {
        "status": status,
        "label": label,
        "detail": detail,
    }


def build_delivery_readiness(validation: dict[str, Any], source_compare: dict[str, Any]) -> dict[str, Any]:
    validation_status = validation.get("status")
    verdict = source_compare.get("verdict", source_compare.get("overall_status"))
    format_status = source_compare.get("format_status")
    structure_status = source_compare.get("structure_status")
    source_compare_unavailable = bool(source_compare.get("source_compare_unavailable"))

    if validation_status == "passed":
        file_structure = delivery_check("pass", "Excel 结构检查通过", "工作表、首点和包结构已通过校验。")
    else:
        file_structure = delivery_check(
            "fail",
            "Excel 结构检查未通过",
            f"当前 validation 状态：{validation_status or 'unknown'}。",
        )

    if source_compare_unavailable:
        protocol_content = delivery_check(
            "warn",
            "源协议对照未执行",
            "软件包未随附历史源协议；已完成生成和 Excel 结构校验，交付前按项目要求抽查关键地址。",
        )
    elif verdict == "match" and structure_status == "match":
        protocol_content = delivery_check("pass", "点表结构与参考方案一致", "页结构、地址组织与点表主体已对齐。")
    elif verdict in {"match", "close"} and structure_status == "match":
        protocol_content = delivery_check("warn", "点表结构可用", "主体结构已对齐，但仍建议核对变化页与关键地址。")
    else:
        protocol_content = delivery_check(
            "fail",
            "点表结构仍需人工复核",
            f"对照状态：{verdict or 'unknown'}；结构状态：{structure_status or 'unknown'}。",
        )

    if source_compare_unavailable:
        format_alignment = delivery_check(
            "warn",
            "版式对照未执行",
            "软件包未随附历史源协议；无法做贴源版式比对，建议抽查关键页。",
        )
    elif format_status == "match":
        format_alignment = delivery_check("pass", "版式已贴近参考模板", "可作为直接交付版本。")
    elif format_status in {None, "unknown"}:
        format_alignment = delivery_check("warn", "版式比对结果待确认", "未拿到明确版式结论，建议先抽查关键页。")
    elif format_status == "close":
        format_alignment = delivery_check("warn", "版式与参考模板仍有差异", "不影响生成，可交付前建议抽查。")
    else:
        format_alignment = delivery_check("fail", "版式差异较大", f"当前版式状态：{format_status or 'unknown'}。")

    check_statuses = [file_structure["status"], protocol_content["status"], format_alignment["status"]]
    blocker_checks = [item for item in (file_structure, protocol_content, format_alignment) if item["status"] == "fail"]
    warning_checks = [item for item in (file_structure, protocol_content, format_alignment) if item["status"] == "warn"]
    blocker_copy_map = {
        "Excel 结构检查未通过": "文件结构",
        "点表结构仍需人工复核": "点表结构",
        "版式差异较大": "关键页版式",
    }
    warning_copy_map = {
        "源协议对照未执行": "关键地址",
        "版式对照未执行": "关键页版式",
        "点表结构可用": "变化页与关键地址",
        "版式比对结果待确认": "关键页版式",
        "版式与参考模板仍有差异": "关键页版式",
    }

    if "fail" in check_statuses:
        overall_status = "not_recommended"
        label = "暂不建议交付"
        blocker_targets = [
            blocker_copy_map.get(item["label"], item["label"])
            for item in blocker_checks
        ]
        customer_message = (
            f"Excel 已生成，但{join_cn(blocker_targets)}仍需人工复核，"
            "暂不建议直接发出。"
        )
    elif "warn" in check_statuses:
        overall_status = "deliverable_with_review"
        label = "可交付但建议抽查"
        warning_targets = [
            warning_copy_map.get(item["label"], item["label"])
            for item in warning_checks[:2]
        ]
        customer_message = (
            f"Excel 可导出使用；建议先核对 {join_cn(warning_targets)}，"
            "确认后再发给客户。"
        )
    else:
        overall_status = "deliverable"
        label = "可直接交付"
        customer_message = "Excel 已通过结构与内容检查，可直接作为交付稿。"

    return {
        "status": overall_status,
        "label": label,
        "customer_message": customer_message,
        "checks": {
            "file_structure": file_structure,
            "protocol_content": protocol_content,
            "format_alignment": format_alignment,
        },
    }


def build_delivery_status(
    validation: dict[str, Any],
    source_compare: dict[str, Any],
    *,
    unified_workflow: bool = False,
    artifact_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    if unified_workflow:
        artifact_statuses = artifact_statuses or {}
        file_structure = delivery_check(
            "pass" if validation.get("status") == "passed" else "fail",
            "协议表结构检查通过" if validation.get("status") == "passed" else "协议表结构检查未通过",
            "最终协议表已通过结构校验。"
            if validation.get("status") == "passed"
            else f"当前 validation 状态：{validation.get('status') or 'unknown'}。",
        )
        alarm_ok = artifact_statuses.get("alarm_code") == "generated"
        upload_ok = artifact_statuses.get("program_upload") == "generated"
        protocol_content = delivery_check(
            "pass" if alarm_ok and upload_ok else "fail",
            "三文件交付包已生成" if alarm_ok and upload_ok else "三文件交付包不完整",
            "动环协议表、报警状态字上传代码和 MCGS 导入 CSV 均已生成。"
            if alarm_ok and upload_ok
            else "报警代码或 MCGS 导入 CSV 生成失败，不能作为完整交付包发出。",
        )
        parameter_compilation = delivery_check(
            "pass",
            "项目参数已确认",
            "交付判定基于项目参数、A/B 路、扩展项与文件校验。",
        )
        checks = {
            "file_structure": file_structure,
            "protocol_content": protocol_content,
            "format_alignment": parameter_compilation,
        }
        blockers = [item["label"] for item in (file_structure, protocol_content) if item["status"] == "fail"]
        status = "deliverable" if not blockers else "not_recommended"
        label = "三文件可直接交付" if not blockers else "三文件交付包未完成"
        customer_message = (
            "协议文件已按当前项目参数生成并完成三文件校验，可直接下载交付。"
            if not blockers
            else "协议文件已执行生成，但三文件或结构校验未全部通过，暂不建议发出。"
        )
        readiness = {
            "status": status,
            "label": label,
            "customer_message": customer_message,
            "checks": checks,
            "basis": "validation_and_three_file_bundle",
            "source_compare_role": "internal_regression_only",
        }
        return {
            "status": status,
            "legacy_status": "deliverable" if status == "deliverable" else "review_required",
            "label": label,
            "ok": status != "not_recommended",
            "downloadable": not blockers,
            "safe_to_send": status == "deliverable",
            "requires_review": status != "deliverable",
            "blockers": blockers,
            "review_items": [],
            "customer_message": customer_message,
            "readiness": readiness,
            "basis": "validation_and_three_file_bundle",
            "source_compare_role": "internal_regression_only",
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    readiness = build_delivery_readiness(validation, source_compare)
    blockers: list[str] = []
    review_items: list[str] = []
    checks = readiness.get("checks", {})
    for key in ("file_structure", "protocol_content", "format_alignment"):
        item = checks.get(key, {})
        if item.get("status") == "fail":
            blockers.append(item.get("label") or item.get("detail") or key)
        elif item.get("status") == "warn":
            review_items.append(item.get("label") or item.get("detail") or key)
    return {
        "status": readiness["status"],
        "legacy_status": "deliverable" if readiness["status"] == "deliverable" else "review_required",
        "label": readiness["label"],
        "ok": readiness["status"] != "not_recommended",
        "downloadable": True,
        "safe_to_send": readiness["status"] == "deliverable",
        "requires_review": readiness["status"] != "deliverable",
        "blockers": blockers,
        "review_items": review_items,
        "customer_message": readiness["customer_message"],
        "readiness": readiness,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def enrich_recommendation(recommendation: dict[str, Any], library: TemplateLibrary) -> dict[str, Any]:
    family = recommendation["recommended_family"]
    profile_ids = recommendation.get("recommended_profile_ids", {})
    templates = build_template_options(library)
    template_maps = {
        "start_box_template_id": {item["id"]: item["label"] for item in templates["start_box_templates"]},
        "plug_branch_template_id": {item["id"]: item["label"] for item in templates["plug_branch_templates"]},
        "repeater_template_id": {item["id"]: item["label"] for item in templates["repeater_templates"]},
        "single_cabinet_template_id": {item["id"]: item["label"] for item in templates["single_cabinet_templates"]},
    }
    family_profiles = build_family_profiles(library)
    address_map = {
        item["id"]: item["label"]
        for family_bundle in family_profiles.values()
        for item in family_bundle["address_profiles"]
    }
    export_map = {
        item["id"]: item["label"]
        for family_bundle in family_profiles.values()
        for item in family_bundle["export_profiles"]
    }
    current_export_profile_id = recommendation.get("current_export_profile_id")
    recommended_export_profile_id = recommendation.get("recommended_export_profile_id")
    return {
        **recommendation,
        "current_family_label": FAMILY_META.get(recommendation.get("current_family"), {}).get("label"),
        "recommended_family_label": FAMILY_META.get(family, {}).get("label", family),
        "current_export_profile_label": export_map.get(current_export_profile_id),
        "recommended_export_profile_label": export_map.get(recommended_export_profile_id),
        "recommended_profile_labels": {
            "export_profile_id": export_map.get(profile_ids.get("export_profile_id")),
            "address_profile_id": address_map.get(profile_ids.get("address_profile_id")),
            "start_box_template_id": template_maps["start_box_template_id"].get(profile_ids.get("start_box_template_id")),
            "plug_branch_template_id": template_maps["plug_branch_template_id"].get(profile_ids.get("plug_branch_template_id")),
            "repeater_template_id": template_maps["repeater_template_id"].get(profile_ids.get("repeater_template_id")),
            "single_cabinet_template_id": template_maps["single_cabinet_template_id"].get(profile_ids.get("single_cabinet_template_id")),
        },
    }


def is_valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(str(run_id or "")))


def run_dir_for(run_id: str, *, must_exist: bool = False) -> Path:
    """Resolve one direct child of ``RUNS_ROOT`` and reject traversal/symlinks."""

    if not is_valid_run_id(run_id):
        raise HTTPException(status_code=404, detail="未找到生成记录")
    root = RUNS_ROOT.resolve()
    candidate = (root / run_id).resolve(strict=False)
    if candidate.parent != root:
        raise HTTPException(status_code=404, detail="未找到生成记录")
    if must_exist and not candidate.is_dir():
        raise HTTPException(status_code=404, detail="未找到生成记录")
    return candidate


def ensure_run_dir(run_id: str) -> Path:
    run_dir = run_dir_for(run_id)
    run_dir.mkdir(parents=False, exist_ok=False)
    return run_dir


def public_run_path(run_id: str, path: Path | None = None) -> str | None:
    """Return a non-absolute reference suitable for API payloads and manifests."""

    if path is None:
        return None
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        if resolved == run_dir_for(run_id).resolve(strict=False):
            return f"runs/{run_id}"
        return f"runs/{run_id}/{resolved.name}"


def sanitize_run_payload_paths(value: Any, run_id: str, key: str = "") -> Any:
    """Redact filesystem locations from persisted and legacy run payloads."""

    if isinstance(value, dict):
        return {
            item_key: sanitize_run_payload_paths(item_value, run_id, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_run_payload_paths(item, run_id, key) for item in value]
    if not isinstance(value, str):
        return value

    normalized_key = key.lower()
    if normalized_key == "run_dir":
        return public_run_path(run_id, run_dir_for(run_id))
    if normalized_key == "path" or normalized_key.endswith("_path"):
        normalized_value = value.replace("\\", "/").rstrip("/")
        return normalized_value.rsplit("/", 1)[-1] if normalized_value else ""
    return value


def resolve_manifest_artifact_path(run_dir: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None

    validated_run_dir = run_dir_for(run_dir.name, must_exist=True)
    if run_dir.resolve(strict=False) != validated_run_dir:
        return None

    original = Path(raw_path)
    candidates: list[Path] = []
    if original.is_absolute():
        candidates.append(original)
    else:
        candidates.append(run_dir / original)
    if original.name:
        candidates.append(run_dir / original.name)

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        resolved = candidate.resolve(strict=False)
        if resolved.parent != validated_run_dir:
            continue
        if resolved.is_file():
            return resolved
    return None


def resolve_run_artifact(run_id: str, artifact: str) -> Path:
    run_dir = run_dir_for(run_id, must_exist=True)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="未找到生成记录")

    manifest = load_json(manifest_path)
    artifact_paths = manifest.get("artifacts", {})
    path_map = {
        "input": artifact_paths.get("input_path"),
        "json": artifact_paths.get("canonical_path"),
        "excel": artifact_paths.get("excel_path"),
        "alarm_code": artifact_paths.get("alarm_code_path"),
        "program_upload": artifact_paths.get("program_upload_path"),
        "validation": artifact_paths.get("validation_path"),
        "compare": artifact_paths.get("compare_path"),
        "delivery": artifact_paths.get("delivery_path"),
    }
    raw_path = path_map.get(artifact)
    if not raw_path:
        raise HTTPException(status_code=404, detail="未找到对应文件")

    target = resolve_manifest_artifact_path(run_dir, raw_path)
    if target is None:
        raise HTTPException(status_code=404, detail=f"{artifact} 文件不存在或已被移除")
    return target


def list_recent_runs(limit: int = 12) -> list[dict[str, Any]]:
    bounded_limit = max(0, min(int(limit), 100))
    valid_run_dirs: list[Path] = []
    for item in RUNS_ROOT.iterdir():
        if not is_valid_run_id(item.name):
            continue
        try:
            valid_run_dirs.append(run_dir_for(item.name, must_exist=True))
        except HTTPException:
            continue
    run_dirs = sorted(
        valid_run_dirs,
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    results = []
    for run_dir in run_dirs[:bounded_limit]:
        delivery_path = run_dir / "delivery-summary.json"
        if delivery_path.exists():
            try:
                delivery_payload = load_json(delivery_path)
            except (json.JSONDecodeError, MemoryError, OSError):
                delivery_payload = None
            if delivery_payload:
                source_protocol = delivery_payload.get("source_protocol_summary") or {}
                source_verdict = source_protocol.get("verdict")
                file_structure_status = (
                    delivery_payload.get("delivery_readiness", {})
                    .get("checks", {})
                    .get("file_structure", {})
                    .get("status")
                )
                validation_status = "passed" if file_structure_status == "pass" else None
                results.append(
                    {
                        "run_id": delivery_payload.get("run_id") or run_dir.name,
                        "created_at": delivery_payload.get("created_at"),
                        "project_name": delivery_payload.get("project_name"),
                        "project_code": delivery_payload.get("project_code"),
                        "summary": {
                            "project_name": delivery_payload.get("project_name"),
                            "project_code": delivery_payload.get("project_code"),
                            "variant_label": delivery_payload.get("variant_label"),
                            "address_cards": delivery_payload.get("address_cards", []),
                            "selected_profiles": delivery_payload.get("selected_profiles", {}),
                            "protocol_diff_summary": delivery_payload.get("protocol_diff_summary", {}),
                            "source_protocol_summary": source_protocol,
                        },
                        "delivery_status": delivery_payload.get("delivery_status"),
                        "delivery_readiness": delivery_payload.get("delivery_readiness"),
                        "protocol_diff_summary": delivery_payload.get("protocol_diff_summary"),
                        "source_protocol_summary": source_protocol,
                        "validation": {"status": validation_status} if validation_status else {},
                        "source_compare": (
                            {
                                "verdict": source_verdict,
                                "overall_status": source_verdict,
                                "structure_status": source_protocol.get("structure_status"),
                                "format_status": source_protocol.get("format_status"),
                                "source_workbook": {"file_name": source_protocol.get("source_file")},
                            }
                            if source_verdict
                            else {}
                        ),
                    }
                )
                continue

        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            payload = load_json(manifest_path)
        except (json.JSONDecodeError, MemoryError, OSError):
            continue
        results.append(sanitize_run_payload_paths(payload, run_dir.name))
    return results


@app.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request) -> HTMLResponse:
    if not SECURITY_SETTINGS.enabled:
        return RedirectResponse(url="/", status_code=303)
    if request_session(request) is not None:
        return RedirectResponse(url="/", status_code=303)

    login_csrf = secrets.token_urlsafe(32)
    reason = request.query_params.get("reason", "")
    notice = ""
    if reason == "session_expired":
        notice = "请登录后继续使用"
    elif request.query_params.get("password") == "changed":
        notice = "密码已更新，请使用新密码登录"
    response = templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "asset_version": template_asset_version(),
            "login_csrf": login_csrf,
            "notice": notice,
            "username": SECURITY_SETTINGS.admin_username,
        },
    )
    response.set_cookie(
        LOGIN_CSRF_COOKIE_NAME,
        login_csrf,
        max_age=10 * 60,
        httponly=True,
        secure=SECURITY_SETTINGS.cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> JSONResponse:
    if not SECURITY_SETTINGS.enabled:
        raise HTTPException(status_code=404, detail="账号系统未启用")
    cookie_token = request.cookies.get(LOGIN_CSRF_COOKIE_NAME, "")
    if not cookie_token or not hmac.compare_digest(cookie_token, payload.csrf_token):
        return auth_error(403, "login_csrf_invalid", "登录页面已过期，请刷新后重试")

    result = SECURITY_MANAGER.authenticate(
        payload.username,
        payload.password,
        client_ip=request_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    response = JSONResponse(
        status_code=result.status_code,
        content={
            "ok": result.ok,
            "detail": result.message,
            "code": "login_succeeded" if result.ok else "login_failed",
            "must_change_password": bool(result.session and result.session.must_change_password),
            "retry_after": result.retry_after,
        },
    )
    if not result.ok or result.session is None:
        if result.retry_after:
            response.headers["Retry-After"] = str(result.retry_after)
        return response

    response.set_cookie(
        SESSION_COOKIE_NAME,
        result.token,
        max_age=SECURITY_SETTINGS.session_absolute_seconds,
        httponly=True,
        secure=SECURITY_SETTINGS.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(LOGIN_CSRF_COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, Any]:
    if not SECURITY_SETTINGS.enabled:
        raise HTTPException(status_code=404, detail="账号系统未启用")
    session = request_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return {
        "authenticated": True,
        "username": session.username,
        "csrf_token": session.csrf_token,
        "must_change_password": session.must_change_password,
        "security": SECURITY_MANAGER.security_summary(),
    }


@app.post("/api/auth/logout")
def logout(request: Request) -> JSONResponse:
    if not SECURITY_SETTINGS.enabled:
        raise HTTPException(status_code=404, detail="账号系统未启用")
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    SECURITY_MANAGER.logout(token, client_ip=request_client_ip(request))
    response = JSONResponse({"ok": True, "detail": "已安全退出"})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordRequest, request: Request) -> JSONResponse:
    if not SECURITY_SETTINGS.enabled:
        raise HTTPException(status_code=404, detail="账号系统未启用")
    session = request_session(request)
    if session is None:
        return auth_error(401, "auth_required", "登录状态已失效，请重新登录")
    ok, message = SECURITY_MANAGER.change_password(
        session,
        payload.current_password,
        payload.new_password,
        client_ip=request_client_ip(request),
    )
    response = JSONResponse(
        status_code=200 if ok else 400,
        content={
            "ok": ok,
            "detail": message,
            "code": "password_changed" if ok else "password_change_failed",
            "reauthenticate": ok,
        },
    )
    if ok:
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@app.get("/", response_class=HTMLResponse)
def assembly_index(request: Request) -> HTMLResponse:
    session = request_session(request)
    response = assembly_templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "asset_version": template_asset_version(),
            "auth_enabled": SECURITY_SETTINGS.enabled,
            "auth_username": session.username if session else "",
            "csrf_token": session.csrf_token if session else "",
            "must_change_password": bool(session and session.must_change_password),
            "security_summary": SECURITY_MANAGER.security_summary(),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/protocol", include_in_schema=False)
def protocol_index_redirect() -> RedirectResponse:
    return RedirectResponse(url="/protocol/", status_code=308)


@app.get("/protocol/", response_class=HTMLResponse)
def protocol_index(request: Request) -> HTMLResponse:
    session = request_session(request)
    response = templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "asset_version": template_asset_version(),
            "auth_enabled": SECURITY_SETTINGS.enabled,
            "auth_username": session.username if session else "",
            "csrf_token": session.csrf_token if session else "",
            "must_change_password": bool(session and session.must_change_password),
            "security_summary": SECURITY_MANAGER.security_summary(),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return build_bootstrap_payload()


@app.get("/api/examples/{family}")
def api_example(family: str) -> dict[str, Any]:
    library = TemplateLibrary.load()
    path = EXAMPLE_PATHS.get(family)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="未找到对应模板族示例")
    return normalize_config(load_json(path), library)


@app.post("/api/recommend")
def api_recommend(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    library = TemplateLibrary.load()
    raw_config = payload.get("config") if isinstance(payload, dict) and "config" in payload else payload
    config = normalize_config(raw_config, library)
    recommendation = recommend_protocol_config(config, library)
    recommendation["recommended_config"] = normalize_config(recommendation["recommended_config"], library)
    return enrich_recommendation(recommendation, library)


@app.get("/api/runs")
def api_runs(limit: int = 12) -> dict[str, Any]:
    items = list_recent_runs(limit)
    return {"items": items, "count": len(items)}


@app.get("/api/runs/{run_id}/manifest")
def api_run_manifest(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id, must_exist=True)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="未找到生成记录")
    return sanitize_run_payload_paths(load_json(manifest_path), run_id)


@app.get("/api/runs/{run_id}/canonical")
def api_run_canonical(run_id: str) -> JSONResponse:
    run_dir = run_dir_for(run_id, must_exist=True)
    canonical_path = run_dir / "canonical-output.json"
    if not canonical_path.exists():
        raise HTTPException(status_code=404, detail="未找到 canonical JSON")
    return JSONResponse(load_json(canonical_path))


@app.get("/api/runs/{run_id}/validation")
def api_run_validation(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id, must_exist=True)
    validation_path = run_dir / "validation-report.json"
    if not validation_path.exists():
        raise HTTPException(status_code=404, detail="未找到 validation 报告")
    return sanitize_run_payload_paths(load_json(validation_path), run_id)


@app.get("/api/runs/{run_id}/quality")
def api_run_quality(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id, must_exist=True)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="未找到生成记录")
    manifest = load_json(manifest_path)
    if manifest.get("quality"):
        return sanitize_run_payload_paths(manifest["quality"], run_id)

    validation_path = run_dir / "validation-report.json"
    compare_path = run_dir / "source-compare.json"
    if not validation_path.exists() or not compare_path.exists():
        raise HTTPException(status_code=404, detail="未找到质量检查结果")
    return sanitize_run_payload_paths({
        "validation": load_json(validation_path),
        "source_compare": load_json(compare_path),
    }, run_id)


@app.get("/api/runs/{run_id}/compare")
def api_run_compare(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id, must_exist=True)
    compare_path = run_dir / "source-compare.json"
    if compare_path.exists():
        return sanitize_run_payload_paths(load_json(compare_path), run_id)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="未找到生成记录")
    manifest = load_json(manifest_path)
    excel_path = resolve_manifest_artifact_path(run_dir, manifest["artifacts"].get("excel_path"))
    if excel_path is None:
        raise HTTPException(status_code=404, detail="未找到 Excel 文件，无法执行源文件对比")
    report = run_source_compare_report(
        excel_path,
        family=manifest["family"],
        export_profile_id=manifest.get("summary", {}).get("profile_selection", {}).get("export_profile_id"),
        address_profile_id=manifest.get("summary", {}).get("profile_selection", {}).get("address_profile_id"),
    )
    save_json(compare_path, report)
    return sanitize_run_payload_paths(report, run_id)


@app.get("/api/runs/{run_id}/download/{artifact}")
def api_run_download(run_id: str, artifact: str) -> FileResponse:
    target = resolve_run_artifact(run_id, artifact)
    return FileResponse(path=target, filename=target.name)


@app.post("/api/preview-address-summary")
def api_preview_address_summary(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    library = TemplateLibrary.load()
    raw_config = payload.get("config") if isinstance(payload, dict) and "config" in payload else payload
    config = normalize_config(raw_config, library)
    generator = ProtocolGenerator(library)

    try:
        output = generator.generate(config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = compute_result_summary(config, output, library)
    summary["protocol_diff_summary"] = build_protocol_diff_summary(
        library,
        config,
        output,
        summary,
        summary.get("selected_profiles", {}),
        source_compare=None,
    )
    summary["source_protocol_summary"] = build_source_protocol_summary(None)
    summary["source_protocol_summary"]["reference_basis_label"] = build_reference_basis_label(summary.get("selected_profiles", {}))
    return {
        "summary": summary,
        "warnings": output.get("warnings", []),
        "address_summary": output.get("address_summary", {}),
    }


@app.post("/api/generate")
def api_generate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    library = TemplateLibrary.load()
    raw_config = payload.get("config") if isinstance(payload, dict) and "config" in payload else payload
    config = normalize_config(raw_config, library)
    generator = ProtocolGenerator(library)

    try:
        output = generator.generate(config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    family = output["profiles"]["export_profile"]["family"]
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    run_dir = ensure_run_dir(run_id)

    input_path = run_dir / "input-config.json"
    canonical_path = run_dir / "canonical-output.json"
    artifact_stem = sanitize_file_stem(config.get("project_name") or config.get("project_code") or "项目")
    excel_name = f"{artifact_stem}-动环通讯协议.xlsx"
    excel_path = run_dir / excel_name

    save_json(input_path, config)
    save_json(canonical_path, output)
    try:
        render_excel(output, excel_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Excel 导出失败：{exc}") from exc
    if not excel_path.exists() or excel_path.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail="Excel 导出失败：未生成 Excel 文件")

    alarm_code_path = run_dir / f"{artifact_stem}-报警状态字上传代码.txt"
    alarm_codegen: dict[str, Any] = {
        "status": "skipped",
        "message": "",
    }
    try:
        alarm_enabled = bool(config.get("extensions", {}).get("alarm_state_word", {}).get("enabled", True))
        if is_unified_workflow(config) and not alarm_enabled:
            alarm_code_path.write_text(
                "' 当前项目未启用报警状态字。\n' 本文件用于保持三文件交付包结构，无需导入 MCGS。\n",
                encoding="utf-8",
            )
            alarm_codegen = {
                "status": "generated",
                "content_status": "not_applicable",
                "message": "未启用报警状态字，已生成不适用说明文件",
                "artifact_path": alarm_code_path.name,
                "file_name": alarm_code_path.name,
            }
        else:
            alarm_config = config.get("extensions", {}).get("alarm_state_word", {})
            if alarm_config.get("legacy_slide_rail_order") is True:
                alarm_code = generate_alarm_code_from_workbook(
                    excel_path,
                    legacy_slide_rail_order=True,
                )
            else:
                alarm_code = generate_alarm_code_from_workbook(excel_path)
            alarm_code_path.write_text(alarm_code, encoding="utf-8")
            alarm_codegen = {
                "status": "generated",
                "content_status": "upload_code",
                "message": "报警状态字代码已生成",
                "artifact_path": alarm_code_path.name,
                "file_name": alarm_code_path.name,
            }
    except AlarmCodegenUnsupportedError as exc:
        alarm_codegen = {
            "status": "unsupported",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        alarm_codegen = {
            "status": "failed",
            "message": str(exc),
        }

    program_upload_path = run_dir / f"{artifact_stem}-MCGS动环上传设备导入.csv"
    program_upload: dict[str, Any] = {
        "status": "skipped",
        "message": "",
    }
    try:
        program_upload = write_program_upload_csv_from_config(excel_path, program_upload_path, config)
    except Exception as exc:  # noqa: BLE001
        program_upload = {
            "status": "failed",
            "message": str(exc),
        }

    validation = run_validation_report(canonical_path, excel_path)
    if is_unified_workflow(config):
        source_compare = {
            "status": "skipped",
            "overall_status": "skipped",
            "verdict": "skipped",
            "structure_status": "not_applicable",
            "format_status": "not_applicable",
            "skipped_for_unified_workflow": True,
            "message": "协议按当前项目参数和业务规则生成，不执行历史模板相似度对比。",
        }
    else:
        source_compare = run_source_compare_report(
            excel_path,
            family=family,
            export_profile_id=config.get("profiles", {}).get("export_profile_id"),
            address_profile_id=config.get("profiles", {}).get("address_profile_id"),
        )
    quality = {
        "validation": validation,
        "source_compare": source_compare,
        "source_compare_role": "internal_regression_only"
        if is_unified_workflow(config)
        else "legacy_delivery_reference",
    }
    quality_summary = build_quality_summary(validation, source_compare)
    quality_summary["source_compare_role"] = quality["source_compare_role"]
    delivery_status = build_delivery_status(
        validation,
        source_compare,
        unified_workflow=is_unified_workflow(config),
        artifact_statuses={
            "excel": "generated",
            "alarm_code": alarm_codegen.get("status", "failed"),
            "program_upload": program_upload.get("status", "failed"),
        },
    )
    delivery_bundle = {
        "id": "protocol_delivery_bundle_v1",
        "status": "complete" if delivery_status.get("status") == "deliverable" else "incomplete",
        "required_keys": ["excel", "alarm_code", "program_upload"],
        "files": {
            "excel": {
                "label": "动环通讯协议",
                "status": "generated",
                "file_name": excel_path.name,
                "download": f"/api/runs/{run_id}/download/excel",
            },
            "alarm_code": {
                "label": "报警状态字上传代码",
                "status": alarm_codegen.get("status"),
                "content_status": alarm_codegen.get("content_status"),
                "file_name": alarm_code_path.name if alarm_codegen.get("status") == "generated" else None,
                "download": f"/api/runs/{run_id}/download/alarm_code"
                if alarm_codegen.get("status") == "generated"
                else None,
            },
            "program_upload": {
                "label": "MCGS 动环上传设备导入表",
                "status": program_upload.get("status"),
                "file_name": program_upload_path.name if program_upload.get("status") == "generated" else None,
                "download": f"/api/runs/{run_id}/download/program_upload"
                if program_upload.get("status") == "generated"
                else None,
            },
        },
    }
    save_json(run_dir / "validation-report.json", validation)
    save_json(run_dir / "source-compare.json", source_compare)

    summary = compute_result_summary(config, output, library)
    summary["run_dir"] = public_run_path(run_id, run_dir)
    summary["validation_status"] = validation["status"]
    summary["source_compare_verdict"] = source_compare.get("verdict", source_compare.get("overall_status"))
    summary["quality_summary"] = quality_summary
    summary["delivery_status"] = delivery_status
    summary["delivery_readiness"] = delivery_status.get("readiness")
    summary["delivery_bundle"] = delivery_bundle
    summary["protocol_diff_summary"] = build_protocol_diff_summary(
        library,
        config,
        output,
        summary,
        summary.get("selected_profiles", {}),
        delivery_status,
        source_compare,
    )
    summary["source_protocol_summary"] = build_source_protocol_summary(source_compare)
    if not is_unified_workflow(config):
        summary["source_protocol_summary"]["reference_basis_label"] = build_reference_basis_label(summary.get("selected_profiles", {}))
    summary["program_upload"] = program_upload
    delivery_summary = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_name": config.get("project_name"),
        "project_code": config.get("project_code"),
        "variant_label": summary.get("variant_label"),
        "delivery_status": delivery_status,
        "delivery_readiness": delivery_status.get("readiness"),
        "protocol_diff_summary": summary.get("protocol_diff_summary"),
        "source_protocol_summary": summary.get("source_protocol_summary"),
        "address_cards": summary.get("address_cards", []),
        "selected_profiles": summary.get("selected_profiles", {}),
        "alarm_codegen": alarm_codegen,
        "program_upload": program_upload,
        "delivery_bundle": delivery_bundle,
    }
    save_json(run_dir / "delivery-summary.json", delivery_summary)
    stored_artifacts = {
        "input_path": input_path.name,
        "canonical_path": canonical_path.name,
        "excel_path": excel_path.name,
        "alarm_code_path": alarm_code_path.name if alarm_codegen["status"] == "generated" else None,
        "program_upload_path": program_upload_path.name if program_upload["status"] == "generated" else None,
        "validation_path": "validation-report.json",
        "compare_path": "source-compare.json",
        "delivery_path": "delivery-summary.json",
    }
    response_artifacts = {
        key: public_run_path(run_id, run_dir / value) if value else None
        for key, value in stored_artifacts.items()
    }
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_name": config.get("project_name"),
        "project_code": config.get("project_code"),
        "protocol_title": config.get("protocol_title"),
        "family": family,
        "workflow": {
            "id": UNIFIED_WORKFLOW_ID if is_unified_workflow(config) else "legacy_template_workflow",
            "generation_basis": config.get("generation_basis"),
        },
        "summary": summary,
        "artifacts": stored_artifacts,
        "downloads": {
            "input": f"/api/runs/{run_id}/download/input",
            "json": f"/api/runs/{run_id}/download/json",
            "excel": f"/api/runs/{run_id}/download/excel",
            "alarm_code": f"/api/runs/{run_id}/download/alarm_code" if alarm_codegen["status"] == "generated" else None,
            "program_upload": f"/api/runs/{run_id}/download/program_upload" if program_upload["status"] == "generated" else None,
            "canonical": f"/api/runs/{run_id}/canonical",
            "validation": f"/api/runs/{run_id}/validation",
            "compare": f"/api/runs/{run_id}/compare",
            "quality": f"/api/runs/{run_id}/quality",
            "delivery": f"/api/runs/{run_id}/download/delivery",
        },
        "validation": validation,
        "source_compare": source_compare,
        "quality": quality,
        "quality_summary": quality_summary,
        "delivery_status": delivery_status,
        "delivery_readiness": delivery_status.get("readiness"),
        "protocol_diff_summary": summary.get("protocol_diff_summary"),
        "source_protocol_summary": summary.get("source_protocol_summary"),
        "alarm_codegen": alarm_codegen,
        "program_upload": program_upload,
        "delivery_bundle": delivery_bundle,
    }
    save_json(run_dir / "manifest.json", manifest)
    return {
        "run_id": run_id,
        "created_at": manifest["created_at"],
        "summary": summary,
        "canonical": output,
        "downloads": manifest["downloads"],
        "artifacts": response_artifacts,
        "validation": validation,
        "source_compare": source_compare,
        "quality": quality,
        "quality_summary": quality_summary,
        "delivery_status": delivery_status,
        "delivery_readiness": delivery_status.get("readiness"),
        "protocol_diff_summary": summary.get("protocol_diff_summary"),
        "source_protocol_summary": summary.get("source_protocol_summary"),
        "alarm_codegen": alarm_codegen,
        "program_upload": program_upload,
        "delivery_bundle": delivery_bundle,
    }


@app.delete("/api/runs/{run_id}")
def api_delete_run(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id, must_exist=True)
    shutil.rmtree(run_dir)
    return {"deleted": True, "run_id": run_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("protocol_studio.app:app", host="127.0.0.1", port=8123, reload=False)
