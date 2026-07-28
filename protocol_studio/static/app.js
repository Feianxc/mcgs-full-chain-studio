const FAMILY_LABELS = {
  classic_combined: "标准单列（含中继页）",
  extended_split: "扩展分页（含单机柜 / 中继页）",
  ab_screen_split: "A / B 分屏（独立数据页 + 报警页）",
};

const STORAGE_KEY = "mcgs-protocol-studio::draft-v2";
const STORAGE_META_KEY = "mcgs-protocol-studio::draft-meta-v1";
const PRESERVED_DRAFT_KEY = "mcgs-protocol-studio::preserved-draft-v1";
const PRESERVED_DRAFT_META_KEY = "mcgs-protocol-studio::preserved-draft-meta-v1";
const TWO_COLUMN_REFERENCE_WORKBOOK = "示例-单屏双列参考协议.xlsx";
const DEFAULT_SCENARIOS = [
  {
    id: "classic_standard",
    label: "标准单列（含中继页）",
    family: "classic_combined",
    example_key: "classic_combined",
    usage_hint: "适合常见单屏项目；A / B 共屏，默认带中继页和统一报警页。",
    meta: "常规项目首选",
  },
  {
    id: "classic_two_columns",
    label: "单屏双列（四组设备独立配置）",
    family: "classic_combined",
    example_key: "classic_combined_two_columns",
    usage_hint: "第一列 A/B 与第二列 A/B 分别配置；端口按设备形态和现场接线分配。",
    source_workbook_file: TWO_COLUMN_REFERENCE_WORKBOOK,
    meta: "四组设备独立配置",
  },
  {
    id: "extended_split",
    label: "扩展分页（含单机柜 / 中继页）",
    family: "extended_split",
    example_key: "extended_split",
    usage_hint: "适合需要把始端箱、插接箱、单机柜和中继分开出表的项目。",
    meta: "分页更完整",
  },
  {
    id: "ab_screen_split",
    label: "A / B 分屏（独立数据页 + 报警页）",
    family: "ab_screen_split",
    example_key: "ab_screen_split",
    usage_hint: "适合 A 路与 B 路分屏显示、分表导出的项目。",
    meta: "双屏独立导出",
  },
];
const LIQUIDCOOL_EXPORT_PROFILE_ID = "classic_combined_liquidcool_default";
const CLASSIC_DEFAULT_EXPORT_PROFILE_ID = "classic_combined_default";
const CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID = "classic_combined_two_columns_default";
const CLASSIC_DEFAULT_ADDRESS_PROFILE_ID = "classic_with_repeater5500_alarm6000_16bit";
const CLASSIC_TWO_COLUMNS_ADDRESS_PROFILE_ID = "classic_main1000_alarm6000_16bit";
const BRANCH_NUMBERING_CONTIGUOUS = "per_output_contiguous";
const BRANCH_NUMBERING_BOARD_SUFFIX = "per_board_suffix";
const BRANCH_NUMBERING_OPTIONS = [
  {
    value: BRANCH_NUMBERING_BOARD_SUFFIX,
    label: "按板卡编号（一拖六第二回路为 _2）",
  },
];
const SCREEN_MODE_SINGLE = "single_screen_one_column";
const SCREEN_MODE_DOUBLE = "single_screen_two_columns";
const PORTS_BY_HARDWARE = Object.freeze({
  horizontal: ["A2B2", "A3B3", "A4B4"],
  din_rail: ["A1B1", "A2B2", "A3B3"],
});
const DEFAULT_ENVIRONMENT_PORT = Object.freeze({
  horizontal: "A4B4",
  din_rail: "A3B3",
});
const BUS_DATA_MODE_OPTIONS = Object.freeze({
  [SCREEN_MODE_SINGLE]: [
    { value: "single_column_shared", label: "A/B 两路共用一个口", help_text: "单列 A 路与 B 路的数据接入同一个物理口。" },
    { value: "single_column_split_ab", label: "A/B 两路分开接两个口", help_text: "单列 A 路与 B 路分别占用一个物理口。" },
  ],
  [SCREEN_MODE_DOUBLE]: [
    { value: "double_column_by_column", label: "每列共用一个口", help_text: "第一列 A/B 共用一个口，第二列 A/B 共用另一个口。" },
    { value: "double_column_by_route", label: "两列按 A/B 路分口", help_text: "两列 A 路共用一个口，两列 B 路共用另一个口。" },
  ],
});
const LIQUIDCOOL_ADDRESS_PROFILE_ID =
  "classic_liquidcool_main1000_repeater5000_cabinet7000_alarm6000_32bit";
const LIQUIDCOOL_START_BOX_TEMPLATE_ID = "start_box_standard_36row_thd_energy_32bit_state";
const LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID = "plug_branch_standard_30row_full_connector";
const LIQUIDCOOL_REPEATER_TEMPLATE_ID = "repeater_abcn_temp_4row";
const LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID = "single_cabinet_liquidcool_ia_pa_ea_ka";
const LEGACY_EXTENDED_DEMO_PROJECT_CODE = "DEMO-MCGS-EXT-001";
const LEGACY_EXTENDED_DEMO_CABINET_COUNT = 152;
const LEGACY_EXTENDED_DEMO_TEMPLATE_ID = "single_cabinet_current_sum_ia_only";
const SCENARIO_BASELINE_PRESETS = {
  classic_combined: {
    key: "classic_combined",
    label: "标准单列（含中继页）",
    export_profile_id: CLASSIC_DEFAULT_EXPORT_PROFILE_ID,
    address_profile_id: CLASSIC_DEFAULT_ADDRESS_PROFILE_ID,
    start_box_template_id: "start_box_standard_36row_thd_energy",
    plug_branch_template_id: "plug_branch_standard_29row_connector_temp",
    repeater_template_id: "repeater_abcn_temp_4row",
    single_cabinet_template_id: null,
  },
  classic_combined_two_columns: {
    key: "classic_combined_two_columns",
    label: "单屏双列（四组设备独立配置）",
    export_profile_id: CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID,
    address_profile_id: CLASSIC_TWO_COLUMNS_ADDRESS_PROFILE_ID,
    start_box_template_id: "start_box_compact_31row_inlet_temp",
    plug_branch_template_id: "plug_branch_compact_21row",
    repeater_template_id: null,
    single_cabinet_template_id: null,
  },
  classic_combined_liquidcool: {
    key: "classic_combined_liquidcool",
    label: "液冷混合版",
    export_profile_id: LIQUIDCOOL_EXPORT_PROFILE_ID,
    address_profile_id: LIQUIDCOOL_ADDRESS_PROFILE_ID,
    start_box_template_id: LIQUIDCOOL_START_BOX_TEMPLATE_ID,
    plug_branch_template_id: LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID,
    repeater_template_id: LIQUIDCOOL_REPEATER_TEMPLATE_ID,
    single_cabinet_template_id: LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID,
  },
  extended_split: {
    key: "extended_split",
    label: "扩展分页（含单机柜 / 中继页）",
    export_profile_id: "extended_split_default",
    address_profile_id: "split_main1000_plug2000_cabinet8200_repeater9000_alarm9200_16bit",
    start_box_template_id: "start_box_extended_load_unbalance_reactive",
    plug_branch_template_id: "plug_branch_extended_load_reactive",
    repeater_template_id: "repeater_abcn_temp_4row",
    single_cabinet_template_id: LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID,
  },
  ab_screen_split: {
    key: "ab_screen_split",
    label: "A / B 分屏（独立数据页 + 报警页）",
    export_profile_id: "ab_screen_split_default",
    address_profile_id: "ab_screen_main1000_alarm3000_16bit",
    start_box_template_id: "start_box_standard_32row_outlet_temp",
    plug_branch_template_id: "plug_branch_compact_21row",
    repeater_template_id: null,
    single_cabinet_template_id: null,
  },
};

const state = {
  bootstrap: null,
  maps: null,
  config: null,
  activeFamily: "classic_combined",
  viewMode: "workspace",
  activeStep: "quickStart",
  activeDrawer: "",
  activeRoute: "A",
  collapsedSections: {
    quickStart: false,
    project: true,
    topology: true,
    profiles: true,
    routeA: true,
    routeB: true,
    extension: true,
    result: true,
    quality: true,
    history: true,
  },
  result: null,
  lastGenerationSeconds: null,
  recommendation: null,
  recommendationBusy: false,
  recentRuns: [],
  jsonPreview: "",
  previewSummary: null,
  previewSummaryHash: "",
  previewPendingHash: "",
  previewError: "",
  previewErrorHash: "",
  previewRequestId: 0,
  previewTimer: null,
  busy: false,
  message: "",
  tone: "",
  resultStale: false,
  savedDraft: null,
  savedDraftMeta: null,
  preservedDraft: null,
  preservedDraftMeta: null,
  railUtilitiesOpen: false,
  sequenceDetailOpen: {},
  routeQuickErrors: {},
  draftSaveTimer: null,
  previewAbortController: null,
  pendingFocusSelector: "",
  openedRunMeta: null,
  openRunRequestId: 0,
  generateRequestId: 0,
  recommendationRequestId: 0,
  quickSequenceDrafts: {},
  railSelection: {},
  railEditorOpen: {},
  activeColumnByRoute: { A: 1, B: 1 },
  pointsetPopover: null,
  pointsetPopoverOption: null,
  pointsetPopoverHideTimer: null,
};

const refs = {
  familySwitch: document.getElementById("familySwitch"),
  railTemplateLabel: document.getElementById("railTemplateLabel"),
  loadPresetBtn: document.getElementById("loadPresetBtn"),
  recoverDraftBtn: document.getElementById("recoverDraftBtn"),
  importJsonTrigger: document.getElementById("importJsonTrigger"),
  importJsonInput: document.getElementById("importJsonInput"),
  downloadDraftBtn: document.getElementById("downloadDraftBtn"),
  generateBtn: document.getElementById("generateBtn"),
  railUtilityToggle: document.getElementById("railUtilityToggle"),
  railUtilityMenu: document.getElementById("railUtilityMenu"),
  workflowSpine: document.getElementById("workflowSpine"),
  mobileActionBar: document.getElementById("mobileActionBar"),
  drawerBackdrop: document.getElementById("drawerBackdrop"),
  previewDrawer: document.getElementById("previewDrawer"),
  communicationDrawer: document.getElementById("communicationDrawer"),
  qualityDrawer: document.getElementById("qualityDrawer"),
  historyDrawer: document.getElementById("historyDrawer"),
  liveSummary: document.getElementById("liveSummary"),
  resultRail: document.getElementById("resultRail"),
  recentRunsRail: document.getElementById("recentRunsRail"),
  statusBadge: document.getElementById("statusBadge"),
  activeFamilyLabel: document.getElementById("activeFamilyLabel"),
  messageBar: document.getElementById("messageBar"),
  headerProjectName: document.getElementById("headerProjectName"),
  summaryStrip: document.getElementById("summaryStrip"),
  quickStartSection: document.getElementById("quickStartSection"),
  projectSection: document.getElementById("projectSection"),
  topologySection: document.getElementById("topologySection"),
  profilesSection: document.getElementById("profilesSection"),
  routeSectionA: document.getElementById("routeSectionA"),
  routeSectionB: document.getElementById("routeSectionB"),
  extensionSection: document.getElementById("extensionSection"),
  resultSection: document.getElementById("resultSection"),
  qualitySection: document.getElementById("qualitySection"),
  historySection: document.getElementById("historySection"),
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function deepMerge(base, override) {
  const output = clone(base);
  Object.entries(override || {}).forEach(([key, value]) => {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      output[key] &&
      typeof output[key] === "object" &&
      !Array.isArray(output[key])
    ) {
      output[key] = deepMerge(output[key], value);
    } else {
      output[key] = clone(value);
    }
  });
  return output;
}

function splitNames(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value || "")
    .replaceAll("，", ",")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function sameStringArray(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => String(item) === String(right[index]));
}

function setByPath(target, path, value) {
  const segments = path.split(".");
  let cursor = target;
  for (let i = 0; i < segments.length - 1; i += 1) {
    const segment = segments[i];
    const key = /^\d+$/u.test(segment) ? Number(segment) : segment;
    cursor = cursor[key];
  }
  const lastSegment = segments.at(-1);
  const lastKey = /^\d+$/u.test(lastSegment) ? Number(lastSegment) : lastSegment;
  cursor[lastKey] = value;
}

function getByPath(target, path) {
  return path.split(".").reduce((cursor, segment) => {
    if (cursor == null) {
      return undefined;
    }
    const key = /^\d+$/u.test(segment) ? Number(segment) : segment;
    return cursor[key];
  }, target);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function optionLabel(option) {
  if (!option) {
    return "";
  }
  return option.label || option.id || option.value || "";
}

function compactSummaryText(value, maxLength = 22) {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return "-";
  }
  const normalized = raw
    .replaceAll("始端箱和插接箱", "始端箱/插接箱")
    .replaceAll("报警状态", "报警")
    .replaceAll("单机柜", "单柜")
    .replaceAll("导出 profile", "导出")
    .replaceAll("地址 profile", "地址")
    .replace(/\s*\/\s*/gu, " / ")
    .replace(/\s*-\s*/gu, " / ")
    .replace(/\s+/gu, " ")
    .trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  const segments = normalized
    .split(" / ")
    .map((item) => item.trim())
    .filter(Boolean);
  if (segments.length > 1) {
    const picked = [];
    let totalLength = 0;
    for (const segment of segments) {
      const chunk = segment.length > 10 ? `${segment.slice(0, 10)}…` : segment;
      const nextLength = totalLength + (picked.length ? 3 : 0) + chunk.length;
      if (picked.length && nextLength > maxLength) {
        break;
      }
      picked.push(chunk);
      totalLength = nextLength;
      if (picked.length >= 3) {
        break;
      }
    }
    if (picked.length) {
      return picked.join(" / ");
    }
  }
  return normalized.length > maxLength ? `${normalized.slice(0, Math.max(1, maxLength - 1))}…` : normalized;
}

function verdictLabel(verdict) {
  return {
    match: "贴近参考模板",
    close: "接近参考模板",
    diverged: "差异较大",
  }[verdict] || "未评估";
}

function verdictClass(verdict) {
  return {
    match: "is-success",
    close: "is-working",
    diverged: "is-error",
  }[verdict] || "";
}

function scoreValue(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(1);
}

function scoreClass(value) {
  const score = Number(value || 0);
  if (score >= 92) {
    return "is-success";
  }
  if (score >= 72) {
    return "is-working";
  }
  return "is-error";
}

function fileNameFromPath(value) {
  const sanitized = String(value || "").split(/[?#]/u)[0];
  return sanitized.split(/[/\\]/u).pop() || "";
}

function fileNameFromDisposition(value) {
  const raw = String(value || "");
  const encodedMatch = raw.match(/filename\*\s*=\s*UTF-8''([^;]+)/iu);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return encodedMatch[1];
    }
  }
  const quotedMatch = raw.match(/filename\s*=\s*"([^"]+)"/iu);
  if (quotedMatch?.[1]) {
    return quotedMatch[1];
  }
  const plainMatch = raw.match(/filename\s*=\s*([^;]+)/iu);
  return plainMatch?.[1]?.trim() || "";
}

function deriveDownloadFileName(response, fallbackFileName, url) {
  return (
    fileNameFromDisposition(response.headers.get("content-disposition")) ||
    fileNameFromPath(fallbackFileName) ||
    fileNameFromPath(url) ||
    "download.bin"
  );
}

async function apiFetch(url, init = {}) {
  const method = String(init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = window.protocolSecurity?.csrfToken?.() || "";
    if (csrfToken && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers,
  });
  if (response.status === 401) {
    window.location.replace("/login?reason=session_expired");
    return response;
  }
  if (response.status === 403) {
    const payload = await response.clone().json().catch(() => ({}));
    if (payload.code === "password_change_required") {
      window.protocolSecurity?.requirePasswordChange?.();
    }
  }
  return response;
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

function preferredScrollBehavior() {
  return prefersReducedMotion() ? "auto" : "smooth";
}

function triggerBlobDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function downloadArtifactFromUrl(url, options = {}) {
  const label = options.label || "文件";
  const fallbackFileName = options.fallbackFileName || "";
  if (!url) {
    throw new Error(`${label} 下载地址缺失`);
  }
  setMessage(`${label} 下载中`, "working");
  renderStatus();
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, `${label} 下载失败：${response.status}`));
  }
  const blob = await response.blob();
  if (!blob.size) {
    throw new Error(`${label} 下载失败：返回文件为空`);
  }
  const fileName = deriveDownloadFileName(response, fallbackFileName, url);
  triggerBlobDownload(blob, fileName);
  setMessage(`${label} 已下载`, "success");
  renderStatus();
  return fileName;
}

async function handleArtifactDownload(trigger, event) {
  if (!trigger) {
    return;
  }
  if (event?.metaKey || event?.ctrlKey || event?.shiftKey || event?.button > 0) {
    return;
  }
  event?.preventDefault();
  try {
    await downloadArtifactFromUrl(trigger.getAttribute("href") || trigger.dataset.url, {
      label: trigger.dataset.downloadLabel || trigger.getAttribute("download") || "文件",
      fallbackFileName: trigger.dataset.downloadFilename || trigger.getAttribute("download") || "",
    });
  } catch (error) {
    setMessage(error.message || String(error), "error");
    renderStatus();
  }
}

function metricPill(label, value) {
  return `<span class="status-pill ${scoreClass(value)}">${escapeHtml(label)} ${escapeHtml(scoreValue(value))}</span>`;
}

function validationLabel(validation) {
  if (!validation) {
    return "未校验";
  }
  return validation.status === "passed" ? "校验通过" : "校验失败";
}

function confidenceLabel(confidence) {
  return {
    high: "高置信",
    medium: "中置信",
    low: "低置信",
  }[confidence] || "未评级";
}

function confidenceClass(confidence) {
  return {
    high: "is-success",
    medium: "is-working",
    low: "is-error",
  }[confidence] || "";
}

function getValidation(target = state.result) {
  return target?.quality?.validation || target?.validation || null;
}

function getSourceCompare(target = state.result) {
  return target?.quality?.source_compare || target?.source_compare || null;
}

function getQualitySummary(target = state.result) {
  return target?.quality_summary || target?.summary?.quality_summary || null;
}

function getDeliveryStatus(target = state.result) {
  return target?.delivery_status || target?.summary?.delivery_status || null;
}

function getDeliveryReadiness(target = state.result) {
  return target?.delivery_readiness || target?.summary?.delivery_readiness || target?.delivery_status?.readiness || null;
}

function getProtocolDiffSummary(target = state.result) {
  return target?.protocol_diff_summary || target?.summary?.protocol_diff_summary || null;
}

function getSourceProtocolSummary(target = state.result) {
  return target?.source_protocol_summary || target?.summary?.source_protocol_summary || null;
}

function getAddressCards(target = state.result) {
  return target?.summary?.address_cards || target?.address_cards || [];
}

function getSelectedProfiles(target = state.result) {
  return target?.summary?.selected_profiles || target?.selected_profiles || {};
}

function readinessToneClass(status) {
  return {
    pass: "is-success",
    warn: "is-working",
    fail: "is-error",
  }[status] || "";
}

function firstMeaningfulItem(groups = []) {
  for (const group of groups) {
    if (!Array.isArray(group)) {
      continue;
    }
    const value = group.find((item) => String(item || "").trim());
    if (value) {
      return value;
    }
  }
  return "";
}

function renderListOrEmpty(items, emptyText = "当前无额外说明") {
  const safeItems = Array.isArray(items) ? items.filter((item) => String(item || "").trim()) : [];
  if (!safeItems.length) {
    return `<div class="muted-note">${escapeHtml(emptyText)}</div>`;
  }
  return `
    <ul class="detail-bullet-list">
      ${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
  `;
}

function renderProfileSnapshotCard(title, detail) {
  if (!detail?.id) {
    return "";
  }
  return `
    <article class="profile-snapshot-card">
      <span>${escapeHtml(title)}</span>
      <strong>${escapeHtml(detail.short_label || detail.label || detail.id)}</strong>
      <em>${escapeHtml(detail.diff_summary || detail.help_text || "当前按默认方案处理")}</em>
      ${
        detail.help_text && detail.help_text !== detail.diff_summary
          ? `<p>${escapeHtml(detail.help_text)}</p>`
          : ""
      }
    </article>
  `;
}

function deliveryLabel(delivery) {
  return {
    deliverable: "可直接交付",
    deliverable_with_review: "可交付但建议抽查",
    not_recommended: "暂不建议交付",
    review_required: "建议复核",
  }[delivery?.status] || "未评估";
}

function deliveryToneClass(delivery, validation = getValidation(), sourceCompare = getSourceCompare()) {
  if (delivery?.status === "deliverable") {
    return "is-success";
  }
  if (delivery?.status === "deliverable_with_review" || delivery?.status === "review_required") {
    return "is-working";
  }
  if (delivery?.status === "not_recommended") {
    return "is-error";
  }
  if (validation?.status && validation.status !== "passed") {
    return "is-error";
  }
  return verdictClass(sourceCompare?.verdict || sourceCompare?.overall_status);
}

function statusPresentation() {
  const validation = getValidation();
  const sourceCompare = getSourceCompare();
  const delivery = getDeliveryStatus();
  const baseReadyMessage = "已就绪：填写项目信息、A/B 路最大设备和扩展项，即可生成三份交付文件。";

  if (state.busy) {
      return {
        label: "生成中",
        badgeTone: "is-working",
        messageTone: "working",
        message: "正在生成动环协议表、报警状态字上传代码和 MCGS 设备导入表，请稍候。",
      };
  }

  if (state.result && state.resultStale) {
    return {
      label: "待更新",
      badgeTone: "is-working",
      messageTone: state.tone === "error" ? "error" : "working",
      message:
        state.tone === "error" && state.message
          ? `本次生成失败，当前保留上次成功结果：${state.message}`
          : "配置已修改，当前仍显示上次成功结果；重新生成后会刷新结果与检查摘要。",
    };
  }

  if (state.message && state.tone === "error") {
    return {
      label: "错误",
      badgeTone: "is-error",
      messageTone: "error",
      message: state.message,
    };
  }

  if (state.result) {
    const durationText = Number.isFinite(state.lastGenerationSeconds)
      ? `，用时 ${state.lastGenerationSeconds.toFixed(1)} 秒`
      : "";
    if (delivery?.status) {
      const badgeTone = deliveryToneClass(delivery, validation, sourceCompare);
      const deliveryMessage =
        delivery.customer_message ||
        (delivery.status === "deliverable"
          ? "三份交付文件已生成，可直接下载。"
          : delivery.status === "deliverable_with_review"
            ? "三份交付文件已生成，建议先完成提示的人工复核。"
            : "交付文件已生成，但当前还不建议直接发出。");
      return {
        label: delivery.label || deliveryLabel(delivery),
        badgeTone,
        messageTone:
          badgeTone === "is-error" ? "error" : badgeTone === "is-working" ? "working" : "success",
        message: durationText
          ? `${deliveryMessage.replace(/[。.]$/, "")}${durationText}。`
          : deliveryMessage,
      };
    }
    if (validation?.status && validation.status !== "passed") {
      return {
        label: "需复核",
        badgeTone: "is-error",
        messageTone: "error",
        message: "交付文件已生成，但业务规则检查未通过；请先复核配置与明细。",
      };
    }
    const readyFileCount = [
      state.result.downloads?.excel,
      state.result.downloads?.alarm_code,
      state.result.downloads?.program_upload,
    ].filter(Boolean).length;
    if (readyFileCount < 3) {
      return {
        label: "需复核",
        badgeTone: "is-working",
        messageTone: "working",
        message: `交付包当前生成 ${readyFileCount} / 3 个文件，请查看结果区说明。`,
      };
    }
    return {
      label: "可直接交付",
      badgeTone: "is-success",
      messageTone: "success",
      message: `三份交付文件已生成${durationText}，可直接下载使用。`,
    };
  }

  if (state.message) {
    const connectedMessage =
      state.message === "已连接" || state.message.startsWith("已连接 ·")
        ? "已连接，可开始配置。"
        : state.message;
    return {
      label: state.tone === "success" ? "已保存" : "待命",
      badgeTone: state.tone === "success" ? "is-success" : "",
      messageTone: state.tone || "",
      message: connectedMessage,
    };
  }

  return {
    label: "已保存",
    badgeTone: "",
    messageTone: "",
    message: baseReadyMessage,
  };
}

function currentConfigHash() {
  return state.config ? JSON.stringify(state.config) : "";
}

function configForActiveMeasurementMode(sourceConfig = state.config) {
  const effectiveConfig = clone(sourceConfig || {});
  const activeMode = effectiveConfig?.protocol_layout?.measurement_layout_mode === "by_branch"
    ? "by_branch"
    : "by_plug_box";
  const deviceRoots = [
    effectiveConfig?.devices,
    effectiveConfig?.devices?.screen_columns?.column_2,
  ].filter(Boolean);

  deviceRoots.forEach((deviceRoot) => {
    ["A", "B"].forEach((route) => {
      if (activeMode === "by_branch") {
        if (deviceRoot.plug_boxes?.[route]) {
          deviceRoot.plug_boxes[route].sequence = [];
        }
        return;
      }
      const moduleConfig = deviceRoot.branch_modules?.[route];
      if (!moduleConfig) {
        return;
      }
      moduleConfig.module_sequence = [];
      delete moduleConfig.module_count;
      delete moduleConfig.branches_per_module;
      delete moduleConfig.branch_template_id;
    });
  });
  return effectiveConfig;
}

function savedDraftHash() {
  return state.savedDraft ? JSON.stringify(state.savedDraft) : "";
}

function isUsingCurrentSavedDraft() {
  const currentHash = currentConfigHash();
  return Boolean(state.savedDraft) && Boolean(currentHash) && currentHash === savedDraftHash() && !state.openedRunMeta;
}

function isCurrentHistoryRun(runId) {
  return Boolean(runId) && Boolean(state.openedRunMeta?.run_id) && String(state.openedRunMeta.run_id) === String(runId);
}

function workspaceContextSummary() {
  const currentProject = String(state.config?.project_name || "").trim() || "当前方案";

  if (state.openedRunMeta) {
    return {
      tone: "is-working",
      badge: "当前正在查看",
      title: `历史记录 · ${state.openedRunMeta.project_name || state.openedRunMeta.run_id || currentProject}`,
      note: state.preservedDraft
        ? "表单与结果当前来自历史记录；原本地草稿已单独保留，可随时恢复。"
        : "表单与结果当前来自历史记录；如需继续产出新稿，请修改后重新生成。",
      actions: [
        state.preservedDraft
          ? '<button class="section-tool" type="button" data-action="restore-preserved-draft">恢复原本地草稿</button>'
          : "",
        '<button class="section-tool section-tool--quiet" type="button" data-action="jump-section" data-section="history">查看全部记录</button>',
      ]
        .filter(Boolean)
        .join(""),
    };
  }

  if (state.result && state.resultStale) {
    return {
      tone: "is-working",
      badge: "当前正在编辑",
      title: "配置已更新，结果待刷新",
      note: "你当前修改的是新配置；页面仍保留上次成功结果作比对，重新生成后会同步刷新交付判断。",
      actions: `<button class="section-tool" type="button" data-action="quick-generate" ${state.busy ? "disabled" : ""}>${state.busy ? "生成中…" : "重新生成并刷新结果"}</button>`,
    };
  }

  if (isUsingCurrentSavedDraft()) {
    return {
      tone: "is-success",
      badge: "当前正在编辑",
      title: `${state.savedDraftMeta?.project_name || currentProject} · 本地草稿`,
      note: state.savedDraftMeta?.saved_at_label
        ? `当前输入会自动保存到本地；最近保存时间 ${state.savedDraftMeta.saved_at_label}。`
        : "当前输入会自动保存到本地，离开页面后仍可恢复。",
      actions: '<button class="section-tool section-tool--quiet" type="button" data-action="jump-section" data-section="history">查看最近生成</button>',
    };
  }

  if (state.preservedDraft) {
    return {
      tone: "is-success",
      badge: "草稿保护",
      title: `${state.preservedDraftMeta?.project_name || "原本地草稿"} 已单独保留`,
      note: "你现在可以继续基于历史方案或当前配置工作；原草稿不会被静默覆盖。",
      actions: '<button class="section-tool" type="button" data-action="restore-preserved-draft">恢复原本地草稿</button>',
    };
  }

  if (state.savedDraft && currentConfigHash() !== savedDraftHash()) {
    return {
      tone: "",
      badge: "当前正在编辑",
      title: "新配置 / 默认方案",
      note: "本地另有一份草稿可恢复；当前页面不会立即覆盖那份草稿。",
      actions: '<button class="section-tool" type="button" data-action="restore-draft">恢复本地草稿</button>',
    };
  }

  return {
    tone: "",
    badge: "当前正在编辑",
    title: currentProject,
    note: "按项目最大设备配置继续录入；生成后先看交付判断，再决定是否展开内部复核。",
    actions: "",
  };
}

function currentPreviewSummary() {
  if (state.result?.summary && !state.resultStale) {
    return state.result.summary;
  }
  const currentHash = currentConfigHash();
  return state.previewSummaryHash && state.previewSummaryHash === currentHash ? state.previewSummary : null;
}

function isCurrentPreviewPending() {
  const currentHash = currentConfigHash();
  return Boolean(currentHash) && state.previewPendingHash === currentHash;
}

function runDisplayName(item) {
  return (
    item?.project_name ||
    item?.summary?.project_name ||
    item?.project_code ||
    item?.summary?.project_code ||
    item?.run_id ||
    "未命名 run"
  );
}

function buildMaps(payload) {
  const exportProfiles = {};
  const addressProfiles = {};
  Object.entries(payload.families).forEach(([family, bundle]) => {
    bundle.export_profiles.forEach((item) => {
      exportProfiles[item.id] = { ...item, family };
    });
    bundle.address_profiles.forEach((item) => {
      addressProfiles[item.id] = { ...item, family };
    });
  });
  const boxTypes = Object.fromEntries(payload.box_types.map((item) => [item.type_code, item]));

  return {
    exportProfiles,
    addressProfiles,
    boxTypes,
    familyDefaults: payload.defaults,
    familyDefaultConfigs: payload.examples,
  };
}

function currentFamilyFromConfig(config = state.config) {
  const exportProfileId = config?.profiles?.export_profile_id;
  const exportProfile = state.maps.exportProfiles[exportProfileId];
  return exportProfile?.family || config?.export_family || state.activeFamily || "classic_combined";
}

function normalizeTypeCode(typeCode) {
  const aliasMap = {
    "1*3P": "3P*1",
    "2*3P": "3P*2",
    "3*3P": "3P*3",
    "4*3P": "3P*4",
    "3*1P": "1P*3",
  };
  return aliasMap[typeCode] || typeCode;
}

function normalizeSequenceItem(item) {
  const typeCode = normalizeTypeCode(item?.type_code || "3P*1");
  const boxType = state.maps.boxTypes[typeCode] || state.bootstrap.box_types[0];
  const allowedPatterns = boxType.allowed_layout_patterns.map((entry) => entry.pattern);
  const fallbackPattern = boxType.default_layout_pattern || allowedPatterns[0] || "1";
  let layoutPattern = item?.layout_pattern || item?.layout_token || fallbackPattern;
  if (!allowedPatterns.includes(layoutPattern)) {
    layoutPattern = fallbackPattern;
  }
  const normalized = {
    type_code: boxType.type_code,
    count: Math.max(1, Number(item?.count || 1)),
    layout_pattern: layoutPattern,
  };
  if (item?.branch_template_id) {
    normalized.branch_template_id = item.branch_template_id;
  }
  if (item?.box_number != null && item.box_number !== "") {
    normalized.box_number = Math.max(1, Number(item.box_number));
  }
  if (item?.board_number_start != null && item.board_number_start !== "") {
    normalized.board_number_start = Math.max(1, Number(item.board_number_start));
  }
  const explicitBoxName = String(item?.box_name || item?.instance_name || "").trim();
  if (explicitBoxName) {
    normalized.box_name = explicitBoxName;
  }
  return normalized;
}

function normalizeBranchNumberingMode(value) {
  return BRANCH_NUMBERING_BOARD_SUFFIX;
}

function normalizeModuleSequenceItem(item) {
  const normalized = normalizeSequenceItem(item || {});
  const output = {
    type_code: normalized.type_code,
    layout_pattern: normalized.layout_pattern,
    count: Math.max(1, Number(normalized.count || 1)),
  };
  if (normalized.branch_template_id) {
    output.branch_template_id = normalized.branch_template_id;
  }
  return output;
}

function defaultModuleSequenceItem(typeCode = "3P*2") {
  const boxType = state.maps.boxTypes[normalizeTypeCode(typeCode)] || state.bootstrap.box_types[0];
  return normalizeModuleSequenceItem({
    type_code: boxType.type_code,
    layout_pattern: boxType.default_layout_pattern || boxType.allowed_layout_patterns?.[0]?.pattern,
    count: 1,
  });
}

function screenColumnCount(config = state.config) {
  return config?.topology?.screen_topology_mode === SCREEN_MODE_DOUBLE ? 2 : 1;
}

function routeScopeKey(route, column = 1) {
  return `C${Math.max(1, Number(column || 1))}${route === "B" ? "B" : "A"}`;
}

function routeColumnLabel(route, column = 1, config = state.config) {
  const routeName = route === "B" ? "B" : "A";
  if (screenColumnCount(config) === 1) {
    return `${routeName} 路`;
  }
  return `${Number(column) === 2 ? "第二列" : "第一列"} ${routeName} 路`;
}

function activeColumnForRoute(route) {
  const requested = Math.max(1, Number(state.activeColumnByRoute?.[route] || 1));
  return Math.min(screenColumnCount(), requested);
}

function configuredRouteScopes() {
  return Array.from({ length: screenColumnCount() }, (_, index) => index + 1)
    .flatMap((column) => ["A", "B"].map((route) => ({ route, column })));
}

function routeDeviceRoot(config, column = 1) {
  if (Number(column) === 2) {
    return config.devices.screen_columns.column_2;
  }
  return config.devices;
}

function routeDevicePath(column = 1) {
  return Number(column) === 2 ? "devices.screen_columns.column_2" : "devices";
}

function routeDefaultBoxStart(route, column = 1) {
  return (route === "B" ? 201 : 101) + (Math.max(1, Number(column || 1)) - 1) * 200;
}

function routeDefaultStartCode(route, column = 1) {
  return (route === "B" ? 2 : 1) + (Math.max(1, Number(column || 1)) - 1) * 2;
}

function createEmptyColumnDevices(column = 2) {
  const result = { start_boxes: {}, plug_boxes: {}, branch_modules: {} };
  ["A", "B"].forEach((route) => {
    const deviceStart = routeDefaultBoxStart(route, column);
    result.start_boxes[route] = {
      count: 0,
      instance_names: [],
      device_code_start: routeDefaultStartCode(route, column),
    };
    result.plug_boxes[route] = {
      box_number_start: deviceStart,
      board_number_start: deviceStart,
      sequence: [],
    };
    result.branch_modules[route] = {
      module_sequence: [],
      variable_numbering_mode: BRANCH_NUMBERING_BOARD_SUFFIX,
      module_number_start: 1,
      output_number_start: 1,
      branch_device_number_start: deviceStart,
      names: [],
    };
  });
  return result;
}

function ensureSecondColumnDevices(config) {
  config.devices.screen_columns = config.devices.screen_columns || {};
  config.devices.screen_columns.column_2 = deepMerge(
    createEmptyColumnDevices(2),
    config.devices.screen_columns.column_2 || {},
  );
  return config.devices.screen_columns.column_2;
}

function normalizePortTopology(topology) {
  const normalized = topology || {};
  normalized.screen_topology_mode = normalized.screen_topology_mode === SCREEN_MODE_DOUBLE
    ? SCREEN_MODE_DOUBLE
    : SCREEN_MODE_SINGLE;
  normalized.columns_per_screen = normalized.screen_topology_mode === SCREEN_MODE_DOUBLE ? 2 : 1;
  normalized.screen_count = 1;
  normalized.screen_route_binding = "both_routes_in_one_screen";
  normalized.route_mode = "AB_dual_route";

  normalized.hardware_form_factor = PORTS_BY_HARDWARE[normalized.hardware_form_factor]
    ? normalized.hardware_form_factor
    : "horizontal";
  const allowedPorts = PORTS_BY_HARDWARE[normalized.hardware_form_factor];
  const defaultEnvironmentPort = DEFAULT_ENVIRONMENT_PORT[normalized.hardware_form_factor];
  const requestedEnvironmentPort = normalized.environment_rs485_port || normalized.upload_port_profile;
  normalized.environment_rs485_port = allowedPorts.includes(requestedEnvironmentPort)
    ? requestedEnvironmentPort
    : defaultEnvironmentPort;
  normalized.upload_port_profile = normalized.environment_rs485_port;

  const allowedModes = BUS_DATA_MODE_OPTIONS[normalized.screen_topology_mode];
  if (!allowedModes.some((item) => item.value === normalized.bus_data_port_mode)) {
    normalized.bus_data_port_mode = allowedModes[0].value;
  }
  const assignmentKeys = {
    single_column_shared: ["shared"],
    single_column_split_ab: ["A", "B"],
    double_column_by_column: ["column_1", "column_2"],
    double_column_by_route: ["A", "B"],
  }[normalized.bus_data_port_mode];
  const dataPorts = allowedPorts.filter((port) => port !== normalized.environment_rs485_port);
  const fallbackPorts = dataPorts.length ? dataPorts : allowedPorts;
  const rawAssignments = normalized.bus_data_port_assignments || {};
  const assignments = {};
  assignmentKeys.forEach((key, index) => {
    let port = rawAssignments[key];
    if (!allowedPorts.includes(port) || port === normalized.environment_rs485_port) {
      port = fallbackPorts[Math.min(index, fallbackPorts.length - 1)];
    }
    if (assignmentKeys.length > 1 && Object.values(assignments).includes(port)) {
      port = fallbackPorts.find((candidate) => !Object.values(assignments).includes(candidate)) || port;
    }
    assignments[key] = port;
  });
  normalized.bus_data_port_assignments = assignments;
  return normalized;
}

function hardwareFormOptions() {
  const options = state.bootstrap?.options?.hardware_form_factors;
  return Array.isArray(options) && options.length
    ? options
    : [
        {
          value: "horizontal",
          label: "卧式屏",
          help_text: "屏后使用 A2B2、A3B3、A4B4。",
          available_ports: PORTS_BY_HARDWARE.horizontal,
          default_environment_port: DEFAULT_ENVIRONMENT_PORT.horizontal,
        },
        {
          value: "din_rail",
          label: "滑轨式屏",
          help_text: "屏后使用 A1B1、A2B2、A3B3。",
          available_ports: PORTS_BY_HARDWARE.din_rail,
          default_environment_port: DEFAULT_ENVIRONMENT_PORT.din_rail,
        },
      ];
}

function currentHardwareForm() {
  const formValue = state.config.topology.hardware_form_factor;
  return hardwareFormOptions().find((item) => item.value === formValue) || hardwareFormOptions()[0];
}

function availablePhysicalPortOptions({ excludeEnvironment = false } = {}) {
  const allowed = PORTS_BY_HARDWARE[state.config.topology.hardware_form_factor] || [];
  const options = state.bootstrap?.options?.physical_ports || allowed.map((value) => ({ value, label: value }));
  return options.filter((item) => (
    allowed.includes(item.value) &&
    (!excludeEnvironment || item.value !== state.config.topology.environment_rs485_port)
  ));
}

function currentBusDataModeOptions() {
  const topologyMode = state.config.topology.screen_topology_mode;
  const bootstrapModes = state.bootstrap?.options?.bus_data_port_modes?.[topologyMode];
  return Array.isArray(bootstrapModes) && bootstrapModes.length
    ? bootstrapModes
    : BUS_DATA_MODE_OPTIONS[topologyMode] || [];
}

function busDataAssignmentDescriptors(mode = state.config.topology.bus_data_port_mode) {
  return {
    single_column_shared: [
      { key: "shared", label: "A/B 路母线数据口", role: "单列 A/B" },
    ],
    single_column_split_ab: [
      { key: "A", label: "A 路母线数据口", role: "单列 A 路" },
      { key: "B", label: "B 路母线数据口", role: "单列 B 路" },
    ],
    double_column_by_column: [
      { key: "column_1", label: "第一列母线数据口", role: "第一列 A/B" },
      { key: "column_2", label: "第二列母线数据口", role: "第二列 A/B" },
    ],
    double_column_by_route: [
      { key: "A", label: "两列 A 路母线数据口", role: "两列 A 路" },
      { key: "B", label: "两列 B 路母线数据口", role: "两列 B 路" },
    ],
  }[mode] || [];
}

function busDataModeLabel() {
  return optionText(
    currentBusDataModeOptions(),
    state.config.topology.bus_data_port_mode,
  );
}

function busDataPortSummary() {
  const assignments = state.config.topology.bus_data_port_assignments || {};
  return busDataAssignmentDescriptors()
    .map((item) => `${item.role} ${assignments[item.key] || "待分配"}`)
    .join("；");
}

function renderHardwareFormChooser() {
  const currentValue = state.config.topology.hardware_form_factor;
  return `
    <div class="hardware-form-options" role="radiogroup" aria-label="设备形态">
      ${hardwareFormOptions().map((item) => {
        const ports = Array.isArray(item.available_ports) ? item.available_ports : PORTS_BY_HARDWARE[item.value] || [];
        const active = item.value === currentValue;
        return `
          <button
            class="hardware-form-card ${active ? "is-active" : ""}"
            type="button"
            role="radio"
            aria-checked="${active ? "true" : "false"}"
            data-action="set-hardware-form"
            data-value="${escapeHtml(item.value)}"
          >
            <span class="hardware-form-card__ports" aria-hidden="true">${ports.map((port) => `<i>${escapeHtml(port.replace("A", "").replace(/B\d+$/u, ""))}</i>`).join("")}</span>
            <span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(ports.join(" · "))}</small></span>
            <em>动环默认 ${escapeHtml(item.default_environment_port || DEFAULT_ENVIRONMENT_PORT[item.value] || "-")}</em>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function renderBusDataModeChooser() {
  const currentValue = state.config.topology.bus_data_port_mode;
  return `
    <div class="bus-port-mode-options" role="radiogroup" aria-label="母线数据接入方式">
      ${currentBusDataModeOptions().map((item) => {
        const active = item.value === currentValue;
        return `
          <button
            class="bus-port-mode-card ${active ? "is-active" : ""}"
            type="button"
            role="radio"
            aria-checked="${active ? "true" : "false"}"
            data-action="set-bus-data-mode"
            data-value="${escapeHtml(item.value)}"
          >
            <strong>${escapeHtml(item.label)}</strong>
            <small>${escapeHtml(item.help_text || "")}</small>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function renderPhysicalPortMap() {
  const environmentPort = state.config.topology.environment_rs485_port;
  const assignments = state.config.topology.bus_data_port_assignments || {};
  const assignmentDescriptors = busDataAssignmentDescriptors();
  return `
    <div class="physical-port-map" aria-label="屏后物理端口占用图">
      ${availablePhysicalPortOptions().map((portOption) => {
        const roles = [];
        if (portOption.value === environmentPort) {
          roles.push({ label: "动环 RS-485", tone: "environment" });
        }
        assignmentDescriptors.forEach((item) => {
          if (assignments[item.key] === portOption.value) {
            roles.push({ label: item.role, tone: "bus" });
          }
        });
        return `
          <div class="port-node ${roles.length ? "is-used" : "is-free"}">
            <span class="port-node__socket" aria-hidden="true"><i></i><i></i></span>
            <strong>${escapeHtml(portOption.label || portOption.value)}</strong>
            <div>${roles.length
              ? roles.map((role) => `<span class="port-role-chip is-${role.tone}">${escapeHtml(role.label)}</span>`).join("")
              : '<span class="port-role-chip is-free">空闲</span>'}</div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function setHardwareForm(value) {
  if (!PORTS_BY_HARDWARE[value] || state.config.topology.hardware_form_factor === value) {
    return;
  }
  state.config.topology.hardware_form_factor = value;
  state.config.topology.environment_rs485_port = DEFAULT_ENVIRONMENT_PORT[value];
  state.config.topology.upload_port_profile = DEFAULT_ENVIRONMENT_PORT[value];
  state.config.topology.bus_data_port_assignments = {};
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`已按${currentHardwareForm().label}重新分配屏后端口`, "success");
  renderAll();
}

function setBusDataMode(value) {
  if (!currentBusDataModeOptions().some((item) => item.value === value)) {
    return;
  }
  state.config.topology.bus_data_port_mode = value;
  state.config.topology.bus_data_port_assignments = {};
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`母线数据接入已切换为“${busDataModeLabel()}”`, "success");
  renderAll();
}

function defaultStartBoxNames(route, count, topologyMode, column = 1) {
  const total = Math.max(0, Number(count || 0));
  if (!total) {
    return [];
  }
  const twoColumns = topologyMode === SCREEN_MODE_DOUBLE;
  const start = routeDefaultStartCode(route, column);
  const step = twoColumns ? 4 : 1;
  return Array.from({ length: total }, (_, index) => `S${start + index * step}`);
}

function expandSequenceItems(route, sequence, options = {}) {
  const rawItems = Array.isArray(sequence) ? sequence : [];
  const expanded = [];
  rawItems.forEach((rawItem) => {
    const normalized = normalizeSequenceItem(rawItem);
    const repeatCount = Math.max(1, Number(normalized.count || 1));
    for (let index = 0; index < repeatCount; index += 1) {
      const item = { ...normalized, count: 1 };
      delete item.box_number;
      delete item.board_number_start;
      if (options.preserveNumbers && index === 0) {
        if (normalized.box_number != null) {
          item.box_number = normalized.box_number;
        }
        if (normalized.board_number_start != null) {
          item.board_number_start = normalized.board_number_start;
        }
      }
      expanded.push(item);
    }
  });
  return expanded;
}

function normalizeConfig(rawConfig) {
  const familyGuess = currentFamilyFromConfig(rawConfig) || state.activeFamily || "classic_combined";
  const familyDefaultConfig = clone(state.maps.familyDefaultConfigs[familyGuess]);
  const config = deepMerge(familyDefaultConfig, rawConfig || {});
  const exportProfileId = config.profiles?.export_profile_id;
  const exportProfile = state.maps.exportProfiles[exportProfileId];
  const family = exportProfile?.family || familyGuess;
  const canonicalDefault = clone(state.maps.familyDefaultConfigs[family]);
  const normalized = deepMerge(canonicalDefault, config);

  normalized.workflow_version = "unified_protocol_v1";
  normalized.generation_basis = "max_column";
  normalized.protocol_layout = normalized.protocol_layout || {};
  normalized.protocol_layout.measurement_layout_mode = ["by_plug_box", "by_branch"].includes(
    normalized.protocol_layout.measurement_layout_mode,
  )
    ? normalized.protocol_layout.measurement_layout_mode
    : "by_plug_box";
  normalized.protocol_layout.base_sheet_name = "始端箱和插接箱";
  normalized.protocol_layout.embed_single_cabinet_in_base_sheet = true;
  normalized.protocol_layout.alarm_start_box_first = true;
  normalized.protocol_layout.main_base_address = Math.max(
    0,
    Number(normalized.protocol_layout.main_base_address ?? 1000),
  );
  if (normalized.protocol_layout.measurement_layout_mode === "by_branch") {
    normalized.protocol_layout.downstream_base_address = Math.max(
      0,
      Number(normalized.protocol_layout.downstream_base_address ?? 2000),
    );
    normalized.protocol_layout.downstream_primary_outputs_per_route = Math.max(
      1,
      Number(normalized.protocol_layout.downstream_primary_outputs_per_route ?? 38),
    );
    normalized.protocol_layout.downstream_extension_base_address = Math.max(
      0,
      Number(normalized.protocol_layout.downstream_extension_base_address ?? 9500),
    );
  } else {
    normalized.protocol_layout.downstream_base_address = null;
    normalized.protocol_layout.downstream_primary_outputs_per_route = null;
    normalized.protocol_layout.downstream_extension_base_address = null;
  }
  normalized.export_family = family;
  normalized.profiles.device_library_id = state.bootstrap.meta.device_library_id;

  const currentAddressProfile = state.maps.addressProfiles[normalized.profiles.address_profile_id];
  if (!currentAddressProfile || currentAddressProfile.family !== family) {
    normalized.profiles.address_profile_id = state.maps.familyDefaults[family].address_profile_id;
  }

  normalized.topology = normalizePortTopology(normalized.topology || {});
  normalized.topology.canonical_column_id = normalized.topology.canonical_column_id || "J01";

  normalized.communication.baud_rate = Math.max(300, Number(normalized.communication.baud_rate || 9600));
  normalized.communication.data_bits = Math.max(1, Number(normalized.communication.data_bits || 8));
  normalized.communication.stop_bits = Math.max(1, Number(normalized.communication.stop_bits || 1));
  normalized.communication.default_screen_address = Math.max(
    1,
    Number(normalized.communication.default_screen_address || 1),
  );

  if (normalized.profiles.export_profile_id === CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID) {
    normalized.profiles.export_profile_id = CLASSIC_DEFAULT_EXPORT_PROFILE_ID;
  }

  normalized.devices.start_boxes = normalized.devices.start_boxes || {};
  normalized.devices.plug_boxes = normalized.devices.plug_boxes || {};
  normalized.devices.branch_modules = normalized.devices.branch_modules || {};
  ensureSecondColumnDevices(normalized);

  [1, 2].forEach((column) => {
    const deviceRoot = routeDeviceRoot(normalized, column);
    deviceRoot.start_boxes = deviceRoot.start_boxes || {};
    deviceRoot.plug_boxes = deviceRoot.plug_boxes || {};
    deviceRoot.branch_modules = deviceRoot.branch_modules || {};
    ["A", "B"].forEach((route) => {
      const boardStart = routeDefaultBoxStart(route, column);
      const defaultName = `S${routeDefaultStartCode(route, column)}`;
      deviceRoot.start_boxes[route] = deviceRoot.start_boxes[route] || {};
      deviceRoot.start_boxes[route].count = Math.max(
        0,
        Number(deviceRoot.start_boxes[route].count || 0),
      );
      deviceRoot.start_boxes[route].device_code_start = Math.max(
        1,
        Number(deviceRoot.start_boxes[route].device_code_start || routeDefaultStartCode(route, column)),
      );
      const startBoxNames = splitNames(deviceRoot.start_boxes[route].instance_names || []);
      const defaultNames = defaultStartBoxNames(
        route,
        deviceRoot.start_boxes[route].count,
        normalized.topology.screen_topology_mode,
        column,
      );
      deviceRoot.start_boxes[route].instance_names = Array.from(
        { length: deviceRoot.start_boxes[route].count },
        (_, index) => startBoxNames[index] || defaultNames[index] || defaultName,
      );

      deviceRoot.plug_boxes[route] = deviceRoot.plug_boxes[route] || {};
      deviceRoot.plug_boxes[route].box_number_start = Math.max(
        1,
        Number(deviceRoot.plug_boxes[route].box_number_start || boardStart),
      );
      deviceRoot.plug_boxes[route].board_number_start = Math.max(
        1,
        Number(deviceRoot.plug_boxes[route].board_number_start || boardStart),
      );
      const sequence = Array.isArray(deviceRoot.plug_boxes[route].sequence)
        ? deviceRoot.plug_boxes[route].sequence
        : [];
      deviceRoot.plug_boxes[route].sequence = expandSequenceItems(route, sequence, {
        preserveNumbers: true,
      }).map((item) => ({
        ...item,
        branch_template_id:
          item.branch_template_id || normalized.profiles.plug_branch_template_id,
      }));

      deviceRoot.branch_modules[route] = deviceRoot.branch_modules[route] || {};
      const branchModuleConfig = deviceRoot.branch_modules[route];
      const legacyModuleCount = Math.max(0, Number(branchModuleConfig.module_count || 0));
      const rawModuleSequence = Array.isArray(branchModuleConfig.module_sequence)
        ? branchModuleConfig.module_sequence
        : [];
      branchModuleConfig.module_sequence = (rawModuleSequence.length
        ? rawModuleSequence.map((item) => normalizeModuleSequenceItem(item))
        : legacyModuleCount > 0
          ? [normalizeModuleSequenceItem({
              type_code: "3P*2",
              layout_pattern: "1+1",
              count: legacyModuleCount,
              branch_template_id: branchModuleConfig.branch_template_id,
            })]
          : []).map((item) => ({
            ...item,
            branch_template_id:
              item.branch_template_id || normalized.profiles.plug_branch_template_id,
          }));
      branchModuleConfig.variable_numbering_mode = BRANCH_NUMBERING_BOARD_SUFFIX;
      branchModuleConfig.module_number_start = Math.max(1, Number(branchModuleConfig.module_number_start || 1));
      branchModuleConfig.output_number_start = Math.max(1, Number(branchModuleConfig.output_number_start || 1));
      branchModuleConfig.branch_device_number_start = Math.max(
        1,
        Number(branchModuleConfig.branch_device_number_start || boardStart),
      );
      branchModuleConfig.names = splitNames(branchModuleConfig.names || []);
      delete branchModuleConfig.module_count;
      delete branchModuleConfig.branches_per_module;
      delete branchModuleConfig.branch_template_id;
    });

    const routeBStartCount = deviceRoot.start_boxes.B?.count || 0;
    const routeBNames = splitNames(deviceRoot.start_boxes.B?.instance_names || []);
    const routeADefaultNames = defaultStartBoxNames(
      "A",
      routeBStartCount,
      normalized.topology.screen_topology_mode,
      column,
    );
    if (sameStringArray(routeBNames, routeADefaultNames)) {
      deviceRoot.start_boxes.B.instance_names = defaultStartBoxNames(
        "B",
        routeBStartCount,
        normalized.topology.screen_topology_mode,
        column,
      );
    }

    const routeBPlugConfig = deviceRoot.plug_boxes.B;
    if (Number(routeBPlugConfig?.board_number_start || 0) === routeDefaultBoxStart("A", column)) {
      routeBPlugConfig.board_number_start = routeDefaultBoxStart("B", column);
      routeBPlugConfig.box_number_start = routeDefaultBoxStart("B", column);
    }
    (routeBPlugConfig?.sequence || []).forEach((item, index) => {
      const expectedA = routeDefaultBoxStart("A", column) + index;
      const expectedB = routeDefaultBoxStart("B", column) + index;
      if (item?.box_number != null && item.box_number !== "" && Number(item.box_number) === expectedA) {
        item.box_number = expectedB;
      }
      if (item?.board_number_start != null && item.board_number_start !== "" && Number(item.board_number_start) === expectedA) {
        item.board_number_start = expectedB;
      }
      const explicitBoxName = String(item?.box_name || item?.instance_name || "").trim();
      if (explicitBoxName === String(expectedA)) {
        item.box_name = String(expectedB);
        delete item.instance_name;
      }
    });
  });

  normalized.devices.repeater_units = normalized.devices.repeater_units || {};
  normalized.devices.single_cabinet_aggregation =
    normalized.devices.single_cabinet_aggregation || {};

  const rawExtensions = normalized.extensions || {};
  const repeaterExtension = rawExtensions.repeater || {};
  const cabinetExtension = rawExtensions.single_cabinet || {};
  const selectedAddressProfile = state.maps.addressProfiles[normalized.profiles.address_profile_id] || {};
  const alarmExtension = rawExtensions.alarm_state_word || {};
  const isTwoColumn = normalized.topology.screen_topology_mode === SCREEN_MODE_DOUBLE;
  const repeaterColumnsSource =
    repeaterExtension.columns || normalized.devices.repeater_units.columns || {};
  const hasRepeaterColumns = ["column_1", "column_2"].some(
    (key) => repeaterColumnsSource?.[key] && typeof repeaterColumnsSource[key] === "object",
  );
  const legacyRepeaterA = Math.max(
    0,
    Number(repeaterExtension.A_count ?? normalized.devices.repeater_units.A_count ?? 0),
  );
  const legacyRepeaterB = Math.max(
    0,
    Number(repeaterExtension.B_count ?? normalized.devices.repeater_units.B_count ?? 0),
  );
  const repeaterColumns = Object.fromEntries([1, 2].map((column) => {
    const key = `column_${column}`;
    const source = repeaterColumnsSource?.[key] || {};
    const enabledColumn = column === 1 || isTwoColumn;
    return [key, {
      ...source,
      A_count: enabledColumn
        ? Math.max(0, Number(source.A_count ?? (!hasRepeaterColumns && column === 1 ? legacyRepeaterA : 0)))
        : 0,
      B_count: enabledColumn
        ? Math.max(0, Number(source.B_count ?? (!hasRepeaterColumns && column === 1 ? legacyRepeaterB : 0)))
        : 0,
    }];
  }));
  const repeaterTotalA = repeaterColumns.column_1.A_count + repeaterColumns.column_2.A_count;
  const repeaterTotalB = repeaterColumns.column_1.B_count + repeaterColumns.column_2.B_count;

  const cabinetColumnsSource =
    cabinetExtension.column_counts || normalized.devices.single_cabinet_aggregation.column_counts || {};
  const hasCabinetColumns = ["column_1", "column_2"].some(
    (key) => cabinetColumnsSource?.[key] != null,
  );
  const legacyCabinetCount = Math.max(
    0,
    Number(
      cabinetExtension.cabinet_count ??
        normalized.devices.single_cabinet_aggregation.cabinet_count ??
        0,
    ),
  );
  const cabinetColumnCounts = {
    column_1: Math.max(
      0,
      Number(cabinetColumnsSource.column_1 ?? (!hasCabinetColumns ? legacyCabinetCount : 0)),
    ),
    column_2: isTwoColumn
      ? Math.max(0, Number(cabinetColumnsSource.column_2 ?? 0))
      : 0,
  };
  const cabinetTotalCount = cabinetColumnCounts.column_1 + cabinetColumnCounts.column_2;
  normalized.extensions = {
    ...rawExtensions,
    repeater: {
      ...repeaterExtension,
      enabled: Boolean(repeaterExtension.enabled ?? normalized.devices.repeater_units.enabled),
      A_count: repeaterTotalA,
      B_count: repeaterTotalB,
      columns: repeaterColumns,
      alias: String(repeaterExtension.alias ?? normalized.devices.repeater_units.alias ?? "中继器"),
      base_address: Math.max(
        0,
        Number(
          repeaterExtension.base_address ??
            normalized.devices.repeater_units.base_address ??
            (normalized.protocol_layout.measurement_layout_mode === "by_branch" ? 9000 : 5500),
        ),
      ),
    },
    single_cabinet: {
      ...cabinetExtension,
      enabled: Boolean(
        cabinetExtension.enabled ?? normalized.devices.single_cabinet_aggregation.enabled,
      ),
      include_route_data: Boolean(
        cabinetExtension.include_route_data ??
          normalized.devices.single_cabinet_aggregation.include_route_data ??
          false,
      ),
      include_total_power_energy: Boolean(
        cabinetExtension.include_total_power_energy ??
          normalized.devices.single_cabinet_aggregation.include_total_power_energy ??
          false,
      ),
      cabinet_count: cabinetTotalCount,
      column_counts: cabinetColumnCounts,
      base_address: Math.max(
        0,
        Number(
          cabinetExtension.base_address ??
            normalized.devices.single_cabinet_aggregation.base_address ??
            (normalized.protocol_layout.measurement_layout_mode === "by_branch" ? 8200 : 7000),
        ),
      ),
      metric_base_addresses: {
        ...(cabinetExtension.metric_base_addresses || {}),
        ...(normalized.protocol_layout.measurement_layout_mode === "by_branch"
          ? {
              IA: Math.max(0, Number(cabinetExtension.metric_base_addresses?.IA ?? 8200)),
              PA: Math.max(0, Number(cabinetExtension.metric_base_addresses?.PA ?? 8400)),
              EA: Math.max(0, Number(cabinetExtension.metric_base_addresses?.EA ?? 8600)),
              KA: Math.max(0, Number(cabinetExtension.metric_base_addresses?.KA ?? 8800)),
            }
          : {}),
      },
    },
    alarm_state_word: {
      ...alarmExtension,
      enabled: alarmExtension.enabled !== false,
      legacy_slide_rail_order: alarmExtension.legacy_slide_rail_order === true,
      base_address: Math.max(
        0,
        Number(alarmExtension.base_address ?? selectedAddressProfile.alarm_base ?? 6000),
      ),
      word_mode: ["16bit", "32bit"].includes(alarmExtension.word_mode)
        ? alarmExtension.word_mode
        : selectedAddressProfile.alarm_word_mode || "16bit",
    },
  };

  normalized.devices.repeater_units = {
    ...normalized.devices.repeater_units,
    ...normalized.extensions.repeater,
  };
  normalized.devices.single_cabinet_aggregation = {
    ...normalized.devices.single_cabinet_aggregation,
    ...normalized.extensions.single_cabinet,
  };

  if (
    family === "extended_split" &&
    normalized.project_code === LEGACY_EXTENDED_DEMO_PROJECT_CODE &&
    normalized.devices.single_cabinet_aggregation.enabled &&
    normalized.devices.single_cabinet_aggregation.cabinet_count === LEGACY_EXTENDED_DEMO_CABINET_COUNT &&
    normalized.profiles.single_cabinet_template_id === LEGACY_EXTENDED_DEMO_TEMPLATE_ID
  ) {
    normalized.devices.single_cabinet_aggregation.cabinet_count = 38;
    normalized.profiles.single_cabinet_template_id = LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID;
  }

  if (normalized.profiles.export_profile_id === LIQUIDCOOL_EXPORT_PROFILE_ID) {
    normalized.profiles.address_profile_id = LIQUIDCOOL_ADDRESS_PROFILE_ID;
    normalized.profiles.start_box_template_id = LIQUIDCOOL_START_BOX_TEMPLATE_ID;
    normalized.profiles.plug_branch_template_id = LIQUIDCOOL_PLUG_BRANCH_TEMPLATE_ID;
    normalized.profiles.repeater_template_id = LIQUIDCOOL_REPEATER_TEMPLATE_ID;
    normalized.profiles.single_cabinet_template_id = LIQUIDCOOL_SINGLE_CABINET_TEMPLATE_ID;
  }

  const templateFallbacks = [
    ["start_box_template_id", "start_box_templates"],
    ["plug_branch_template_id", "plug_branch_templates"],
    ["repeater_template_id", "repeater_templates"],
    ["single_cabinet_template_id", "single_cabinet_templates"],
  ];
  templateFallbacks.forEach(([profileKey, templateGroup]) => {
    const options = state.bootstrap.templates?.[templateGroup] || [];
    const currentValue = normalized.profiles[profileKey];
    if (!options.length) {
      return;
    }
    if (currentValue && options.some((item) => item.id === currentValue)) {
      return;
    }
    normalized.profiles[profileKey] = options[0].id;
  });

  return normalized;
}

function isBasicMode() {
  return true;
}

function optionText(options, value, idKey = "value") {
  return options.find((item) => item[idKey] === value)?.label || value || "-";
}

function optionById(options, value, idKey = "id") {
  return (Array.isArray(options) ? options : []).find((item) => item?.[idKey] === value) || null;
}

function optionSupportNote(option) {
  if (!option) {
    return "";
  }
  return [option.diff_summary, option.help_text || option.description].filter(Boolean).join("；");
}

function compactOptionSupportNote(note, maxLength = 34) {
  const text = String(note || "").replace(/\s+/gu, " ").trim();
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, Math.max(1, maxLength - 1))}…` : text;
}

function uniqueValues(values) {
  return [...new Set((Array.isArray(values) ? values : []).map((item) => String(item || "").trim()).filter(Boolean))];
}

function reviewItemsFromResult(target = state.result) {
  const delivery = getDeliveryStatus(target);
  const protocolDiff = getProtocolDiffSummary(target);
  const unifiedWorkflow = state.config?.workflow_version === "unified_protocol_v1";
  if (unifiedWorkflow) {
    return uniqueValues([
      ...(delivery?.blockers || []),
      ...(delivery?.review_items || []),
      ...(target?.summary?.warnings || []),
    ]);
  }
  return uniqueValues([
    ...(protocolDiff?.blocking_items || []),
    ...(delivery?.blockers || []),
    ...(protocolDiff?.focus_items || []),
    ...(delivery?.review_items || []),
    ...(protocolDiff?.review_items || []),
    ...(target?.summary?.warnings || []),
  ]);
}

function scenarioOptions() {
  const bootstrapScenarios = Array.isArray(state.bootstrap?.scenarios) ? state.bootstrap.scenarios : [];
  const source = bootstrapScenarios.length ? bootstrapScenarios : DEFAULT_SCENARIOS;
  return source
    .map((item) => ({
      ...item,
      config:
        item.config ||
        state.maps?.familyDefaultConfigs?.[item.example_key] ||
        state.maps?.familyDefaultConfigs?.[item.family] ||
        null,
    }))
    .filter((item) => item.config);
}

function currentScenarioKey(config = state.config) {
  const topologyMode = config?.topology?.screen_topology_mode;
  const exportProfileId = config?.profiles?.export_profile_id;
  const family = currentFamilyFromConfig(config);
  if (topologyMode === "single_screen_two_columns" || exportProfileId === CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID) {
    return "classic_two_columns";
  }
  if (family === "ab_screen_split" || topologyMode === "dual_screens_ab_separated") {
    return "ab_screen_split";
  }
  if (family === "extended_split") {
    return "extended_split";
  }
  return "classic_standard";
}

function currentScenarioOption(config = state.config) {
  const currentKey = currentScenarioKey(config);
  return scenarioOptions().find((item) => item.id === currentKey) || scenarioOptions()[0] || null;
}

function currentScenarioGuide(config = state.config) {
  const scenario = currentScenarioOption(config);
  if (!scenario) {
    return {
      title: "标准单列（含中继页）",
      note: "适合常见单屏项目；如需双列或 A/B 分屏，可直接切换方案。",
    };
  }
  const noteParts = [];
  if (scenario.usage_hint) {
    noteParts.push(scenario.usage_hint);
  }
  if (scenario.source_workbook_file) {
    noteParts.push("已绑定当前场景参考口径");
  }
  if (scenario.recommended_upload_port) {
    noteParts.push(`默认动环 RS-485 口：${scenario.recommended_upload_port}`);
  }
  return {
    title: scenario.label,
    note: noteParts.join("；"),
  };
}

function joinCn(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .join("、");
}

function currentBaselinePreset(config = state.config) {
  const profiles = config?.profiles || {};
  const family = currentFamilyFromConfig(config);
  if (
    family === "classic_combined" &&
    (profiles.export_profile_id === LIQUIDCOOL_EXPORT_PROFILE_ID ||
      profiles.address_profile_id === LIQUIDCOOL_ADDRESS_PROFILE_ID)
  ) {
    return SCENARIO_BASELINE_PRESETS.classic_combined_liquidcool;
  }
  if (family === "classic_combined" && profiles.export_profile_id === CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID) {
    return SCENARIO_BASELINE_PRESETS.classic_combined_two_columns;
  }
  return SCENARIO_BASELINE_PRESETS[family] || SCENARIO_BASELINE_PRESETS.classic_combined;
}

function contextualizeExportOptions(options, baselinePreset = currentBaselinePreset()) {
  const safeOptions = Array.isArray(options) ? options : [];
  const baseline = safeOptions.find((item) => item.id === baselinePreset?.export_profile_id);
  if (!baseline) {
    return safeOptions;
  }
  const baselineOrder = Array.isArray(baseline.sheet_order) ? baseline.sheet_order : [];
  return safeOptions.map((option) => {
    const sheetOrder = Array.isArray(option.sheet_order) ? option.sheet_order : [];
    if (option.id === baseline.id) {
      return {
        ...option,
        diff_summary: "当前场景标准 Excel 页面结构",
      };
    }
    const added = sheetOrder.filter((item) => !baselineOrder.includes(item));
    const removed = baselineOrder.filter((item) => !sheetOrder.includes(item));
    const diffParts = [];
    if (added.length) {
      diffParts.push(`比当前标准多：${joinCn(added)}`);
    }
    if (removed.length) {
      diffParts.push(`比当前标准少：${joinCn(removed)}`);
    }
    if (!diffParts.length && baselineOrder.join("|") !== sheetOrder.join("|") && sheetOrder.length) {
      diffParts.push(`Excel 页面顺序调整为：${sheetOrder.join(" / ")}`);
    }
    return {
      ...option,
      diff_summary: diffParts.join("；") || option.diff_summary || "与当前标准 Excel 页面结构接近",
    };
  });
}

function contextualizeAddressOptions(options, baselinePreset = currentBaselinePreset()) {
  const safeOptions = Array.isArray(options) ? options : [];
  const baseline = safeOptions.find((item) => item.id === baselinePreset?.address_profile_id);
  if (!baseline) {
    return safeOptions;
  }
  return safeOptions.map((option) => {
    if (option.id === baseline.id) {
      return {
        ...option,
        diff_summary: "与当前标准地址方案一致",
      };
    }
    const diffParts = [];
    if (baseline.main_base !== option.main_base) {
      diffParts.push(`主地址起始改为 ${option.main_base}`);
    }
    if (baseline.plug_base == null && option.plug_base != null) {
      diffParts.push(`比当前标准多插接箱地址段（${option.plug_base} 起）`);
    } else if (baseline.plug_base != null && option.plug_base == null) {
      diffParts.push("比当前标准少插接箱地址段");
    } else if (baseline.plug_base !== option.plug_base && option.plug_base != null) {
      diffParts.push(`插接箱地址起始改为 ${option.plug_base}`);
    }
    if (baseline.repeater_base == null && option.repeater_base != null) {
      diffParts.push(`比当前标准多中继地址段（${option.repeater_base} 起）`);
    } else if (baseline.repeater_base != null && option.repeater_base == null) {
      diffParts.push("比当前标准少中继地址段");
    } else if (baseline.repeater_base !== option.repeater_base && option.repeater_base != null) {
      diffParts.push(`中继地址起始改为 ${option.repeater_base}`);
    }
    if (baseline.cabinet_base == null && option.cabinet_base != null) {
      diffParts.push(`比当前标准多单机柜地址段（${option.cabinet_base} 起）`);
    } else if (baseline.cabinet_base != null && option.cabinet_base == null) {
      diffParts.push("比当前标准少单机柜地址段");
    } else if (baseline.cabinet_base !== option.cabinet_base && option.cabinet_base != null) {
      diffParts.push(`单机柜地址起始改为 ${option.cabinet_base}`);
    }
    if (baseline.alarm_base !== option.alarm_base) {
      diffParts.push(`报警地址起始改为 ${option.alarm_base}`);
    }
    if (baseline.alarm_word_mode !== option.alarm_word_mode) {
      diffParts.push(`报警字改为 ${option.alarm_word_mode === "32bit" ? "32 位" : "16 位"}`);
    }
    return {
      ...option,
      diff_summary: diffParts.join("；") || option.diff_summary || "与当前标准地址方案接近",
    };
  });
}

function contextualizeTemplateOptions(options, baselineTemplateId) {
  const safeOptions = Array.isArray(options) ? options : [];
  const baseline = safeOptions.find((item) => item.id === baselineTemplateId);
  if (!baseline) {
    return safeOptions;
  }
  const baselineFeatures = Array.isArray(baseline.features) ? baseline.features : [];
  return safeOptions.map((option) => {
    if (option.id === baseline.id) {
      return {
        ...option,
        diff_summary: "当前场景标准模板",
      };
    }
    const features = Array.isArray(option.features) ? option.features : [];
    const added = features.filter((item) => !baselineFeatures.includes(item));
    const removed = baselineFeatures.filter((item) => !features.includes(item));
    const diffParts = [];
    if (added.length) {
      diffParts.push(`比当前标准多：${joinCn(added)}`);
    }
    if (removed.length) {
      diffParts.push(`比当前标准少：${joinCn(removed)}`);
    }
    if (!diffParts.length && features.length) {
      diffParts.push(`监测项：${joinCn(features)}`);
    }
    return {
      ...option,
      diff_summary: diffParts.join("；") || option.diff_summary || "与当前标准模板接近",
    };
  });
}

function getSourceProtocolSummary(target = state.result) {
  return (
    target?.summary?.source_protocol_summary ||
    target?.source_protocol_summary ||
    target?.quality?.source_protocol_summary ||
    null
  );
}

function scenarioLabelFromSummary(summary = {}) {
  if (summary?.variant_label) {
    return summary.variant_label;
  }
  const exportProfileId = summary?.profile_selection?.export_profile_id;
  const family = summary?.family;
  if (exportProfileId === CLASSIC_TWO_COLUMNS_EXPORT_PROFILE_ID) {
    return "单屏双列";
  }
  return FAMILY_LABELS[family] || family || currentScenarioGuide().title;
}

function shouldCollapseQualitySection(result = state.result) {
  if (!result) {
    return true;
  }
  if (state.viewMode === "workspace") {
    return true;
  }
  const validation = getValidation(result);
  const sourceCompare = getSourceCompare(result);
  const delivery = getDeliveryStatus(result);
  const validationFailed = Boolean(validation?.status) && validation.status !== "passed";
  const compareNeedsReview = Boolean(sourceCompare?.overall_status) && sourceCompare.overall_status === "diverged";
  const deliveryNeedsReview = ["deliverable_with_review", "not_recommended", "review_required"].includes(
    delivery?.status,
  );
  return !(validationFailed || compareNeedsReview || deliveryNeedsReview);
}

function isCompactViewport() {
  return Boolean(window.matchMedia?.("(max-width: 900px)").matches);
}

const WORKFLOW_STEP_KEYS = ["quickStart", "routeA", "routeB", "extension", "project", "result"];

function collapsedDefaults(mode = state.viewMode, hasResult = Boolean(state.result)) {
  return {
    quickStart: hasResult,
    project: true,
    topology: true,
    profiles: true,
    routeA: true,
    routeB: true,
    extension: true,
    result: !hasResult,
    quality: hasResult ? shouldCollapseQualitySection() : true,
    history: true,
  };
}

function ensureCollapsedSections() {
  state.collapsedSections = {
    ...collapsedDefaults(state.viewMode, Boolean(state.result)),
    ...(state.collapsedSections || {}),
  };
}

function isSectionCollapsed(key) {
  ensureCollapsedSections();
  return Boolean(state.collapsedSections[key]);
}

function setViewMode(mode) {
  state.viewMode = "workspace";
  state.railUtilitiesOpen = false;
  state.collapsedSections = collapsedDefaults(state.viewMode, Boolean(state.result));
  renderAll();
}

function toggleSection(key) {
  if (WORKFLOW_STEP_KEYS.includes(key)) {
    jumpToSection(key);
    return;
  }
  ensureCollapsedSections();
  state.collapsedSections[key] = !state.collapsedSections[key];
  queueFocus(`[data-action="toggle-section"][data-section="${key}"]`);
  renderSectionByKey(key);
  updateWorkspaceVisibility();
  applyPendingFocus();
}

function routeSectionKey(route) {
  return route === "B" ? "routeB" : "routeA";
}

function ensureRouteQuickErrors() {
  if (!state.routeQuickErrors) {
    state.routeQuickErrors = {};
  }
}

function routeQuickError(route, column = activeColumnForRoute(route)) {
  ensureRouteQuickErrors();
  return state.routeQuickErrors[routeScopeKey(route, column)] || "";
}

function setRouteQuickError(route, message, column = activeColumnForRoute(route)) {
  ensureRouteQuickErrors();
  state.routeQuickErrors[routeScopeKey(route, column)] = String(message || "").trim();
}

function clearRouteQuickError(route, column = activeColumnForRoute(route)) {
  ensureRouteQuickErrors();
  state.routeQuickErrors[routeScopeKey(route, column)] = "";
}

function renderInlineQuickError(route, message = "", column = activeColumnForRoute(route)) {
  const panel = document.querySelector(`#routeSection${route} [data-route-column="${column}"] .quick-entry-panel`);
  if (!panel) {
    return;
  }
  const existing = panel.querySelector(".inline-feedback--error");
  const scopeKey = routeScopeKey(route, column);
  const input = panel.querySelector(`[data-quick-sequence-input="${scopeKey}"]`);
  const errorId = `quick-sequence-error-${scopeKey}`;
  const text = String(message || "").trim();
  if (!text) {
    existing?.remove();
    input?.removeAttribute("aria-invalid");
    input?.removeAttribute("aria-describedby");
    return;
  }
  if (existing) {
    existing.textContent = text;
    existing.id = errorId;
    existing.setAttribute("role", "alert");
    return;
  }
  const field = panel.querySelector(".field");
  if (!field) {
    return;
  }
  const node = document.createElement("div");
  node.className = "inline-feedback inline-feedback--error";
  node.id = errorId;
  node.setAttribute("role", "alert");
  node.textContent = text;
  field.insertAdjacentElement("afterend", node);
  input?.setAttribute("aria-invalid", "true");
  input?.setAttribute("aria-describedby", errorId);
}

function ensureSequenceExpandedState() {
  if (!state.sequenceExpanded) {
    state.sequenceExpanded = { A: {}, B: {} };
  }
  state.sequenceExpanded.A = state.sequenceExpanded.A || {};
  state.sequenceExpanded.B = state.sequenceExpanded.B || {};
}

function isSequenceDetailOpen(route, index, entry = null) {
  ensureSequenceExpandedState();
  const explicitValue = state.sequenceExpanded?.[route]?.[index];
  if (explicitValue != null) {
    return Boolean(explicitValue);
  }
  const routeSequence = state.config.devices.plug_boxes[route]?.sequence || [];
  if (routeSequence.length <= 1) {
    return true;
  }
  return Boolean(entry?.explicit_box_number != null || entry?.explicit_box_name);
}

function setSequenceExpanded(route, index, expanded) {
  ensureSequenceExpandedState();
  state.sequenceExpanded[route][index] = Boolean(expanded);
}

function setAllSequenceExpanded(route, expanded) {
  ensureSequenceExpandedState();
  const routeSequence = state.config.devices.plug_boxes[route]?.sequence || [];
  state.sequenceExpanded[route] = Object.fromEntries(
    routeSequence.map((_, index) => [index, Boolean(expanded)]),
  );
}

function resetSequenceDetailState(route = null) {
  ensureSequenceExpandedState();
  if (!route) {
    state.sequenceExpanded = { A: {}, B: {} };
    return;
  }
  state.sequenceExpanded[route] = {};
}

function sectionElementByKey(key) {
  return {
    quickStart: refs.quickStartSection,
    project: refs.projectSection,
    topology: refs.topologySection,
    profiles: refs.profilesSection,
    routeA: refs.routeSectionA,
    routeB: refs.routeSectionB,
    extension: refs.extensionSection,
    result: refs.resultSection,
    quality: refs.qualitySection,
    history: refs.historySection,
  }[key] || null;
}

function sectionDomIdByKey(key) {
  return {
    quickStart: "quickStartSection",
    project: "projectSection",
    topology: "topologySection",
    profiles: "profilesSection",
    routeA: "routeSectionA",
    routeB: "routeSectionB",
    extension: "extensionSection",
    result: "resultSection",
    quality: "qualitySection",
    history: "historySection",
  }[key] || "";
}

function focusElement(element, scroll = false) {
  if (!(element instanceof HTMLElement)) {
    return;
  }
  if (element.tabIndex < 0 && !element.hasAttribute("tabindex")) {
    element.setAttribute("tabindex", "-1");
  }
  try {
    element.focus({ preventScroll: true });
  } catch {
    element.focus();
  }
  if (scroll) {
    element.scrollIntoView({ behavior: preferredScrollBehavior(), block: "start" });
  }
}

function queueFocus(selector) {
  state.pendingFocusSelector = selector || "";
}

function applyPendingFocus() {
  if (!state.pendingFocusSelector) {
    return;
  }
  const selector = state.pendingFocusSelector;
  state.pendingFocusSelector = "";
  const target = document.querySelector(selector);
  if (target instanceof HTMLElement) {
    focusElement(target, false);
  }
}

function focusSectionByKey(key, scroll = true) {
  const element = sectionElementByKey(key) || document.getElementById("mainWorkspace");
  focusElement(element, scroll);
}

function jumpToSection(key) {
  if (["topology", "quality", "history"].includes(key)) {
    openDrawer(key === "topology" ? "communication" : key);
    return;
  }
  ensureCollapsedSections();
  WORKFLOW_STEP_KEYS.forEach((stepKey) => {
    state.collapsedSections[stepKey] = stepKey !== key;
  });
  state.activeStep = WORKFLOW_STEP_KEYS.includes(key) ? key : state.activeStep;
  if (key === "routeA") {
    state.activeRoute = "A";
  } else if (key === "routeB") {
    state.activeRoute = "B";
  }
  WORKFLOW_STEP_KEYS.forEach((stepKey) => renderSectionByKey(stepKey));
  renderLiveSummary();
  updateWorkspaceVisibility();
  renderWorkflowSpine();
  renderMobileActionBar();
  refreshLucideIcons();
  focusSectionByKey(key, true);
}

function compactRouteSummary(route) {
  return `${route}路 ${routePresentation(route).summary}`;
}

function compactSequenceState(route) {
  const resolved = resolvedSequenceItems(route);
  const expandedCount = resolved.reduce(
    (count, item, index) => count + (isSequenceDetailOpen(route, index, item) ? 1 : 0),
    0,
  );
  return {
    total: resolved.length,
    expanded: expandedCount,
  };
}

function showElement(element, visible) {
  if (!element) {
    return;
  }
  element.hidden = !visible;
}

function drawerElement(name) {
  return {
    preview: refs.previewDrawer,
    communication: refs.communicationDrawer,
    quality: refs.qualityDrawer,
    history: refs.historyDrawer,
  }[name] || null;
}

function renderDrawerState() {
  ["preview", "communication", "quality", "history"].forEach((name) => {
    const drawer = drawerElement(name);
    const open = state.activeDrawer === name;
    showElement(drawer, open);
    drawer?.setAttribute("aria-hidden", open ? "false" : "true");
  });
  showElement(refs.drawerBackdrop, Boolean(state.activeDrawer));
  document.body.dataset.drawerOpen = state.activeDrawer ? "true" : "false";
}

function openDrawer(name) {
  if (!drawerElement(name)) {
    return;
  }
  state.activeDrawer = name;
  state.railUtilitiesOpen = false;
  if (name === "communication") {
    state.collapsedSections.topology = false;
    renderTopologySection();
  } else if (name === "quality") {
    state.collapsedSections.quality = false;
    renderQualitySection();
  } else if (name === "history") {
    state.collapsedSections.history = false;
    renderHistorySection();
  }
  renderStatus();
  renderDrawerState();
  window.requestAnimationFrame(() => {
    const target = drawerElement(name)?.querySelector("button, input, select, textarea, summary");
    target?.focus({ preventScroll: true });
  });
}

function closeDrawer() {
  if (!state.activeDrawer) {
    return;
  }
  const triggerSelector = state.activeDrawer === "communication"
    ? "#communicationSettingsBtn"
    : state.activeDrawer === "preview"
      ? "#previewBtn"
      : `[data-action="open-drawer"][data-drawer="${state.activeDrawer}"]`;
  state.activeDrawer = "";
  renderDrawerState();
  document.querySelector(triggerSelector)?.focus({ preventScroll: true });
}

function setSectionVisualState(element, collapsed, role = "") {
  if (!element) {
    return;
  }
  element.dataset.collapsed = collapsed ? "true" : "false";
  if (role) {
    element.dataset.role = role;
  }
}

function renderPreviewDependentSections() {
  renderQuickStart();
  renderExtensionSection();
  renderLiveSummary();
}

function toggleRailUtilities() {
  state.railUtilitiesOpen = !state.railUtilitiesOpen;
  queueFocus("#railUtilityToggle");
  renderStatus();
  updateWorkspaceVisibility();
  applyPendingFocus();
}

async function extractErrorDetail(response, fallbackMessage) {
  try {
    const payload = await response.clone().json();
    if (payload?.detail) {
      return String(payload.detail);
    }
    if (payload?.message) {
      return String(payload.message);
    }
  } catch {
    // noop
  }

  try {
    const text = (await response.text()).trim();
    if (text) {
      return text.length > 240 ? `${text.slice(0, 240)}…` : text;
    }
  } catch {
    // noop
  }

  return fallbackMessage;
}

function scheduleAddressPreview() {
  if (!state.bootstrap || !state.config) {
    return;
  }

  const currentHash = currentConfigHash();
  if (!currentHash || state.previewSummaryHash === currentHash || state.previewPendingHash === currentHash) {
    return;
  }

  const cabinetCfg = state.config.devices?.single_cabinet_aggregation || {};
  const cabinetEnabled = Boolean(cabinetCfg.enabled) && Number(cabinetCfg.cabinet_count || 0) > 0;
  const addressProfile = currentAddressProfile();
  if (!cabinetEnabled || addressProfile.cabinet_base != null) {
    state.previewAbortController?.abort();
    state.previewPendingHash = "";
    state.previewError = "";
    state.previewErrorHash = "";
    return;
  }

  state.previewPendingHash = currentHash;
  state.previewError = "";
  state.previewErrorHash = "";
  const requestId = ++state.previewRequestId;
  if (state.previewTimer) {
    window.clearTimeout(state.previewTimer);
  }
  state.previewAbortController?.abort();

  state.previewTimer = window.setTimeout(async () => {
    const controller = new AbortController();
    state.previewAbortController = controller;
    try {
      const response = await apiFetch("/api/preview-address-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: configForActiveMeasurementMode() }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await extractErrorDetail(response, `地址预览失败：${response.status}`));
      }
      const payload = await response.json();
      if (requestId !== state.previewRequestId) {
        return;
      }
      state.previewSummary = payload?.summary || null;
      state.previewSummaryHash = currentHash;
      state.previewPendingHash = "";
      state.previewError = "";
      state.previewErrorHash = "";
      renderPreviewDependentSections();
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      if (requestId !== state.previewRequestId) {
        return;
      }
      state.previewSummary = null;
      state.previewSummaryHash = "";
      state.previewPendingHash = "";
      state.previewError = error?.message || "地址预览失败";
      state.previewErrorHash = currentHash;
      renderPreviewDependentSections();
    } finally {
      if (state.previewAbortController === controller) {
        state.previewAbortController = null;
      }
    }
  }, 120);
}

function setActiveRoute(route, scrollIntoView = false) {
  state.activeRoute = route === "B" ? "B" : "A";
  ensureCollapsedSections();
  const targetKey = routeSectionKey(state.activeRoute);
  WORKFLOW_STEP_KEYS.forEach((stepKey) => {
    state.collapsedSections[stepKey] = stepKey !== targetKey;
  });
  state.activeStep = targetKey;
  WORKFLOW_STEP_KEYS.forEach((stepKey) => renderSectionByKey(stepKey));
  renderLiveSummary();
  updateWorkspaceVisibility();
  renderWorkflowSpine();
  renderMobileActionBar();
  if (scrollIntoView) {
    focusSectionByKey(targetKey, true);
  } else {
    applyPendingFocus();
  }
}

function syncBoundFieldsFromDom(root) {
  if (!(root instanceof Element)) {
    return;
  }
  root.querySelectorAll("[data-path]").forEach((target) => {
    const path = target.dataset.path;
    let value = target.type === "checkbox" ? target.checked : target.value;
    if (target.dataset.cast === "number") {
      value = Number(value || 0);
    } else if (target.dataset.cast === "optional-number") {
      value = value === "" ? null : Math.max(1, Number(value || 0));
    } else if (target.dataset.cast === "optional-text") {
      value = String(value || "").trim() || null;
    }
    if (target.dataset.transform === "names") {
      value = splitNames(value);
    }
    setByPath(state.config, path, value);
  });
  state.config = normalizeConfig(state.config);
}

function copyRouteSequence(source, target) {
  const sourceRoute = source === "B" ? "B" : "A";
  const targetRoute = target === "A" ? "A" : "B";
  syncBoundFieldsFromDom(document.getElementById(`routeSection${sourceRoute}`));
  Array.from({ length: screenColumnCount() }, (_, index) => index + 1).forEach((column) => {
    const deviceRoot = routeDeviceRoot(state.config, column);
    const sourceConfig = deviceRoot.plug_boxes[sourceRoute];
    const targetConfig = deviceRoot.plug_boxes[targetRoute];
    const sourceStart = deviceRoot.start_boxes[sourceRoute];
    const targetStart = deviceRoot.start_boxes[targetRoute];
    const scopeKey = routeScopeKey(targetRoute, column);
    if (measurementLayoutMode() === "by_branch") {
      const sourceModules = deviceRoot.branch_modules[sourceRoute];
      const targetModules = deviceRoot.branch_modules[targetRoute];
      targetModules.module_sequence = clone(sourceModules.module_sequence || []).map((item) =>
        normalizeModuleSequenceItem(item),
      );
      targetModules.variable_numbering_mode = normalizeBranchNumberingMode(sourceModules.variable_numbering_mode);
      targetModules.module_number_start = 1;
      targetModules.output_number_start = 1;
      targetModules.branch_device_number_start = routeDefaultBoxStart(targetRoute, column);
      targetModules.names = [];
    } else {
      targetConfig.sequence = clone(sourceConfig.sequence).map((item) => {
        const nextItem = { ...item };
        delete nextItem.box_number;
        delete nextItem.board_number_start;
        delete nextItem.box_name;
        delete nextItem.instance_name;
        return nextItem;
      });
      targetConfig.box_number_start = routeDefaultBoxStart(targetRoute, column);
      targetConfig.board_number_start = routeDefaultBoxStart(targetRoute, column);
    }
    targetStart.count = Number(sourceStart.count || 0);
    targetStart.instance_names = [];
    targetStart.device_code_start = routeDefaultStartCode(targetRoute, column);
    setRailSelection(targetRoute, 0, 0, false, column);
    state.railEditorOpen[scopeKey] = false;
    delete state.quickSequenceDrafts[scopeKey];
  });
  resetSequenceDetailState(targetRoute);

  state.config = normalizeConfig(state.config);
  ensureCollapsedSections();
  state.activeRoute = targetRoute;
  WORKFLOW_STEP_KEYS.forEach((stepKey) => {
    state.collapsedSections[stepKey] = stepKey !== routeSectionKey(targetRoute);
  });
  state.activeStep = routeSectionKey(targetRoute);
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(
    `已套用 ${sourceRoute} 路${screenColumnCount() === 2 ? "两列" : ""}结构到 ${targetRoute} 路，并按各列默认编号重排`,
    "success",
  );
  renderAll();
}

function setMessage(text, tone = "") {
  state.message = text;
  state.tone = tone;
  refs.messageBar.textContent = text;
  refs.messageBar.className = `message-bar${tone ? ` is-${tone}` : ""}`;
}

function renderStatus() {
  document.body.setAttribute("aria-busy", state.busy ? "true" : "false");
  if (refs.loadPresetBtn) {
    refs.loadPresetBtn.textContent = "重置默认参数";
  }
  if (refs.activeFamilyLabel) {
    refs.activeFamilyLabel.textContent = "项目协议 · 参数驱动生成";
  }
  const presentation = statusPresentation();
  if (refs.headerProjectName) {
    refs.headerProjectName.textContent = String(state.config?.project_name || "").trim() || "未命名项目";
    refs.headerProjectName.title = refs.headerProjectName.textContent;
  }
  refs.statusBadge.textContent = presentation.label;
  refs.statusBadge.className = `status-badge${presentation.badgeTone ? ` ${presentation.badgeTone}` : ""}`;
  refs.messageBar.textContent = presentation.message;
  refs.messageBar.title = presentation.message || "";
  refs.messageBar.className = `message-bar${presentation.messageTone ? ` is-${presentation.messageTone}` : ""}`;
  const generateBlockers = getGenerateBlockers({ includeDomDrafts: false });
  const dirtyRoutes = configuredRouteScopes().filter(({ route, column }) => isQuickSequenceDirty(route, column));
  refs.generateBtn.disabled = state.busy;
  refs.generateBtn.textContent = state.busy
    ? "生成中…"
    : dirtyRoutes.length
      ? "应用清单并生成三份文件"
      : generateBlockers.length
        ? generateBlockers[0].buttonLabel
        : state.result
          ? "重新生成三份交付文件"
          : "生成三份交付文件";
  if (refs.railUtilityToggle) {
    refs.railUtilityToggle.textContent = state.railUtilitiesOpen ? "收起" : "更多";
    refs.railUtilityToggle.setAttribute("aria-expanded", state.railUtilitiesOpen ? "true" : "false");
  }
  refs.railUtilityMenu?.setAttribute("aria-hidden", state.railUtilitiesOpen ? "false" : "true");
  if (refs.recoverDraftBtn) {
    refs.recoverDraftBtn.hidden = !state.savedDraft;
    if (state.savedDraftMeta?.project_name || state.savedDraftMeta?.saved_at_label) {
      refs.recoverDraftBtn.title = [state.savedDraftMeta.project_name, state.savedDraftMeta.saved_at_label]
        .filter(Boolean)
        .join(" · ");
    }
  }
  if (state.config) {
    renderMobileActionBar();
  }
}

function scenarioSwitchMarkup(extraClass = "", options = {}) {
  const activeScenarioKey = currentScenarioKey();
  const showMeta = options.showMeta !== false;
  return scenarioOptions()
    .map((scenario) => {
      const classes = ["family-chip", "family-chip--scenario", extraClass];
      if (scenario.id === activeScenarioKey) {
        classes.push("is-active");
      }
      return `
        <button
          class="${classes.filter(Boolean).join(" ")}"
          type="button"
          data-action="switch-scenario"
          data-scenario="${scenario.id}"
          aria-pressed="${scenario.id === activeScenarioKey ? "true" : "false"}"
          title="${escapeHtml(scenario.usage_hint || scenario.meta || scenario.label)}"
        >
          <span class="family-chip__title">${escapeHtml(scenario.label)}</span>
          ${showMeta ? `<span class="family-chip__meta">${escapeHtml(scenario.meta || scenario.usage_hint || "")}</span>` : ""}
        </button>
      `;
    })
    .join("");
}

function renderFamilySwitch() {
  if (!refs.familySwitch) {
    return;
  }
  refs.familySwitch.setAttribute("role", "group");
  refs.familySwitch.setAttribute("aria-label", "常用出表场景");
  refs.familySwitch.innerHTML = scenarioSwitchMarkup();
}

function renderScreenModeChooser() {
  const currentMode = state.config.topology.screen_topology_mode;
  const options = [
    {
      value: SCREEN_MODE_SINGLE,
      title: "单屏单列",
      note: "一列机柜 · A/B 两路",
      columns: [["A", "B"]],
    },
    {
      value: SCREEN_MODE_DOUBLE,
      title: "单屏双列",
      note: "第一列 A/B + 第二列 A/B",
      columns: [["A", "B"], ["A", "B"]],
    },
  ];
  return `
    <div class="screen-mode-field" role="group" aria-labelledby="screen-mode-label">
      <div class="screen-mode-field__label" id="screen-mode-label">屏内机柜列数</div>
      <div class="screen-mode-options">
        ${options.map((option) => `
          <button
            class="screen-mode-card ${currentMode === option.value ? "is-active" : ""}"
            type="button"
            data-action="set-screen-topology"
            data-mode="${option.value}"
            aria-pressed="${currentMode === option.value ? "true" : "false"}"
          >
            <span class="screen-mode-card__diagram" aria-hidden="true">
              ${option.columns.map((routes, columnIndex) => `
                <span class="screen-column-mini"><em>${option.columns.length > 1 ? `列 ${columnIndex + 1}` : "一列"}</em><span>${routes.map((route) => `<i class="is-route-${route.toLowerCase()}">${route}</i>`).join("")}</span></span>
              `).join("")}
            </span>
            <span><strong>${option.title}</strong><small>${option.note}</small></span>
            <i class="screen-mode-check" aria-hidden="true">✓</i>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderQuickStart() {
  if (!refs.quickStartSection) {
    return;
  }
  const projectName = String(state.config.project_name || "").trim();
  const projectCode = String(state.config.project_code || "").trim();
  const collapsed = isSectionCollapsed("quickStart");
  setSectionVisualState(refs.quickStartSection, collapsed, "overview");
  const summary = `<span>${escapeHtml(projectName || "项目待填写")}</span><span>${escapeHtml(projectCode || "编号待填写")}</span>`;
  refs.quickStartSection.innerHTML = `
    ${renderSectionHead("项目信息", "先确定项目与点位组织方式", "", {
      sectionKey: "quickStart",
      summary,
      collapsed,
    })}
    ${collapsed ? "" : `
      <div class="step-body">
        ${state.openedRunMeta ? `<div class="alert-panel is-working"><strong>正在查看历史结果</strong><p>${escapeHtml(state.openedRunMeta.project_name || state.openedRunMeta.run_id || "历史结果")}</p></div>` : ""}
        <div class="quick-start-form quick-form-shell quick-form-shell--intake">
          ${spanWrap(
            textField("项目名称", "project_name", state.config.project_name, {
              autocomplete: "organization",
              fieldId: "quick-project-name",
              placeholder: "例如：示例数据中心A区",
              required: true,
            }),
            6,
          )}
          ${spanWrap(
            textField("项目编号", "project_code", state.config.project_code, {
              fieldId: "quick-project-code",
              placeholder: "例如：GZ-MCGS-001",
              required: true,
            }),
            6,
          )}
          ${spanWrap(
            textField("协议标题", "protocol_title", state.config.protocol_title, {
              fieldId: "project-protocol-title",
              placeholder: "上位机通讯协议",
            }),
            6,
          )}
          ${spanWrap(
            selectField(
              "点位组织",
              "protocol_layout.measurement_layout_mode",
              state.config.protocol_layout.measurement_layout_mode,
              [
                {
                  value: "by_plug_box",
                  label: "按插接箱",
                  help_text: "始端箱、插接箱和单机柜数据汇入同一主表，插接箱作为设备分组。",
                },
                {
                  value: "by_branch",
                  label: "按监控模块",
                  help_text: "按监控模块、板卡布局动态展开实际输出分路；通讯报警按模块，遥测与模拟量报警按分路。",
                },
              ],
              "value",
              { fieldId: "measurement-layout-mode" },
            ),
            6,
          )}
          ${spanWrap(renderScreenModeChooser(), 12, "screen-mode-span")}
        </div>
        <div class="step-actions">
          <button class="button button--primary" type="button" data-action="jump-section" data-section="routeA">继续到 A 路</button>
          <button class="button button--ghost" type="button" data-action="open-drawer" data-drawer="communication">高级设置</button>
        </div>
      </div>
    `}
  `;
}

function renderSummaryStrip() {
  if (!refs.summaryStrip) {
    return;
  }
  refs.summaryStrip.innerHTML = "";
}

function renderSectionHead(title, note, tools = "", options = {}) {
  const actionGroup = [];
  const showCollapsedMeta = Boolean(options.keepMetaWhenCollapsed);
  const showNote = Boolean(note) && (!options.collapsed || showCollapsedMeta);
  const showSummary =
    Boolean(options.summary) && (Boolean(options.showSummaryWhenExpanded) || options.collapsed || showCollapsedMeta);
  if (tools) {
    actionGroup.push(tools);
  }
  if (options.sectionKey) {
    const controlsId = sectionDomIdByKey(options.sectionKey) || options.sectionKey;
    if (!WORKFLOW_STEP_KEYS.includes(options.sectionKey) || options.collapsed) {
      actionGroup.push(
        `<button class="section-tool section-tool--quiet" type="button" data-action="toggle-section" data-section="${options.sectionKey}" aria-expanded="${options.collapsed ? "false" : "true"}" aria-controls="${controlsId}">${options.collapsed ? "编辑" : "收起"}</button>`,
      );
    }
  }
  return `
    <div class="section-head">
      <div class="section-head__main">
        <h2 class="section-title">${escapeHtml(title)}</h2>
        ${showNote ? `<p class="section-note">${escapeHtml(note)}</p>` : ""}
      </div>
      <div class="section-head__aside">
        ${showSummary ? `<div class="section-summary">${options.summary}</div>` : ""}
        ${actionGroup.length ? `<div class="section-tools">${actionGroup.join("")}</div>` : ""}
      </div>
    </div>
  `;
}

function spanWrap(content, span = 4, extraClass = "") {
  const classes = ["field-span", `span-${span}`, extraClass].filter(Boolean).join(" ");
  return `<div class="${classes}">${content}</div>`;
}

function textField(label, path, value, options = {}) {
  const fieldId = options.fieldId || path;
  const placeholder = options.placeholder || "";
  const transformAttr = options.transform ? ` data-transform="${options.transform}"` : "";
  const autocomplete = options.autocomplete || "off";
  const requiredAttr = options.required ? ' required aria-required="true"' : "";
  return `
    <div class="field">
      <label for="${escapeHtml(fieldId)}">${escapeHtml(label)}</label>
      <input
        id="${escapeHtml(fieldId)}"
        name="${escapeHtml(fieldId)}"
        type="text"
        data-path="${escapeHtml(path)}"
        value="${escapeHtml(value ?? "")}"
        placeholder="${escapeHtml(placeholder)}"
        autocomplete="${escapeHtml(autocomplete)}"
        ${transformAttr}${requiredAttr}
      />
    </div>
  `;
}

function numberField(label, path, value, min = 0, options = {}) {
  const fieldId = options.fieldId || path;
  const maxAttr = Number.isFinite(options.max) ? ` max="${Number(options.max)}"` : "";
  return `
    <div class="field">
      <label for="${escapeHtml(fieldId)}">${escapeHtml(label)}</label>
      <input
        id="${escapeHtml(fieldId)}"
        name="${escapeHtml(fieldId)}"
        type="number"
        min="${min}"
        ${maxAttr}
        step="1"
        inputmode="numeric"
        data-path="${escapeHtml(path)}"
        data-cast="number"
        value="${escapeHtml(value ?? 0)}"
        autocomplete="off"
      />
    </div>
  `;
}

function selectField(label, path, value, options, idKey = "id", fieldOptions = {}) {
  const safeOptions = Array.isArray(options) ? options : [];
  const selectedOption = safeOptions.find((option) => option[idKey] === value);
  const selectedLabel = selectedOption?.short_label || optionLabel(selectedOption) || value || label;
  const supportNote = optionSupportNote(selectedOption);
  const fieldId = fieldOptions.fieldId || path;
  const showOptionHints = Boolean(fieldOptions.showOptionHints);
  const showFieldHelp = Boolean(fieldOptions.showFieldHelp);
  return `
    <div class="field field--select">
      <label for="${escapeHtml(fieldId)}">${escapeHtml(label)}</label>
      <select
        id="${escapeHtml(fieldId)}"
        name="${escapeHtml(fieldId)}"
        data-path="${escapeHtml(path)}"
        title="${escapeHtml([selectedLabel, supportNote].filter(Boolean).join("｜"))}"
      >
        ${safeOptions
          .map((option) => {
            const optionId = option[idKey];
            const optionSupport = optionSupportNote(option);
            const optionTextLabel = showOptionHints && optionSupport
              ? `${optionLabel(option)}｜${compactOptionSupportNote(optionSupport)}`
              : optionLabel(option);
            return `
              <option value="${escapeHtml(optionId)}" ${optionId === value ? "selected" : ""}>
                ${escapeHtml(optionTextLabel)}
              </option>
            `;
          })
          .join("")}
      </select>
      ${
        showFieldHelp && selectedOption
          ? `<div class="field-help">
               <span>${escapeHtml(selectedLabel)}</span>
               ${supportNote ? `<em>${escapeHtml(supportNote)}</em>` : ""}
              </div>`
          : ""
      }
    </div>
  `;
}

function renderProjectSection() {
  const collapsed = isSectionCollapsed("project");
  setSectionVisualState(refs.projectSection, collapsed, "project");
  const routeA = routeReviewPresentation("A");
  const routeB = routeReviewPresentation("B");
  const extensions = currentExtensions();
  const warnings = computeWarnings();
  const blockers = getGenerateBlockers({ includeDomDrafts: false });
  const files = expectedDeliveryFileNames();
  const sheets = expectedSheetOrder();
  const hardwareLabel = currentHardwareForm()?.label || state.config.topology.hardware_form_factor;
  const environmentPort = state.config.topology.environment_rs485_port;
  const enabledExtensions = [
    extensions.single_cabinet?.enabled
      ? screenColumnCount() === 2
        ? `单机柜 第一列 ${formatNumber(singleCabinetColumnCount(1, extensions))} / 第二列 ${formatNumber(singleCabinetColumnCount(2, extensions))}`
        : `单机柜 ${formatNumber(singleCabinetColumnCount(1, extensions))} 个`
      : "",
    extensions.repeater?.enabled
      ? screenColumnCount() === 2
        ? `中继 第一列 A${formatNumber(repeaterColumnCount(1, "A", extensions))}/B${formatNumber(repeaterColumnCount(1, "B", extensions))} · 第二列 A${formatNumber(repeaterColumnCount(2, "A", extensions))}/B${formatNumber(repeaterColumnCount(2, "B", extensions))}`
        : `中继 A ${formatNumber(repeaterColumnCount(1, "A", extensions))} / B ${formatNumber(repeaterColumnCount(1, "B", extensions))}`
      : "",
    extensions.alarm_state_word?.enabled
      ? `报警状态字 ${formatNumber(extensions.alarm_state_word.base_address)} / ${extensions.alarm_state_word.word_mode}${extensions.alarm_state_word.legacy_slide_rail_order ? " · 旧滑轨顺序" : ""}`
      : "",
  ].filter(Boolean);
  const summary = `
    <span>${escapeHtml(state.config.project_name || "项目待填写")}</span>
    <span>${blockers.length ? `${formatNumber(blockers.length)} 项待完善` : "参数可生成"}</span>
  `;
  refs.projectSection.innerHTML = `
    ${renderSectionHead("复核", "确认后即可生成", "", {
      sectionKey: "project",
      summary,
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="parameter-review step-body">
            <div class="review-list">
              <div class="review-row">
                <div><span>项目</span><strong>${escapeHtml(`${state.config.project_name || "待填写"} · ${state.config.project_code || "待填写编号"}`)}</strong><em>${escapeHtml(measurementLayoutMode() === "by_branch" ? "按监控模块" : "按插接箱")}</em></div>
                <button class="section-tool" type="button" data-action="jump-section" data-section="quickStart">修改</button>
              </div>
              <div class="review-row review-row--a">
                <div><span>A 路</span><strong>${escapeHtml(routeA.headline)}</strong><em>${escapeHtml(routeA.detail)}</em></div>
                <button class="section-tool" type="button" data-action="jump-section" data-section="routeA">修改</button>
              </div>
              <div class="review-row review-row--b">
                <div><span>B 路</span><strong>${escapeHtml(routeB.headline)}</strong><em>${escapeHtml(routeB.detail)}</em></div>
                <button class="section-tool" type="button" data-action="jump-section" data-section="routeB">修改</button>
              </div>
              <div class="review-row">
                <div><span>扩展</span><strong>${escapeHtml(enabledExtensions.join("；") || "未启用")}</strong><em>${formatNumber(sheets.length)} 个页签</em></div>
                <button class="section-tool" type="button" data-action="jump-section" data-section="extension">修改</button>
              </div>
              <div class="review-row">
                <div><span>通讯与端口</span><strong>${escapeHtml(`${state.config.communication.protocol} · ${formatNumber(state.config.communication.baud_rate)} · ${hardwareLabel}`)}</strong><em>${escapeHtml(`动环 ${environmentPort}；母线 ${busDataPortSummary()}`)}</em></div>
                <button class="section-tool" type="button" data-action="open-drawer" data-drawer="communication">修改</button>
              </div>
            </div>
            ${blockers.length ? `<div class="warning-list parameter-review__warnings">${blockers.map((item) => `<div class="warning-item">${escapeHtml(item.message)}</div>`).join("")}</div>` : ""}
            ${warnings.length ? `<div class="warning-list parameter-review__warnings">${warnings.map((item) => `<div class="warning-item">${escapeHtml(item)}</div>`).join("")}</div>` : ""}
            <div class="delivery-manifest" aria-label="将生成的三个文件">
              <div><span>Excel</span><strong>${escapeHtml(files.excel)}</strong></div>
              <div><span>代码</span><strong>${escapeHtml(files.alarm)}</strong></div>
              <div><span>CSV</span><strong>${escapeHtml(files.program)}</strong></div>
            </div>
            <div class="step-actions parameter-review__actions">
              <button class="button button--primary" type="button" data-action="quick-generate" ${state.busy ? "disabled" : ""}>${state.busy ? "正在生成…" : "生成三份文件"}</button>
            </div>
          </div>`
    }
  `;
}

function renderTopologySection() {
  const collapsed = isSectionCollapsed("topology");
  setSectionVisualState(refs.topologySection, collapsed, "topology");
  const assignments = state.config.topology.bus_data_port_assignments || {};
  const dataPortOptions = availablePhysicalPortOptions({ excludeEnvironment: true });
  const assignmentFields = busDataAssignmentDescriptors().map((item) => spanWrap(
    selectField(
      item.label,
      `topology.bus_data_port_assignments.${item.key}`,
      assignments[item.key],
      dataPortOptions,
      "value",
      { fieldId: `bus-data-port-${item.key}` },
    ),
    busDataAssignmentDescriptors().length > 1 ? 6 : 12,
  )).join("");
  refs.topologySection.innerHTML = `
    ${renderSectionHead("通讯与屏后端口", "先选设备形态，再分配动环上传口与母线数据接入口", "", {
      sectionKey: "topology",
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="port-topology-panel">
            <section class="port-topology-block">
              <div class="port-topology-block__head"><span>01</span><div><strong>设备形态</strong><small>决定屏后实际存在的三个物理口</small></div></div>
              ${renderHardwareFormChooser()}
            </section>
            <section class="port-topology-block">
              <div class="port-topology-block__head"><span>02</span><div><strong>动环 RS-485 上传口</strong><small>只占一个物理口，用于把协议数据上传给动环平台</small></div></div>
              <div class="port-assignment-grid field-grid">
                ${spanWrap(selectField(
                  "动环 RS-485 上传口",
                  "topology.environment_rs485_port",
                  state.config.topology.environment_rs485_port,
                  availablePhysicalPortOptions(),
                  "value",
                  { fieldId: "environment-rs485-port" },
                ), 12)}
              </div>
            </section>
            <section class="port-topology-block">
              <div class="port-topology-block__head"><span>03</span><div><strong>母线数据接入</strong><small>${escapeHtml(screenColumnCount() === 2 ? "按两列的实际接线选择分组方式" : "选择 A/B 共口或分口")}</small></div></div>
              ${renderBusDataModeChooser()}
              <div class="port-assignment-grid field-grid">${assignmentFields}</div>
            </section>
            <section class="port-topology-block port-topology-block--map">
              <div class="port-topology-block__head"><span>04</span><div><strong>当前端口占用</strong><small>${escapeHtml(currentHardwareForm()?.help_text || "")}</small></div></div>
              ${renderPhysicalPortMap()}
              <p class="port-topology-note">动环上传口与母线数据口按独立物理接口分配；未使用的接口会标记为空闲。</p>
            </section>
          </div>
          <details class="communication-advanced">
            <summary>通讯协议与地址参数</summary>
            <div class="field-grid">
              ${spanWrap(textField("参考列号", "topology.canonical_column_id", state.config.topology.canonical_column_id), 4)}
              ${spanWrap(textField("协议", "communication.protocol", state.config.communication.protocol), 8)}
              ${spanWrap(numberField("波特率", "communication.baud_rate", state.config.communication.baud_rate, 300), 3)}
              ${spanWrap(textField("校验位", "communication.parity", state.config.communication.parity), 3)}
              ${spanWrap(numberField("数据位", "communication.data_bits", state.config.communication.data_bits, 1), 3)}
              ${spanWrap(numberField("停止位", "communication.stop_bits", state.config.communication.stop_bits, 1), 3)}
              ${spanWrap(numberField("默认屏地址", "communication.default_screen_address", state.config.communication.default_screen_address, 1), 4)}
              ${spanWrap(numberField("始端箱主数据基址", "protocol_layout.main_base_address", state.config.protocol_layout.main_base_address, 0), 4)}
              ${measurementLayoutMode() === "by_branch" ? `
                ${spanWrap(numberField("输出分路主地址基址", "protocol_layout.downstream_base_address", state.config.protocol_layout.downstream_base_address, 0), 4)}
                ${spanWrap(numberField("每路主地址段分路数", "protocol_layout.downstream_primary_outputs_per_route", state.config.protocol_layout.downstream_primary_outputs_per_route, 1), 4)}
                ${spanWrap(numberField("扩展分路地址基址", "protocol_layout.downstream_extension_base_address", state.config.protocol_layout.downstream_extension_base_address, 0), 4)}
              ` : ""}
            </div>
          </details>`
    }
  `;
}

function renderProfilesSection() {
  const family = state.activeFamily;
  const baselinePreset = currentBaselinePreset();
  const exportOptions = contextualizeExportOptions(state.bootstrap.families[family].export_profiles, baselinePreset);
  const addressOptions = contextualizeAddressOptions(state.bootstrap.families[family].address_profiles, baselinePreset);
  const templates = state.bootstrap.templates;
  const startTemplateOptions = contextualizeTemplateOptions(
    templates.start_box_templates,
    baselinePreset.start_box_template_id,
  );
  const plugTemplateOptions = contextualizeTemplateOptions(
    templates.plug_branch_templates,
    baselinePreset.plug_branch_template_id,
  );
  const repeaterTemplateOptions = contextualizeTemplateOptions(
    templates.repeater_templates,
    baselinePreset.repeater_template_id,
  );
  const cabinetTemplateOptions = contextualizeTemplateOptions(
    templates.single_cabinet_templates,
    baselinePreset.single_cabinet_template_id,
  );
  const recommendation = state.recommendation;
  const collapsed = isSectionCollapsed("profiles");
  setSectionVisualState(refs.profilesSection, collapsed, "profiles");
  const tools = `
    <button
      class="section-tool"
      type="button"
      data-action="recommend-profiles"
      ${state.recommendationBusy ? "disabled" : ""}
    >
      ${state.recommendationBusy ? "匹配中…" : recommendation ? "重新匹配" : "自动匹配"}
    </button>
  `;
  const recommendedLabels = recommendation?.recommended_profile_labels || {};
  const recommendedTemplatePlan = recommendation?.recommended_template_plan || {};
  const recommendedPatchSummary =
    Array.isArray(recommendedTemplatePlan.patch_labels) && recommendedTemplatePlan.patch_labels.length
      ? recommendedTemplatePlan.patch_labels.join("；")
      : "-";
  const selectedExport = exportOptions.find((item) => item.id === state.config.profiles.export_profile_id);
  const selectedAddress = addressOptions.find((item) => item.id === state.config.profiles.address_profile_id);
  const selectedStart = optionById(startTemplateOptions, state.config.profiles.start_box_template_id);
  const selectedPlug = optionById(plugTemplateOptions, state.config.profiles.plug_branch_template_id);
  const selectedRepeater = optionById(repeaterTemplateOptions, state.config.profiles.repeater_template_id);
  const selectedCabinet = optionById(cabinetTemplateOptions, state.config.profiles.single_cabinet_template_id);
  const exportSummary = compactSummaryText(selectedExport?.label || state.config.profiles.export_profile_id, 18);
  const addressSummary = compactSummaryText(selectedAddress?.label || state.config.profiles.address_profile_id, 24);
  const profileCards = [
    {
      label: "当前采用的 Excel 页面结构",
      title: selectedExport?.short_label || selectedExport?.label || "按方案自动带出",
      note: optionSupportNote(selectedExport) || "常规项目一般不用改。",
    },
    {
      label: "关键地址排布",
      title: selectedAddress?.short_label || selectedAddress?.label || "-",
      note: optionSupportNote(selectedAddress) || "常规项目一般不用改。",
    },
    {
      label: "始端箱采集项",
      title: selectedStart?.short_label || selectedStart?.label || "-",
      note: optionSupportNote(selectedStart) || "需要改单点监测项时再展开。",
    },
    {
      label: "插接箱采集项",
      title: selectedPlug?.short_label || selectedPlug?.label || "-",
      note: optionSupportNote(selectedPlug) || "需要改单点监测项时再展开。",
    },
    {
      label: "中继采集项",
      title: selectedRepeater?.short_label || selectedRepeater?.label || "-",
      note: optionSupportNote(selectedRepeater) || "只在启用中继时生效。",
    },
    {
      label: "单机柜采集项",
      title: selectedCabinet?.short_label || selectedCabinet?.label || "-",
      note: optionSupportNote(selectedCabinet) || "只在启用单机柜聚合时生效。",
    },
  ];
  const recommendationMarkup = recommendation
    ? `
      <div class="recommend-card">
        <div class="recommend-card__top">
          <div>
            <h3>${escapeHtml(recommendation.recommended_family_label || FAMILY_LABELS[recommendation.recommended_family] || recommendation.recommended_family || "-")}</h3>
            <div class="muted-note">${escapeHtml((recommendation.reasons || []).slice(0, 1).join("；") || "已按当前配置匹配。")}</div>
          </div>
          <div class="pill-row">
            <span class="status-pill ${confidenceClass(recommendation.confidence)}">${escapeHtml(confidenceLabel(recommendation.confidence))}</span>
            <span class="status-pill">${escapeHtml(recommendation.current_family_label || FAMILY_LABELS[recommendation.current_family] || recommendation.current_family || "当前方案")}</span>
          </div>
        </div>
        <div class="recommend-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
          <div class="recommend-card__group">
            <div class="recommend-card__title">建议主配置</div>
            <div class="summary-list">
              <div class="summary-row"><span>渲染变体</span><strong>${escapeHtml(recommendation.recommended_render_variant_id || "-")}</strong></div>
              <div class="summary-row"><span>Excel 样式</span><strong>${escapeHtml(recommendedLabels.export_profile_id || recommendation.recommended_profile_ids?.export_profile_id || "-")}</strong></div>
              <div class="summary-row"><span>活动区 / patch</span><strong>${escapeHtml(recommendedPatchSummary)}</strong></div>
              <div class="summary-row"><span>地址方案</span><strong>${escapeHtml(recommendedLabels.address_profile_id || recommendation.recommended_profile_ids?.address_profile_id || "-")}</strong></div>
              <div class="summary-row"><span>始端箱样式</span><strong>${escapeHtml(recommendedLabels.start_box_template_id || recommendation.recommended_profile_ids?.start_box_template_id || "-")}</strong></div>
              <div class="summary-row"><span>插接箱样式</span><strong>${escapeHtml(recommendedLabels.plug_branch_template_id || recommendation.recommended_profile_ids?.plug_branch_template_id || "-")}</strong></div>
            </div>
          </div>
          <div class="recommend-card__group">
            <div class="recommend-card__title">将发生的调整</div>
            ${
              Array.isArray(recommendation?.changes) && recommendation.changes.length
                ? `<ul class="change-list">
                    ${recommendation.changes
                      .slice(0, 4)
                      .map(
                        (item) => `
                          <li>
                            <span>${escapeHtml(item.field)}</span>
                            <strong>${escapeHtml(String(item.from ?? "当前值"))}</strong>
                            <span>→</span>
                            <strong>${escapeHtml(String(item.to ?? "推荐值"))}</strong>
                          </li>
                        `,
                      )
                      .join("")}
                  </ul>`
                : `<div class="muted-note">当前已经比较合适，不需要调整。</div>`
            }
          </div>
        </div>
        <div class="recommend-card__footer">
          ${
            recommendation.changes?.length
              ? `<button class="button button--primary" type="button" data-action="apply-recommendation">应用推荐</button>`
              : ""
          }
        </div>
      </div>
    `
    : "";
  refs.profilesSection.innerHTML = `
    ${renderSectionHead("模板与地址", "特殊项目再改", tools, {
      sectionKey: "profiles",
      summary: `<span>导出 ${escapeHtml(exportSummary)}</span><span>地址 ${escapeHtml(addressSummary)}</span>`,
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="field-grid">
              ${spanWrap(
                selectField(
                  "Excel 页面结构",
                 "profiles.export_profile_id",
                 state.config.profiles.export_profile_id,
                 exportOptions,
                  "id",
                  {},
                ),
                6,
              )}
             ${spanWrap(
                selectField(
                  "地址方案",
                  "profiles.address_profile_id",
                  state.config.profiles.address_profile_id,
                  addressOptions,
                  "id",
                  {},
                ),
                6,
              )}
            </div>
            <details class="artifact-debug artifact-debug--panel" style="margin-top: 16px;">
              <summary>
                <span>模板细项</span>
                <em>需要时再展开</em>
              </summary>
             <div class="field-grid" style="margin-top: 16px;">
                ${spanWrap(
                 selectField(
                    "始端箱采集项",
                    "profiles.start_box_template_id",
                    state.config.profiles.start_box_template_id,
                    startTemplateOptions.map((item) => ({
                     ...item,
                     label: item.label,
                   })),
                    "id",
                    {},
                 ),
                 6,
               )}
                ${spanWrap(
                  selectField(
                    "插接箱采集项",
                    "profiles.plug_branch_template_id",
                    state.config.profiles.plug_branch_template_id,
                    plugTemplateOptions.map((item) => ({
                     ...item,
                     label: item.label,
                   })),
                    "id",
                    {},
                 ),
                 6,
               )}
                ${spanWrap(
                  selectField(
                    "中继采集项",
                    "profiles.repeater_template_id",
                    state.config.profiles.repeater_template_id,
                    repeaterTemplateOptions.map((item) => ({
                     ...item,
                     label: item.label,
                   })),
                    "id",
                    {},
                 ),
                 6,
               )}
                ${spanWrap(
                  selectField(
                    "单机柜采集项",
                    "profiles.single_cabinet_template_id",
                    state.config.profiles.single_cabinet_template_id,
                    cabinetTemplateOptions.map((item) => ({
                     ...item,
                     label: item.label,
                   })),
                    "id",
                    {},
                 ),
                 6,
               )}
            </div>
          </details>
          ${recommendationMarkup}`
    }
  `;
}

function routeColumnTotals(route, column = 1) {
  const deviceRoot = routeDeviceRoot(state.config, column);
  if (measurementLayoutMode() === "by_branch") {
    const moduleConfig = deviceRoot.branch_modules?.[route] || {};
    const totals = (moduleConfig.module_sequence || []).reduce(
      (summary, rawItem) => {
        const item = normalizeModuleSequenceItem(rawItem);
        const layout = layoutOption(item.type_code, item.layout_pattern);
        const count = Math.max(1, Number(item.count || 1));
        const boardCount = Number(layout?.board_count || 0);
        const outputCount = Number(layout?.branch_count || 0);
        const templateId = item.branch_template_id || state.config.profiles.plug_branch_template_id;
        const allocationCount = pointsetAllocationCount(layout, templateId);
        const template = templateOption("plug_branch_templates", templateId);
        summary.modules += count;
        summary.boards += count * boardCount;
        summary.branches += count * outputCount;
        summary.allocations += count * allocationCount;
        summary.points += count * allocationCount * Number(template?.point_count || 0);
        summary.registers += count * allocationCount * Number(template?.register_footprint || 0);
        return summary;
      },
      { modules: 0, boards: 0, branches: 0, allocations: 0, points: 0, registers: 0 },
    );
    return {
      physicalBoxes: 0,
      ...totals,
    };
  }
  const routeConfig = deviceRoot.plug_boxes[route];
  let physicalBoxes = 0;
  let boards = 0;
  let branches = 0;
  routeConfig.sequence.forEach((item) => {
    const boxType = state.maps.boxTypes[item.type_code];
    const layout = boxType.allowed_layout_patterns.find(
      (entry) => entry.pattern === item.layout_pattern,
    );
    physicalBoxes += 1;
    boards += Number(layout?.board_count || 0);
    branches += Number(layout?.branch_count || 0);
  });
  return { physicalBoxes, boards, branches, modules: 0, allocations: branches, points: 0, registers: 0 };
}

function routeTotals(route) {
  const empty = { physicalBoxes: 0, boards: 0, branches: 0, modules: 0, allocations: 0, points: 0, registers: 0 };
  return Array.from({ length: screenColumnCount() }, (_, index) => routeColumnTotals(route, index + 1))
    .reduce((total, item) => {
      Object.keys(total).forEach((key) => {
        total[key] += Number(item[key] || 0);
      });
      return total;
    }, empty);
}

function routePresentation(route) {
  const totals = routeTotals(route);
  if (measurementLayoutMode() === "by_branch") {
    return {
      route,
      summary: `${formatNumber(totals.modules)} 模块 / ${formatNumber(totals.branches)} 输出分路`,
      metrics: [
        { label: "监控模块", value: formatNumber(totals.modules) },
        { label: "板卡", value: formatNumber(totals.boards) },
        { label: "输出分路", value: formatNumber(totals.branches) },
        { label: "遥测点位", value: formatNumber(totals.points) },
      ],
    };
  }
  return {
    route,
    summary: `${formatNumber(totals.physicalBoxes)} 箱 / ${formatNumber(totals.boards)} 板 / ${formatNumber(totals.branches)} 回路`,
    metrics: [
      { label: "插接箱", value: formatNumber(totals.physicalBoxes) },
      { label: "板卡", value: formatNumber(totals.boards) },
      { label: "回路", value: formatNumber(totals.branches) },
    ],
  };
}

function routeReviewPresentation(route) {
  const isBranchMode = measurementLayoutMode() === "by_branch";
  const deviceNoun = isBranchMode ? "监控模块" : "插接箱";
  let startBoxCount = 0;
  const deviceLabels = [];
  Array.from({ length: screenColumnCount() }, (_, index) => index + 1).forEach((column) => {
    const deviceRoot = routeDeviceRoot(state.config, column);
    startBoxCount += Number(deviceRoot.start_boxes?.[route]?.count || 0);
    const columnPrefix = screenColumnCount() === 2
      ? `${column === 1 ? "第一列" : "第二列"} · `
      : "";
    const instances = isBranchMode
      ? resolvedModuleInstances(route, column)
      : resolvedPlugInstances(route, column);
    instances.forEach((instance) => {
      const typeLabel = instance.boxType?.short_label || instance.item?.type_code || "未标类型";
      const deviceName = isBranchMode
        ? `${formatNumber(instance.moduleNo)}#监控模块`
        : `${instance.entry?.box_name || instance.entry?.box_number}插接箱`;
      deviceLabels.push(`${columnPrefix}[${typeLabel}] ${deviceName}`);
    });
  });
  return {
    headline: `${formatNumber(startBoxCount)} 个始端箱 + ${formatNumber(deviceLabels.length)} 个${deviceNoun}`,
    detail: deviceLabels.join("；") || `未配置${deviceNoun}`,
  };
}

function resolvedSequenceItems(route, column = activeColumnForRoute(route)) {
  const routeConfig = routeDeviceRoot(state.config, column).plug_boxes[route];
  const sequence = routeConfig?.sequence || [];
  let nextBoxNumber = Math.max(1, Number(routeConfig?.box_number_start || routeDefaultBoxStart(route, column)));
  let nextBoardNumber = Math.max(
    1,
    Number(routeConfig?.board_number_start || routeDefaultBoxStart(route, column)),
  );
  return sequence.map((item) => {
    const layout = layoutOption(item.type_code, item.layout_pattern);
    const boardCount = Math.max(1, Number(layout?.board_count || 0));
    const explicitBoxNumber =
      item?.box_number != null && item.box_number !== ""
        ? Math.max(1, Number(item.box_number))
        : item?.board_number_start != null && item.board_number_start !== ""
          ? Math.max(1, Number(item.board_number_start))
          : null;
    const explicitBoardNumber =
      item?.board_number_start != null && item.board_number_start !== ""
        ? Math.max(1, Number(item.board_number_start))
        : null;
    const explicitBoxName = String(item?.box_name || item?.instance_name || "").trim() || "";
    const resolvedBoxNumber = explicitBoxNumber ?? nextBoxNumber;
    const resolvedBoardNumber = explicitBoardNumber ?? explicitBoxNumber ?? nextBoardNumber;
    nextBoxNumber = resolvedBoxNumber + 1;
    nextBoardNumber = resolvedBoardNumber + boardCount;
    return {
      item,
      layout,
      explicit_box_number: explicitBoxNumber,
      explicit_board_number: explicitBoardNumber,
      explicit_box_name: explicitBoxName,
      box_number: resolvedBoxNumber,
      box_name: explicitBoxName || String(resolvedBoxNumber),
      board_number_start: resolvedBoardNumber,
      board_count: boardCount,
      branch_count: Math.max(0, Number(layout?.branch_count || 0)),
    };
  });
}

function currentAddressProfile() {
  return state.maps.addressProfiles[state.config.profiles.address_profile_id] || {};
}

function currentExtensions() {
  return state.config.extensions || {
    repeater: state.config.devices.repeater_units,
    single_cabinet: state.config.devices.single_cabinet_aggregation,
    alarm_state_word: {
      enabled: true,
      base_address: currentAddressProfile().alarm_base ?? 6000,
      word_mode: currentAddressProfile().alarm_word_mode || "16bit",
      legacy_slide_rail_order: false,
    },
  };
}

function routeIsConfigured(route) {
  const totals = routeTotals(route);
  return measurementLayoutMode() === "by_branch"
    ? totals.modules > 0
    : totals.physicalBoxes > 0;
}

function workflowStepDefinitions() {
  const identityReady = Boolean(
    String(state.config?.project_name || "").trim() && String(state.config?.project_code || "").trim(),
  );
  const routeAReady = routeIsConfigured("A");
  const routeBReady = routeIsConfigured("B");
  const blockers = getGenerateBlockers({ includeDomDrafts: false });
  return [
    { key: "quickStart", index: "01", label: "项目", complete: identityReady },
    { key: "routeA", index: "02", label: "A 路", complete: routeAReady, tone: "route-a" },
    { key: "routeB", index: "03", label: "B 路", complete: routeBReady, tone: "route-b" },
    { key: "extension", index: "04", label: "扩展", complete: routeAReady && routeBReady },
    { key: "project", index: "05", label: "复核", complete: blockers.length === 0 },
    { key: "result", index: "06", label: "交付", complete: Boolean(state.result && !state.resultStale) },
  ];
}

function renderWorkflowSpine() {
  if (!refs.workflowSpine) {
    return;
  }
  refs.workflowSpine.innerHTML = `
    <ol class="workflow-step-list">
      ${workflowStepDefinitions()
        .map((step) => {
          const active = state.activeStep === step.key;
          return `
            <li>
              <button
                class="workflow-step ${active ? "is-current" : ""} ${step.complete ? "is-complete" : ""} ${step.tone ? `is-${step.tone}` : ""}"
                type="button"
                data-action="jump-section"
                data-section="${step.key}"
                ${active ? 'aria-current="step"' : ""}
              >
                <span class="workflow-step__index">${escapeHtml(step.index)}</span>
                <strong>${escapeHtml(step.label)}</strong>
              </button>
            </li>
          `;
        })
        .join("")}
    </ol>
  `;
}

function pointsetPickerField(label, path, value, fieldOptions = {}) {
  const options = moduleTemplateOptions(fieldOptions.layout);
  const resolvedValue = value || state.config.profiles.plug_branch_template_id;
  const selected = options.find((item) => item.id === resolvedValue) || options[0];
  const selectedId = selected?.id || resolvedValue;
  const fieldId = fieldOptions.fieldId || path.replaceAll(".", "-");
  const selectedCount = Number(selected?.point_count || selected?.points?.length || 0);
  return `
    <div class="field field--pointset">
      <label id="${escapeHtml(fieldId)}-label">${escapeHtml(label)}</label>
      <details class="pointset-picker" data-pointset-picker>
        <summary aria-labelledby="${escapeHtml(fieldId)}-label">
          <span>${escapeHtml(branchTemplateUserLabel(selected))}</span>
          <em>${formatNumber(selectedCount)} 点</em>
        </summary>
        <div class="pointset-menu" role="listbox" aria-label="${escapeHtml(label)}">
          ${options.map((option) => {
            const optionCount = Number(option?.point_count || option?.points?.length || 0);
            const previewId = option.resolved_template_id || option.id || state.config.profiles.plug_branch_template_id;
            return `
              <button
                type="button"
                role="option"
                class="pointset-option ${option.id === selectedId ? "is-selected" : ""}"
                data-action="select-pointset"
                data-path="${escapeHtml(path)}"
                data-value="${escapeHtml(option.id)}"
                data-pointset-id="${escapeHtml(previewId)}"
                aria-selected="${option.id === selectedId ? "true" : "false"}"
              >
                <span><strong>${escapeHtml(branchTemplateUserLabel(option))}</strong><small>${escapeHtml(branchTemplateUserHelp(option))}</small></span>
                <em>${formatNumber(optionCount)} 点</em>
              </button>
            `;
          }).join("")}
        </div>
      </details>
      <div class="field-help field-help--pointset"><span>点数为逻辑变量数量（非寄存器数量）</span><em>单组对应 1 个三相分路；双组仅用于一拖六，并自动拆分为第 1 / 第 2 回路。悬停查看变量明细。</em></div>
    </div>
  `;
}

function pointsetTemplateById(templateId) {
  return (state.bootstrap.templates?.plug_branch_templates || []).find(
    (item) => item.id === templateId,
  ) || null;
}

function pointsetDatasetLabel(template, point) {
  if (template?.id !== "plug_branch_dual_dataset_47row") {
    return "";
  }
  if (Number(point?.dataset_group || 0) === 2) {
    return "第 2 回路 · _2";
  }
  const pointIndex = Number(point?.index || 0);
  if (pointIndex === 1) {
    return "第 1 回路 · 状态字";
  }
  return "第 1 回路";
}

function ensurePointsetPopover() {
  if (state.pointsetPopover?.isConnected) {
    return state.pointsetPopover;
  }
  const popover = document.createElement("aside");
  popover.className = "pointset-popover";
  popover.hidden = true;
  popover.setAttribute("aria-hidden", "true");
  popover.addEventListener("pointerenter", cancelPointsetPopoverHide);
  popover.addEventListener("pointerleave", schedulePointsetPopoverHide);
  document.body.appendChild(popover);
  state.pointsetPopover = popover;
  return popover;
}

function positionPointsetPopover(clientX, clientY, anchor = null) {
  const popover = ensurePointsetPopover();
  if (popover.hidden) {
    return;
  }
  const anchorRect = anchor?.getBoundingClientRect?.();
  const preferredX = Number.isFinite(clientX) ? clientX + 18 : (anchorRect?.right || 0) + 14;
  const preferredY = Number.isFinite(clientY) ? clientY + 16 : (anchorRect?.top || 0);
  const rect = popover.getBoundingClientRect();
  const margin = 12;
  const left = Math.max(margin, Math.min(preferredX, window.innerWidth - rect.width - margin));
  const top = Math.max(margin, Math.min(preferredY, window.innerHeight - rect.height - margin));
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function showPointsetPopover(optionElement, pointerEvent = null) {
  const template = pointsetTemplateById(optionElement?.dataset?.pointsetId);
  if (!template) {
    return;
  }
  const points = Array.isArray(template.points) ? template.points : [];
  const registerFootprint = Number(template.register_footprint || 0);
  const popover = ensurePointsetPopover();
  cancelPointsetPopoverHide();
  popover.innerHTML = `
    <div class="pointset-popover__head">
      <div><span>采集点位明细</span><strong>${escapeHtml(branchTemplateUserLabel(template))}</strong></div>
      <em>${formatNumber(points.length)} 个逻辑变量${registerFootprint ? ` · ${formatNumber(registerFootprint)} 个 16 位寄存器` : ""}</em>
    </div>
    <p class="pointset-popover__note"><code>{设备号}</code> 会在生成时替换为实际设备编号。</p>
    <div class="pointset-popover__columns" aria-hidden="true"><span>变量</span><span>名称 / 单位 / 类型</span></div>
    <ol class="pointset-popover__list">
      ${points.map((point) => {
        const datasetLabel = pointsetDatasetLabel(template, point);
        return `
        <li>
          <span class="pointset-popover__index">${String(point.index || 0).padStart(2, "0")}</span>
          <code>${escapeHtml(point.variable_pattern || point.prefix || "-")}</code>
          <span><strong>${datasetLabel ? `<b class="pointset-popover__dataset">${escapeHtml(datasetLabel)}</b>` : ""}${escapeHtml(point.name || "未命名点位")}</strong><small>${escapeHtml([point.unit || "无单位", point.data_type || ""].filter(Boolean).join(" · "))}</small></span>
        </li>
      `;
      }).join("")}
    </ol>
  `;
  popover.hidden = false;
  popover.setAttribute("aria-hidden", "false");
  state.pointsetPopoverOption = optionElement;
  positionPointsetPopover(pointerEvent?.clientX, pointerEvent?.clientY, optionElement);
}

function hidePointsetPopover() {
  cancelPointsetPopoverHide();
  const popover = state.pointsetPopover;
  if (popover) {
    popover.hidden = true;
    popover.setAttribute("aria-hidden", "true");
  }
  state.pointsetPopoverOption = null;
}

function cancelPointsetPopoverHide() {
  if (state.pointsetPopoverHideTimer) {
    window.clearTimeout(state.pointsetPopoverHideTimer);
    state.pointsetPopoverHideTimer = null;
  }
}

function schedulePointsetPopoverHide() {
  cancelPointsetPopoverHide();
  state.pointsetPopoverHideTimer = window.setTimeout(() => {
    state.pointsetPopoverHideTimer = null;
    hidePointsetPopover();
  }, 180);
}

function renderMobileActionBar() {
  if (!refs.mobileActionBar) {
    return;
  }
  const steps = workflowStepDefinitions();
  const index = Math.max(0, steps.findIndex((step) => step.key === state.activeStep));
  const previous = steps[index - 1];
  const next = steps[index + 1];
  const excelFileName = fileNameFromPath(state.result?.artifacts?.excel_path || "") || "动环通讯协议.xlsx";
  refs.mobileActionBar.innerHTML = `
    ${previous ? `<button class="button button--ghost" type="button" data-action="jump-section" data-section="${previous.key}">返回 ${escapeHtml(previous.label)}</button>` : `<span></span>`}
    ${
      state.activeStep === "project"
        ? `<button class="button button--primary" type="button" data-action="quick-generate" ${state.busy ? "disabled" : ""}>${state.busy ? "生成中…" : "生成三份文件"}</button>`
        : state.activeStep === "result" && state.result?.downloads?.excel
          ? `<a class="button button--primary" href="${state.result.downloads.excel}" download="${escapeHtml(excelFileName)}">下载协议表</a>`
          : next
            ? `<button class="button button--primary" type="button" data-action="jump-section" data-section="${next.key}">继续到 ${escapeHtml(next.label)}</button>`
            : ""
    }
  `;
}

function measurementLayoutMode() {
  return state.config?.protocol_layout?.measurement_layout_mode === "by_branch"
    ? "by_branch"
    : "by_plug_box";
}

function expectedSheetOrder() {
  const extensions = currentExtensions();
  return [
    "始端箱和插接箱",
    extensions.repeater?.enabled ? "中继器" : "",
    extensions.alarm_state_word?.enabled ? "报警状态" : "",
  ].filter(Boolean);
}

function expectedDeliveryFileNames() {
  const projectName = String(state.config.project_name || "未命名项目").trim() || "未命名项目";
  return {
    excel: `${projectName}-动环通讯协议.xlsx`,
    alarm: `${projectName}-报警状态字上传代码.txt`,
    program: `${projectName}-MCGS动环上传设备导入.csv`,
  };
}

function templateOption(groupKey, templateId) {
  return (state.bootstrap.templates[groupKey] || []).find((item) => item.id === templateId) || null;
}

function templateRegisterFootprint(groupKey, templateId, field = "register_footprint", fallback = 0) {
  return Number(templateOption(groupKey, templateId)?.[field] || fallback || 0);
}

function layoutOption(typeCode, layoutPattern) {
  return (
    state.maps.boxTypes[typeCode]?.allowed_layout_patterns?.find((item) => item.pattern === layoutPattern) || null
  );
}

function lucideIcon(name) {
  return `<i data-lucide="${escapeHtml(name)}" aria-hidden="true"></i>`;
}

function refreshLucideIcons() {
  if (window.lucide?.createIcons) {
    window.lucide.createIcons({
      attrs: {
        "aria-hidden": "true",
        "stroke-width": 1.8,
      },
    });
  }
}

function layoutBoardGroups(layout, options = {}) {
  const boardCount = Math.max(1, Number(layout?.board_count || 1));
  const branchCount = Math.max(0, Number(layout?.branch_count || 0));
  const variableDeviceStart = options.variableDeviceStart == null
    ? null
    : Math.max(1, Number(options.variableDeviceStart || 1));
  let capacities = String(layout?.pattern || "")
    .split("+")
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (capacities.length !== boardCount || capacities.reduce((sum, value) => sum + value, 0) !== branchCount) {
    capacities = Array.from({ length: boardCount }, (_, index) => {
      const remainingBranches = branchCount - index;
      const remainingBoards = boardCount - index;
      return Math.max(1, Math.ceil(remainingBranches / Math.max(1, remainingBoards)));
    });
  }
  if (options.singlePhaseTriplet && boardCount === 1 && branchCount === 3) {
    capacities = [3];
  }
  let outputNo = Math.max(1, Number(options.outputStart || 1));
  const boardStart = Math.max(1, Number(options.boardStart || 1));
  return capacities.map((capacity, boardIndex) => {
    const outputs = Array.from({ length: capacity }, () => outputNo++);
    return {
      boardNo: boardStart + boardIndex,
      variableDeviceCode: variableDeviceStart == null
        ? null
        : String(variableDeviceStart + boardIndex),
      outputs,
      sharedMeasurement: Boolean(options.singlePhaseTriplet && boardCount === 1 && branchCount === 3),
    };
  });
}

function selectedRailKey(route, column = activeColumnForRoute(route)) {
  return String(state.railSelection?.[routeScopeKey(route, column)] || "0:0");
}

function parseRailKey(value) {
  const [sourceIndexRaw, instanceIndexRaw] = String(value || "0:0").split(":");
  return {
    sourceIndex: Math.max(0, Number(sourceIndexRaw || 0)),
    instanceIndex: Math.max(0, Number(instanceIndexRaw || 0)),
  };
}

function singleCabinetColumnCount(column, extensions = currentExtensions()) {
  const key = `column_${Math.max(1, Number(column || 1))}`;
  if (extensions.single_cabinet?.column_counts?.[key] != null) {
    return Math.max(0, Number(extensions.single_cabinet.column_counts[key] || 0));
  }
  return Number(column) === 1
    ? Math.max(0, Number(extensions.single_cabinet?.cabinet_count || 0))
    : 0;
}

function repeaterColumnCount(column, route, extensions = currentExtensions()) {
  const key = `column_${Math.max(1, Number(column || 1))}`;
  if (extensions.repeater?.columns?.[key]?.[`${route}_count`] != null) {
    return Math.max(0, Number(extensions.repeater.columns[key][`${route}_count`] || 0));
  }
  return Number(column) === 1
    ? Math.max(0, Number(extensions.repeater?.[`${route}_count`] || 0))
    : 0;
}

function totalRepeaterCount(extensions = currentExtensions()) {
  return Array.from({ length: screenColumnCount() }, (_, index) => index + 1)
    .reduce(
      (total, column) => total + repeaterColumnCount(column, "A", extensions) + repeaterColumnCount(column, "B", extensions),
      0,
    );
}

function setRailSelection(route, sourceIndex, instanceIndex = 0, openEditor = true, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  state.railSelection[scopeKey] = `${Math.max(0, Number(sourceIndex || 0))}:${Math.max(0, Number(instanceIndex || 0))}`;
  if (openEditor) {
    state.railEditorOpen[scopeKey] = true;
  }
}

function selectedRailSourceIndex(route, sequenceLength, column = activeColumnForRoute(route)) {
  if (!sequenceLength) {
    return -1;
  }
  const { sourceIndex } = parseRailKey(selectedRailKey(route, column));
  return Math.min(sequenceLength - 1, sourceIndex);
}

function resolvedModuleInstances(route, column = activeColumnForRoute(route)) {
  const moduleConfig = routeDeviceRoot(state.config, column).branch_modules?.[route] || {};
  let moduleNo = Math.max(1, Number(moduleConfig.module_number_start || 1));
  let outputNo = Math.max(1, Number(moduleConfig.output_number_start || 1));
  let variableDeviceNo = Math.max(
    1,
    Number(moduleConfig.branch_device_number_start || (route === "A" ? 101 : 201)),
  );
  const instances = [];
  moduleSequenceForRoute(route, column).forEach((rawItem, sourceIndex) => {
    const item = normalizeModuleSequenceItem(rawItem);
    const boxType = state.maps.boxTypes[item.type_code] || branchCompatibleBoxTypes()[0];
    const layout = layoutOption(item.type_code, item.layout_pattern);
    const count = Math.max(1, Number(item.count || 1));
    const branchCount = Math.max(0, Number(layout?.branch_count || 0));
    for (let instanceIndex = 0; instanceIndex < count; instanceIndex += 1) {
      const groups = layoutBoardGroups(layout, {
        boardStart: 1,
        outputStart: outputNo,
        variableDeviceStart: variableDeviceNo,
        singlePhaseTriplet: boxType?.phase_mode === "single_phase_triplet",
      });
      instances.push({
        key: `${sourceIndex}:${instanceIndex}`,
        sourceIndex,
        instanceIndex,
        item,
        boxType,
        layout,
        moduleNo,
        outputStart: outputNo,
        outputEnd: Math.max(outputNo, outputNo + branchCount - 1),
        groups,
      });
      moduleNo += 1;
      outputNo += branchCount;
      variableDeviceNo += groups.length;
    }
  });
  return instances;
}

function resolvedPlugInstances(route, column = activeColumnForRoute(route)) {
  return resolvedSequenceItems(route, column).map((entry, sourceIndex) => {
    const boxType = state.maps.boxTypes[entry.item.type_code];
    return {
      key: `${sourceIndex}:0`,
      sourceIndex,
      instanceIndex: 0,
      entry,
      item: entry.item,
      boxType,
      layout: entry.layout,
      groups: layoutBoardGroups(entry.layout, {
        boardStart: entry.board_number_start,
        outputStart: 1,
        variableDeviceStart: entry.board_number_start,
        singlePhaseTriplet: boxType?.phase_mode === "single_phase_triplet",
      }),
    };
  });
}

function ensureRailSelection(route, instances, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  if (!instances.length) {
    state.railSelection[scopeKey] = "0:0";
    state.railEditorOpen[scopeKey] = false;
    return;
  }
  if (!instances.some((instance) => instance.key === selectedRailKey(route, column))) {
    const parsed = parseRailKey(selectedRailKey(route, column));
    const sameSource = instances.find((instance) => instance.sourceIndex === parsed.sourceIndex);
    state.railSelection[scopeKey] = (sameSource || instances[0]).key;
  }
}

function branchRegistersForRoute(route) {
  return Array.from({ length: screenColumnCount() }, (_, index) => {
    const deviceRoot = routeDeviceRoot(state.config, index + 1);
    const sequence = measurementLayoutMode() === "by_branch"
      ? deviceRoot.branch_modules?.[route]?.module_sequence || []
      : deviceRoot.plug_boxes?.[route]?.sequence || [];
    return sequence.reduce((total, item) => {
      const layout = layoutOption(item.type_code, item.layout_pattern);
      const branchTemplateId = item.branch_template_id || state.config.profiles.plug_branch_template_id;
      const branchAllocations = pointsetAllocationCount(layout, branchTemplateId);
      const branchFootprint = templateRegisterFootprint("plug_branch_templates", branchTemplateId);
      return total + Math.max(1, Number(item.count || 1)) * branchAllocations * branchFootprint;
    }, 0);
  }).reduce((sum, value) => sum + value, 0);
}

function startRegistersForRoute(route) {
  const startFootprint = templateRegisterFootprint(
    "start_box_templates",
    state.config.profiles.start_box_template_id,
  );
  return Array.from({ length: screenColumnCount() }, (_, index) => (
    Number(routeDeviceRoot(state.config, index + 1).start_boxes[route]?.count || 0) * startFootprint
  )).reduce((sum, value) => sum + value, 0);
}

function nextDerivedAddressBlock(anchor, registerStep) {
  let derived = (Math.floor(Number(anchor || 0) / 1000) + 1) * 1000;
  const step = Math.max(1, Number(registerStep || 2));
  if (derived % step !== 0) {
    derived += step - (derived % step);
  }
  return derived;
}

function singleCabinetAddressPreview() {
  const addressProfile = currentAddressProfile();
  const cabinetConfig = state.config.devices.single_cabinet_aggregation;
  const cabinetCount = Number(cabinetConfig.cabinet_count || 0);
  const cabinetEnabled =
    cabinetConfig.enabled && cabinetCount > 0;
  const registerStep = Number(addressProfile.register_step || 2);
  const basePerCabinetRegisters = templateRegisterFootprint(
    "single_cabinet_templates",
    state.config.profiles.single_cabinet_template_id,
    "register_footprint_per_cabinet",
    2,
  );
  const cabinetTemplate = templateOption(
    "single_cabinet_templates",
    state.config.profiles.single_cabinet_template_id,
  );
  const routeSplitRegisters = Number(
    cabinetTemplate?.route_split_register_footprint_per_cabinet || 0,
  );
  const perCabinetRegisters = basePerCabinetRegisters + (
    cabinetConfig.include_route_data ? routeSplitRegisters * 2 : 0
  );
  const screenTotalRegisters = cabinetConfig.include_total_power_energy ? 4 : 0;

  if (!cabinetEnabled) {
    return {
      enabled: false,
      mode: "disabled",
      startAddress: null,
      nextAddress: null,
      perCabinetRegisters,
      screenTotalRegisters,
      note: "未启用单机柜数据。",
    };
  }

  const configuredCabinetBase = state.config.extensions?.single_cabinet?.base_address;
  if (configuredCabinetBase != null || addressProfile.cabinet_base != null) {
    const startAddress = Number(configuredCabinetBase ?? addressProfile.cabinet_base);
    return {
      enabled: true,
      mode: "fixed",
      startAddress,
      nextAddress: startAddress + cabinetCount * perCabinetRegisters + screenTotalRegisters,
      perCabinetRegisters,
      screenTotalRegisters,
      note: configuredCabinetBase != null ? "按当前项目填写的单机柜数据基址生成。" : "当前地址模板已固定单机柜起始地址。",
    };
  }

  const previewSummary = currentPreviewSummary();
  if (previewSummary?.single_cabinet_start_address != null) {
    const startAddress = Number(previewSummary.single_cabinet_start_address);
    const nextAddress =
      previewSummary?.address_summary?.cabinet_next_address != null
        ? Number(previewSummary.address_summary.cabinet_next_address)
        : startAddress + cabinetCount * perCabinetRegisters + screenTotalRegisters;
    return {
      enabled: true,
      mode: "derived-confirmed",
      startAddress,
      nextAddress,
      perCabinetRegisters,
      screenTotalRegisters,
      note: "已按当前布局调用后端生成逻辑自动推导，和实际生成口径保持一致。",
    };
  }

  const family = currentFamilyFromConfig();
  const startA = startRegistersForRoute("A");
  const startB = startRegistersForRoute("B");
  const branchA = branchRegistersForRoute("A");
  const branchB = branchRegistersForRoute("B");
  let mainNext = null;
  let plugNext = null;

  if (family === "ab_screen_split") {
    mainNext = Math.max(
      Number(addressProfile.main_base || 0) + startA + branchA,
      Number(addressProfile.main_base || 0) + startB + branchB,
    );
  } else if (addressProfile.plug_base != null) {
    mainNext = Number(addressProfile.main_base || 0) + startA + startB;
    plugNext = Number(addressProfile.plug_base || 0) + branchA + branchB;
  } else {
    mainNext = Number(addressProfile.main_base || 0) + startA + startB + branchA + branchB;
  }

  let repeaterNext = null;
  if (state.config.devices.repeater_units.enabled && addressProfile.repeater_base != null) {
    const repeaterFootprint = templateRegisterFootprint(
      "repeater_templates",
      state.config.profiles.repeater_template_id,
    );
    const repeaterCount =
      Number(state.config.devices.repeater_units.A_count || 0) +
      Number(state.config.devices.repeater_units.B_count || 0);
    repeaterNext = Number(addressProfile.repeater_base) + repeaterCount * repeaterFootprint;
  }

  const anchorCandidates = [
    addressProfile.main_base,
    addressProfile.plug_base,
    addressProfile.repeater_base,
    addressProfile.alarm_base,
    mainNext,
    plugNext,
    repeaterNext,
  ].filter((value) => value != null && Number.isFinite(Number(value)));
  const anchor = anchorCandidates.length ? Math.max(...anchorCandidates.map((value) => Number(value))) : 1000;
  const startAddress = nextDerivedAddressBlock(anchor, registerStep);
  return {
    enabled: true,
    mode: "derived",
    startAddress,
    nextAddress: startAddress + cabinetCount * perCabinetRegisters + screenTotalRegisters,
    perCabinetRegisters,
    screenTotalRegisters,
    note: isCurrentPreviewPending()
      ? "已按当前布局先做本地预估，后端正在同步计算精确起始地址。"
      : "按当前布局预估，生成时以后端实际计算结果为准。",
  };
}

function quickEntryToken(item) {
  const boxType = state.maps.boxTypes[item.type_code];
  const defaultPattern = boxType?.default_layout_pattern || boxType?.allowed_layout_patterns?.[0]?.pattern || "1";
  const layoutPart = item.layout_pattern && item.layout_pattern !== defaultPattern ? `@${item.layout_pattern}` : "";
  return `${item.type_code}${layoutPart}`;
}

function routeQuickEntryValue(route, column = activeColumnForRoute(route)) {
  const sequence = routeDeviceRoot(state.config, column).plug_boxes[route]?.sequence || [];
  return sequence.map((item) => quickEntryToken(item)).join(", ");
}

function quickSequenceInputValue(route, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  const input = document.querySelector(`[data-quick-sequence-input="${scopeKey}"]`);
  if (input) {
    state.quickSequenceDrafts[scopeKey] = input.value;
  }
  return Object.prototype.hasOwnProperty.call(state.quickSequenceDrafts, scopeKey)
    ? state.quickSequenceDrafts[scopeKey]
    : routeQuickEntryValue(route, column);
}

function isQuickSequenceDirty(route, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  if (!Object.prototype.hasOwnProperty.call(state.quickSequenceDrafts, scopeKey)) {
    return false;
  }
  return String(state.quickSequenceDrafts[scopeKey] || "").trim() !== String(routeQuickEntryValue(route, column) || "").trim();
}

function parseQuickSequence(text) {
  const normalizedText = String(text || "")
    .replaceAll("，", ",")
    .replaceAll("；", ",")
    .replaceAll("×", "x");
  const chunks = normalizedText
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!chunks.length) {
    throw new Error("请先输入插接箱清单，例如 3P*3x2, 1P*3x1");
  }
  return chunks.flatMap((chunk) => {
    const token = chunk.replace(/\s+/gu, "").toUpperCase();
    const match = token.match(/^([0-9P*]+)(?:@([0-9+]+))?(?:X(\d+))?$/u);
    if (!match) {
      throw new Error(`无法识别：${chunk}`);
    }
    const [, rawTypeCode, layoutPattern, rawCount] = match;
    const typeCode = normalizeTypeCode(rawTypeCode);
    if (!state.maps.boxTypes[typeCode]) {
      throw new Error(`未知插接箱类型：${rawTypeCode}`);
    }
    const repeatCount = rawCount ? Number(rawCount) : 1;
    return Array.from({ length: repeatCount }, () => normalizeSequenceItem({
      type_code: typeCode,
      layout_pattern: layoutPattern,
      count: 1,
    }));
  });
}

function commitQuickSequence(route, text, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  const parsed = parseQuickSequence(text);
  routeDeviceRoot(state.config, column).plug_boxes[route].sequence = parsed;
  setRailSelection(route, 0, 0, false, column);
  state.railEditorOpen[scopeKey] = false;
  resetSequenceDetailState(route);
  state.config = normalizeConfig(state.config);
  delete state.quickSequenceDrafts[scopeKey];
  clearRouteQuickError(route, column);
  renderInlineQuickError(route, "", column);
  clearResult();
  clearRecommendation();
  saveDraft();
}

function applyQuickSequence(route, text, column = activeColumnForRoute(route)) {
  commitQuickSequence(route, text, column);
  setMessage(`已更新${routeColumnLabel(route, column)}插接箱清单`, "success");
  renderAll();
}

function clearRouteSequence(route, column = activeColumnForRoute(route)) {
  const scopeKey = routeScopeKey(route, column);
  routeDeviceRoot(state.config, column).plug_boxes[route].sequence = [];
  setRailSelection(route, 0, 0, false, column);
  state.railEditorOpen[scopeKey] = false;
  delete state.quickSequenceDrafts[scopeKey];
  resetSequenceDetailState(route);
  state.config = normalizeConfig(state.config);
  clearRouteQuickError(route, column);
  renderInlineQuickError(route, "", column);
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`已清空${routeColumnLabel(route, column)}插接箱`, "success");
  renderAll();
}

function getGenerateBlockers(options = {}) {
  if (!state.config?.devices) {
    return [];
  }
  if (options.includeDomDrafts) {
    configuredRouteScopes().forEach(({ route, column }) => quickSequenceInputValue(route, column));
  }

  const blockers = [];
  if (!String(state.config.project_name || "").trim()) {
    blockers.push({
      section: "project",
      selector: "#quick-project-name, #project-name",
      message: "请先填写项目名称。",
      buttonLabel: "先填项目名称",
    });
  }
  if (!String(state.config.project_code || "").trim()) {
    blockers.push({
      section: "project",
      selector: "#quick-project-code, #project-code",
      message: "请先填写项目编号。",
      buttonLabel: "先填项目编号",
    });
  }

  configuredRouteScopes().forEach(({ route, column }) => {
    const scopeKey = routeScopeKey(route, column);
    const scopeLabel = routeColumnLabel(route, column);
    const deviceRoot = routeDeviceRoot(state.config, column);
    if (measurementLayoutMode() === "by_branch") {
      const moduleSequence = deviceRoot.branch_modules?.[route]?.module_sequence || [];
      const invalidDualIndex = moduleSequence.findIndex((item) => (
        item?.branch_template_id === "plug_branch_dual_dataset_47row" &&
        !layoutAllowsDualDataset(layoutOption(item.type_code, item.layout_pattern))
      ));
      if (invalidDualIndex >= 0) {
        blockers.push({
          section: routeSectionKey(route),
          selector: `[data-action="select-rail-device"][data-route="${route}"][data-column="${column}"][data-source-index="${invalidDualIndex}"]`,
          message: `${scopeLabel}第 ${invalidDualIndex + 1} 组模块选择了“双组电参”，但其布局并非全一拖六板卡。请改用单组参数或调整板卡布局。`,
          buttonLabel: `先修正${scopeLabel}参数`,
        });
      }
      const moduleCount = routeColumnTotals(route, column).modules;
      if (moduleCount <= 0) {
        blockers.push({
          section: routeSectionKey(route),
          selector: `[data-action="add-module-sequence"][data-route="${route}"][data-column="${column}"]`,
          message: `请先为${scopeLabel}添加至少一种监控模块，并确认板卡布局与数量。`,
          buttonLabel: `先配置${scopeLabel}模块`,
        });
      }
      return;
    }
    const sequence = deviceRoot.plug_boxes?.[route]?.sequence || [];
    const invalidDualIndex = sequence.findIndex((item) => (
      item?.branch_template_id === "plug_branch_dual_dataset_47row" &&
      !layoutAllowsDualDataset(layoutOption(item.type_code, item.layout_pattern))
    ));
    if (invalidDualIndex >= 0) {
      blockers.push({
        section: routeSectionKey(route),
        selector: `[data-action="select-rail-device"][data-route="${route}"][data-column="${column}"][data-source-index="${invalidDualIndex}"]`,
        message: `${scopeLabel}第 ${invalidDualIndex + 1} 个插接箱选择了“双组电参”，但其布局并非全一拖六板卡。请改用单组参数或调整板卡布局。`,
        buttonLabel: `先修正${scopeLabel}参数`,
      });
    }
    if (isQuickSequenceDirty(route, column)) {
      blockers.push({
        section: routeSectionKey(route),
        selector: `#quick-sequence-${scopeKey}`,
        message: `${scopeLabel}插接箱清单已修改，请先应用到配置。`,
        buttonLabel: "应用清单并生成三份文件",
      });
    } else if (!sequence.length) {
      blockers.push({
        section: routeSectionKey(route),
        selector: `#quick-sequence-${scopeKey}`,
        message: `请先录入${scopeLabel}插接箱清单。`,
        buttonLabel: `先录入${scopeLabel}`,
      });
    } else if (routeQuickError(route, column)) {
      blockers.push({
        section: routeSectionKey(route),
        selector: `#quick-sequence-${scopeKey}`,
        message: routeQuickError(route, column),
        buttonLabel: `先修正${scopeLabel}清单`,
      });
    }
  });

  const extensions = currentExtensions();
  if (
    extensions.single_cabinet?.enabled &&
    Number(extensions.single_cabinet.cabinet_count || 0) <= 0
  ) {
    blockers.push({
      section: "extension",
      selector: '[data-path="extensions.single_cabinet.column_counts.column_1"]',
      message: "已启用单机柜数据，请填写机柜数量。",
      buttonLabel: "先填单机柜数量",
    });
  }
  if (
    extensions.repeater?.enabled &&
    totalRepeaterCount(extensions) <= 0
  ) {
    blockers.push({
      section: "extension",
      selector: '[data-path="extensions.repeater.columns.column_1.A_count"]',
      message: "已启用中继，请填写 A 路或 B 路中继数量。",
      buttonLabel: "先填中继数量",
    });
  }

  return blockers;
}

function syncQuickSequencesForGenerate() {
  if (measurementLayoutMode() === "by_branch") {
    return getGenerateBlockers({ includeDomDrafts: false });
  }
  const blockers = [];
  configuredRouteScopes().forEach(({ route, column }) => {
    const scopeKey = routeScopeKey(route, column);
    const scopeLabel = routeColumnLabel(route, column);
    const text = quickSequenceInputValue(route, column);
    if (!isQuickSequenceDirty(route, column)) {
      return;
    }
    try {
      commitQuickSequence(route, text, column);
    } catch (error) {
      const message = `${scopeLabel}插接箱清单无法应用：${error.message || String(error)}`;
      setRouteQuickError(route, message, column);
      blockers.push({
        section: routeSectionKey(route),
        selector: `#quick-sequence-${scopeKey}`,
        message,
        buttonLabel: `先修正${scopeLabel}清单`,
      });
    }
  });

  return [...blockers, ...getGenerateBlockers({ includeDomDrafts: false })];
}

function branchCompatibleBoxTypes() {
  return (state.bootstrap.box_types || []).filter((item) => item.phase_mode !== "single_phase_triplet");
}

function moduleSequenceForRoute(route, column = activeColumnForRoute(route)) {
  return routeDeviceRoot(state.config, column).branch_modules?.[route]?.module_sequence || [];
}

const BRANCH_TEMPLATE_UI_LABELS = Object.freeze({
  plug_branch_standard_29row_connector_temp: "标准电参 + 完整温度",
  plug_branch_compact_21row: "基础电参 + 入线温度",
  plug_branch_mid_26row_partial_connector: "32 位状态字 + 温度",
  plug_branch_dual_dataset_47row: "双组电参",
  plug_branch_compact_22row_freq: "基础电参 + 频率",
  plug_branch_standard_30row_full_connector: "完整温度 + 32 位状态字",
  plug_branch_extended_load_reactive: "扩展功率（含无功 / 视在）",
  plug_branch_single_phase_triplet_30row_full_connector: "三单相共用",
});

function branchTemplateUserLabel(template) {
  if (template?.id === "" && template?.label) {
    return template.label;
  }
  return (
    BRANCH_TEMPLATE_UI_LABELS[template?.id] ||
    template?.short_label ||
    template?.label ||
    template?.id ||
    "自定义采集点位"
  );
}

function branchTemplateUserHelp(template) {
  const features = Array.isArray(template?.features)
    ? template.features.filter(Boolean).join("、")
    : "";
  const registerFootprint = Number(template?.register_footprint || 0);
  const parts = [];
  if (features) {
    parts.push(`包含：${features}`);
  }
  if (registerFootprint) {
    parts.push(`占用 ${formatNumber(registerFootprint)} 个 16 位寄存器`);
  }
  if (template?.id === "plug_branch_dual_dataset_47row") {
    parts.push("仅限一拖六板卡；第 2 组变量自动使用 _2");
  }
  return parts.join(" · ") || "悬停查看每个变量与中文名称";
}

function layoutAllowsDualDataset(layout) {
  const boardIds = Array.isArray(layout?.board_template_ids)
    ? layout.board_template_ids
    : Array.isArray(layout?.board_template_sequence)
      ? layout.board_template_sequence
      : [];
  return boardIds.length > 0 && boardIds.every((item) => item === "board_1to6_3phase_dual");
}

function pointsetAllocationCount(layout, templateId) {
  if (templateId === "plug_branch_dual_dataset_47row" && layoutAllowsDualDataset(layout)) {
    return Number(layout?.board_count || 0);
  }
  return Number(layout?.branch_allocation_count || layout?.branch_count || 0);
}

function moduleTemplateOptions(layout = null) {
  return (state.bootstrap.templates?.plug_branch_templates || [])
      .filter((template) => (
        template.id !== "plug_branch_dual_dataset_47row" || layoutAllowsDualDataset(layout)
      ))
      .map((template) => ({
        ...template,
        label: branchTemplateUserLabel(template),
      }));
}

function boxTypeUserSummary(boxType) {
  const branchCount = Math.max(0, Number(boxType?.branch_count || 0));
  if (boxType?.phase_mode === "single_phase_triplet") {
    return `${formatNumber(branchCount)} 个单相分路 · 1 块板卡共用一套采集点位`;
  }
  const defaultLayout = (boxType?.allowed_layout_patterns || []).find(
    (layout) => layout.pattern === boxType?.default_layout_pattern,
  );
  const layoutLabel = defaultLayout?.label || `布局 ${boxType?.default_layout_pattern || "自动"}`;
  return `${formatNumber(branchCount)} 个三相分路 · 默认 ${layoutLabel}`;
}

function boxTypePropertyNote(boxType) {
  if (boxType?.phase_mode === "single_phase_triplet") {
    return "1 块板卡对应 3 个单相分路，共享同一组测量点。";
  }
  return "更换类型或布局后，板卡与输出分路会立即重新计算。";
}

function renderBoardMap(groups, options = {}) {
  if (!groups.length) {
    return `<div class="rail-board-map rail-board-map--empty">当前布局没有输出分路</div>`;
  }
  return `
    <ol class="rail-board-map" aria-label="板卡与输出分路映射">
      ${groups
        .map((group) => {
          const firstOutput = group.outputs[0];
          const lastOutput = group.outputs[group.outputs.length - 1];
          const baseVariableCode = String(group.variableDeviceCode || "").trim();
          const outputMarkup = group.sharedMeasurement
            ? `<span class="rail-branch-chip rail-branch-chip--shared">分路 ${formatNumber(firstOutput)}–${formatNumber(lastOutput)}<small>${baseVariableCode ? `变量 ${escapeHtml(baseVariableCode)} · ` : ""}共用一套采集点位</small></span>`
            : group.outputs
                .map((outputNo, outputIndex) => {
                  const variableCode = baseVariableCode
                    ? `${baseVariableCode}${outputIndex > 0 ? `_${outputIndex + 1}` : ""}`
                    : "";
                  return `<span class="rail-branch-chip">分路 ${formatNumber(outputNo)}${variableCode ? `<small>变量 ${escapeHtml(variableCode)}</small>` : ""}</span>`;
                })
                .join("");
          return `
            <li>
              <span class="rail-board-label">${lucideIcon("circuit-board")}<span>${escapeHtml(options.boardPrefix || "板卡")} ${formatNumber(group.boardNo)}</span></span>
              <span class="rail-map-arrow" aria-hidden="true">${lucideIcon("arrow-right")}</span>
              <span class="rail-branch-list">${outputMarkup}</span>
            </li>
          `;
        })
        .join("")}
    </ol>
  `;
}

function renderRailDeviceCard(route, column, instance, mode, sourceLength) {
  const selected = selectedRailKey(route, column) === instance.key;
  const sourceIndex = instance.sourceIndex;
  const layoutPattern = instance.layout?.pattern || instance.item.layout_pattern || "—";
  const boardCount = instance.groups.length;
  const outputCount = instance.groups.reduce((sum, group) => sum + group.outputs.length, 0);
  const isModule = mode === "branch";
  const numberLabel = isModule ? `M${String(instance.moduleNo).padStart(2, "0")}` : String(instance.entry.box_number);
  const title = isModule
    ? `${formatNumber(instance.moduleNo)}# 监控模块`
    : `${escapeHtml(instance.entry.box_name)} 插接箱`;
  const eyebrow = isModule ? "监控模块" : "物理插接箱";
  const typeLabel = instance.boxType?.short_label || instance.item.type_code;
  return `
    <article class="rail-device-card rail-device-card--${route.toLowerCase()} ${selected ? "is-selected" : ""}" data-rail-key="${escapeHtml(instance.key)}">
      <button
        class="rail-device-card__select"
        type="button"
        data-action="select-rail-device"
        data-route="${route}"
        data-column="${column}"
        data-source-index="${sourceIndex}"
        data-instance-index="${instance.instanceIndex}"
        aria-pressed="${selected ? "true" : "false"}"
        aria-label="编辑${escapeHtml(title)}"
      >
        <span class="rail-device-card__topline">
          <span class="rail-device-number">${escapeHtml(numberLabel)}</span>
          <span class="rail-device-kind">${escapeHtml(eyebrow)}</span>
          ${lucideIcon(isModule ? "panels-top-left" : "box")}
        </span>
        <span class="rail-device-card__title">${title}</span>
        <span class="rail-device-card__meta">${escapeHtml(typeLabel)} · 布局 ${escapeHtml(layoutPattern)}</span>
        ${renderBoardMap(instance.groups, { boardPrefix: isModule ? "板卡" : "板卡" })}
        <span class="rail-device-card__stats">
          <span>${lucideIcon("network")} ${formatNumber(boardCount)} 板</span>
          <span>${lucideIcon("git-branch")} ${formatNumber(outputCount)} 分路</span>
        </span>
      </button>
      <div class="rail-card-order" aria-label="设备快捷操作">
        <button class="rail-card-delete" type="button" data-action="remove-rail-device" data-mode="${mode}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}" data-instance-index="${instance.instanceIndex}" aria-label="删除${escapeHtml(title)}" title="删除${escapeHtml(title)}">${lucideIcon("trash-2")}</button>
        <button type="button" data-action="move-rail-item" data-mode="${mode}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}" data-direction="-1" ${sourceIndex <= 0 ? "disabled" : ""} aria-label="前移${escapeHtml(title)}">${lucideIcon("arrow-left")}</button>
        <button type="button" data-action="move-rail-item" data-mode="${mode}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}" data-direction="1" ${sourceIndex >= sourceLength - 1 ? "disabled" : ""} aria-label="后移${escapeHtml(title)}">${lucideIcon("arrow-right")}</button>
      </div>
    </article>
  `;
}

function renderRailAddCard(route, column, mode) {
  const types = mode === "branch" ? branchCompatibleBoxTypes() : state.bootstrap.box_types || [];
  const noun = mode === "branch" ? "监控模块" : "插接箱";
  return `
    <details class="rail-add-card">
      <summary>
        <span class="rail-add-card__icon">${lucideIcon("plus")}</span>
        <strong>添加${noun}</strong>
        <small>选择设备类型</small>
      </summary>
      <div class="rail-add-menu" role="group" aria-label="选择${noun}类型">
        ${types
          .map(
            (type) => `
              <button
                type="button"
                data-action="${mode === "branch" ? "add-module-sequence" : "add-sequence-type"}"
                data-route="${route}"
                data-column="${column}"
                data-type="${escapeHtml(type.type_code)}"
              >
                <strong>${escapeHtml(type.short_label || type.type_code)}</strong>
                <span>${escapeHtml(boxTypeUserSummary(type))}</span>
              </button>
            `,
          )
          .join("")}
      </div>
    </details>
  `;
}

function renderDeviceRail(route, column, mode, startBoxes, instances, totals) {
  const deviceRoot = routeDeviceRoot(state.config, column);
  const sourceLength = mode === "branch"
    ? moduleSequenceForRoute(route, column).length
    : deviceRoot.plug_boxes[route].sequence.length;
  const startNames = splitNames(startBoxes.instance_names);
  const startName = startNames[0] || `S${routeDefaultStartCode(route, column)}`;
  const hasStartBox = Number(startBoxes.count || 0) > 0;
  const modeLabel = mode === "branch" ? "按监控模块" : "按插接箱";
  return `
    <section class="device-rail-shell device-rail-shell--${route.toLowerCase()}" aria-label="${route} 路图形化设备编排">
      <div class="device-rail-head">
        <div>
          <span class="device-rail-kicker">${lucideIcon("workflow")} ${escapeHtml(routeColumnLabel(route, column))}设备编排</span>
          <strong>${escapeHtml(modeLabel)}</strong>
        </div>
        <div class="route-mode-switch" role="group" aria-label="遥测组织方式">
          <button type="button" data-action="set-measurement-mode" data-mode="by_plug_box" class="${mode === "plug" ? "is-active" : ""}" aria-pressed="${mode === "plug" ? "true" : "false"}">按插接箱</button>
          <button type="button" data-action="set-measurement-mode" data-mode="by_branch" class="${mode === "branch" ? "is-active" : ""}" aria-pressed="${mode === "branch" ? "true" : "false"}">按监控模块</button>
        </div>
      </div>
      <div class="device-rail-viewport">
        <img class="din-rail-image" src="/static/assets/din-rail.svg" alt="" aria-hidden="true">
        <div class="device-rail-track">
          <article class="rail-start-node ${hasStartBox ? "" : "is-empty"}">
            <span class="rail-start-node__icon">${lucideIcon("package-open")}</span>
            <div>
              <strong>${hasStartBox ? `${route} 路始端箱 ${escapeHtml(startName)}` : `${route} 路始端箱`}</strong>
              <span>${hasStartBox ? `${formatNumber(startBoxes.count)} 台 · 起点设备` : "未配置 · 填写后参与生成"}</span>
            </div>
            <span class="rail-start-node__port" aria-hidden="true">${lucideIcon("circle-dot")}</span>
          </article>
          ${instances.map((instance) => renderRailDeviceCard(route, column, instance, mode, sourceLength)).join("")}
          ${renderRailAddCard(route, column, mode)}
        </div>
      </div>
      <div class="device-rail-summary">
        ${lucideIcon("network")}
        <span>${route} 路汇总</span>
        <strong>${mode === "branch" ? `${formatNumber(totals.modules)} 个监控模块` : `${formatNumber(totals.physicalBoxes)} 个插接箱`}</strong>
        <span>·</span>
        <strong>${formatNumber(totals.boards)} 块板卡</strong>
        <span>·</span>
        <strong>${formatNumber(totals.branches)} 个输出分路</strong>
      </div>
    </section>
  `;
}

function renderRailPropertyActions(route, column, mode, sourceIndex, sourceLength, deleteAction) {
  return `
    <div class="rail-property-actions">
      <div>
        <button class="button button--ghost" type="button" data-action="move-rail-item" data-mode="${mode}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}" data-direction="-1" ${sourceIndex <= 0 ? "disabled" : ""}>${lucideIcon("arrow-left")} 前移</button>
        <button class="button button--ghost" type="button" data-action="move-rail-item" data-mode="${mode}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}" data-direction="1" ${sourceIndex >= sourceLength - 1 ? "disabled" : ""}>后移 ${lucideIcon("arrow-right")}</button>
      </div>
      <button class="button rail-delete-button" type="button" data-action="${deleteAction}" data-route="${route}" data-column="${column}" data-index="${sourceIndex}">${lucideIcon("trash-2")} 删除</button>
    </div>
  `;
}

function renderModuleRailProperties(route, column, instances) {
  const sequence = moduleSequenceForRoute(route, column);
  if (!sequence.length) {
    return "";
  }
  const parsed = parseRailKey(selectedRailKey(route, column));
  const sourceIndex = Math.min(sequence.length - 1, parsed.sourceIndex);
  const matchingInstances = instances.filter((instance) => instance.sourceIndex === sourceIndex);
  const instance = matchingInstances[Math.min(matchingInstances.length - 1, parsed.instanceIndex)] || matchingInstances[0];
  if (!instance) {
    return "";
  }
  const item = normalizeModuleSequenceItem(sequence[sourceIndex]);
  const boxType = state.maps.boxTypes[item.type_code] || branchCompatibleBoxTypes()[0];
  const layout = layoutOption(item.type_code, item.layout_pattern);
  const pathBase = `${routeDevicePath(column)}.branch_modules.${route}.module_sequence.${sourceIndex}`;
  const scopeKey = routeScopeKey(route, column);
  const mobileOpen = state.railEditorOpen[scopeKey];
  return `
    ${mobileOpen ? `<button class="rail-sheet-backdrop" type="button" data-action="close-rail-properties" data-route="${route}" data-column="${column}" aria-label="关闭设备属性"></button>` : ""}
    <section id="rail-properties-${route}-${column}" class="rail-properties rail-properties--${route.toLowerCase()} ${mobileOpen ? "is-mobile-open" : ""}" tabindex="-1" aria-label="监控模块属性">
      <div class="rail-properties__head">
        <div><span>${escapeHtml(routeColumnLabel(route, column))} · M${String(instance.moduleNo).padStart(2, "0")}</span><strong>${formatNumber(instance.moduleNo)}# 监控模块</strong><small>属性与板卡结构</small></div>
        <button class="rail-sheet-close" type="button" data-action="close-rail-properties" data-route="${route}" data-column="${column}" aria-label="关闭设备属性">${lucideIcon("x")}</button>
      </div>
      <div class="rail-properties__body">
        <div class="rail-property-fields">
          <h3>基本信息</h3>
          <div class="field-grid">
            ${spanWrap(selectField("模块类型", `${pathBase}.type_code`, item.type_code, branchCompatibleBoxTypes(), "type_code"), 4)}
            ${spanWrap(selectField("板卡布局", `${pathBase}.layout_pattern`, item.layout_pattern, boxType?.allowed_layout_patterns || [], "pattern"), 4)}
            ${spanWrap(numberField("同配置模块数", `${pathBase}.count`, item.count, 1), 4)}
            ${spanWrap(pointsetPickerField("分路采集点位", `${pathBase}.branch_template_id`, item.branch_template_id || "", { layout }), 12)}
          </div>
          <p class="rail-property-note">${escapeHtml(boxTypePropertyNote(boxType))}</p>
        </div>
        <div class="rail-property-map">
          <div class="rail-property-map__head"><h3>板卡与分路映射</h3><span>本组第 ${formatNumber(instance.instanceIndex + 1)} 个模块</span></div>
          ${renderBoardMap(instance.groups)}
          <div class="rail-map-result"><span>自动结果</span><strong>${formatNumber(layout?.board_count || 0)} 板 · ${formatNumber(layout?.branch_count || 0)} 分路</strong></div>
        </div>
      </div>
      ${renderRailPropertyActions(route, column, "branch", sourceIndex, sequence.length, "remove-module-sequence")}
    </section>
  `;
}

function renderPlugRailProperties(route, column, instances) {
  const sequence = routeDeviceRoot(state.config, column).plug_boxes[route].sequence;
  if (!sequence.length) {
    return "";
  }
  const sourceIndex = selectedRailSourceIndex(route, sequence.length, column);
  const instance = instances.find((entry) => entry.sourceIndex === sourceIndex) || instances[0];
  if (!instance) {
    return "";
  }
  const entry = instance.entry;
  const item = entry.item;
  const boxType = instance.boxType;
  const layout = instance.layout;
  const pathBase = `${routeDevicePath(column)}.plug_boxes.${route}.sequence.${sourceIndex}`;
  const scopeKey = routeScopeKey(route, column);
  const mobileOpen = state.railEditorOpen[scopeKey];
  return `
    ${mobileOpen ? `<button class="rail-sheet-backdrop" type="button" data-action="close-rail-properties" data-route="${route}" data-column="${column}" aria-label="关闭设备属性"></button>` : ""}
    <section id="rail-properties-${route}-${column}" class="rail-properties rail-properties--${route.toLowerCase()} ${mobileOpen ? "is-mobile-open" : ""}" tabindex="-1" aria-label="插接箱属性">
      <div class="rail-properties__head">
        <div><span>${escapeHtml(routeColumnLabel(route, column))} · ${escapeHtml(String(entry.box_number))}</span><strong>${escapeHtml(entry.box_name)} 插接箱</strong><small>属性与板卡结构</small></div>
        <button class="rail-sheet-close" type="button" data-action="close-rail-properties" data-route="${route}" data-column="${column}" aria-label="关闭设备属性">${lucideIcon("x")}</button>
      </div>
      <div class="rail-properties__body">
        <div class="rail-property-fields">
          <h3>基本信息</h3>
          <div class="field-grid">
            ${spanWrap(selectField("插接箱类型", `${pathBase}.type_code`, item.type_code, state.bootstrap.box_types, "type_code"), 4)}
            ${spanWrap(selectField("板卡布局", `${pathBase}.layout_pattern`, item.layout_pattern, boxType?.allowed_layout_patterns || [], "pattern"), 4)}
            ${spanWrap(numberField("插接箱编号", `${pathBase}.box_number`, entry.box_number, 1), 4)}
            ${spanWrap(textField("插接箱名称", `${pathBase}.box_name`, entry.box_name, { placeholder: String(entry.box_number) }), 8)}
            ${spanWrap(pointsetPickerField("分路采集点位", `${pathBase}.branch_template_id`, item.branch_template_id || "", { layout }), 4)}
          </div>
          <p class="rail-property-note">${escapeHtml(boxTypePropertyNote(boxType))}</p>
        </div>
        <div class="rail-property-map">
          <div class="rail-property-map__head"><h3>板卡与分路映射</h3><span>点位起点 ${formatNumber(entry.board_number_start)}</span></div>
          ${renderBoardMap(instance.groups)}
          <div class="rail-map-result"><span>自动结果</span><strong>${formatNumber(layout?.board_count || 0)} 板 · ${formatNumber(layout?.branch_count || 0)} 分路</strong></div>
        </div>
      </div>
      ${renderRailPropertyActions(route, column, "plug", sourceIndex, sequence.length, "remove-sequence")}
    </section>
  `;
}

function renderModuleSequenceRow(route, rawItem, index) {
  const item = normalizeModuleSequenceItem(rawItem);
  const boxType = state.maps.boxTypes[item.type_code] || branchCompatibleBoxTypes()[0];
  const layout = layoutOption(item.type_code, item.layout_pattern);
  const pathBase = `devices.branch_modules.${route}.module_sequence.${index}`;
  const typeId = `branch-module-${route}-${index}-type`;
  const layoutId = `branch-module-${route}-${index}-layout`;
  const countId = `branch-module-${route}-${index}-count`;
  const templateId = `branch-module-${route}-${index}-template`;
  const moduleCount = Math.max(1, Number(item.count || 1));
  const boardCount = Number(layout?.board_count || 0) * moduleCount;
  const branchCount = Number(layout?.branch_count || 0) * moduleCount;
  return `
    <div class="module-row" data-module-route="${route}" data-module-index="${index}">
      <div class="module-row__fields">
        <span class="module-row__number" aria-label="模块组合 ${index + 1}">${formatNumber(index + 1)}</span>
        ${selectField("模块类型", `${pathBase}.type_code`, item.type_code, branchCompatibleBoxTypes(), "type_code", { fieldId: typeId })}
        ${selectField("板卡布局", `${pathBase}.layout_pattern`, item.layout_pattern, boxType?.allowed_layout_patterns || [], "pattern", { fieldId: layoutId })}
        ${numberField("数量", `${pathBase}.count`, item.count, 1, { fieldId: countId })}
        <output class="module-row__result" aria-label="自动计算结果">
          <span>自动结果</span>
          <strong>${formatNumber(boardCount)} 板 · ${formatNumber(branchCount)} 分路</strong>
        </output>
      </div>
      <details class="module-row__details">
        <summary>更多</summary>
        <div class="module-row__detail-popover">
          <div class="field-grid module-row__detail-grid">
            ${spanWrap(pointsetPickerField("分路采集点位", `${pathBase}.branch_template_id`, item.branch_template_id || "", { fieldId: templateId, layout }), 12)}
          </div>
          <div class="module-calculation">
            <span>每模块 ${formatNumber(layout?.board_count || 0)} 板</span>
            <span>每模块 ${formatNumber(layout?.branch_count || 0)} 分路</span>
            <span>${formatNumber(layout?.branch_allocation_count || 0)} 套采集点位</span>
          </div>
          <button class="row-remove" type="button" data-action="remove-module-sequence" data-route="${route}" data-index="${index}" aria-label="删除模块组合 ${index + 1}">删除模块</button>
        </div>
      </details>
    </div>
  `;
}

function addModuleSequence(route, typeCode = "3P*2", column = activeColumnForRoute(route)) {
  const moduleConfig = routeDeviceRoot(state.config, column).branch_modules[route];
  moduleConfig.module_sequence = moduleConfig.module_sequence || [];
  moduleConfig.module_sequence.push(defaultModuleSequenceItem(typeCode));
  const newIndex = moduleConfig.module_sequence.length - 1;
  setRailSelection(route, newIndex, 0, true, column);
  state.config = normalizeConfig(state.config);
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
  renderAll();
  queueFocus(`#rail-properties-${route}-${column}`);
  applyPendingFocus();
}

function removeModuleSequence(route, index, column = activeColumnForRoute(route)) {
  const moduleConfig = routeDeviceRoot(state.config, column).branch_modules[route];
  moduleConfig.module_sequence.splice(index, 1);
  setRailSelection(route, Math.max(0, Math.min(index, moduleConfig.module_sequence.length - 1)), 0, false, column);
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  renderAll();
}

function removeRailDevice(
  route,
  mode,
  index,
  instanceIndex = 0,
  column = activeColumnForRoute(route),
) {
  const deviceRoot = routeDeviceRoot(state.config, column);
  const sequence = mode === "branch"
    ? deviceRoot.branch_modules[route].module_sequence
    : deviceRoot.plug_boxes[route].sequence;
  const sourceIndex = Number(index);
  if (!Array.isArray(sequence) || sourceIndex < 0 || sourceIndex >= sequence.length) {
    return;
  }
  const item = sequence[sourceIndex];
  const repeatCount = Math.max(1, Number(item?.count || 1));
  if (repeatCount > 1) {
    item.count = repeatCount - 1;
  } else {
    sequence.splice(sourceIndex, 1);
  }
  const nextSourceIndex = Math.max(0, Math.min(sourceIndex, sequence.length - 1));
  const nextInstanceIndex = repeatCount > 1
    ? Math.max(0, Math.min(Number(instanceIndex || 0), repeatCount - 2))
    : 0;
  setRailSelection(route, nextSourceIndex, nextInstanceIndex, false, column);
  resetSequenceDetailState(route);
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`已删除${mode === "branch" ? "监控模块" : "插接箱"}`, "success");
  renderAll();
}

function moveRailItem(route, mode, index, direction, column = activeColumnForRoute(route)) {
  const deviceRoot = routeDeviceRoot(state.config, column);
  const sequence = mode === "branch"
    ? deviceRoot.branch_modules[route].module_sequence
    : deviceRoot.plug_boxes[route].sequence;
  const sourceIndex = Number(index);
  const targetIndex = sourceIndex + Number(direction);
  if (!Array.isArray(sequence) || sourceIndex < 0 || targetIndex < 0 || sourceIndex >= sequence.length || targetIndex >= sequence.length) {
    return;
  }
  const [item] = sequence.splice(sourceIndex, 1);
  sequence.splice(targetIndex, 0, item);
  const currentSelection = parseRailKey(selectedRailKey(route, column));
  setRailSelection(route, targetIndex, currentSelection.sourceIndex === sourceIndex ? currentSelection.instanceIndex : 0, true, column);
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  renderAll();
  queueFocus(`[data-rail-key="${targetIndex}:${Math.max(0, currentSelection.instanceIndex)}"] .rail-device-card__select`);
  applyPendingFocus();
}

function setMeasurementMode(mode) {
  const nextMode = mode === "by_branch" ? "by_branch" : "by_plug_box";
  if (measurementLayoutMode() === nextMode) {
    return;
  }
  state.config.protocol_layout.measurement_layout_mode = nextMode;
  state.config = normalizeConfig(state.config);
  state.railSelection = {};
  state.railEditorOpen = {};
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`已切换为${nextMode === "by_branch" ? "按监控模块" : "按插接箱"}编排`, "success");
  renderAll();
}

function setScreenTopology(mode) {
  const nextMode = mode === SCREEN_MODE_DOUBLE ? SCREEN_MODE_DOUBLE : SCREEN_MODE_SINGLE;
  if (state.config.topology.screen_topology_mode === nextMode) {
    return;
  }
  state.config.topology.screen_topology_mode = nextMode;
  state.config = normalizeConfig(state.config);
  if (nextMode === SCREEN_MODE_SINGLE) {
    state.activeColumnByRoute = { A: 1, B: 1 };
  }
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(nextMode === SCREEN_MODE_DOUBLE ? "已启用单屏双列：每列分别配置 A/B 路" : "已切换为单屏单列", "success");
  renderAll();
}

function setActiveRouteColumn(route, column) {
  const nextColumn = Math.min(screenColumnCount(), Math.max(1, Number(column || 1)));
  state.activeColumnByRoute[route] = nextColumn;
  state.activeRoute = route;
  renderAll();
  queueFocus(`#routeSection${route} [data-route-column="${nextColumn}"]`);
  applyPendingFocus();
}

function renderRouteSection(route, container) {
  const column = activeColumnForRoute(route);
  const scopeKey = routeScopeKey(route, column);
  const deviceRoot = routeDeviceRoot(state.config, column);
  const routeConfig = deviceRoot.plug_boxes[route];
  const startBoxes = deviceRoot.start_boxes[route];
  const pathRoot = routeDevicePath(column);
  const collapsed = isSectionCollapsed(routeSectionKey(route));
  const sectionTitle = route === "A" ? "A 路设备" : "B 路设备";
  const startBoxNames = splitNames(startBoxes.instance_names);
  const totals = routeColumnTotals(route, column);
  const aggregateTotals = routeTotals(route);
  const branchMode = measurementLayoutMode() === "by_branch";
  const moduleConfig = deviceRoot.branch_modules[route];
  const instances = branchMode ? resolvedModuleInstances(route, column) : resolvedPlugInstances(route, column);
  ensureRailSelection(route, instances, column);
  setSectionVisualState(container, collapsed, route === "A" ? "route-a" : "route-b");
  const tools = route === "B"
    ? `<button class="section-tool" type="button" data-action="copy-route-sequence" data-source="A" data-target="B">${lucideIcon("copy")} 沿用 A 路${screenColumnCount() === 2 ? "两列" : ""}结构</button>`
    : "";
  const quickSequenceText = Object.prototype.hasOwnProperty.call(state.quickSequenceDrafts, scopeKey)
    ? state.quickSequenceDrafts[scopeKey]
    : routeQuickEntryValue(route, column);
  const quickError = routeQuickError(route, column);
  const columnSwitcher = screenColumnCount() === 2
    ? `<div class="route-column-switcher" role="tablist" aria-label="${route} 路所在机柜列">
         ${[1, 2].map((candidateColumn) => {
           const candidateTotals = routeColumnTotals(route, candidateColumn);
           const active = candidateColumn === column;
           return `<button
             type="button"
             role="tab"
             class="route-column-tab ${active ? "is-active" : ""}"
             data-action="set-route-column"
             data-route="${route}"
             data-column="${candidateColumn}"
             aria-selected="${active ? "true" : "false"}"
             tabindex="${active ? "0" : "-1"}"
           ><span>${candidateColumn === 1 ? "第一列" : "第二列"} <strong>${route} 路</strong></span><em>${branchMode ? `${formatNumber(candidateTotals.modules)} 模块 · ${formatNumber(candidateTotals.branches)} 分路` : `${formatNumber(candidateTotals.physicalBoxes)} 箱 · ${formatNumber(candidateTotals.branches)} 分路`}</em></button>`;
         }).join("")}
       </div>`
    : "";
  const startControls = `
    <details class="start-box-settings" ${Number(startBoxes.count || 0) <= 0 ? "open" : ""}>
      <summary>${lucideIcon("package-open")}<strong>始端箱</strong><span>${formatNumber(startBoxes.count)} 台 · ${escapeHtml(startBoxNames.join("、") || "待设置")}</span></summary>
      <div class="field-grid route-start-fields">
        ${spanWrap(numberField("始端箱数量", `${pathRoot}.start_boxes.${route}.count`, startBoxes.count, 0, { max: 1 }), 3)}
        ${spanWrap(textField("始端箱名称", `${pathRoot}.start_boxes.${route}.instance_names`, startBoxNames.join(", "), {
          placeholder: `S${routeDefaultStartCode(route, column)}`,
          transform: "names",
        }), 9)}
      </div>
    </details>
  `;
  container.innerHTML = `
    ${renderSectionHead(sectionTitle, "", tools, {
      sectionKey: routeSectionKey(route),
      summary: `<span>${escapeHtml(compactRouteSummary(route))}</span><span>${screenColumnCount() === 2 ? "两列合计 · " : ""}始端箱 ${formatNumber(Array.from({ length: screenColumnCount() }, (_, index) => Number(routeDeviceRoot(state.config, index + 1).start_boxes[route].count || 0)).reduce((sum, value) => sum + value, 0))}</span>`,
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="route-editor route-editor--rail step-body" data-route-column="${column}">
            ${columnSwitcher}
            ${screenColumnCount() === 2 ? `<div class="route-column-context"><span>${column === 1 ? "第一列" : "第二列"}</span><strong>${route} 路独立配置</strong><em>默认设备号从 ${formatNumber(routeDefaultBoxStart(route, column))} 开始</em></div>` : ""}
            ${startControls}
            ${renderDeviceRail(route, column, branchMode ? "branch" : "plug", startBoxes, instances, totals)}
            ${branchMode ? renderModuleRailProperties(route, column, instances) : renderPlugRailProperties(route, column, instances)}
            ${branchMode
              ? `<details class="numbering-details rail-advanced-settings">
                   <summary>${lucideIcon("settings-2")} 编号与高级参数</summary>
                   <div class="field-grid numbering-fields">
                     ${spanWrap(`<div class="field field--readonly"><label>变量编号规则</label><div class="readonly-value">按板卡编号 · 一拖六第二回路自动使用 <code>_2</code></div></div>`, 6)}
                     ${spanWrap(numberField("模块编号起点", `${pathRoot}.branch_modules.${route}.module_number_start`, moduleConfig.module_number_start, 1), 2)}
                     ${spanWrap(numberField("输出分路起点", `${pathRoot}.branch_modules.${route}.output_number_start`, moduleConfig.output_number_start, 1), 2)}
                     ${spanWrap(numberField("变量设备号起点", `${pathRoot}.branch_modules.${route}.branch_device_number_start`, moduleConfig.branch_device_number_start, 1), 2)}
                   </div>
                 </details>`
              : `<details class="quick-entry-panel quick-entry-panel--streamlined rail-advanced-settings">
                   <summary>${lucideIcon("list-plus")}<strong>批量录入插接箱</strong><span>可选</span></summary>
                   <div class="quick-entry-content">
                     <div class="field">
                       <label for="quick-sequence-${scopeKey}">插接箱清单</label>
                       <textarea id="quick-sequence-${scopeKey}" class="quick-entry-input" data-quick-sequence-input="${scopeKey}" data-route="${route}" data-column="${column}" aria-label="${escapeHtml(routeColumnLabel(route, column))}插接箱清单" ${quickError ? `aria-invalid="true" aria-describedby="quick-sequence-error-${scopeKey}"` : ""} placeholder="例如：3P*3x2, 3P*1x1, 1P*3x1">${escapeHtml(quickSequenceText)}</textarea>
                     </div>
                     ${quickError ? `<div class="inline-feedback inline-feedback--error" id="quick-sequence-error-${scopeKey}" role="alert">${escapeHtml(quickError)}</div>` : ""}
                     <div class="inline-group">
                       <button class="section-tool" type="button" data-action="apply-quick-sequence" data-route="${route}" data-column="${column}">更新设备轨道</button>
                       <button class="section-tool section-tool--quiet" type="button" data-action="clear-route-sequence" data-route="${route}" data-column="${column}">清空</button>
                     </div>
                   </div>
                 </details>`}
            <div class="step-actions">
              <button class="button button--primary" type="button" data-action="jump-section" data-section="${route === "A" ? "routeB" : "extension"}">${route === "A" ? "继续到 B 路" : "继续到扩展"}</button>
            </div>
          </div>`
    }
  `;
}

function renderSequenceRow(route, entry, index) {
  const item = entry.item;
  const boxType = state.maps.boxTypes[item.type_code];
  const layout =
    entry.layout || boxType.allowed_layout_patterns.find((candidate) => candidate.pattern === item.layout_pattern);
  const typeLabel = boxType.label || boxType.type_code;
  const typeHelp = boxType.help_text || `${boxType.branch_count} 回路`;
  const layoutLabel = layout ? layout.label || `${layout.pattern} · ${layout.board_count} 板卡 / ${layout.branch_count} 回路` : item.layout_pattern;
  const layoutHelp = layout?.help_text || `${layout?.board_count || entry.board_count} 板卡 / ${layout?.branch_count || entry.branch_count} 回路`;
  const meta = `${typeLabel} · ${layoutLabel} · 默认点位起点 ${entry.board_number_start}`;
  const typeFieldId = `devices-plug-boxes-${route}-sequence-${index}-type-code`;
  const layoutFieldId = `devices-plug-boxes-${route}-sequence-${index}-layout-pattern`;
  const numberFieldId = `devices-plug-boxes-${route}-sequence-${index}-box-number`;
  const nameFieldId = `devices-plug-boxes-${route}-sequence-${index}-box-name`;
  const defaultNamePlaceholder = String(entry.box_number || "");
  const numberValue = entry.explicit_box_number != null ? String(entry.explicit_box_number) : "";
  const nameValue = entry.explicit_box_name || "";
  const numberBadgeLabel = entry.explicit_box_number != null ? `编号 ${entry.box_number}` : `默认编号 ${entry.box_number}`;
  const nameBadgeLabel = entry.explicit_box_name ? `名称 ${entry.explicit_box_name}` : `默认名称 ${entry.box_name}`;
  const shouldOpen = isSequenceDetailOpen(route, index, entry);
  const previewText = `${typeLabel} · ${layoutLabel} · 默认点位起点 ${entry.board_number_start}`;
  const layoutOptions = boxType.allowed_layout_patterns
    .map(
      (layoutOptionItem) => `
        <option value="${escapeHtml(layoutOptionItem.pattern)}" ${layoutOptionItem.pattern === item.layout_pattern ? "selected" : ""}>
          ${escapeHtml(layoutOptionItem.label || layoutOptionItem.pattern)}
        </option>
      `,
    )
    .join("");
  return `
    <details class="sequence-card" data-route="${route}" data-index="${index}" ${shouldOpen ? "open" : ""}>
      <summary class="sequence-card__summary">
        <div class="sequence-card__head">
          <div>
            <strong>${escapeHtml(typeLabel)}</strong>
            <span>${escapeHtml(layoutLabel)}</span>
          </div>
          <div class="sequence-card__pills">
            <span class="status-pill">${escapeHtml(numberBadgeLabel)}</span>
            <span class="status-pill">${escapeHtml(nameBadgeLabel)}</span>
          </div>
        </div>
        <div class="sequence-card__preview">${escapeHtml(previewText)}</div>
      </summary>
      <div class="sequence-card__body">
        <div>
          <div class="muted-note" style="margin-bottom: 10px;">${escapeHtml(`${typeHelp} · ${layoutHelp}`)}</div>
        </div>
        <div class="sequence-row">
          <div class="field field--select">
            <label for="${escapeHtml(typeFieldId)}">插接箱类型</label>
            <select
              id="${escapeHtml(typeFieldId)}"
              name="${escapeHtml(typeFieldId)}"
              data-path="devices.plug_boxes.${route}.sequence.${index}.type_code"
              title="${escapeHtml(`${typeLabel}｜${typeHelp}`)}"
            >
              ${state.bootstrap.box_types
                .map(
                  (type) => `
                    <option value="${escapeHtml(type.type_code)}" ${type.type_code === item.type_code ? "selected" : ""}>
                      ${escapeHtml(type.label || type.type_code)}
                    </option>
                  `,
                )
                .join("")}
            </select>
            <div class="field-help">
              <span>${escapeHtml(boxType.short_label || typeLabel)}</span>
              <em>${escapeHtml(typeHelp)}</em>
            </div>
          </div>
          <div class="field field--select">
            <label for="${escapeHtml(layoutFieldId)}">出线方式</label>
            <select
              id="${escapeHtml(layoutFieldId)}"
              name="${escapeHtml(layoutFieldId)}"
              data-path="devices.plug_boxes.${route}.sequence.${index}.layout_pattern"
              title="${escapeHtml(`${layoutLabel}｜${layoutHelp}`)}"
            >
              ${layoutOptions}
            </select>
            <div class="field-help">
              <span>${escapeHtml(layout?.short_label || layout?.label || item.layout_pattern)}</span>
              <em>${escapeHtml(layoutHelp)}</em>
            </div>
          </div>
          <div class="field">
            <label for="${escapeHtml(numberFieldId)}">插接箱编号</label>
            <input
              id="${escapeHtml(numberFieldId)}"
              name="${escapeHtml(numberFieldId)}"
              type="number"
              min="1"
              step="1"
              data-path="devices.plug_boxes.${route}.sequence.${index}.box_number"
              data-cast="optional-number"
              value="${escapeHtml(numberValue)}"
              placeholder="${escapeHtml(String(entry.box_number))}"
            />
          </div>
          <button
            class="row-remove"
            type="button"
            data-action="remove-sequence"
            data-route="${route}"
            data-index="${index}"
            title="删除当前插接箱"
            aria-label="删除当前插接箱"
          >删除</button>
        </div>
        <div class="sequence-extra">
          <div class="field">
            <label for="${escapeHtml(nameFieldId)}">插接箱名称</label>
            <input
              id="${escapeHtml(nameFieldId)}"
              name="${escapeHtml(nameFieldId)}"
              type="text"
              data-path="devices.plug_boxes.${route}.sequence.${index}.box_name"
              data-cast="optional-text"
              value="${escapeHtml(nameValue)}"
              placeholder="${escapeHtml(defaultNamePlaceholder)}"
              autocomplete="off"
            />
          </div>
          <div class="sequence-meta">${escapeHtml(meta)}</div>
        </div>
      </div>
    </details>
  `;
}

function renderRouteWorkspace() {
  renderRouteSection("A", refs.routeSectionA);
  renderRouteSection("B", refs.routeSectionB);
}

function renderExtensionSection() {
  const collapsed = isSectionCollapsed("extension");
  const extensions = currentExtensions();
  const cabinetPreview = singleCabinetAddressPreview();
  const repeaterToggleId = "extensions-repeater-enabled";
  const cabinetToggleId = "extensions-single-cabinet-enabled";
  const cabinetRouteDataToggleId = "extensions-single-cabinet-route-data";
  const cabinetTotalPowerEnergyToggleId = "extensions-single-cabinet-total-power-energy";
  const alarmToggleId = "extensions-alarm-state-word-enabled";
  const alarmLegacyOrderToggleId = "extensions-alarm-state-word-legacy-order";
  const isTwoColumn = screenColumnCount() === 2;
  const repeaterSummary = extensions.repeater.enabled
    ? isTwoColumn
      ? `一列 A${formatNumber(repeaterColumnCount(1, "A", extensions))}/B${formatNumber(repeaterColumnCount(1, "B", extensions))} · 二列 A${formatNumber(repeaterColumnCount(2, "A", extensions))}/B${formatNumber(repeaterColumnCount(2, "B", extensions))}`
      : `A ${formatNumber(repeaterColumnCount(1, "A", extensions))} / B ${formatNumber(repeaterColumnCount(1, "B", extensions))}`
    : "未启用";
  const cabinetSummary = extensions.single_cabinet.enabled
    ? isTwoColumn
      ? `一列 ${formatNumber(singleCabinetColumnCount(1, extensions))} · 二列 ${formatNumber(singleCabinetColumnCount(2, extensions))}${extensions.single_cabinet.include_route_data ? " · 含 A/B 单路" : ""}${extensions.single_cabinet.include_total_power_energy ? " · 含整屏 P/E" : ""}`
      : `${formatNumber(singleCabinetColumnCount(1, extensions))} 机柜${extensions.single_cabinet.include_route_data ? " · 含 A/B 单路" : ""}${extensions.single_cabinet.include_total_power_energy ? " · 含整屏 P/E" : ""}`
    : "未启用";
  const alarmSummary = extensions.alarm_state_word.enabled
    ? `${formatNumber(extensions.alarm_state_word.base_address)} / ${extensions.alarm_state_word.word_mode}${extensions.alarm_state_word.legacy_slide_rail_order ? " · 旧滑轨顺序" : ""}`
    : "未启用";
  const cabinetAddressLabel = cabinetPreview.enabled
    ? cabinetPreview.mode === "fixed"
      ? `固定 ${cabinetPreview.startAddress}`
      : cabinetPreview.mode === "derived-confirmed"
        ? `自动 ${cabinetPreview.startAddress}`
      : `预估 ${cabinetPreview.startAddress}`
    : "未启用";
  setSectionVisualState(refs.extensionSection, collapsed, "extension");
  refs.extensionSection.innerHTML = `
    ${renderSectionHead("扩展项", "按需启用", "", {
      sectionKey: "extension",
      summary: `<span>单机柜 ${escapeHtml(cabinetSummary)}</span><span>中继 ${escapeHtml(repeaterSummary)}</span><span>报警 ${escapeHtml(alarmSummary)}</span>`,
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="extension-step step-body"><div class="extension-options">
            <section class="extension-option extension-option--cabinet ${extensions.single_cabinet.enabled ? "is-enabled" : ""}">
              <label class="toggle-line" for="${cabinetToggleId}">
                 <span><strong>单机柜数据</strong><em>增加每柜汇总数据</em></span>
                <input id="${cabinetToggleId}" name="${cabinetToggleId}" type="checkbox" data-path="extensions.single_cabinet.enabled" ${extensions.single_cabinet.enabled ? "checked" : ""} />
              </label>
              ${extensions.single_cabinet.enabled ? `
                <div class="field-grid extension-option__fields">
                  ${isTwoColumn
                    ? `<div class="cabinet-column-count-grid">
                         ${numberField("第一列机柜数量", "extensions.single_cabinet.column_counts.column_1", singleCabinetColumnCount(1, extensions), 0)}
                         ${numberField("第二列机柜数量", "extensions.single_cabinet.column_counts.column_2", singleCabinetColumnCount(2, extensions), 0)}
                       </div>`
                    : spanWrap(numberField("机柜数量", "extensions.single_cabinet.column_counts.column_1", singleCabinetColumnCount(1, extensions), 0), 4)}
                  ${spanWrap(numberField("单机柜数据基址", "extensions.single_cabinet.base_address", extensions.single_cabinet.base_address, 0), 4)}
                  ${spanWrap(`<div class="summary-list">
                    <div class="summary-row"><span>起始寄存器</span><strong><code>${exportHtmlNumber(cabinetPreview.startAddress)}</code></strong></div>
                    <div class="summary-row"><span>地址方式</span><strong>${escapeHtml(cabinetPreview.mode === "fixed" ? "固定" : "系统自动推导")}</strong></div>
                    <div class="summary-row"><span>每柜占用</span><strong>${escapeHtml(`${formatNumber(cabinetPreview.perCabinetRegisters)} 寄存器`)}</strong></div>
                    ${cabinetPreview.screenTotalRegisters ? `<div class="summary-row"><span>整屏汇总</span><strong>${formatNumber(cabinetPreview.screenTotalRegisters)} 寄存器</strong></div>` : ""}
                  </div>`, 4)}
                  ${measurementLayoutMode() === "by_branch" ? `
                    ${spanWrap(numberField("和电流 IA 基址", "extensions.single_cabinet.metric_base_addresses.IA", extensions.single_cabinet.metric_base_addresses?.IA, 0), 3)}
                    ${spanWrap(numberField("和功率 PA 基址", "extensions.single_cabinet.metric_base_addresses.PA", extensions.single_cabinet.metric_base_addresses?.PA, 0), 3)}
                    ${spanWrap(numberField("和电能 EA 基址", "extensions.single_cabinet.metric_base_addresses.EA", extensions.single_cabinet.metric_base_addresses?.EA, 0), 3)}
                    ${spanWrap(numberField("通电状态 KA 基址", "extensions.single_cabinet.metric_base_addresses.KA", extensions.single_cabinet.metric_base_addresses?.KA, 0), 3)}
                  ` : ""}
                </div>
                <div class="cabinet-upload-options" aria-label="单机柜上传内容">
                  <label class="cabinet-upload-option" for="${cabinetRouteDataToggleId}">
                    <span><strong>上传单路数据</strong><em>每柜保留总值，并增加 A 路、B 路电流 / 功率 / 电能</em></span>
                    <input id="${cabinetRouteDataToggleId}" name="${cabinetRouteDataToggleId}" type="checkbox" data-path="extensions.single_cabinet.include_route_data" ${extensions.single_cabinet.include_route_data ? "checked" : ""} />
                  </label>
                  <label class="cabinet-upload-option cabinet-upload-option--total" for="${cabinetTotalPowerEnergyToggleId}">
                    <span><strong>上传总功率和总电能</strong><em>在全部单机柜数据后追加整屏汇总变量 P、E</em></span>
                    <input id="${cabinetTotalPowerEnergyToggleId}" name="${cabinetTotalPowerEnergyToggleId}" type="checkbox" data-path="extensions.single_cabinet.include_total_power_energy" ${extensions.single_cabinet.include_total_power_energy ? "checked" : ""} />
                  </label>
                </div>
                <div class="muted-note">${escapeHtml(cabinetPreview.note)}</div>` : ""}
            </section>

            <section class="extension-option extension-option--repeater ${extensions.repeater.enabled ? "is-enabled" : ""}">
              <label class="toggle-line" for="${repeaterToggleId}">
                 <span><strong>中继</strong><em>增加中继设备与页签</em></span>
                <input id="${repeaterToggleId}" name="${repeaterToggleId}" type="checkbox" data-path="extensions.repeater.enabled" ${extensions.repeater.enabled ? "checked" : ""} />
              </label>
              ${extensions.repeater.enabled ? `
                <div class="field-grid extension-option__fields">
                  ${isTwoColumn
                    ? `${spanWrap(numberField("第一列 A 路", "extensions.repeater.columns.column_1.A_count", repeaterColumnCount(1, "A", extensions), 0), 3)}
                       ${spanWrap(numberField("第一列 B 路", "extensions.repeater.columns.column_1.B_count", repeaterColumnCount(1, "B", extensions), 0), 3)}
                       ${spanWrap(numberField("第二列 A 路", "extensions.repeater.columns.column_2.A_count", repeaterColumnCount(2, "A", extensions), 0), 3)}
                       ${spanWrap(numberField("第二列 B 路", "extensions.repeater.columns.column_2.B_count", repeaterColumnCount(2, "B", extensions), 0), 3)}`
                    : `${spanWrap(numberField("A 路数量", "extensions.repeater.columns.column_1.A_count", repeaterColumnCount(1, "A", extensions), 0), 3)}
                       ${spanWrap(numberField("B 路数量", "extensions.repeater.columns.column_1.B_count", repeaterColumnCount(1, "B", extensions), 0), 3)}`}
                  ${spanWrap(numberField("中继地址基址", "extensions.repeater.base_address", extensions.repeater.base_address, 0), 3)}
                  ${spanWrap(textField("设备名称", "extensions.repeater.alias", extensions.repeater.alias, { placeholder: "中继器" }), 3)}
                </div>` : ""}
            </section>

            <section class="extension-option extension-option--alarm ${extensions.alarm_state_word.enabled ? "is-enabled" : ""}">
              <label class="toggle-line" for="${alarmToggleId}">
                 <span><strong>报警状态字</strong><em>生成报警页与上传代码</em></span>
                <input id="${alarmToggleId}" name="${alarmToggleId}" type="checkbox" data-path="extensions.alarm_state_word.enabled" ${extensions.alarm_state_word.enabled ? "checked" : ""} />
              </label>
              ${extensions.alarm_state_word.enabled ? `
                <div class="field-grid extension-option__fields">
                  ${spanWrap(numberField("报警起始地址", "extensions.alarm_state_word.base_address", extensions.alarm_state_word.base_address, 0), 6)}
                  ${spanWrap(selectField("报警字模式", "extensions.alarm_state_word.word_mode", extensions.alarm_state_word.word_mode, [
                    { value: "16bit", label: "16 位报警字" },
                    { value: "32bit", label: "32 位报警字" },
                  ], "value"), 6)}
                </div>
                <label class="alarm-order-option" for="${alarmLegacyOrderToggleId}">
                  <span><strong>启用旧滑轨模板顺序</strong><em>调整频率与电压报警序号；插接箱温度仅判断入线接点</em></span>
                  <input id="${alarmLegacyOrderToggleId}" name="${alarmLegacyOrderToggleId}" type="checkbox" data-path="extensions.alarm_state_word.legacy_slide_rail_order" ${extensions.alarm_state_word.legacy_slide_rail_order ? "checked" : ""} />
                </label>` : `<div class="muted-note">关闭后协议不包含报警状态页，报警代码文件将标记为不适用。</div>`}
            </section>
          </div>
          <div class="step-actions">
            <button class="button button--primary" type="button" data-action="jump-section" data-section="project">预览全部参数</button>
            <span class="muted-note">单机柜起始地址：${escapeHtml(cabinetAddressLabel)}</span>
          </div></div>`
     }
  `;
}

function computeWarnings() {
  const warnings = [];
  const addressProfile = currentAddressProfile();
  const cabinetPreview = singleCabinetAddressPreview();

  const repeaterCount =
    Number(state.config.devices.repeater_units.A_count || 0) +
    Number(state.config.devices.repeater_units.B_count || 0);
  if (
    state.config.devices.repeater_units.enabled &&
    repeaterCount > 0 &&
    addressProfile.repeater_base == null
  ) {
    warnings.push("当前地址规则无法分配中继起始地址，请检查中继参数后再生成。");
  }

  if (
    state.config.devices.single_cabinet_aggregation.enabled &&
    Number(state.config.devices.single_cabinet_aggregation.cabinet_count || 0) > 0 &&
    addressProfile.cabinet_base == null
  ) {
    warnings.push(
      cabinetPreview.startAddress != null
        ? `单机柜起始地址将按当前布局自动推导（当前预估 ${cabinetPreview.startAddress}，生成结果为最终值）。`
        : "单机柜起始地址将在生成时自动推导。",
    );
  }

  return [...new Set(warnings)];
}

function exportHtmlNumber(value) {
  return escapeHtml(value == null ? "-" : String(value));
}

function renderLiveSummary() {
  if (!refs.liveSummary) {
    return;
  }
  const addressProfile = currentAddressProfile();
  const extensions = currentExtensions();
  const warnings = computeWarnings();
  const cabinetPreview = singleCabinetAddressPreview();
  const totalsA = routeTotals("A");
  const totalsB = routeTotals("B");
  const sheetOrder = expectedSheetOrder();
  const previewFileName = expectedDeliveryFileNames().excel;
  const screenModeLabel = optionText(
    state.bootstrap.options.screen_topology_modes,
    state.config.topology.screen_topology_mode,
  );
  const hardwareLabel = currentHardwareForm()?.label || state.config.topology.hardware_form_factor;
  const environmentPort = state.config.topology.environment_rs485_port;
  const currentHash = currentConfigHash();
  const cabinetConfig = state.config.devices?.single_cabinet_aggregation || {};
  const cabinetNeedsBackendPreview =
    Boolean(cabinetConfig.enabled) && Number(cabinetConfig.cabinet_count || 0) > 0 && addressProfile?.cabinet_base == null;
  const previewFailed = Boolean(state.previewError) && state.previewErrorHash === currentHash;
  const previewConfirmed = Boolean(currentPreviewSummary());
  const previewPending = isCurrentPreviewPending();
  const syncState = state.result && !state.resultStale
    ? { label: "生成已确认", className: "is-confirmed" }
    : previewPending
      ? { label: "正在计算", className: "is-working" }
      : previewFailed
        ? { label: "预览失败", className: "is-error" }
        : cabinetNeedsBackendPreview && previewConfirmed
          ? { label: "后端已确认", className: "is-confirmed" }
          : { label: "结构预估", className: "is-estimated" };
  const sheetTabs = sheetOrder
    .slice(0, 4)
    .map((sheet, index) => `<span class="workbook-tab ${index === 0 ? "is-active" : ""}">${escapeHtml(sheet)}</span>`)
    .join("");
  const branchMode = measurementLayoutMode() === "by_branch";
  const metricLabels = branchMode ? ["监控模块", "板卡", "输出分路"] : ["插接箱", "板卡", "回路"];
  const metricValues = (totals) => branchMode
    ? [totals.modules, totals.boards, totals.branches]
    : [totals.physicalBoxes, totals.boards, totals.branches];
  const routeScopes = configuredRouteScopes();
  const structureRows = branchMode
    ? routeScopes.flatMap(({ route, column }) => moduleSequenceForRoute(route, column).map((item) => {
        const layout = layoutOption(item.type_code, item.layout_pattern);
        return `<div class="structure-row is-route-${route.toLowerCase()}"><span>${escapeHtml(routeColumnLabel(route, column))}</span><strong>${escapeHtml(item.type_code)}</strong><em>${escapeHtml(layout?.short_label || item.layout_pattern)} · ${formatNumber(item.count)} 个</em></div>`;
      }))
    : routeScopes.flatMap(({ route, column }) => (routeDeviceRoot(state.config, column).plug_boxes?.[route]?.sequence || []).slice(0, 2).map((item) => `<div class="structure-row is-route-${route.toLowerCase()}"><span>${escapeHtml(routeColumnLabel(route, column))}</span><strong>${escapeHtml(item.type_code)}</strong><em>${escapeHtml(item.layout_pattern)} · ${formatNumber(item.count || 1)} 个</em></div>`));
  const totalsRows = routeScopes.map(({ route, column }) => {
    const totals = routeColumnTotals(route, column);
    return `<div class="workbook-grid__row"><strong>${escapeHtml(routeColumnLabel(route, column))}</strong>${metricValues(totals).map((value) => `<span>${formatNumber(value)}</span>`).join("")}</div>`;
  }).join("");
  refs.liveSummary.innerHTML = `
    <div class="workbook-preview" data-testid="live-workbook-preview">
      <div class="workbook-preview__bar">
        <div class="workbook-file-icon" aria-hidden="true">Excel</div>
        <div class="workbook-preview__title">
          <strong>${escapeHtml(previewFileName)}</strong>
          <span>${escapeHtml(`${sheetOrder.length || 0} 个工作表 · ${branchMode ? "按监控模块" : "按插接箱"}`)}</span>
        </div>
        <span class="workbook-sync-dot ${syncState.className}">${escapeHtml(syncState.label)}</span>
      </div>
      <div class="workbook-grid" aria-label="工作簿结构预览">
        <div class="workbook-grid__header">
          <span>区域</span>${metricLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
        </div>
        ${totalsRows}
        <div class="structure-preview">${structureRows.slice(0, 8).join("") || `<div class="structure-row is-empty"><em>配置设备后显示结构明细</em></div>`}</div>
        <div class="workbook-grid__meta">
          <span>屏内结构</span><strong>${escapeHtml(screenModeLabel)}</strong>
          <span>设备形态</span><strong>${escapeHtml(hardwareLabel)}</strong>
          <span>动环 485</span><strong>${escapeHtml(environmentPort)}</strong>
          <span>母线数据</span><strong>${escapeHtml(busDataModeLabel())}</strong>
          <span>报警基址</span><strong><code>${exportHtmlNumber(extensions.alarm_state_word?.enabled ? extensions.alarm_state_word.base_address : null)}</code></strong>
          <span>单机柜起始</span><strong><code>${exportHtmlNumber(cabinetPreview.startAddress)}</code></strong>
        </div>
      </div>
      <div class="workbook-tabs">
        ${sheetTabs || `<span class="workbook-tab is-active">等待模板</span>`}
        ${sheetOrder.length > 4 ? `<span class="workbook-tab workbook-tab--more">+${formatNumber(sheetOrder.length - 4)}</span>` : ""}
      </div>
      <div class="workbook-preview__note">结构预览用于确认页签和规模，最终内容以生成文件为准。</div>
    </div>
    <div class="preview-facts">
      <div><span>遥测组织</span><strong>${branchMode ? "按监控模块" : "按插接箱"}</strong></div>
      <div><span>${branchMode ? "总输出分路" : "总回路"}</span><strong>${formatNumber(totalsA.branches + totalsB.branches)}</strong></div>
      <div><span>端口分配</span><strong>${escapeHtml(`${environmentPort} 动环 · ${busDataPortSummary()}`)}</strong></div>
    </div>
    ${
      warnings.length
        ? `<div class="warning-list warning-list--preview">${warnings
            .map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`)
            .join("")}</div>`
        : `<div class="preview-ready"><strong>当前配置无地址预警</strong></div>`
    }
    ${previewFailed ? `<div class="preview-error" role="status">地址预览暂不可用：${escapeHtml(state.previewError)}</div>` : ""}
    <div class="aside-actions">
      <button class="section-tool" type="button" data-action="jump-section" data-section="routeA">检查 A 路</button>
      <button class="section-tool" type="button" data-action="jump-section" data-section="routeB">检查 B 路</button>
    </div>
  `;
}

function renderResultRail() {
  if (!refs.resultRail) {
    return;
  }
  if (!state.result) {
    refs.resultRail.innerHTML = `<div class="empty-state">未生成</div>`;
    return;
  }
  const validation = getValidation();
  const sourceCompare = getSourceCompare();
  const delivery = getDeliveryStatus();
  const protocolDiff = getProtocolDiffSummary();
  const sourceProtocol = getSourceProtocolSummary();
  const reviewItems = reviewItemsFromResult();
  const excelFileName = fileNameFromPath(state.result?.artifacts?.excel_path || "") || "生成结果.xlsx";
  const alarmCodeFileName = fileNameFromPath(state.result?.artifacts?.alarm_code_path || "") || "报警状态字上传代码.txt";
  const programUploadFileName = fileNameFromPath(state.result?.artifacts?.program_upload_path || "") || "MCGS动环上传设备导入.csv";
  const routeSummaries = Array.isArray(state.result.summary?.route_summaries) ? state.result.summary.route_summaries : [];
  const totalPoints = formatNumber(routeSummaries.reduce((sum, item) => sum + Number(item.point_count || 0), 0));
  const sheetCount = formatNumber(state.result.summary?.sheet_order?.length || 0);
  const deliveryTitle = delivery?.label || deliveryLabel(delivery);
  const deliveryFileCount = [
    state.result.downloads.excel,
    state.result.downloads.alarm_code,
    state.result.downloads.program_upload,
  ].filter(Boolean).length;
  refs.resultRail.innerHTML = `
    <div class="summary-list">
      <div class="summary-row"><span>这版能否发给客户</span><strong>${escapeHtml(deliveryTitle)}</strong></div>
      <div class="summary-row"><span>三文件完整性</span><strong>${escapeHtml(`${deliveryFileCount} / 3`)}</strong></div>
      <div class="summary-row"><span>业务规则校验</span><strong>${escapeHtml(validationLabel(validation))}</strong></div>
      <div class="summary-row"><span>总点位数</span><strong>${escapeHtml(totalPoints)}</strong></div>
    </div>
    <div class="pill-row" style="margin-top: 12px;">
      ${state.resultStale ? `<span class="status-pill is-working">显示上次成功结果</span>` : ""}
      <span class="status-pill ${validation?.status === "passed" ? "is-success" : validation?.status ? "is-error" : ""}">
        ${escapeHtml(validationLabel(validation))}
      </span>
      <span class="status-pill ${verdictClass(sourceCompare?.verdict || sourceCompare?.overall_status)}">
        ${escapeHtml(verdictLabel(sourceCompare?.verdict || sourceCompare?.overall_status))}
      </span>
      <span class="status-pill">${escapeHtml(`${sheetCount} 页`)}</span>
      <span class="status-pill ${reviewItems.length ? "is-working" : "is-success"}">${escapeHtml(reviewItems.length ? `${formatNumber(reviewItems.length)} 项复核` : "无额外复核")}</span>
    </div>
    <div class="link-group delivery-bundle">
      <a class="download-link delivery-bundle__item" href="${state.result.downloads.excel}" download="${escapeHtml(excelFileName)}" data-action="download-artifact" data-download-label="${state.resultStale ? "上次成功动环协议表" : "动环协议表"}" data-download-filename="${escapeHtml(excelFileName)}">${state.resultStale ? "下载上次动环协议表" : "下载动环协议表"}</a>
      ${state.result.downloads.alarm_code ? `<a class="download-link delivery-bundle__item" href="${state.result.downloads.alarm_code}" download="${escapeHtml(alarmCodeFileName)}" data-action="download-artifact" data-download-label="报警状态字上传代码" data-download-filename="${escapeHtml(alarmCodeFileName)}">下载报警状态字上传代码</a>` : `<span class="download-link delivery-bundle__item is-disabled">报警状态字上传代码未生成</span>`}
      ${state.result.downloads.program_upload ? `<a class="download-link delivery-bundle__item" href="${state.result.downloads.program_upload}" download="${escapeHtml(programUploadFileName)}" data-action="download-artifact" data-download-label="MCGS 动环上传设备导入 CSV" data-download-filename="${escapeHtml(programUploadFileName)}">下载 MCGS 设备导入表</a>` : `<span class="download-link delivery-bundle__item is-disabled">MCGS 设备导入表未生成</span>`}
    </div>
  `;
}


function renderResultSection() {
  const collapsed = isSectionCollapsed("result");
  setSectionVisualState(refs.resultSection, collapsed, "result");
  if (!state.result) {
    refs.resultSection.innerHTML = `
      ${renderSectionHead("交付", "生成三份文件", "", {
        sectionKey: "result",
        summary: "<span>三文件交付包待生成</span>",
        collapsed,
      })}
      ${
        collapsed
          ? ""
          : state.tone === "error" && state.message
            ? `<div class="alert-panel is-error">
                <strong>生成失败</strong>
                <p>${escapeHtml(state.message)}</p>
              </div>`
            : `<div class="delivery-bundle delivery-bundle--empty">
                <div class="delivery-bundle__item"><strong>动环通讯协议表</strong><span>.xlsx</span></div>
                <div class="delivery-bundle__item"><strong>报警状态字上传代码</strong><span>.txt</span></div>
                <div class="delivery-bundle__item"><strong>MCGS 动环上传设备导入表</strong><span>.csv</span></div>
                <button class="button button--primary" type="button" data-action="quick-generate" ${state.busy ? "disabled" : ""}>${state.busy ? "正在生成三份文件…" : "生成三份交付文件"}</button>
              </div>`
      }
    `;
    return;
  }

  const validation = getValidation();
  const sourceCompare = getSourceCompare();
  const qualitySummary = getQualitySummary();
  const delivery = getDeliveryStatus();
  const readiness = getDeliveryReadiness();
  const protocolDiff = getProtocolDiffSummary();
  const sourceProtocol = getSourceProtocolSummary();
  const selectedProfiles = getSelectedProfiles();
  const addressCards = getAddressCards();
  const reviewItems = reviewItemsFromResult();
  const excelPath = state.result.artifacts.excel_path || "";
  const excelFileName = fileNameFromPath(excelPath) || excelPath || "生成结果.xlsx";
  const alarmCodePath = state.result.artifacts?.alarm_code_path || "";
  const alarmCodeFileName = fileNameFromPath(alarmCodePath) || "报警状态字上传代码.txt";
  const alarmCodeStatus = state.result.alarm_codegen?.status || "";
  const alarmCodeMessage = state.result.alarm_codegen?.message || "";
  const programUploadPath = state.result.artifacts?.program_upload_path || "";
  const programUploadFileName = fileNameFromPath(programUploadPath) || "MCGS动环上传设备导入.csv";
  const programUploadStatus = state.result.program_upload?.status || state.result.summary?.program_upload?.status || "";
  const programUploadMessage = state.result.program_upload?.message || state.result.summary?.program_upload?.message || "";
  const programUploadPointCount = state.result.program_upload?.point_count || state.result.summary?.program_upload?.point_count;
  const scenarioLabel = scenarioLabelFromSummary(state.result.summary);
  const deliveryTitle = delivery?.label || deliveryLabel(delivery);
  const deliveryTone = deliveryToneClass(delivery, validation, sourceCompare);
  const routeSummaries = Array.isArray(state.result.summary.route_summaries) ? state.result.summary.route_summaries : [];
  const routeTagLine = routeSummaries
    .map((item) => `${item.route} ${formatNumber(item.board_count)}板 / ${formatNumber(item.branch_count)}回路`)
    .join(" · ");
  const sheetCount = formatNumber(state.result.summary.sheet_order?.length || 0);
  const totalPoints = formatNumber(routeSummaries.reduce((sum, item) => sum + Number(item.point_count || 0), 0));
  const sourceFile = qualitySummary?.source_compare_source_file || sourceCompare?.source_workbook?.file_name || "-";
  const templatePlan = state.result.summary.template_plan || {};
  const baselineTemplatePlan = state.result.summary.baseline_template_plan || {};
  const primaryDelta =
    firstMeaningfulItem([
      protocolDiff?.variant_changes,
      protocolDiff?.sheet_changes,
      protocolDiff?.template_changes,
      protocolDiff?.address_changes,
    ]) || "";
  const highlightDiff =
    primaryDelta ||
    protocolDiff?.focus_items?.[0] ||
    firstMeaningfulItem([protocolDiff?.alarm_changes]) ||
    protocolDiff?.overview ||
    "当前方案与标准模板接近。";
  const sourceHeadline =
    firstMeaningfulItem([
      sourceProtocol?.protocol_items,
      sourceProtocol?.layout_items,
    ]) ||
    sourceProtocol?.customer_message ||
    sourceProtocol?.overview ||
    "未返回参考口径摘要。";
  const deliveryNote = state.resultStale
    ? "当前配置已修改；若要获得最新三文件交付包，请先重新生成。当前仍可下载上次成功结果作比对。"
    : delivery?.customer_message || "三份交付文件已生成。";
  const staleNote = state.resultStale
    ? `<div class="alert-panel is-working">
         <strong>当前保留上次成功结果</strong>
         <p>${
           state.tone === "error" && state.message
             ? `本次生成失败：${escapeHtml(state.message)}`
             : "配置已修改，请重新生成以刷新 Excel 与校验结果。"
         }</p>
       </div>`
    : "";

  const readinessChecks = readiness?.checks || {};
  const qualitySummaryItems = [
    {
      label: "外发判断",
      value: deliveryTitle,
      detail: delivery?.safe_to_send === false ? "不可直接外发" : delivery?.requires_review ? "外发前建议抽查" : "可按项目流程外发",
      tone: deliveryTone,
    },
    {
      label: "文件结构",
      value: readinessChecks.file_structure?.label || "未评估",
      detail: readinessChecks.file_structure?.detail || "未返回说明",
      tone: readinessToneClass(readinessChecks.file_structure?.status),
    },
    {
      label: "点表结构",
      value: readinessChecks.protocol_content?.label || "未评估",
      detail: readinessChecks.protocol_content?.detail || "未返回说明",
      tone: readinessToneClass(readinessChecks.protocol_content?.status),
    },
    {
      label: "三文件完整性",
      value: `${[state.result.downloads.excel, state.result.downloads.alarm_code, state.result.downloads.program_upload].filter(Boolean).length} / 3`,
      detail: "协议表、报警代码与 MCGS 设备导入表",
      tone: [state.result.downloads.excel, state.result.downloads.alarm_code, state.result.downloads.program_upload].filter(Boolean).length === 3 ? "is-success" : "is-working",
    },
    {
      label: "人工复核",
      value: reviewItems.length ? `${formatNumber(reviewItems.length)} 项` : "无",
      detail: reviewItems[0] || "当前没有必须额外说明的人工复核项。",
      tone: reviewItems.length ? "is-working" : "is-success",
    },
  ];
  const qualitySummaryMarkup = `
    <section class="customer-quality-summary" aria-label="质量摘要">
      <div class="customer-quality-summary__head">
        <span>质量摘要</span>
        <em>下载前先看这 5 项</em>
      </div>
      <div class="result-signoff-strip">
        ${qualitySummaryItems
          .map(
            (item) => `
              <div class="result-signoff-item ${item.tone || ""}">
                <span>${escapeHtml(item.label)}</span>
                <strong>${escapeHtml(item.value)}</strong>
                <em>${escapeHtml(item.detail)}</em>
              </div>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
  const focusItems = uniqueValues(reviewItems);
  const deliveryActionMarkup = focusItems.length
    ? `<div class="artifact-card__action-list">
         <span>建议先看</span>
         <ul>
           ${focusItems.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
         </ul>
       </div>`
    : "";

  const detailRows = [
    { label: "项目", value: state.result.summary.project_name || "-" },
    { label: "项目编号", value: state.result.summary.project_code || "-" },
    { label: "方案类型", value: scenarioLabel },
    { label: "导出页面", value: state.result.summary.sheet_order.join(" / ") || "-" },
    { label: "生成时间", value: state.result.created_at || "-" },
    {
      label: "综合 / 结构 / 版式",
      value: `${scoreValue(qualitySummary?.overall_score || sourceCompare?.overall_score)} / ${scoreValue(qualitySummary?.structure_score || sourceCompare?.structure_score)} / ${scoreValue(qualitySummary?.format_score || sourceCompare?.format_score)}`,
    },
    {
      label: "主数据尾地址后一个地址",
      value: exportHtmlNumber(state.result.summary.address_summary.main_next_address),
      code: true,
    },
    ...(Number(state.result.summary.single_cabinet_rows || 0) > 0
      ? [
          {
            label: "单机柜起始",
            value: exportHtmlNumber(state.result.summary.single_cabinet_start_address),
            code: true,
          },
        ]
      : []),
    {
      label: "报警基址",
      value: exportHtmlNumber(state.result.summary.address_summary.alarm_base),
      code: true,
    },
    { label: "内部参考源", value: sourceFile },
    ...routeSummaries.map((item) => ({
      label: `${item.route} 路`,
      value: `${formatNumber(item.board_count)} 板卡 / ${formatNumber(item.branch_count)} 输出 / ${formatNumber(item.point_count)} 点`,
    })),
  ];
  const detailGrid = `
    <div class="result-grid" style="margin-top: 18px;">
      ${detailRows
        .map(
          (item) => `
            <div class="result-row">
              <span>${escapeHtml(item.label)}</span>
              <strong>${item.code ? `<code>${item.value}</code>` : escapeHtml(item.value)}</strong>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
  const detailWarnings = reviewItems.length
    ? `<div class="warning-list" style="margin-top: 16px;">
         ${reviewItems.map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`).join("")}
       </div>`
    : `<div class="muted-note" style="margin-top: 16px;">当前没有必须额外说明的人工复核项。</div>`;
  const detailLinks = `
    <div class="link-group ${isBasicMode() ? "link-group--compact" : ""}" style="margin-top: 16px;">
      <a class="download-link" href="${state.result.downloads.input}" download="input-config.json" data-action="download-artifact" data-download-label="本次配置" data-download-filename="input-config.json" aria-label="下载本次配置">本次配置</a>
      <a class="download-link" href="${state.result.downloads.json}" download="canonical-output.json" data-action="download-artifact" data-download-label="结构明细" data-download-filename="canonical-output.json" aria-label="下载结构明细">结构明细</a>
      ${state.result.downloads.program_upload ? `<a class="download-link" href="${state.result.downloads.program_upload}" download="${escapeHtml(programUploadFileName)}" data-action="download-artifact" data-download-label="程序上传点表 CSV" data-download-filename="${escapeHtml(programUploadFileName)}" aria-label="下载程序上传点表 CSV">程序上传点表 CSV</a>` : ""}
      ${state.result.downloads.alarm_code ? `<a class="download-link" href="${state.result.downloads.alarm_code}" download="${escapeHtml(alarmCodeFileName)}" data-action="download-artifact" data-download-label="报警代码" data-download-filename="${escapeHtml(alarmCodeFileName)}" aria-label="下载报警代码">报警代码</a>` : ""}
      ${state.result.downloads.delivery ? `<a class="download-link" href="${state.result.downloads.delivery}" download="delivery-summary.json" data-action="download-artifact" data-download-label="交付说明 JSON（内部）" data-download-filename="delivery-summary.json" aria-label="下载交付说明 JSON（内部）">交付说明 JSON（内部）</a>` : ""}
      ${state.result.downloads.validation ? `<a class="download-link" href="${state.result.downloads.validation}" download="validation-report.json" data-action="download-artifact" data-download-label="检查结果（内部）" data-download-filename="validation-report.json" aria-label="下载检查结果（内部）">检查结果（内部）</a>` : ""}
      ${state.result.downloads.compare ? `<a class="download-link" href="${state.result.downloads.compare}" download="source-compare.json" data-action="download-artifact" data-download-label="参考源对照明细（内部）" data-download-filename="source-compare.json" aria-label="下载参考源对照明细（内部）">参考源对照明细（内部）</a>` : ""}
    </div>
    ${!state.result.downloads.program_upload && programUploadStatus && programUploadStatus !== "skipped" && programUploadMessage ? `<div class="muted-note" style="margin-top: 12px;">程序上传点表：${escapeHtml(programUploadMessage)}</div>` : ""}
    ${!state.result.downloads.alarm_code && alarmCodeStatus && alarmCodeStatus !== "skipped" && alarmCodeMessage ? `<div class="muted-note" style="margin-top: 12px;">报警代码：${escapeHtml(alarmCodeMessage)}</div>` : ""}
  `;
  const detailPath = `
    <div class="artifact-card__meta-line artifact-card__meta-line--path" style="margin-top: 16px;">
      <span>文件路径</span>
      <code title="${escapeHtml(state.result.artifacts.excel_path)}">${escapeHtml(state.result.artifacts.excel_path)}</code>
    </div>
  `;
  const templateSnapshotMarkup = [
    renderProfileSnapshotCard("Excel 页面结构", selectedProfiles?.export_profile),
    renderProfileSnapshotCard("关键地址排布", selectedProfiles?.address_profile),
    renderProfileSnapshotCard("始端箱采集项", selectedProfiles?.start_box_template),
    renderProfileSnapshotCard("插接箱采集项", selectedProfiles?.plug_branch_template),
    (state.result.summary.totals?.repeater_count || state.result.summary.sheet_order?.includes("中继器")) && selectedProfiles?.repeater_template?.id
      ? renderProfileSnapshotCard("中继采集项", selectedProfiles.repeater_template)
      : "",
    state.result.summary.totals?.single_cabinet_count && selectedProfiles?.single_cabinet_template?.id
      ? renderProfileSnapshotCard("单机柜采集项", selectedProfiles.single_cabinet_template)
      : "",
  ]
    .filter(Boolean)
    .join("");
  const canDownloadExcel = delivery?.downloadable !== false && Boolean(state.result.downloads.excel);
  const safeToSend = delivery?.safe_to_send === true || (delivery?.status === "deliverable" && delivery?.safe_to_send !== false);
  const requiresReview =
    delivery?.requires_review === true ||
    ["deliverable_with_review", "review_required"].includes(delivery?.status);
  const primaryArtifactLabel = !canDownloadExcel
    ? "暂不能下载，先处理阻塞项"
    : state.resultStale
      ? "下载上次动环协议表"
      : safeToSend
        ? "下载动环协议表（可外发）"
        : requiresReview
          ? "下载动环协议表（抽查后外发）"
          : "下载动环协议表（内部复核版）";
  const heroEyebrow = state.resultStale
    ? "当前保留上次成功结果"
    : !canDownloadExcel
      ? "暂不建议下载"
      : safeToSend
        ? "三文件交付包已生成"
        : requiresReview
          ? "三文件已生成，建议抽查"
          : "三文件已生成，需内部复核";
  const primaryDownloadControl = canDownloadExcel
    ? `<a
          class="button button--primary"
          href="${state.result.downloads.excel}"
          download="${escapeHtml(excelFileName)}"
          data-action="download-artifact"
          data-download-label="${state.resultStale ? "上次成功动环协议表" : "动环协议表"}"
          data-download-filename="${escapeHtml(excelFileName)}"
        >${escapeHtml(primaryArtifactLabel)}</a>`
    : `<button class="button button--primary" type="button" disabled>${escapeHtml(primaryArtifactLabel)}</button>`;
  const deliveryFiles = [
    { label: "动环协议表", fileName: excelFileName, ready: Boolean(state.result.downloads.excel) },
    { label: "报警状态字上传代码", fileName: alarmCodeFileName, ready: Boolean(state.result.downloads.alarm_code) },
    { label: "MCGS 设备导入表", fileName: programUploadFileName, ready: Boolean(state.result.downloads.program_upload) },
  ];
  const readyDeliveryFileCount = deliveryFiles.filter((item) => item.ready).length;
  const resultHero = `
    <div class="delivery-hero ${deliveryTone}">
      <div class="delivery-hero__main">
        <span class="artifact-card__eyebrow">${escapeHtml(heroEyebrow)}</span>
        <h3>${escapeHtml(deliveryTitle)}</h3>
        <p>${escapeHtml(deliveryNote)}</p>
        <div class="artifact-card__meta-pills">
          ${Object.entries(readiness?.checks || {})
            .map(
              ([key, item]) => `<span class="artifact-mini-pill ${readinessToneClass(item?.status)}">${escapeHtml(`${({ file_structure: "结构", protocol_content: "三文件", format_alignment: "参数" }[key] || "检查")}${({ pass: "通过", warn: "待抽查", fail: "未通过" }[item?.status] || "未评估")}`)}</span>`,
            )
            .join("")}
          ${state.resultStale ? `<span class="artifact-mini-pill is-working">上次成功结果</span>` : ""}
        </div>
        ${deliveryActionMarkup}
      </div>
      <div class="delivery-hero__actions delivery-bundle">
        ${primaryDownloadControl}
        ${
          state.result.downloads.alarm_code
            ? `<a class="button button--ghost delivery-bundle__item" href="${state.result.downloads.alarm_code}" download="${escapeHtml(alarmCodeFileName)}" data-action="download-artifact" data-download-label="报警状态字上传代码" data-download-filename="${escapeHtml(alarmCodeFileName)}">下载报警状态字上传代码</a>`
            : `<button class="button button--ghost delivery-bundle__item" type="button" disabled>报警状态字上传代码未生成</button>`
        }
        ${
          state.result.downloads.program_upload
            ? `<a class="button button--ghost delivery-bundle__item" href="${state.result.downloads.program_upload}" download="${escapeHtml(programUploadFileName)}" data-action="download-artifact" data-download-label="MCGS 动环上传设备导入 CSV" data-download-filename="${escapeHtml(programUploadFileName)}">下载 MCGS 设备导入表</a>`
            : `<button class="button button--ghost delivery-bundle__item" type="button" disabled>MCGS 设备导入表未生成</button>`
        }
        <button class="button button--ghost" type="button" data-action="jump-section" data-section="quality">内部复核</button>
        <div class="summary-list">
          <div class="summary-row"><span>Excel 文件</span><strong>${escapeHtml(excelFileName)}</strong></div>
          <div class="summary-row"><span>导出页面</span><strong>${escapeHtml(`${sheetCount} 页`)}</strong></div>
          <div class="summary-row"><span>总点位数</span><strong>${escapeHtml(totalPoints)}</strong></div>
            ${programUploadPointCount ? `<div class="summary-row"><span>MCGS 设备导入表</span><strong>${escapeHtml(`${formatNumber(programUploadPointCount)} 点`)}</strong></div>` : ""}
          <div class="summary-row"><span>生成时间</span><strong>${escapeHtml(state.result.created_at || "-")}</strong></div>
          ${routeTagLine ? `<div class="summary-row"><span>两路规模</span><strong>${escapeHtml(routeTagLine)}</strong></div>` : ""}
        </div>
      </div>
    </div>
  `;
  const evidenceStrip = `
    <div class="delivery-evidence-strip">
      <div class="delivery-evidence-item">
        <span>运行编号</span>
        <strong>${escapeHtml(state.result.run_id || "-")}</strong>
        <em>本次生成结果的唯一标识</em>
      </div>
      <div class="delivery-evidence-item">
        <span>出表路径</span>
        <strong>${escapeHtml(templatePlan.render_variant_label || templatePlan.render_variant_id || "-")}</strong>
        <em>${escapeHtml(templatePlan.render_variant_id || "当前导出路径")}</em>
      </div>
      <div class="delivery-evidence-item">
        <span>标准基线</span>
        <strong>${escapeHtml(baselineTemplatePlan.reference_label || baselineTemplatePlan.render_variant_label || baselineTemplatePlan.render_variant_id || "-")}</strong>
        <em>${escapeHtml(baselineTemplatePlan.render_variant_id || "默认标准模板")}</em>
      </div>
      <div class="delivery-evidence-item">
        <span>内部参考源</span>
        <strong>${escapeHtml(sourceFile)}</strong>
        <em>${escapeHtml(sourceCompare?.checked_at || state.result.created_at || "-")}</em>
      </div>
    </div>
  `;
  const supportDetailsMarkup = `
    <details class="artifact-debug artifact-debug--panel delivery-review__details">
      <summary>
        <span>内部复核材料</span>
        <em>${escapeHtml(reviewItems.length ? `${formatNumber(reviewItems.length)} 项待确认` : "需要时展开")}</em>
      </summary>
      <div class="surface-strip surface-strip--secondary delivery-review__internal">
        <section class="rail-panel">
          <div class="panel-head">
                    <span>本次模板与采集项</span>
            <span class="status-pill">${escapeHtml(scenarioLabel)}</span>
          </div>
          ${templateSnapshotMarkup ? `<div class="profile-snapshot-grid">${templateSnapshotMarkup}</div>` : `<div class="muted-note">未返回模板快照</div>`}
        </section>
        <section class="rail-panel">
          <div class="panel-head">
            <span>人工确认项</span>
            <span class="status-pill ${reviewItems.length ? "is-working" : "is-success"}">${escapeHtml(reviewItems.length ? `${formatNumber(reviewItems.length)} 项` : "无")}</span>
          </div>
          ${detailWarnings}
        </section>
        <section class="rail-panel">
          <div class="panel-head">
                    <span>内部留档文件</span>
            <span class="status-pill">${escapeHtml(excelFileName)}</span>
          </div>
          <div class="muted-note">三份业务文件都属于正式交付包；JSON 与校验明细仅用于内部留档。</div>
          ${detailLinks}
        </section>
      </div>
      ${evidenceStrip}
      ${detailGrid}
      ${detailPath}
    </details>
  `;

  refs.resultSection.innerHTML = `
    ${renderSectionHead(
        "06 生成交付",
      "",
      isBasicMode()
        ? ""
        : `<button class="section-tool" type="button" data-action="preview-json">${state.jsonPreview ? "刷新 JSON" : "JSON 预览"}</button>`,
      {
        sectionKey: "result",
        summary: `<span>${escapeHtml(deliveryTitle)}</span><span>${escapeHtml(state.result.created_at || "-")}</span>`,
        collapsed,
      },
    )}
    ${
      collapsed
        ? ""
        : `${staleNote}
            ${resultHero}
             ${qualitySummaryMarkup}
             <div class="surface-strip delivery-review">
               <section class="rail-panel delivery-review__rules">
                 <div class="panel-head">
                   <span>业务规则校验</span>
                   <span class="status-pill ${validation?.status === "passed" ? "is-success" : "is-working"}">${escapeHtml(validationLabel(validation))}</span>
                 </div>
                 <div class="summary-list">
                   <div class="summary-row"><span>交付判断</span><strong>${escapeHtml(deliveryTitle)}</strong></div>
                   <div class="summary-row"><span>A/B 路规模</span><strong>${escapeHtml(routeTagLine || "未返回")}</strong></div>
                   <div class="summary-row"><span>总点位数</span><strong>${escapeHtml(totalPoints)}</strong></div>
                 </div>
               </section>
               <section class="rail-panel delivery-review__files">
                 <div class="panel-head">
                   <span>三文件完整性</span>
                   <span class="status-pill ${readyDeliveryFileCount === 3 ? "is-success" : "is-working"}">${escapeHtml(`${readyDeliveryFileCount} / 3`)}</span>
                 </div>
                 <div class="summary-list">
                   ${deliveryFiles.map((item) => `<div class="summary-row"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.ready ? item.fileName : "未生成")}</strong></div>`).join("")}
                 </div>
               </section>
               <section class="rail-panel delivery-review__structure">
                 <div class="panel-head">
                   <span>地址区段与页签</span>
                   <span class="status-pill">${escapeHtml(`${sheetCount} 页`)}</span>
                 </div>
                 <div class="summary-list">
                   <div class="summary-row"><span>页签</span><strong>${escapeHtml((state.result.summary.sheet_order || []).join("、") || "未返回")}</strong></div>
                   ${addressCards.map((card) => `<div class="summary-row"><span>${escapeHtml(card.label)}</span><strong>${escapeHtml(String(card.value ?? "-"))}</strong></div>`).join("")}
                 </div>
               </section>
               <section class="rail-panel delivery-review__manual">
                 <div class="panel-head">
                   <span>人工复核</span>
                   <span class="status-pill ${reviewItems.length ? "is-working" : "is-success"}">${escapeHtml(reviewItems.length ? `${formatNumber(reviewItems.length)} 项` : "无")}</span>
                 </div>
                 ${reviewItems.length ? `<ul class="change-list">${reviewItems.map((item) => `<li><span>${escapeHtml(item)}</span></li>`).join("")}</ul>` : `<div class="muted-note">当前没有必须额外确认的人工复核项。</div>`}
               </section>
           </div>
           ${supportDetailsMarkup}
           ${
             state.jsonPreview
               ? `<div class="field result-json-preview">
                   <label>结果 JSON</label>
                   <textarea readonly>${escapeHtml(state.jsonPreview)}</textarea>
                 </div>`
               : ""
           }`
    }
  `;
}



function renderQualitySection() {
  if (!refs.qualitySection) {
    return;
  }
  const validation = getValidation();
  const sourceCompare = getSourceCompare();
  const qualitySummary = getQualitySummary();
  const delivery = getDeliveryStatus();
  const readiness = getDeliveryReadiness();
  const overallScore = qualitySummary?.overall_score || sourceCompare?.overall_score;
  const collapsed = isSectionCollapsed("quality");
  setSectionVisualState(refs.qualitySection, collapsed, "quality");
  const summary = state.result
    ? `<span class="status-pill ${deliveryToneClass(delivery, validation, sourceCompare)}">${escapeHtml(delivery?.label || deliveryLabel(delivery))}</span><span class="status-pill ${validation?.status === "passed" ? "is-success" : validation?.status ? "is-error" : ""}">${escapeHtml(validationLabel(validation))}</span><span class="status-pill ${verdictClass(sourceCompare?.verdict || sourceCompare?.overall_status)}">${escapeHtml(verdictLabel(sourceCompare?.verdict || sourceCompare?.overall_status))}</span>`
    : "<span>生成后自动对照</span>";
  if (!state.result) {
    refs.qualitySection.innerHTML = `
      ${renderSectionHead("内部复核", "", "", {
        sectionKey: "quality",
        summary,
        collapsed,
      })}
      ${collapsed ? "" : `<div class="empty-state">${state.busy ? "校验中" : "未生成"}</div>`}
    `;
    return;
  }

  const sheetResults = Array.isArray(sourceCompare?.sheet_results) ? sourceCompare.sheet_results : [];
  const topFixes = Array.isArray(sourceCompare?.top_priority_fixes) ? sourceCompare.top_priority_fixes : [];
  const worstSheet = qualitySummary?.worst_sheet || sourceCompare?.score_summary?.worst_sheet;
  const readinessPanels = Object.entries(readiness?.checks || {})
    .map(([key, item]) => {
      const titles = {
        file_structure: "文件结构",
        protocol_content: "点表结构",
        format_alignment: "版式与参考模板差异",
      };
      return `
        <div class="insight-panel">
          <div class="panel-head">
            <span>${escapeHtml(titles[key] || key)}</span>
            <span class="status-pill ${readinessToneClass(item?.status)}">${escapeHtml(({ pass: "通过", warn: "建议抽查", fail: "需人工复核" }[item?.status] || "未评估"))}</span>
          </div>
          <div class="summary-list">
            <div class="summary-row"><span>结论</span><strong>${escapeHtml(item?.label || "未返回")}</strong></div>
            <div class="summary-row"><span>说明</span><strong>${escapeHtml(item?.detail || "未返回")}</strong></div>
          </div>
        </div>
      `;
    })
    .join("");

  refs.qualitySection.innerHTML = `
      ${renderSectionHead("内部复核", "技术留档", "", {
      sectionKey: "quality",
      summary,
      collapsed,
    })}
    ${
      collapsed
        ? ""
        : `<div class="insight-grid">
            ${readinessPanels}
            <div class="insight-panel">
              <div class="panel-head">
                <span>生成检查</span>
                <span class="status-pill ${validation?.status === "passed" ? "is-success" : validation?.status ? "is-error" : ""}">
                  ${escapeHtml(validationLabel(validation))}
                </span>
              </div>
              <div class="summary-list">
                <div class="summary-row"><span>状态</span><strong>${escapeHtml(validation?.message || "未返回")}</strong></div>
                <div class="summary-row"><span>校验时间</span><strong>${escapeHtml(validation?.checked_at || "-")}</strong></div>
                <div class="summary-row"><span>生成工作表</span><strong>${escapeHtml(state.result.summary.sheet_order.join(" / "))}</strong></div>
              </div>
            </div>
            <div class="insight-panel">
              <div class="panel-head">
                <span>参考源对照</span>
                <span class="status-pill ${verdictClass(sourceCompare?.verdict || sourceCompare?.overall_status)}">
                  ${escapeHtml(verdictLabel(sourceCompare?.verdict || sourceCompare?.overall_status))}
                </span>
                ${overallScore != null ? `<span class="status-pill ${scoreClass(overallScore)}">${escapeHtml(scoreValue(overallScore))}</span>` : ""}
              </div>
              <div class="summary-list">
                <div class="summary-row"><span>内部参考源</span><strong><code>${escapeHtml(qualitySummary?.source_compare_source_file || sourceCompare?.source_workbook?.file_name || "-")}</code></strong></div>
                <div class="summary-row"><span>综合评分</span><strong>${escapeHtml(scoreValue(qualitySummary?.overall_score || sourceCompare?.overall_score))}</strong></div>
                <div class="summary-row"><span>结构 / 版式</span><strong>${escapeHtml(scoreValue(qualitySummary?.structure_score || sourceCompare?.structure_score))} / ${escapeHtml(scoreValue(qualitySummary?.format_score || sourceCompare?.format_score))}</strong></div>
                <div class="summary-row"><span>页面顺序</span><strong>${sourceCompare?.sheet_order_match ? "一致" : "存在差异"}</strong></div>
              </div>
            </div>
            <div class="insight-panel">
              <div class="panel-head">
                <span>最弱页面</span>
                ${worstSheet ? `<span class="status-pill ${scoreClass(worstSheet?.overall_score)}">${escapeHtml(scoreValue(worstSheet?.overall_score))}</span>` : ""}
              </div>
              <div class="summary-list">
                <div class="summary-row"><span>工作表</span><strong>${escapeHtml(worstSheet?.sheet_name || worstSheet?.canonical_name || "-")}</strong></div>
                <div class="summary-row"><span>综合 / 版式</span><strong>${escapeHtml(scoreValue(worstSheet?.overall_score))} / ${escapeHtml(scoreValue(worstSheet?.format_score))}</strong></div>
                <div class="summary-row"><span>生成文件</span><strong><code>${escapeHtml(sourceCompare?.generated_workbook?.file_name || "-")}</code></strong></div>
              </div>
            </div>
          </div>
          ${
            topFixes.length
              ? `<div class="compare-list" style="margin-top: 16px;">
                  ${topFixes
                    .slice(0, isBasicMode() ? 3 : 6)
                    .map(
                      (fix) => `
                        <div class="compare-row">
                          <div>
                            <strong>${escapeHtml(fix.sheet || fix.label || "-")}</strong>
                            <div class="compare-meta">${escapeHtml(fix.label || "-")} · ${escapeHtml(fix.note || "-")}</div>
                          </div>
                          <div class="compare-stats">
                            <span class="status-pill ${scoreClass(fix.score)}">${escapeHtml(scoreValue(fix.score))}</span>
                          </div>
                        </div>
                      `,
                    )
                    .join("")}
                </div>`
              : ""
          }
          ${
            sheetResults.length && !isBasicMode()
              ? `<div class="compare-list" style="margin-top: 16px;">
                  ${sheetResults
                    .map(
                      (item) => `
                        <div class="compare-row">
                          <div>
                            <strong>${escapeHtml(item.generated_sheet || item.source_sheet || item.canonical_name || "-")}</strong>
                            <div class="compare-meta">
                              结构 ${escapeHtml(scoreValue(item.structure_score))} · 版式 ${escapeHtml(scoreValue(item.format_score))} · Header ${exportHtmlNumber(item.source_header_row)} → ${exportHtmlNumber(item.generated_header_row)}
                            </div>
                            <div class="compare-meta">${escapeHtml((item.major_differences || []).slice(0, 2).join("；") || item.notes?.[0] || "-")}</div>
                          </div>
                          <div class="compare-stats">
                            <span class="status-pill ${verdictClass(item.status)}">${escapeHtml(verdictLabel(item.status))}</span>
                            <span class="status-pill ${scoreClass(item.overall_score)}">总分 ${escapeHtml(scoreValue(item.overall_score))}</span>
                          </div>
                        </div>
                      `,
                    )
                    .join("")}
                </div>`
              : isBasicMode()
              ? `<div class="muted-note" style="margin-top: 16px;">逐页结果可在对照文件中查看。</div>`
                : `<div class="muted-note">无对比</div>`
          }`
    }
  `;
}


function renderRecentRunsRail() {
  if (!refs.recentRunsRail) {
    return;
  }
  if (!state.recentRuns.length) {
    refs.recentRunsRail.innerHTML = `<div class="empty-state">无记录</div>`;
    return;
  }
  const unifiedWorkflow = state.config?.workflow_version === "unified_protocol_v1";
  refs.recentRunsRail.innerHTML = `
    <div class="run-list run-list--rail">
      ${state.recentRuns
        .slice(0, isBasicMode() ? 3 : 5)
        .map((item) => {
          const delivery = getDeliveryStatus(item);
          const active = isCurrentHistoryRun(item.run_id);
          return `
            <button class="run-card run-card--rail ${active ? "is-active" : ""}" type="button" data-action="open-run" data-run-id="${escapeHtml(item.run_id)}" aria-current="${active ? "true" : "false"}">
              <div class="run-card__top">
                <strong>${escapeHtml(runDisplayName(item))}</strong>
                <span class="run-card__time">${escapeHtml(item.created_at || "")}</span>
              </div>
              <div class="run-card__meta">
                <span>${escapeHtml(unifiedWorkflow ? "参数化生成记录" : scenarioLabelFromSummary(item.summary || item))}</span>
                <span class="status-pill ${deliveryToneClass(delivery, getValidation(item), getSourceCompare(item))}">
                  ${escapeHtml(delivery?.label || deliveryLabel(delivery))}
                </span>
                ${active ? '<span class="status-pill is-working">当前查看</span>' : ""}
              </div>
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderHistorySection() {
  const collapsed = isSectionCollapsed("history");
  const unifiedWorkflow = state.config?.workflow_version === "unified_protocol_v1";
  setSectionVisualState(refs.historySection, collapsed, "history");
  refs.historySection.innerHTML = `
    ${renderSectionHead(
      "最近记录",
      "",
      `<button class="section-tool" type="button" data-action="refresh-runs">刷新</button>`,
      {
        sectionKey: "history",
        summary: `<span>${formatNumber(state.recentRuns.length)} 条记录</span>`,
        collapsed,
      },
    )}
    ${
      collapsed
        ? ""
        : state.recentRuns.length
          ? `<div class="run-list">
              ${state.recentRuns
                .map((item) => {
                  const delivery = getDeliveryStatus(item);
                  const sourceCompare = getSourceCompare(item);
                  const active = isCurrentHistoryRun(item.run_id);
                  return `
                    <button class="run-card ${active ? "is-active" : ""}" type="button" data-action="open-run" data-run-id="${escapeHtml(item.run_id)}" aria-current="${active ? "true" : "false"}">
                      <div class="run-card__top">
                        <strong>${escapeHtml(runDisplayName(item))}</strong>
                        <span class="run-card__time">${escapeHtml(item.created_at || "")}</span>
                      </div>
                      <div class="run-card__meta">
                        <span>${escapeHtml(unifiedWorkflow ? "参数化生成记录" : scenarioLabelFromSummary(item.summary || item))}</span>
                        <span class="status-pill ${deliveryToneClass(delivery, getValidation(item), sourceCompare)}">
                          ${escapeHtml(delivery?.label || deliveryLabel(delivery))}
                        </span>
                        ${unifiedWorkflow ? "" : `<span class="status-pill ${verdictClass(sourceCompare?.verdict || sourceCompare?.overall_status)}">
                          ${escapeHtml(verdictLabel(sourceCompare?.verdict || sourceCompare?.overall_status))}
                        </span>`}
                        ${active ? '<span class="status-pill is-working">当前查看</span>' : ""}
                      </div>
                    </button>
                  `;
                })
                .join("")}
            </div>`
          : `<div class="empty-state">无记录</div>`
    }
  `;
}

function renderSectionByKey(key) {
  switch (key) {
    case "quickStart":
      renderQuickStart();
      break;
    case "project":
      renderProjectSection();
      break;
    case "topology":
      renderTopologySection();
      break;
    case "profiles":
      renderProfilesSection();
      break;
    case "routeA":
      renderRouteSection("A", refs.routeSectionA);
      break;
    case "routeB":
      renderRouteSection("B", refs.routeSectionB);
      break;
    case "extension":
      renderExtensionSection();
      break;
    case "result":
      renderResultSection();
      break;
    case "quality":
      renderQualitySection();
      break;
    case "history":
      renderHistorySection();
      break;
    default:
      break;
  }
}

function updateWorkspaceVisibility() {
  const activeStep = WORKFLOW_STEP_KEYS.includes(state.activeStep) ? state.activeStep : "quickStart";
  showElement(refs.quickStartSection, activeStep === "quickStart");
  showElement(refs.routeSectionA, activeStep === "routeA");
  showElement(refs.routeSectionB, activeStep === "routeB");
  showElement(refs.summaryStrip, Boolean(state.result));
  showElement(refs.projectSection, activeStep === "project");
  showElement(refs.topologySection, true);
  showElement(refs.profilesSection, false);
  showElement(refs.extensionSection, activeStep === "extension");
  showElement(refs.resultSection, activeStep === "result");
  showElement(refs.qualitySection, true);
  showElement(refs.historySection, true);
  showElement(refs.resultRail?.closest(".rail-panel"), Boolean(state.result));
  showElement(refs.recentRunsRail?.closest(".rail-panel"), state.recentRuns.length > 0);
  showElement(refs.liveSummary?.closest(".rail-panel"), true);
  showElement(refs.generateBtn, true);
  showElement(refs.railUtilityToggle, true);
  showElement(refs.railUtilityMenu, state.railUtilitiesOpen);
  showElement(refs.familySwitch, false);
  if (refs.railTemplateLabel) {
    showElement(refs.railTemplateLabel, false);
  }
  [
    refs.quickStartSection,
    refs.projectSection,
    refs.topologySection,
    refs.profilesSection,
    refs.routeSectionA,
    refs.routeSectionB,
    refs.extensionSection,
    refs.resultSection,
    refs.qualitySection,
    refs.historySection,
  ].forEach((element) => {
    if (element && !element.hasAttribute("tabindex")) {
      element.setAttribute("tabindex", "-1");
    }
  });
  renderDrawerState();
}

function renderAll() {
  hidePointsetPopover();
  ensureCollapsedSections();
  document.body.dataset.viewMode = state.viewMode;
  scheduleAddressPreview();
  renderStatus();
  renderFamilySwitch();
  renderQuickStart();
  renderSummaryStrip();
  renderProjectSection();
  renderTopologySection();
  renderProfilesSection();
  renderRouteWorkspace();
  renderExtensionSection();
  renderLiveSummary();
  renderResultRail();
  renderResultSection();
  renderQualitySection();
  renderRecentRunsRail();
  renderHistorySection();
  updateWorkspaceVisibility();
  renderWorkflowSpine();
  renderMobileActionBar();
  renderDrawerState();
  refreshLucideIcons();
  applyPendingFocus();
}

function formatDraftTimestamp(value) {
  if (!value) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function currentDraftMeta() {
  return {
    project_name: String(state.config?.project_name || "").trim() || "未命名项目",
    project_code: String(state.config?.project_code || "").trim() || "",
    scenario_label: currentScenarioGuide().title,
    saved_at: new Date().toISOString(),
  };
}

function persistDraftNow() {
  if (!state.config) {
    return;
  }
  const meta = currentDraftMeta();
  state.savedDraftMeta = {
    ...meta,
    saved_at_label: formatDraftTimestamp(meta.saved_at),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.config));
  localStorage.setItem(STORAGE_META_KEY, JSON.stringify(meta));
}

function saveDraft() {
  if (!state.config) {
    return;
  }
  state.savedDraft = clone(state.config);
  const meta = currentDraftMeta();
  state.savedDraftMeta = {
    ...meta,
    saved_at_label: formatDraftTimestamp(meta.saved_at),
  };
  if (state.draftSaveTimer) {
    window.clearTimeout(state.draftSaveTimer);
  }
  state.draftSaveTimer = window.setTimeout(() => {
    persistDraftNow();
    state.draftSaveTimer = null;
  }, 360);
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function loadDraftMeta() {
  try {
    const raw = localStorage.getItem(STORAGE_META_KEY);
    if (!raw) {
      return null;
    }
    const payload = JSON.parse(raw);
    return {
      ...payload,
      saved_at_label: formatDraftTimestamp(payload?.saved_at),
    };
  } catch {
    return null;
  }
}

function loadPreservedDraft() {
  try {
    const raw = localStorage.getItem(PRESERVED_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function loadPreservedDraftMeta() {
  try {
    const raw = localStorage.getItem(PRESERVED_DRAFT_META_KEY);
    if (!raw) {
      return null;
    }
    const payload = JSON.parse(raw);
    return {
      ...payload,
      saved_at_label: formatDraftTimestamp(payload?.saved_at),
      preserved_at_label: formatDraftTimestamp(payload?.preserved_at),
    };
  } catch {
    return null;
  }
}

function persistPreservedDraftNow() {
  if (!state.preservedDraft) {
    localStorage.removeItem(PRESERVED_DRAFT_KEY);
    localStorage.removeItem(PRESERVED_DRAFT_META_KEY);
    return;
  }
  const baseMeta = state.preservedDraftMeta || {};
  const meta = {
    ...baseMeta,
    saved_at: baseMeta.saved_at || new Date().toISOString(),
    preserved_at: baseMeta.preserved_at || new Date().toISOString(),
    source: "history_backup",
  };
  state.preservedDraftMeta = {
    ...meta,
    saved_at_label: formatDraftTimestamp(meta.saved_at),
    preserved_at_label: formatDraftTimestamp(meta.preserved_at),
  };
  localStorage.setItem(PRESERVED_DRAFT_KEY, JSON.stringify(state.preservedDraft));
  localStorage.setItem(PRESERVED_DRAFT_META_KEY, JSON.stringify(meta));
}

function clearPreservedDraft() {
  state.preservedDraft = null;
  state.preservedDraftMeta = null;
  localStorage.removeItem(PRESERVED_DRAFT_KEY);
  localStorage.removeItem(PRESERVED_DRAFT_META_KEY);
}

function preserveCurrentDraftBeforeHistory() {
  if (!state.savedDraft || state.openedRunMeta) {
    return false;
  }
  const meta = {
    ...(state.savedDraftMeta || currentDraftMeta()),
    preserved_at: new Date().toISOString(),
    source: "history_backup",
  };
  state.preservedDraft = clone(state.savedDraft);
  state.preservedDraftMeta = {
    ...meta,
    saved_at_label: state.savedDraftMeta?.saved_at_label || formatDraftTimestamp(meta.saved_at),
    preserved_at_label: formatDraftTimestamp(meta.preserved_at),
  };
  persistPreservedDraftNow();
  return true;
}

function restoreSavedDraft() {
  if (!state.savedDraft) {
    setMessage("没有可恢复的草稿", "error");
    renderStatus();
    return;
  }
  state.config = normalizeConfig(state.savedDraft);
  state.activeFamily = currentFamilyFromConfig();
  state.railUtilitiesOpen = false;
  clearResult();
  clearRecommendation();
  state.openedRunMeta = null;
  setMessage(
    state.savedDraftMeta?.saved_at_label
      ? `已恢复本地草稿（${state.savedDraftMeta.saved_at_label}）`
      : "已恢复本地草稿",
    "success",
  );
  renderAll();
}

function restorePreservedDraft() {
  if (!state.preservedDraft) {
    setMessage("没有可恢复的原本地草稿", "error");
    renderStatus();
    return;
  }
  state.config = normalizeConfig(state.preservedDraft);
  state.activeFamily = currentFamilyFromConfig();
  state.railUtilitiesOpen = false;
  clearResult();
  clearRecommendation();
  state.openedRunMeta = null;
  clearPreservedDraft();
  saveDraft();
  setMessage("已恢复原本地草稿", "success");
  renderAll();
}

function clearResult() {
  const hadResult = Boolean(state.result);
  state.jsonPreview = "";
  if (!hadResult) {
    state.result = null;
    state.resultStale = false;
    return;
  }
  state.resultStale = true;
}

function dropResult() {
  const hadResult = Boolean(state.result);
  state.result = null;
  state.lastGenerationSeconds = null;
  state.resultStale = false;
  state.jsonPreview = "";
  if (hadResult) {
    state.collapsedSections = collapsedDefaults(state.viewMode, false);
  }
}

function clearRecommendation() {
  state.recommendation = null;
  state.recommendationBusy = false;
}

async function loadRecentRuns() {
  const response = await apiFetch("/api/runs?limit=9");
  if (!response.ok) {
    throw new Error(`读取 runs 失败：${response.status}`);
  }
  const payload = await response.json();
  state.recentRuns = Array.isArray(payload.items) ? payload.items : [];
}

async function openRun(runId) {
  const requestId = ++state.openRunRequestId;
  setMessage("载入中", "working");
  renderStatus();
  try {
    const response = await apiFetch(`/api/runs/${runId}/manifest`);
    if (!response.ok) {
      throw new Error(`读取 run 失败：${response.status}`);
    }
    const manifest = await response.json();
    if (requestId !== state.openRunRequestId) {
      return;
    }
    const preserved = preserveCurrentDraftBeforeHistory() || Boolean(state.preservedDraft);
    state.result = manifest;
    state.lastGenerationSeconds = null;
    state.resultStale = false;
    if (state.result.downloads?.input) {
      const inputResponse = await apiFetch(state.result.downloads.input);
      if (requestId !== state.openRunRequestId) {
        return;
      }
      if (inputResponse.ok) {
        state.config = normalizeConfig(await inputResponse.json());
        resetSequenceDetailState();
        state.activeFamily = currentFamilyFromConfig();
      }
    }
    if (!getValidation(state.result) && state.result.downloads?.quality) {
      const qualityResponse = await apiFetch(state.result.downloads.quality);
      if (requestId !== state.openRunRequestId) {
        return;
      }
      if (qualityResponse.ok) {
        state.result.quality = await qualityResponse.json();
      }
    }
    state.collapsedSections = collapsedDefaults(state.viewMode, true);
    state.activeStep = "result";
    clearRecommendation();
    state.jsonPreview = "";
    state.openedRunMeta = {
      run_id: state.result.run_id || runId,
      project_name: state.result.summary?.project_name || state.result.project_name || "",
      created_at: state.result.created_at || "",
    };
    setMessage(
      preserved
        ? "已载入历史结果与当时配置（原本地草稿已单独保留）"
        : "已载入历史结果与当时配置",
      "success",
    );
  } catch (error) {
    if (requestId !== state.openRunRequestId) {
      return;
    }
    setMessage(error.message || String(error), "error");
  } finally {
    if (requestId !== state.openRunRequestId) {
      return;
    }
    renderAll();
    if (state.result) {
      focusSectionByKey("result", true);
    }
  }
}

function applyScenario(scenarioId, preserveCurrent = true, preserveIdentity = false) {
  const scenario = scenarioOptions().find((item) => item.id === scenarioId);
  const baseConfig =
    scenario?.config ||
    state.maps.familyDefaultConfigs[scenario?.example_key] ||
    state.maps.familyDefaultConfigs[scenario?.family];
  if (!baseConfig) {
    setMessage("未找到对应方案模板", "error");
    renderStatus();
    return;
  }
  const nextConfig = clone(baseConfig);
  if ((preserveCurrent || preserveIdentity) && state.config) {
    nextConfig.project_name = state.config.project_name;
    nextConfig.project_code = state.config.project_code;
    nextConfig.protocol_title = state.config.protocol_title;
  }
  if (preserveCurrent && state.config) {
    nextConfig.devices.start_boxes = clone(state.config.devices.start_boxes);
    nextConfig.devices.plug_boxes.A.sequence = clone(state.config.devices.plug_boxes.A.sequence);
    nextConfig.devices.plug_boxes.B.sequence = clone(state.config.devices.plug_boxes.B.sequence);
    nextConfig.devices.plug_boxes.A.board_number_start =
      state.config.devices.plug_boxes.A.board_number_start;
    nextConfig.devices.plug_boxes.B.board_number_start =
      state.config.devices.plug_boxes.B.board_number_start;
    nextConfig.devices.repeater_units = clone(state.config.devices.repeater_units);
    nextConfig.devices.single_cabinet_aggregation = clone(
      state.config.devices.single_cabinet_aggregation,
    );
    if (scenario.id === "classic_two_columns") {
      nextConfig.devices.repeater_units = clone(scenario.config.devices.repeater_units || {
        enabled: false,
        A_count: 0,
        B_count: 0,
      });
      nextConfig.devices.single_cabinet_aggregation = clone(
        scenario.config.devices.single_cabinet_aggregation || {
          enabled: false,
          cabinet_count: 0,
        },
      );
    }
  }
  state.config = normalizeConfig(nextConfig);
  resetSequenceDetailState();
  state.activeFamily = currentFamilyFromConfig();
  state.railUtilitiesOpen = false;
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage(`已切换到${scenario?.label || "所选方案"}`, "success");
  renderAll();
}

function updateField(path, rawValue, options = {}) {
  let value = rawValue;
  if (options.cast === "number") {
    value = Number(rawValue || 0);
  } else if (options.cast === "optional-number") {
    value = rawValue === "" ? null : Math.max(1, Number(rawValue || 0));
  } else if (options.cast === "optional-text") {
    value = String(rawValue || "").trim() || null;
  }
  if (options.transform === "names") {
    value = splitNames(rawValue);
  }

  setByPath(state.config, path, value);

  if (path.endsWith(".type_code")) {
    const basePath = path.replace(/\.type_code$/u, "");
    setByPath(state.config, basePath, normalizeSequenceItem(getByPath(state.config, basePath)));
  }

  state.config = normalizeConfig(state.config);
  state.activeFamily = currentFamilyFromConfig();
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
}

function handleBoundField(event, rerender = true) {
  const target = event.target.closest("[data-path]");
  if (!target) {
    return;
  }
  const path = target.dataset.path;
  const value = target.type === "checkbox" ? target.checked : target.value;
  updateField(path, value, {
    cast: target.dataset.cast,
    transform: target.dataset.transform,
  });
  if (rerender) {
    renderAll();
  } else {
    renderStatus();
  }
}

async function runGenerate() {
  const blockers = syncQuickSequencesForGenerate();
  if (blockers.length) {
    const firstBlocker = blockers[0];
    ensureCollapsedSections();
    if (WORKFLOW_STEP_KEYS.includes(firstBlocker.section)) {
      WORKFLOW_STEP_KEYS.forEach((stepKey) => {
        state.collapsedSections[stepKey] = stepKey !== firstBlocker.section;
      });
      state.activeStep = firstBlocker.section;
    } else {
      state.collapsedSections[firstBlocker.section] = false;
    }
    setMessage(firstBlocker.message, "error");
    renderAll();
    if (firstBlocker.selector) {
      queueFocus(firstBlocker.selector);
      applyPendingFocus();
    } else if (firstBlocker.section) {
      focusSectionByKey(firstBlocker.section, true);
    }
    return;
  }

  const requestId = ++state.generateRequestId;
  const requestConfigHash = currentConfigHash();
  const generateStartedAt = performance.now();
  const generateController = new AbortController();
  const generateTimeoutId = window.setTimeout(() => generateController.abort(), 180_000);
  state.busy = true;
  state.lastGenerationSeconds = null;
  state.jsonPreview = "";
  setMessage("正在生成三份文件；完整规模主要耗时在 Excel 排版，请勿关闭页面或重复点击。", "working");
  renderAll();
  const generateProgressId = window.setInterval(() => {
    if (requestId !== state.generateRequestId || !state.busy) {
      return;
    }
    const elapsedSeconds = Math.max(1, Math.floor((performance.now() - generateStartedAt) / 1000));
    setMessage(
      `正在生成三份文件，已用时 ${elapsedSeconds} 秒；完整规模通常约 20–30 秒，主要耗时在 Excel 排版，请勿重复点击。`,
      "working",
    );
  }, 1_000);
  let generated = false;
  try {
    const response = await apiFetch("/api/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ config: configForActiveMeasurementMode() }),
      signal: generateController.signal,
    });
    if (!response.ok) {
      throw new Error(await extractErrorDetail(response, `生成失败：${response.status}`));
    }
    const payload = await response.json();
    if (requestId !== state.generateRequestId) {
      return;
    }
    state.result = payload;
    state.lastGenerationSeconds = (performance.now() - generateStartedAt) / 1000;
    state.resultStale = currentConfigHash() !== requestConfigHash;
    state.collapsedSections = collapsedDefaults(state.viewMode, true);
    state.activeStep = "result";
    state.openedRunMeta = null;
    await loadRecentRuns();
    if (requestId !== state.generateRequestId) {
      return;
    }
    setMessage(
      state.resultStale
        ? "已生成，但你在生成过程中修改了配置；当前结果先保留作比对。"
        : `已生成，用时 ${state.lastGenerationSeconds.toFixed(1)} 秒`,
      state.resultStale ? "working" : "success",
    );
    generated = true;
  } catch (error) {
    if (requestId !== state.generateRequestId) {
      return;
    }
    if (state.result) {
      state.resultStale = true;
    }
    setMessage(
      error?.name === "AbortError"
        ? "生成超过 180 秒，已停止等待。服务端可能仍在收尾，请先查看最近记录，避免重复生成。"
        : error.message || String(error),
      "error",
    );
  } finally {
    window.clearTimeout(generateTimeoutId);
    window.clearInterval(generateProgressId);
    if (requestId !== state.generateRequestId) {
      return;
    }
    state.busy = false;
    renderAll();
    if (generated) {
      focusSectionByKey("result", true);
    }
  }
}

async function runRecommendation() {
  const requestId = ++state.recommendationRequestId;
  const requestConfigHash = currentConfigHash();
  state.recommendationBusy = true;
  setMessage("自动匹配中", "working");
  renderAll();
  let matched = false;
  try {
    const response = await apiFetch("/api/recommend", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ config: configForActiveMeasurementMode() }),
    });
    if (!response.ok) {
      throw new Error(await extractErrorDetail(response, `自动匹配失败：${response.status}`));
    }
    const payload = await response.json();
    if (requestId !== state.recommendationRequestId) {
      return;
    }
    if (requestConfigHash !== currentConfigHash()) {
      state.recommendation = null;
      setMessage("当前配置已变化，请重新自动匹配", "working");
      return;
    }
    state.recommendation = payload;
    ensureCollapsedSections();
    state.collapsedSections.profiles = false;
    setMessage("已匹配", "success");
    matched = true;
  } catch (error) {
    if (requestId !== state.recommendationRequestId) {
      return;
    }
    state.recommendation = null;
    setMessage(error.message || String(error), "error");
  } finally {
    if (requestId !== state.recommendationRequestId) {
      return;
    }
    state.recommendationBusy = false;
    renderAll();
    if (matched) {
      focusSectionByKey("profiles", true);
    }
  }
}

function applyRecommendation() {
  if (!state.recommendation?.recommended_config) {
    return;
  }
  state.config = normalizeConfig(state.recommendation.recommended_config);
  resetSequenceDetailState();
  state.activeFamily = currentFamilyFromConfig();
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage("已应用", "success");
  renderAll();
}

async function previewJson() {
  if (!state.result) {
    return;
  }
  setMessage("读取 JSON", "working");
  renderStatus();
  try {
    const response = await apiFetch(state.result.downloads.canonical);
    if (!response.ok) {
      throw new Error(`读取 JSON 失败：${response.status}`);
    }
    state.jsonPreview = JSON.stringify(await response.json(), null, 2);
    setMessage("JSON 就绪", "success");
  } catch (error) {
    setMessage(error.message || String(error), "error");
  } finally {
    renderAll();
  }
}

function downloadDraft() {
  const blob = new Blob([`${JSON.stringify(state.config, null, 2)}\n`], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "protocol-config.json";
  anchor.click();
  URL.revokeObjectURL(url);
  setMessage("已导出", "success");
}

async function importDraft(file) {
  const text = await file.text();
  const payload = JSON.parse(text);
  state.config = normalizeConfig(payload);
  state.railSelection = {};
  state.railEditorOpen = {};
  state.activeColumnByRoute = { A: 1, B: 1 };
  resetSequenceDetailState();
  state.activeFamily = currentFamilyFromConfig();
  state.railUtilitiesOpen = false;
  state.openedRunMeta = null;
  clearResult();
  clearRecommendation();
  saveDraft();
  setMessage("已导入", "success");
  renderAll();
}

function addSequence(route, typeCode = "3P*1", column = activeColumnForRoute(route)) {
  const sequence = routeDeviceRoot(state.config, column).plug_boxes[route].sequence;
  sequence.push(
    normalizeSequenceItem({
      type_code: typeCode,
      count: 1,
    }),
  );
  const newIndex = sequence.length - 1;
  setRailSelection(route, newIndex, 0, true, column);
  state.config = normalizeConfig(state.config);
  setSequenceExpanded(route, sequence.length - 1, true);
  clearResult();
  clearRecommendation();
  saveDraft();
  renderAll();
  queueFocus(`#rail-properties-${route}-${column}`);
  applyPendingFocus();
}

function removeSequence(route, index, column = activeColumnForRoute(route)) {
  const sequence = routeDeviceRoot(state.config, column).plug_boxes[route].sequence;
  sequence.splice(index, 1);
  setRailSelection(route, Math.max(0, Math.min(index, sequence.length - 1)), 0, false, column);
  resetSequenceDetailState(route);
  state.config = normalizeConfig(state.config);
  clearResult();
  clearRecommendation();
  saveDraft();
  renderAll();
}

document.addEventListener("click", async (event) => {
  const actionTrigger = event.target.closest("[data-action]");
  if (!actionTrigger) {
    return;
  }
  const { action } = actionTrigger.dataset;
  if (action === "select-pointset") {
    updateField(actionTrigger.dataset.path, actionTrigger.dataset.value || "");
    actionTrigger.closest("details")?.removeAttribute("open");
    hidePointsetPopover();
    renderAll();
  } else if (action === "switch-scenario") {
    applyScenario(actionTrigger.dataset.scenario, true);
  } else if (action === "switch-family") {
    applyScenario(actionTrigger.dataset.family, true);
  } else if (action === "switch-family-quick") {
    applyScenario(actionTrigger.dataset.family, false, true);
  } else if (action === "download-artifact") {
    await handleArtifactDownload(actionTrigger, event);
  } else if (action === "toggle-rail-utilities") {
    toggleRailUtilities();
  } else if (action === "open-drawer") {
    openDrawer(actionTrigger.dataset.drawer);
  } else if (action === "close-drawer") {
    closeDrawer();
  } else if (action === "set-view-mode") {
    setViewMode(actionTrigger.dataset.mode);
  } else if (action === "toggle-section") {
    toggleSection(actionTrigger.dataset.section);
  } else if (action === "jump-section") {
    jumpToSection(actionTrigger.dataset.section);
  } else if (action === "focus-route") {
    setActiveRoute(actionTrigger.dataset.route, true);
  } else if (action === "switch-route-tab") {
    setActiveRoute(actionTrigger.dataset.route, false);
  } else if (action === "set-measurement-mode") {
    setMeasurementMode(actionTrigger.dataset.mode);
  } else if (action === "set-screen-topology") {
    setScreenTopology(actionTrigger.dataset.mode);
  } else if (action === "set-hardware-form") {
    setHardwareForm(actionTrigger.dataset.value);
  } else if (action === "set-bus-data-mode") {
    setBusDataMode(actionTrigger.dataset.value);
  } else if (action === "set-route-column") {
    setActiveRouteColumn(
      actionTrigger.dataset.route || state.activeRoute,
      Number(actionTrigger.dataset.column || 1),
    );
  } else if (action === "select-rail-device") {
    const route = actionTrigger.dataset.route || state.activeRoute;
    const column = Number(actionTrigger.dataset.column || activeColumnForRoute(route));
    state.activeColumnByRoute[route] = column;
    setRailSelection(
      route,
      Number(actionTrigger.dataset.sourceIndex || 0),
      Number(actionTrigger.dataset.instanceIndex || 0),
      true,
      column,
    );
    state.activeRoute = route;
    renderAll();
    queueFocus(`#rail-properties-${route}-${column}`);
    applyPendingFocus();
  } else if (action === "close-rail-properties") {
    const route = actionTrigger.dataset.route || state.activeRoute;
    const column = Number(actionTrigger.dataset.column || activeColumnForRoute(route));
    state.railEditorOpen[routeScopeKey(route, column)] = false;
    renderAll();
    queueFocus(`[data-rail-key="${selectedRailKey(route, column)}"] .rail-device-card__select`);
    applyPendingFocus();
  } else if (action === "move-rail-item") {
    moveRailItem(
      actionTrigger.dataset.route || state.activeRoute,
      actionTrigger.dataset.mode,
      Number(actionTrigger.dataset.index),
      Number(actionTrigger.dataset.direction),
      Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)),
    );
  } else if (action === "remove-rail-device") {
    removeRailDevice(
      actionTrigger.dataset.route || state.activeRoute,
      actionTrigger.dataset.mode || "plug",
      Number(actionTrigger.dataset.index),
      Number(actionTrigger.dataset.instanceIndex || 0),
      Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)),
    );
  } else if (action === "copy-route-sequence") {
    copyRouteSequence(actionTrigger.dataset.source, actionTrigger.dataset.target);
  } else if (action === "add-module-sequence") {
    addModuleSequence(actionTrigger.dataset.route || state.activeRoute, actionTrigger.dataset.type || "3P*2", Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)));
  } else if (action === "remove-module-sequence") {
    removeModuleSequence(actionTrigger.dataset.route || state.activeRoute, Number(actionTrigger.dataset.index), Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)));
  } else if (action === "add-sequence") {
    addSequence(actionTrigger.dataset.route, "3P*1", Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route)));
  } else if (action === "apply-quick-sequence") {
    try {
      const route = actionTrigger.dataset.route || state.activeRoute;
      const column = Number(actionTrigger.dataset.column || activeColumnForRoute(route));
      const quickInput = document.querySelector(`[data-quick-sequence-input="${routeScopeKey(route, column)}"]`);
      applyQuickSequence(route, quickInput?.value || "", column);
    } catch (error) {
      const route = actionTrigger.dataset.route || state.activeRoute;
      const column = Number(actionTrigger.dataset.column || activeColumnForRoute(route));
      const message = error.message || String(error);
      setRouteQuickError(route, message, column);
      renderInlineQuickError(route, message, column);
      setMessage(message, "error");
      renderStatus();
    }
  } else if (action === "clear-route-sequence") {
    clearRouteSequence(actionTrigger.dataset.route || state.activeRoute, Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)));
  } else if (action === "add-sequence-type") {
    addSequence(actionTrigger.dataset.route || state.activeRoute, actionTrigger.dataset.type || "3P*1", Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route || state.activeRoute)));
  } else if (action === "expand-all-sequence") {
    const route = actionTrigger.dataset.route || state.activeRoute;
    setAllSequenceExpanded(route, true);
    renderAll();
  } else if (action === "collapse-all-sequence") {
    setAllSequenceExpanded(actionTrigger.dataset.route || state.activeRoute, false);
    renderAll();
  } else if (action === "remove-sequence") {
    removeSequence(actionTrigger.dataset.route, Number(actionTrigger.dataset.index), Number(actionTrigger.dataset.column || activeColumnForRoute(actionTrigger.dataset.route)));
  } else if (action === "quick-generate") {
    await runGenerate();
  } else if (action === "quick-recommend") {
    await runRecommendation();
  } else if (action === "recommend-profiles") {
    await runRecommendation();
  } else if (action === "apply-recommendation") {
    applyRecommendation();
  } else if (action === "preview-json") {
    await previewJson();
  } else if (action === "restore-draft") {
    restoreSavedDraft();
  } else if (action === "restore-preserved-draft") {
    restorePreservedDraft();
  } else if (action === "refresh-runs") {
    try {
      await loadRecentRuns();
      setMessage("已刷新", "success");
    } catch (error) {
      setMessage(error.message || String(error), "error");
    } finally {
      renderAll();
    }
  } else if (action === "open-run") {
    await openRun(actionTrigger.dataset.runId);
  }
});

document.addEventListener("pointerover", (event) => {
  const option = event.target.closest(".pointset-option[data-pointset-id]");
  if (!option || option.contains(event.relatedTarget)) {
    return;
  }
  showPointsetPopover(option, event);
});

document.addEventListener("pointermove", (event) => {
  if (
    !state.pointsetPopoverOption ||
    event.pointerType === "touch" ||
    !event.target.closest(".pointset-option[data-pointset-id]")
  ) {
    return;
  }
  positionPointsetPopover(event.clientX, event.clientY, state.pointsetPopoverOption);
});

document.addEventListener("pointerout", (event) => {
  const option = event.target.closest(".pointset-option[data-pointset-id]");
  if (!option || option.contains(event.relatedTarget)) {
    return;
  }
  if (!event.relatedTarget?.closest?.(".pointset-popover")) {
    schedulePointsetPopoverHide();
  }
});

document.addEventListener("focusin", (event) => {
  const option = event.target.closest(".pointset-option[data-pointset-id]");
  if (option) {
    showPointsetPopover(option);
  }
});

document.addEventListener("focusout", (event) => {
  const option = event.target.closest(".pointset-option[data-pointset-id]");
  if (option && !event.relatedTarget?.closest?.(".pointset-option, .pointset-popover")) {
    schedulePointsetPopoverHide();
  }
});

document.addEventListener("change", (event) => {
  handleBoundField(event, true);
});

document.addEventListener(
  "toggle",
  (event) => {
    const details = event.target;
    if (!(details instanceof HTMLDetailsElement) || !details.matches(".sequence-card[data-route][data-index]")) {
      return;
    }
    setSequenceExpanded(details.dataset.route, Number(details.dataset.index), details.open);
  },
  true,
);

document.addEventListener("input", (event) => {
  const quickInput = event.target.closest("[data-quick-sequence-input]");
  if (quickInput) {
    const route = quickInput.dataset.route || state.activeRoute;
    const column = Number(quickInput.dataset.column || activeColumnForRoute(route));
    const scopeKey = quickInput.dataset.quickSequenceInput || routeScopeKey(route, column);
    state.quickSequenceDrafts[scopeKey] = quickInput.value;
    if (routeQuickError(route, column)) {
      clearRouteQuickError(route, column);
      renderInlineQuickError(route, "", column);
    }
    renderStatus();
    return;
  }
  const target = event.target.closest("[data-path]");
  if (!target || target.type === "checkbox" || target.tagName === "SELECT") {
    return;
  }
  handleBoundField(event, false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.pointsetPopoverOption) {
    hidePointsetPopover();
  } else if (event.key === "Escape" && state.activeDrawer) {
    closeDrawer();
  } else if (event.key === "Escape" && state.railEditorOpen[routeScopeKey(state.activeRoute, activeColumnForRoute(state.activeRoute))]) {
    state.railEditorOpen[routeScopeKey(state.activeRoute, activeColumnForRoute(state.activeRoute))] = false;
    renderAll();
  } else if (event.key === "Escape" && state.railUtilitiesOpen) {
    state.railUtilitiesOpen = false;
    queueFocus("#railUtilityToggle");
    renderAll();
  }
});

function buildBlankUnifiedConfig() {
  const defaultScenario = scenarioOptions().find((item) => item.id === "classic_standard") || scenarioOptions()[0];
  const config = normalizeConfig(defaultScenario?.config || state.maps.familyDefaultConfigs.classic_combined);
  config.project_name = "";
  config.project_code = "";
  config.protocol_title = "上位机通讯协议";
  config.protocol_layout = {
    ...config.protocol_layout,
    measurement_layout_mode: "by_plug_box",
    base_sheet_name: "始端箱和插接箱",
    embed_single_cabinet_in_base_sheet: true,
    alarm_start_box_first: true,
  };
  config.topology = {
    ...config.topology,
    screen_topology_mode: SCREEN_MODE_SINGLE,
    columns_per_screen: 1,
    hardware_form_factor: "horizontal",
    environment_rs485_port: "A4B4",
    upload_port_profile: "A4B4",
    bus_data_port_mode: "single_column_shared",
    bus_data_port_assignments: { shared: "A2B2" },
  };
  ["A", "B"].forEach((route) => {
    config.devices.start_boxes[route].count = 1;
    config.devices.start_boxes[route].instance_names = defaultStartBoxNames(
      route,
      1,
      SCREEN_MODE_SINGLE,
      1,
    );
    config.devices.plug_boxes[route].sequence = [];
    config.devices.branch_modules[route] = {
      ...config.devices.branch_modules[route],
      module_sequence: [],
      variable_numbering_mode: BRANCH_NUMBERING_BOARD_SUFFIX,
      module_number_start: 1,
      output_number_start: 1,
      branch_device_number_start: route === "A" ? 101 : 201,
      names: [],
    };
    delete config.devices.branch_modules[route].module_count;
    delete config.devices.branch_modules[route].branches_per_module;
  });
  config.devices.screen_columns = {
    ...(config.devices.screen_columns || {}),
    column_2: createEmptyColumnDevices(2),
  };
  ["A", "B"].forEach((route) => {
    config.devices.screen_columns.column_2.start_boxes[route].count = 1;
    config.devices.screen_columns.column_2.start_boxes[route].instance_names =
      defaultStartBoxNames(route, 1, SCREEN_MODE_DOUBLE, 2);
  });
  config.extensions.repeater = {
    ...config.extensions.repeater,
    enabled: false,
    A_count: 0,
    B_count: 0,
    columns: {
      column_1: { A_count: 0, B_count: 0 },
      column_2: { A_count: 0, B_count: 0 },
    },
    base_address: 5500,
  };
  config.extensions.single_cabinet = {
    ...config.extensions.single_cabinet,
    enabled: false,
    cabinet_count: 0,
    column_counts: { column_1: 0, column_2: 0 },
    base_address: 7000,
    include_route_data: false,
    include_total_power_energy: false,
  };
  config.extensions.alarm_state_word = {
    ...config.extensions.alarm_state_word,
    enabled: true,
  };
  config.devices.repeater_units = {
    ...config.devices.repeater_units,
    ...config.extensions.repeater,
  };
  config.devices.single_cabinet_aggregation = {
    ...config.devices.single_cabinet_aggregation,
    ...config.extensions.single_cabinet,
  };
  return normalizeConfig(config);
}

refs.loadPresetBtn.addEventListener("click", () => {
  const confirmed = window.confirm("这会清空当前任务并恢复标准参数，是否继续？");
  if (!confirmed) {
    return;
  }
  state.config = buildBlankUnifiedConfig();
  state.railSelection = {};
  state.railEditorOpen = {};
  state.activeColumnByRoute = { A: 1, B: 1 };
  state.quickSequenceDrafts = {};
  state.collapsedSections = collapsedDefaults(state.viewMode, false);
  state.activeStep = "quickStart";
  dropResult();
  clearRecommendation();
  saveDraft();
  setMessage("已重置为新的协议生成任务", "success");
  renderAll();
});

refs.recoverDraftBtn?.addEventListener("click", () => {
  restoreSavedDraft();
});

refs.importJsonTrigger?.addEventListener("click", () => {
  refs.importJsonInput?.click();
});

refs.downloadDraftBtn.addEventListener("click", () => {
  downloadDraft();
});

refs.generateBtn.addEventListener("click", async () => {
  await runGenerate();
});

refs.importJsonInput.addEventListener("change", async (event) => {
  const [file] = event.target.files || [];
  if (!file) {
    return;
  }
  try {
    await importDraft(file);
  } catch (error) {
    setMessage(error.message || String(error), "error");
    renderStatus();
  } finally {
    refs.importJsonInput.value = "";
  }
});

async function init() {
  if (document.querySelector('meta[name="password-change-required"]')?.content === "true") {
    setMessage("请先完成首次登录密码更新", "working");
    refs.quickStartSection.innerHTML = '<div class="empty-state">更新密码后将自动载入工作台</div>';
    refs.resultSection.innerHTML = "";
    renderStatus();
    return;
  }
  try {
    const response = await apiFetch("/api/bootstrap");
    if (!response.ok) {
      throw new Error(`bootstrap 失败：${response.status}`);
    }
    state.bootstrap = await response.json();
    state.maps = buildMaps(state.bootstrap);
    state.recentRuns = Array.isArray(state.bootstrap.recent_runs) ? state.bootstrap.recent_runs : [];

    const draft = loadDraft();
    state.savedDraft = draft ? normalizeConfig(draft) : null;
    state.savedDraftMeta = loadDraftMeta();
    const preservedDraft = loadPreservedDraft();
    state.preservedDraft = preservedDraft ? normalizeConfig(preservedDraft) : null;
    state.preservedDraftMeta = loadPreservedDraftMeta();
    if (!state.savedDraftMeta && state.savedDraft) {
      state.savedDraftMeta = {
        project_name: String(state.savedDraft.project_name || "").trim() || "未命名项目",
        project_code: String(state.savedDraft.project_code || "").trim() || "",
        scenario_label: currentScenarioGuide(state.savedDraft).title,
        saved_at_label: "本地缓存",
      };
    }
    if (!state.preservedDraftMeta && state.preservedDraft) {
      state.preservedDraftMeta = {
        project_name: String(state.preservedDraft.project_name || "").trim() || "未命名项目",
        project_code: String(state.preservedDraft.project_code || "").trim() || "",
        scenario_label: currentScenarioGuide(state.preservedDraft).title,
        saved_at_label: "已保留",
        preserved_at_label: "已保留",
      };
    }
    state.config = buildBlankUnifiedConfig();
    state.collapsedSections = collapsedDefaults(state.viewMode, false);
    state.activeStep = "quickStart";
    state.activeFamily = currentFamilyFromConfig();
    await loadRecentRuns();
    setMessage(state.savedDraft ? "已连接 · 检测到本地草稿，可按需恢复" : "已连接", "success");
    renderAll();
  } catch (error) {
    setMessage(error.message || String(error), "error");
    refs.resultSection.innerHTML = `
      <div class="empty-state">${escapeHtml(error.message || String(error))}</div>
    `;
    renderStatus();
  }
}

window.addEventListener("beforeunload", () => {
  if (!state.draftSaveTimer) {
    return;
  }
  window.clearTimeout(state.draftSaveTimer);
  state.draftSaveTimer = null;
  persistDraftNow();
});

init();
