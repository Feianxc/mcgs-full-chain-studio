(function () {
  "use strict";

  const source = window.MCGS_SOURCE;
  const core = window.MCGS_WORKFLOW_CORE;
  const typeExtensionCore = window.MCGS_TYPE_EXTENSION_CORE;
  const typeExtensionSources = {
    ...(window.MCGS_TYPE_EXTENSION_SOURCES?.sources || {}),
    ...(window.MCGS_TYPE_EXTENSION_REFRESH_SOURCES?.sources || {}),
  };
  const root = document.getElementById("step-content");

  if (!source || !core) {
    root.innerHTML =
      '<div class="empty-state"><div><strong>结构化数据或业务内核未载入</strong><span>请确认 data.js、workflow-core.js 与 index.html 位于同一目录。</span></div></div>';
    return;
  }

  const TYPES = Object.fromEntries(
    source.typeMatrix.baseline_types.map((item) => [item.type_id, item]),
  );
  const BASELINE_TYPE_IDS = Object.keys(TYPES);
  const OWNERSHIP_BY_OBJECT = Object.fromEntries(
    source.runtimeModel.databaseOwnership.map((item) => [item.objectName, item]),
  );
  const DATABASE_BASELINE = Object.fromEntries(
    source.databaseChanges.map((item) => [item.object_name, item.before_value]),
  );
  const RECIPE_BASELINE = Object.fromEntries(
    source.recipe.fields.map((item) => [item.recipe_field, item.baseline_recipe_value]),
  );

  const STEPS = [
    {
      id: "recipe",
      label: "配方",
      title: "修改配方",
      description: "只显示当前项目与模板不同、并且需要亲手修改的字段。",
    },
    {
      id: "database",
      label: "数据库",
      title: "修改数据库初值",
      description: "这里只保留配方和启动脚本不会自动写入的对象。",
    },
    {
      id: "device",
      label: "设备",
      title: "设置设备与导入表",
      description: "只显示需要在设备窗口亲手完成的设置。",
    },
    {
      id: "jgdl",
      label: "机柜映射",
      title: "写入插接箱与机柜映射",
      description: "直接复制由第一页接线关系生成的JG_DL值。",
    },
    {
      id: "backend",
      label: "运行策略",
      title: "替换运行策略代码",
      description: "每张卡片都写清楚位置，并提供当前项目的完整代码。",
    },
    {
      id: "alarm",
      label: "报警",
      title: "替换报警相关代码",
      description: "只显示当前映射和上传方式实际需要替换的代码。",
    },
    {
      id: "window",
      label: "窗口",
      title: "修改用户窗口",
      description: "按目标窗口和控件编号执行，代码可以逐块复制。",
    },
  ];

  const state = {
    selectedStepId: "parameters",
    visited: new Set(["parameters"]),
    params: {},
    typesA: [],
    typesB: [],
    secondLoopTemperatureModes: {},
    protocolCatalog: core.normalizeProtocolCatalog(core.FALLBACK_PROTOCOL_TYPE_CATALOG),
    protocolCatalogStatus: "fallback",
    circuitMappings: {
      A: { A: {}, B: {} },
      B: { A: {}, B: {} },
    },
    dialogCode: "",
    dialogCopyMode: "whole",
    protocol: {
      status: "idle",
      signature: "",
      result: null,
      alarmCode: "",
      error: "",
    },
  };

  let copyCounter = 0;
  let copyStore = new Map();
  let codeStore = new Map();
  let toastTimer = null;

  const els = {
    workflowTrack: document.getElementById("workflow-track"),
    capacityRibbon: document.getElementById("capacity-ribbon"),
    form: document.getElementById("project-form"),
    headerProjectName: document.getElementById("header-project-name"),
    configurationView: document.getElementById("configuration-view"),
    executionView: document.getElementById("execution-view"),
    configurationStatus: document.getElementById("configuration-status"),
    configurationErrors: document.getElementById("configuration-errors"),
    returnToConfig: document.getElementById("return-to-config"),
    previousStep: document.getElementById("previous-step"),
    nextStep: document.getElementById("next-step"),
    stepPosition: document.getElementById("step-position"),
    columnBFields: document.getElementById("column-b-fields"),
    boxTypesA: document.getElementById("box-types-a"),
    boxTypesB: document.getElementById("box-types-b"),
    boxTypeA: document.getElementById("box-type-a"),
    boxTypeB: document.getElementById("box-type-b"),
    circuitMappingA: document.getElementById("circuit-mapping-a"),
    circuitMappingB: document.getElementById("circuit-mapping-b"),
    circuitStatusA: document.getElementById("circuit-status-a"),
    circuitStatusB: document.getElementById("circuit-status-b"),
    codeDialog: document.getElementById("code-dialog"),
    codeDialogTitle: document.getElementById("code-dialog-title"),
    codeDialogTarget: document.getElementById("code-dialog-target"),
    codeDialogMeta: document.getElementById("code-dialog-meta"),
    codeDialogContent: document.getElementById("code-dialog-content"),
    copyDialogCode: document.getElementById("copy-dialog-code"),
    closeCodeDialog: document.getElementById("close-code-dialog"),
    agentProjectSnapshot: document.getElementById("agent-project-snapshot"),
    toast: document.getElementById("toast"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function parseNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clampInt(value, min, max) {
    return Math.min(max, Math.max(min, Math.round(parseNumber(value, min))));
  }

  function formatValue(value, quoteStrings = false) {
    if (value === null || value === undefined) return "待确认";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "string") return quoteStrings ? `"${value}"` : value || "（空字符串）";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function assignmentValue(value) {
    if (typeof value === "string") return `"${value.replaceAll('"', '\\"')}"`;
    if (typeof value === "boolean") return value ? "1" : "0";
    if (value === null || value === undefined) return "待确认";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function registerCopy(text) {
    const key = `copy-${++copyCounter}`;
    copyStore.set(key, String(text));
    return key;
  }

  function copyButton(text, label = "复制", options = {}) {
    const key = registerCopy(text);
    const className = options.className || "button button-secondary button-small button-copy";
    const title = options.title ? ` title="${escapeHtml(options.title)}"` : "";
    return `<button type="button" class="${className}" data-copy-key="${key}"${title}>${escapeHtml(label)}</button>`;
  }

  async function copyText(text, successMessage = "已复制") {
    try {
      const activeElement = document.activeElement;
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      let copied = document.execCommand("copy");
      textarea.remove();
      if (activeElement instanceof HTMLElement) activeElement.focus();

      if (!copied && navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        copied = true;
      }
      if (!copied) throw new Error("clipboard copy failed");
      showToast(successMessage);
    } catch (error) {
      showToast("复制失败，请打开代码窗口后手动复制");
      console.error(error);
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    els.toast.textContent = message;
    els.toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => els.toast.classList.remove("is-visible"), 1800);
  }

  async function apiFetch(url, init = {}) {
    const method = String(init.method || "GET").toUpperCase();
    const headers = new Headers(init.headers || {});
    const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
    if (unsafe && !headers.has("X-CSRF-Token")) {
      const csrfToken =
        window.protocolSecurity?.csrfToken?.() ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
      if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
    }

    const response = await fetch(url, {
      cache: "no-store",
      ...init,
      headers,
    });

    if (response.status === 401) {
      window.location.replace("/login?reason=session_expired");
      const error = new Error("登录状态已失效，正在返回登录页");
      error.code = "auth_required";
      throw error;
    }

    if (response.status === 403) {
      const payload = await response.clone().json().catch(() => ({}));
      if (payload?.code === "password_change_required") {
        window.protocolSecurity?.requirePasswordChange?.();
        const error = new Error(payload.detail || "首次登录需要先修改密码");
        error.code = "password_change_required";
        throw error;
      }
      if (payload?.code === "csrf_invalid") {
        const error = new Error(payload.detail || "安全校验已失效，请刷新页面后重试");
        error.code = "csrf_invalid";
        throw error;
      }
    }

    return response;
  }

  function replacementSelection(typeId) {
    return String(state.params.typeReplacements?.[typeId] || "").trim();
  }

  function activeSlotIds() {
    const used = state.typesA.slice(0, state.params.boxCountA || 0);
    if (state.params.screenMode === "single_screen_double_column") {
      used.push(...state.typesB.slice(0, state.params.boxCountB || 0));
    }
    return Array.from(new Set(used));
  }

  function protocolDescriptorForType(typeId) {
    const baseline = core.PROTOCOL_TYPE_MAP[typeId] || core.PROTOCOL_TYPE_MAP["3x1P"];
    const replacement = core.parseProtocolSelection(replacementSelection(typeId));
    const target = replacement.typeCode && replacement.layoutPattern ? replacement : baseline;
    return core.protocolLayoutDescriptor(
      state.protocolCatalog,
      target.typeCode,
      target.layoutPattern,
    );
  }

  function getType(typeId) {
    const slotId = BASELINE_TYPE_IDS.includes(typeId) ? typeId : "3x1P";
    const baseline = TYPES[slotId] || TYPES["3x1P"];
    const descriptor = protocolDescriptorForType(slotId);
    const replacement = Boolean(replacementSelection(slotId));
    return {
      ...baseline,
      type_id: slotId,
      class_slot: slotId,
      display_name: replacement
        ? `${descriptor.typeCode} · ${descriptor.layoutLabel}`
        : slotId,
      board_count: descriptor.boardCount,
      output_branch_count: descriptor.branchCount,
      output_semantics:
        descriptor.phaseMode === "single_phase_triplet"
          ? "一块板卡的A/B/C三相分别作为三个单相输出"
          : `${descriptor.branchCount}个三相输出；${descriptor.layoutLabel}`,
      phase_mode: descriptor.phaseMode,
      protocol_type_code: descriptor.typeCode,
      protocol_layout_pattern: descriptor.layoutPattern,
      board_template_ids: descriptor.boardTemplateIds,
      electrical_branches: descriptor.branches,
      has_dual_loop_board: descriptor.hasDualLoopBoard,
      replacement,
      custom: replacement,
    };
  }

  function isSinglePhaseTriplet(typeId) {
    return getType(typeId).phase_mode === "single_phase_triplet";
  }

  function typeDisplayLabel(typeId) {
    const type = getType(typeId);
    return type.replacement
      ? `${typeId}槽 → ${type.protocol_type_code} / ${type.protocol_layout_pattern}`
      : typeId;
  }

  function activeTypeIds() {
    return [...BASELINE_TYPE_IDS];
  }

  function typeOptions(selected) {
    return activeTypeIds()
      .map((typeId) => {
        const type = getType(typeId);
        const isSelected = typeId === selected ? " selected" : "";
        return `<option value="${escapeHtml(typeId)}"${isSelected}>${escapeHtml(typeDisplayLabel(typeId))} · ${type.board_count}板/${type.output_branch_count}输出</option>`;
      })
      .join("");
  }

  function replacementOptions(slotId, selected) {
    const baseline = core.PROTOCOL_TYPE_MAP[slotId];
    const baselineText = `${baseline.typeCode} / ${baseline.layoutPattern}`;
    const groups = state.protocolCatalog
      .map((type) => {
        const options = type.allowed_layout_patterns
          .filter(
            (layout) =>
              core.protocolSelectionKey(type.type_code, layout.pattern) !==
              core.protocolSelectionKey(baseline.typeCode, baseline.layoutPattern),
          )
          .map((layout) => {
            const value = core.protocolSelectionKey(type.type_code, layout.pattern);
            return `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(layout.label)} · ${layout.board_count}板/${layout.branch_count}输出</option>`;
          })
          .join("");
        return options ? `<optgroup label="${escapeHtml(type.label)}">${options}</optgroup>` : "";
      })
      .join("");
    return `<option value=""${selected ? "" : " selected"}>保持模板 · ${escapeHtml(slotId)} = ${escapeHtml(baselineText)}</option>${groups}`;
  }

  function populateReplacementSelectors() {
    document.querySelectorAll("[data-replacement-slot]").forEach((select) => {
      const slotId = select.dataset.replacementSlot;
      const selected = replacementSelection(slotId);
      select.innerHTML = replacementOptions(slotId, selected);
      select.value = selected;
    });
    const count = BASELINE_TYPE_IDS.filter((slotId) => replacementSelection(slotId)).length;
    const summary = document.getElementById("type-replacement-count");
    if (summary) summary.textContent = count ? `${count}个槽已替换` : "保持四种模板类型";
    const sourceStatus = document.getElementById("protocol-catalog-status");
    if (sourceStatus) {
      const combinations = state.protocolCatalog.reduce(
        (sum, item) => sum + item.allowed_layout_patterns.length,
        0,
      );
      sourceStatus.textContent = `${state.protocolCatalog.length}种箱型 · ${combinations}种板卡组合 · ${state.protocolCatalogStatus === "live" ? "协议平台在线目录" : "内置验证目录"}`;
    }
  }

  function initializeTypeSelectors() {
    const mixed = '<option value="__mixed__" disabled>逐箱混合类型</option>';
    const selectedA = activeTypeIds().includes(els.boxTypeA.value) ? els.boxTypeA.value : "3x1P";
    const selectedB = activeTypeIds().includes(els.boxTypeB.value) ? els.boxTypeB.value : "3x1P";
    els.boxTypeA.innerHTML = mixed + typeOptions(selectedA);
    els.boxTypeB.innerHTML = mixed + typeOptions(selectedB);
    populateReplacementSelectors();
  }

  async function loadProtocolCatalog() {
    try {
      const response = await apiFetch("/api/bootstrap");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      state.protocolCatalog = core.normalizeProtocolCatalog(payload.box_types);
      state.protocolCatalogStatus = "live";
      initializeTypeSelectors();
      reconcileSecondLoopTemperatureModes();
      renderCircuitEditors();
      renderEverything();
    } catch (_error) {
      state.protocolCatalog = core.normalizeProtocolCatalog(core.FALLBACK_PROTOCOL_TYPE_CATALOG);
      state.protocolCatalogStatus = "fallback";
      populateReplacementSelectors();
    }
  }

  function emptyCircuitMappings() {
    return {
      A: { A: {}, B: {} },
      B: { A: {}, B: {} },
    };
  }

  function circuitKey(boxPosition, branchNo) {
    return `P${String(boxPosition).padStart(2, "0")}-R${String(branchNo).padStart(2, "0")}`;
  }

  function cabinetIndexFromId(cabinetId) {
    const match = String(cabinetId || "").match(/(\d+)$/);
    return match ? Number(match[1]) : 0;
  }

  function columnMappingConfig(columnKey) {
    const second = columnKey === "B";
    return {
      columnKey,
      label: second ? "第二物理列" : "第一物理列",
      cabinetPrefix: second ? "B" : "A",
      boxCount: second ? state.params.boxCountB : state.params.boxCountA,
      cabinetCount: second ? state.params.cabinetCountB : state.params.cabinetCountA,
      types: second ? state.typesB : state.typesA,
      enabled: !second || state.params.screenMode === "single_screen_double_column",
      boxBase: second ? { A: 300, B: 400 } : { A: 100, B: 200 },
    };
  }

  function outputSlots(columnKey) {
    const config = columnMappingConfig(columnKey);
    const slots = [];
    for (let boxIndex = 0; boxIndex < config.boxCount; boxIndex += 1) {
      const typeId = config.types[boxIndex] || "3x1P";
      const branchCount = getType(typeId)?.output_branch_count || 0;
      for (let branchNo = 1; branchNo <= branchCount; branchNo += 1) {
        slots.push({
          key: circuitKey(boxIndex + 1, branchNo),
          boxPosition: boxIndex + 1,
          branchNo,
          branchCount,
          typeId,
        });
      }
    }
    return slots;
  }

  function branchLabel(slot) {
    if (isSinglePhaseTriplet(slot.typeId) && slot.branchCount === 3) {
      return `${["A", "B", "C"][slot.branchNo - 1]}相`;
    }
    return `回路${String(slot.branchNo).padStart(2, "0")}`;
  }

  function mappingValue(columnKey, busPath, key) {
    return clampInt(state.circuitMappings[columnKey]?.[busPath]?.[key] ?? 0, 0, 99);
  }

  function setMappingValue(columnKey, busPath, key, value) {
    state.circuitMappings[columnKey][busPath][key] = clampInt(value, 0, 99);
  }

  function currentRouteValues(columnKey, busPath) {
    return outputSlots(columnKey).map((slot) => mappingValue(columnKey, busPath, slot.key));
  }

  function normalizeCircuitMappings(columnKey) {
    const config = columnMappingConfig(columnKey);
    for (const busPath of ["A", "B"]) {
      for (const slot of outputSlots(columnKey)) {
        const value = mappingValue(columnKey, busPath, slot.key);
        setMappingValue(columnKey, busPath, slot.key, value <= config.cabinetCount ? value : 0);
      }
    }
  }

  function routeMappingStatus(columnKey, busPath) {
    const config = columnMappingConfig(columnKey);
    return core.cabinetCoverageStatus(
      currentRouteValues(columnKey, busPath),
      config.cabinetCount,
      config.enabled,
    );
  }

  function columnMappingStatus(columnKey) {
    const config = columnMappingConfig(columnKey);
    const routeA = routeMappingStatus(columnKey, "A");
    const routeB = routeMappingStatus(columnKey, "B");
    return {
      enabled: config.enabled,
      routeA,
      routeB,
      valid: !config.enabled || (routeA.valid && routeB.valid),
    };
  }

  function isCircuitMappingReady() {
    return columnMappingStatus("A").valid && columnMappingStatus("B").valid;
  }

  function mappingStatusText(columnKey) {
    const status = columnMappingStatus(columnKey);
    if (!status.enabled) return "当前未启用";
    const a = status.routeA;
    const b = status.routeB;
    if (status.valid) return `A路 ${a.mappedCount}/${a.cabinetCount} · B路 ${b.mappedCount}/${b.cabinetCount} · 完整`;
    return `A路 ${a.mappedCount}/${a.cabinetCount} · B路 ${b.mappedCount}/${b.cabinetCount} · 待补齐`;
  }

  function cabinetOptions(columnKey, selected) {
    const config = columnMappingConfig(columnKey);
    const options = [
      `<option value="0"${selected === 0 ? " selected" : ""}>备用</option>`,
    ];
    for (let index = 1; index <= config.cabinetCount; index += 1) {
      const id = `${config.cabinetPrefix}${String(index).padStart(2, "0")}`;
      options.push(`<option value="${index}"${selected === index ? " selected" : ""}>${id}</option>`);
    }
    return options.join("");
  }

  function routeEditorHtml(columnKey, busPath, boxPosition, slots) {
    const config = columnMappingConfig(columnKey);
    const boxNo = config.boxBase[busPath] + boxPosition;
    return `<div class="circuit-route-row">
      <div class="circuit-route-id"><span>${busPath}路</span><strong>C${boxNo}</strong></div>
      <div class="circuit-output-grid" style="--branch-count:${slots.length}">
        ${slots
          .map((slot) => {
            const selected = mappingValue(columnKey, busPath, slot.key);
            return `<label class="circuit-output${selected === 0 ? " is-spare" : ""}">
              <span>${escapeHtml(branchLabel(slot))}</span>
              <select data-circuit-column="${columnKey}" data-circuit-route="${busPath}" data-circuit-key="${slot.key}" aria-label="${config.label}${busPath}路C${boxNo}${branchLabel(slot)}对应机柜">
                ${cabinetOptions(columnKey, selected)}
              </select>
            </label>`;
          })
          .join("")}
      </div>
    </div>`;
  }

  function boardTopology(columnKey) {
    const config = columnMappingConfig(columnKey);
    const boxes = config.types.slice(0, config.boxCount).map((typeId, index) => {
      const type = getType(typeId);
      return {
        boxPosition: index + 1,
        slotId: typeId,
        typeCode: type.protocol_type_code,
        layoutPattern: type.protocol_layout_pattern,
        boardTemplateIds: type.board_template_ids,
      };
    });
    return core.buildBoardTopology({
      columnKey: columnKey === "B" ? "COL-B" : "COL-A",
      boxes,
      temperatureModes: state.secondLoopTemperatureModes,
    });
  }

  function reconcileSecondLoopTemperatureModes() {
    const activeColumns = state.params.screenMode === "single_screen_double_column" ? ["A", "B"] : ["A"];
    const next = {};
    for (const columnKey of activeColumns) {
      for (const row of boardTopology(columnKey).rows) {
        if (!row.second_loop) continue;
        const current = state.secondLoopTemperatureModes[row.configuration_key];
        if (
          current &&
          typeof current === "object" &&
          current.topologyFingerprint === row.topology_fingerprint &&
          core.secondLoopModeValue(current.mode) !== null
        ) {
          next[row.configuration_key] = { ...current };
        }
      }
    }
    state.secondLoopTemperatureModes = next;
  }

  function boardTemperatureControlsHtml(columnKey, boxPosition, slots) {
    const rows = boardTopology(columnKey).rows.filter(
      (row) => row.box_position === boxPosition && row.second_loop,
    );
    if (!rows.length) return "";
    const typeId = slots[0]?.typeId || "3x1P";
    return `<div class="temperature-settings">
      <div class="temperature-title"><strong>第二回路温度来源</strong><span>同一箱位的A/B母路采用相同设置</span></div>
      <div class="temperature-grid">
        ${rows
          .map((row) => {
            const branches = getType(typeId).electrical_branches
              .map((branch, index) => ({ ...branch, branchNo: index + 1 }))
              .filter((branch) => branch.boardOffset === row.board_offset)
              .map((branch) => branch.branchNo);
            const selected = row.temperature_mode || "";
            return `<label class="temperature-choice">
              <span>板卡${row.board_ordinal} · 回路${branches.map((value) => String(value).padStart(2, "0")).join("/")}</span>
              <select
                data-second-loop-mode
                data-configuration-key="${escapeHtml(row.configuration_key)}"
                data-topology-fingerprint="${escapeHtml(row.topology_fingerprint)}"
                aria-label="${columnMappingConfig(columnKey).label}第${boxPosition}箱第${row.board_ordinal}块一拖六板卡第二回路温度"
              >
                <option value=""${selected ? "" : " selected"}>请选择</option>
                <option value="independent_temperature"${selected === "independent_temperature" ? " selected" : ""}>独立测温</option>
                <option value="shared_temperature"${selected === "shared_temperature" ? " selected" : ""}>复用第一回路温度</option>
              </select>
            </label>`;
          })
          .join("")}
      </div>
    </div>`;
  }

  function boxConfigurationCardHtml(columnKey, boxPosition, slots) {
    const typeId = slots[0]?.typeId || "3x1P";
    const config = columnMappingConfig(columnKey);
    return `<article class="circuit-box-card" data-box-column="${columnKey}" data-box-position="${boxPosition}">
      <header class="box-card-header">
        <div>
          <span>第${String(boxPosition).padStart(2, "0")}箱位</span>
          <strong>C${config.boxBase.A + boxPosition} / C${config.boxBase.B + boxPosition}</strong>
        </div>
        <label class="box-type-field">
          <span>实际箱型</span>
          <select data-position-column="${columnKey}" data-position-index="${boxPosition - 1}" aria-label="${config.label}第${boxPosition}箱实际箱型">
            ${typeOptions(typeId)}
          </select>
        </label>
      </header>
      ${boardTemperatureControlsHtml(columnKey, boxPosition, slots)}
      <div class="route-pair-editor">
        ${routeEditorHtml(columnKey, "A", boxPosition, slots)}
        ${routeEditorHtml(columnKey, "B", boxPosition, slots)}
      </div>
    </article>`;
  }

  function updateCircuitStatus(columnKey) {
    const statusTarget = columnKey === "A" ? els.circuitStatusA : els.circuitStatusB;
    const status = columnMappingStatus(columnKey);
    if (!statusTarget) return;
    statusTarget.textContent = mappingStatusText(columnKey);
    statusTarget.classList.toggle("is-valid", status.valid);
    statusTarget.classList.toggle("is-warning", !status.valid && status.enabled);
    const workspace = document.querySelector(`[data-column-workspace="${columnKey}"]`);
    const visibleStatus = workspace?.querySelector("[data-column-mapping-status]");
    if (visibleStatus) {
      visibleStatus.textContent = mappingStatusText(columnKey);
      visibleStatus.classList.toggle("is-valid", status.valid);
      visibleStatus.classList.toggle("is-warning", !status.valid && status.enabled);
    }
  }

  function renderCircuitColumn(columnKey, target, statusTarget) {
    if (!target || !statusTarget) return;
    const config = columnMappingConfig(columnKey);
    normalizeCircuitMappings(columnKey);
    const grouped = new Map();
    for (const slot of outputSlots(columnKey)) {
      if (!grouped.has(slot.boxPosition)) grouped.set(slot.boxPosition, []);
      grouped.get(slot.boxPosition).push(slot);
    }
    const status = columnMappingStatus(columnKey);
    target.innerHTML = `<div class="column-workspace-inner" data-column-workspace="${columnKey}">
      <div class="circuit-toolbar" aria-label="${escapeHtml(config.label)}快捷填充">
        <button class="mapping-tool" type="button" data-mapping-column="${columnKey}" data-mapping-action="reverse-fill">反序填充 A/B 路</button>
        <button class="mapping-tool" type="button" data-mapping-column="${columnKey}" data-mapping-action="sequential">顺序填充 A/B 路</button>
        <button class="mapping-tool" type="button" data-mapping-column="${columnKey}" data-mapping-action="copy-a-to-b">A路复制到B路</button>
        <button class="mapping-tool is-clear" type="button" data-mapping-column="${columnKey}" data-mapping-action="clear">全部备用</button>
        <span class="wiring-status${status.valid ? " is-valid" : " is-warning"}" data-column-mapping-status>${escapeHtml(mappingStatusText(columnKey))}</span>
      </div>
      <p class="wiring-rule">反序示例：第1箱回路1/2/3对应${config.cabinetPrefix}03/${config.cabinetPrefix}02/${config.cabinetPrefix}01，第2箱从${config.cabinetPrefix}06继续。</p>
      <div class="circuit-matrix">
        ${Array.from(grouped.entries())
          .map(([boxPosition, slots]) => boxConfigurationCardHtml(columnKey, boxPosition, slots))
          .join("")}
      </div>
    </div>`;
    updateCircuitStatus(columnKey);
  }

  function renderCircuitEditors() {
    if (els.circuitMappingA && els.circuitStatusA) {
      renderCircuitColumn("A", els.circuitMappingA, els.circuitStatusA);
    }
    if (els.circuitMappingB && els.circuitStatusB) {
      renderCircuitColumn("B", els.circuitMappingB, els.circuitStatusB);
    }
  }

  function circuitColumnEditorHtml(columnKey) {
    const config = columnMappingConfig(columnKey);
    if (!config.enabled) return "";
    const holder = document.createElement("div");
    const statusHolder = document.createElement("div");
    renderCircuitColumn(columnKey, holder, statusHolder);
    return holder.innerHTML;
  }

  function applyMappingAction(columnKey, action) {
    const config = columnMappingConfig(columnKey);
    const slots = outputSlots(columnKey);
    if (action === "clear") {
      for (const busPath of ["A", "B"]) {
        for (const slot of slots) setMappingValue(columnKey, busPath, slot.key, 0);
      }
      return "已将全部输出设为备用";
    }
    if (action === "sequential") {
      for (const busPath of ["A", "B"]) {
        let cabinet = 1;
        for (const slot of slots) {
          setMappingValue(columnKey, busPath, slot.key, cabinet <= config.cabinetCount ? cabinet : 0);
          cabinet += 1;
        }
      }
      return "已按机柜号顺序填充A/B路";
    }
    if (action === "copy-a-to-b") {
      for (const slot of slots) {
        setMappingValue(columnKey, "B", slot.key, mappingValue(columnKey, "A", slot.key));
      }
      return "已把A路映射复制到B路";
    }
    if (action === "reverse-fill") {
      const values = core.reverseFill(slots, config.cabinetCount);
      for (const busPath of ["A", "B"]) {
        for (const slot of slots) setMappingValue(columnKey, busPath, slot.key, values[slot.key] || 0);
      }
      return "已按连续机柜块逐箱反序，并同步填充A/B路";
    }
    return "映射未变化";
  }

  function loadBlankProject() {
    state.params = {
      projectName: "",
      room: "",
      screenMode: "single_screen_single_column",
      boxCountA: 1,
      boxCountB: 1,
      cabinetCountA: 3,
      cabinetCountB: 3,
      relayCountA: 0,
      relayCountB: 0,
      uploadProtocol: "modbus_rtu_forwarder",
      serialPort: "COM4",
      baudRate: 9600,
      stationAddress: 1,
      tcpPort: 502,
      tcpBindIp: "",
      confirmStation: true,
      featureTemperature: "preserve",
      featureLeakage: "preserve",
      featureSpd: "preserve",
      featurePower: "preserve",
      channelA: String(RECIPE_BASELINE["通道号_1"] ?? "D"),
      channelB: String(RECIPE_BASELINE["通道号_2"] ?? "D"),
      confirmChannelA: false,
      confirmChannelB: false,
      confirmRoom: false,
      alarmDelay: Number(RECIPE_BASELINE.ALM_Comdelay ?? 100),
      confirmAlarmDelay: false,
      typeReplacements: {},
    };
    state.typesA = ["3x1P"];
    state.typesB = ["3x1P"];
    state.secondLoopTemperatureModes = {};
    state.circuitMappings = emptyCircuitMappings();
    state.protocol = { status: "idle", signature: "", result: null, alarmCode: "", error: "" };
    state.selectedStepId = "parameters";
    state.visited = new Set();
    syncFormFromState();
    renderEverything();
  }

  function syncFormFromState() {
    const p = state.params;
    document.getElementById("project-name").value = p.projectName;
    document.getElementById("room").value = p.room;
    document.getElementById("screen-mode").value = p.screenMode;
    document.getElementById("box-count-a").value = p.boxCountA;
    document.getElementById("box-count-b").value = p.boxCountB;
    document.getElementById("cabinet-count-a").value = p.cabinetCountA;
    document.getElementById("cabinet-count-b").value = p.cabinetCountB;
    document.getElementById("relay-count-a").value = p.relayCountA;
    document.getElementById("relay-count-b").value = p.relayCountB;
    document.getElementById("upload-protocol").value = p.uploadProtocol;
    document.getElementById("serial-port").value = p.serialPort;
    document.getElementById("baud-rate").value = p.baudRate;
    document.getElementById("station-address").value = p.stationAddress;
    document.getElementById("tcp-port").value = p.tcpPort;
    document.getElementById("tcp-bind-ip").value = p.tcpBindIp;
    document.getElementById("feature-temperature").value = p.featureTemperature;
    document.getElementById("feature-leakage").value = p.featureLeakage;
    document.getElementById("feature-spd").value = p.featureSpd;
    document.getElementById("feature-power").value = p.featurePower;
    document.getElementById("channel-a").value = p.channelA;
    document.getElementById("channel-b").value = p.channelB;
    document.getElementById("alarm-delay").value = p.alarmDelay;
    initializeTypeSelectors();
    syncVisibility();
    renderPositionEditors();
    renderCircuitEditors();
  }

  function normalizeTypes(items, count, fallback) {
    const normalized = items.slice(0, count);
    while (normalized.length < count) normalized.push(fallback);
    return normalized;
  }

  function readFormIntoState(changedName = "") {
    const formData = new FormData(els.form);
    const previousA = state.params.boxCountA || 1;
    const previousB = state.params.boxCountB || 1;
    const previousCabinetsA = state.params.cabinetCountA || 0;
    const previousCabinetsB = state.params.cabinetCountB || 0;
    const previousScreenMode = state.params.screenMode || "single_screen_single_column";
    const previousReplacementSignature = core.stableStringify(state.params.typeReplacements || {});
    const nextA = clampInt(formData.get("boxCountA"), 1, 25);
    const nextB = clampInt(formData.get("boxCountB"), 1, 25);
    const fallbackA = els.boxTypeA.value === "__mixed__" ? state.typesA[0] || "3x1P" : els.boxTypeA.value;
    const fallbackB = els.boxTypeB.value === "__mixed__" ? state.typesB[0] || "3x1P" : els.boxTypeB.value;

    const typeReplacements = {};
    for (const slotId of BASELINE_TYPE_IDS) {
      const value = String(formData.get(`replacement_${slotId}`) || "").trim();
      if (value) typeReplacements[slotId] = value;
    }

    const screenMode = String(formData.get("screenMode") || "single_screen_single_column");
    const room = String(formData.get("room") || "").trim();
    const channelA = String(formData.get("channelA") || "").trim();
    const channelB = String(formData.get("channelB") || "").trim();

    state.params = {
      projectName: String(formData.get("projectName") || "").trim(),
      room,
      screenMode,
      boxCountA: nextA,
      boxCountB: nextB,
      cabinetCountA: clampInt(formData.get("cabinetCountA"), 0, 99),
      cabinetCountB: clampInt(formData.get("cabinetCountB"), 0, 99),
      relayCountA: clampInt(formData.get("relayCountA"), 0, 20),
      relayCountB: clampInt(formData.get("relayCountB"), 0, 20),
      uploadProtocol: String(formData.get("uploadProtocol") || "modbus_rtu_forwarder"),
      serialPort: String(formData.get("serialPort") || "").trim(),
      baudRate: clampInt(formData.get("baudRate"), 1200, 921600),
      stationAddress: clampInt(formData.get("stationAddress"), 1, 247),
      tcpPort: clampInt(formData.get("tcpPort"), 1, 65535),
      tcpBindIp: String(formData.get("tcpBindIp") || "").trim(),
      confirmStation: true,
      featureTemperature: String(formData.get("featureTemperature") || "preserve"),
      featureLeakage: String(formData.get("featureLeakage") || "preserve"),
      featureSpd: String(formData.get("featureSpd") || "preserve"),
      featurePower: String(formData.get("featurePower") || "preserve"),
      channelA,
      channelB,
      confirmChannelA: Boolean(channelA),
      confirmChannelB: screenMode === "single_screen_double_column" && Boolean(channelB),
      confirmRoom: Boolean(room),
      alarmDelay: clampInt(formData.get("alarmDelay"), 0, 999999),
      confirmAlarmDelay: true,
      typeReplacements,
    };

    const replacementChanged =
      previousReplacementSignature !== core.stableStringify(state.params.typeReplacements || {});
    if (replacementChanged || changedName.startsWith("replacement_")) {
      initializeTypeSelectors();
    }

    if (changedName === "boxTypeA" && els.boxTypeA.value !== "__mixed__") {
      state.typesA = Array.from({ length: nextA }, () => els.boxTypeA.value);
    } else {
      state.typesA = normalizeTypes(state.typesA, nextA, fallbackA);
    }
    if (changedName === "boxTypeB" && els.boxTypeB.value !== "__mixed__") {
      state.typesB = Array.from({ length: nextB }, () => els.boxTypeB.value);
    } else {
      state.typesB = normalizeTypes(state.typesB, nextB, fallbackB);
    }

    reconcileSecondLoopTemperatureModes();

    if (previousA !== nextA || previousB !== nextB || changedName.startsWith("box") || changedName.startsWith("replacement_")) {
      renderPositionEditors();
    }
    syncVisibility();
    if (
      previousA !== nextA ||
      previousB !== nextB ||
      previousCabinetsA !== state.params.cabinetCountA ||
      previousCabinetsB !== state.params.cabinetCountB ||
      previousScreenMode !== state.params.screenMode ||
      replacementChanged ||
      changedName.startsWith("box") ||
      changedName.startsWith("replacement_")
    ) {
      populateReplacementSelectors();
    }
  }

  function syncVisibility() {
    const doubleColumn = state.params.screenMode === "single_screen_double_column";
    els.columnBFields.hidden = !doubleColumn;
    document.querySelectorAll(".rtu-field").forEach((item) => {
      item.hidden = state.params.uploadProtocol !== "modbus_rtu_forwarder";
    });
    document.querySelectorAll(".tcp-field").forEach((item) => {
      item.hidden = state.params.uploadProtocol !== "tcpip";
    });
  }

  function commonType(types) {
    if (!types.length) return "3x1P";
    return types.every((item) => item === types[0]) ? types[0] : "__mixed__";
  }

  function renderPositionEditors() {
    if (els.boxTypesA) els.boxTypesA.innerHTML = "";
    if (els.boxTypesB) els.boxTypesB.innerHTML = "";
    els.boxTypeA.value = commonType(state.typesA);
    els.boxTypeB.value = commonType(state.typesB);
  }

  function deriveColumn(types, count, firstBase, secondBase, classStart) {
    const activeTypes = normalizeTypes(types, count, "3x1P");
    let layout = 0;
    let layoutSub = 0;
    const classMasks = [0, 0, 0, 0];
    let boardCount = 0;
    let outputCount = 0;
    const firstHeads = [];
    const secondHeads = [];
    let firstCursor = firstBase;
    let secondCursor = secondBase;

    activeTypes.forEach((typeId, index) => {
      const type = getType(typeId) || TYPES["3x1P"];
      const bit = 1 << index;
      if (type.layout_bit) layout |= bit;
      if (type.layout_sub_bit) layoutSub |= bit;
      const typeIndex = BASELINE_TYPE_IDS.indexOf(type.custom ? type.class_slot : type.type_id);
      if (typeIndex >= 0) classMasks[typeIndex] |= bit;
      firstHeads.push(firstCursor);
      secondHeads.push(secondCursor);
      firstCursor += type.board_count;
      secondCursor += type.board_count;
      boardCount += type.board_count;
      outputCount += type.output_branch_count;
    });

    while (firstHeads.length < 25) firstHeads.push(0);
    while (secondHeads.length < 25) secondHeads.push(0);

    const classes = {};
    classMasks.forEach((mask, index) => {
      classes[`CJX_Class${classStart + index}`] = mask >>> 0;
    });

    return {
      count,
      types: activeTypes,
      layout: layout >>> 0,
      layoutSub: layoutSub >>> 0,
      classes,
      boardCount,
      outputCount,
      firstHeads,
      secondHeads,
    };
  }

  function deriveProject() {
    const p = state.params;
    const hasSecondColumn = p.screenMode === "single_screen_double_column";
    const columnA = deriveColumn(state.typesA, p.boxCountA, 101, 201, 1);
    const columnB = deriveColumn(
      state.typesB,
      hasSecondColumn ? p.boxCountB : 0,
      301,
      401,
      5,
    );
    const flat = {
      CJX_NumberA: columnA.count,
      CJX_NumberB: columnB.count,
      N_BK1: columnA.boardCount,
      N_BK2: columnB.boardCount,
      jgsl_A: p.cabinetCountA,
      jgsl_B: hasSecondColumn ? p.cabinetCountB : 0,
      N_ZJ1: p.relayCountA,
      N_ZJ2: hasSecondColumn ? p.relayCountB : 0,
      jgls: hasSecondColumn ? 1 : 0,
      Layout_A: columnA.layout,
      Layout_sub_A: columnA.layoutSub,
      Layout_B: columnB.layout,
      Layout_sub_B: columnB.layoutSub,
      ...columnA.classes,
      ...columnB.classes,
      Modbus_com: p.uploadProtocol === "modbus_rtu_forwarder" ? 0 : 1,
    };
    const replacementSlots = Array.from(
      new Set(
        [...columnA.types, ...columnB.types].filter((typeId) => replacementSelection(typeId)),
      ),
    );
    const checks = [
      {
        id: "type-model",
        label: "箱型模型",
        value: replacementSlots.length ? `${replacementSlots.length}个槽替换` : "四种基线",
        limit: "Class槽内替换",
        pass: true,
      },
      {
        id: "boxes",
        label: "打开策略",
        value: `${columnA.count}/${columnB.count}`,
        limit: "每列≤15箱",
        pass: columnA.count <= 15 && columnB.count <= 15,
      },
      {
        id: "boards",
        label: "板卡设备",
        value: `${columnA.boardCount}/${columnB.boardCount}`,
        limit: "每路≤33板",
        pass: columnA.boardCount <= 33 && columnB.boardCount <= 33,
      },
      {
        id: "cabinets",
        label: "机柜与开关组",
        value: `${p.cabinetCountA}/${hasSecondColumn ? p.cabinetCountB : 0}`,
        limit: `第一列≤${core.TEMPLATE_LIMITS.switchCabinets["COL-A"]}、第二列≤${core.TEMPLATE_LIMITS.switchCabinets["COL-B"]}`,
        pass:
          p.cabinetCountA <= core.TEMPLATE_LIMITS.switchCabinets["COL-A"] &&
          (!hasSecondColumn || p.cabinetCountB <= core.TEMPLATE_LIMITS.switchCabinets["COL-B"]),
      },
      {
        id: "outputs",
        label: "JG_DL输出",
        value: `${columnA.outputCount}/${columnB.outputCount}`,
        limit: "每列≤50路",
        pass: columnA.outputCount <= 50 && columnB.outputCount <= 50,
      },
      {
        id: "relays",
        label: "中继策略",
        value: `${p.relayCountA}/${hasSecondColumn ? p.relayCountB : 0}`,
        limit: "每路≤7个",
        pass: p.relayCountA <= 7 && (!hasSecondColumn || p.relayCountB <= 7),
      },
    ];

    return {
      hasSecondColumn,
      columnA,
      columnB,
      flat,
      checks,
      withinTemplate: checks.every((item) => item.pass),
      headArrays: {
        AA: columnA.firstHeads,
        AB: columnA.secondHeads,
        BA: columnB.firstHeads,
        BB: columnB.secondHeads,
      },
      circuitMapping: {
        A: columnMappingStatus("A"),
        B: columnMappingStatus("B"),
        ready: isCircuitMappingReady(),
      },
      activityDomain: core.activityDomain(hasSecondColumn),
      replacementSlots,
    };
  }

  function dualLoopConfiguration(derived) {
    const topologies = (derived.hasSecondColumn ? ["A", "B"] : ["A"]).map(boardTopology);
    const rows = topologies.flatMap((topology) =>
      topology.rows.map((row) => ({
        ...row,
        object_name: row.object_name,
        object_id: row.object_id,
        mcgs_type_name: "浮点数",
        before_value: 0,
        target_value: row.target_value,
        column: row.column,
        box_position: row.box_position,
        board_index: row.board_index,
        board_offset: row.board_offset,
        template_slot: row.slot_id,
        board_template_id: row.board_template_id,
        second_loop: row.second_loop,
        temperature_mode: row.temperature_mode,
        needsAction: row.manual_action,
        reason: row.second_loop
          ? row.target_value === 1
            ? "第二回路温度独立。"
            : row.target_value === 2
              ? "第二回路与第一回路共用温度。"
              : "请在对应箱位选择第二回路温度方式。"
          : "单回路板卡保持0。",
      })),
    );
    const unresolved = topologies.flatMap((topology) => topology.unresolved);
    return {
      rows,
      actions: rows.filter((row) => row.needsAction),
      missingSlots: unresolved.map((row) => ({
        slotId: row.slot_id,
        label: `${row.column === "COL-A" ? "第一" : "第二"}物理列第${String(row.box_position).padStart(2, "0")}箱·板卡${row.board_ordinal}`,
        positions: [
          {
            column: row.column,
            boxPosition: row.box_position,
            boardOffset: row.board_offset,
            boardIndex: row.board_index,
          },
        ],
        configuration_key: row.configuration_key,
      })),
      complete: unresolved.length === 0,
    };
  }

  function recipeRows(derived) {
    const p = state.params;
    const feature = (value, baseline) =>
      value === "preserve"
        ? { target: baseline, write: false, classification: "保持模板 / 待确认" }
        : { target: Number(value), write: true, classification: "已确认值" };

    return source.recipe.fields.map((field) => {
      let target = field.target_value;
      let write = field.write_allowed;
      let classification = field.classification;
      let reason = field.reason;
      let displayPrefix = "";

      switch (field.recipe_field) {
        case "通讯地址":
          target = p.stationAddress;
          write = p.confirmStation;
          classification = write ? "已确认值" : "保持模板 / 待确认";
          reason = write
            ? "从站地址已在参数区勾选确认。"
            : "当前数值只来自模板/上游默认；未勾选确认，不写入。";
          displayPrefix = write ? "" : "保持 ";
          break;
        case "通道号_1":
          target = p.channelA;
          write = p.confirmChannelA;
          classification = write ? "已确认值" : "待确认 / 不写入";
          reason = write ? "第一列显示通道号已确认。" : "显示通道号尚未确认。";
          displayPrefix = write ? "" : "候选 ";
          break;
        case "通道号_2":
          target = p.channelB;
          write = p.confirmChannelB;
          classification = write ? "已确认值" : "待确认 / 不写入";
          reason = write ? "第二列显示通道号已确认。" : "显示通道号尚未确认。";
          displayPrefix = write ? "" : "候选 ";
          break;
        case "CJX_NumberA":
        case "CJX_NumberB":
        case "N_BK1":
        case "N_BK2":
        case "jgsl_A":
        case "jgsl_B":
          target = derived.flat[field.recipe_field];
          write = true;
          classification = "项目派生值";
          reason = "由当前屏/列、插接箱类型和数量即时派生；无需额外按钮。";
          break;
        case "TempEnable": {
          const result = feature(p.featureTemperature, field.baseline_recipe_value);
          ({ target, write, classification } = result);
          reason = write ? "温度测量开关已明确选择。" : "保持模板值，等待项目确认。";
          displayPrefix = write ? "" : "保持 ";
          break;
        }
        case "InEnable": {
          const result = feature(p.featureLeakage, field.baseline_recipe_value);
          ({ target, write, classification } = result);
          reason = write ? "漏电流测量开关已明确选择。" : "保持模板值，等待项目确认。";
          displayPrefix = write ? "" : "保持 ";
          break;
        }
        case "SPDEnable": {
          const result = feature(p.featureSpd, field.baseline_recipe_value);
          ({ target, write, classification } = result);
          reason = write ? "SPD监测开关已明确选择。" : "保持模板值，等待项目确认。";
          displayPrefix = write ? "" : "保持 ";
          break;
        }
        case "PHEnable": {
          const result = feature(p.featurePower, field.baseline_recipe_value);
          ({ target, write, classification } = result);
          reason = write ? "功率报警开关已明确选择。" : "保持模板值，等待项目确认。";
          displayPrefix = write ? "" : "保持 ";
          break;
        }
        case "Modbus_com":
          target = derived.flat.Modbus_com;
          write = true;
          classification = "项目派生值";
          reason = target === 0 ? "已选择Modbus-RTU，模板规则规定写0。" : "已选择TCP/IP，模板规则规定写1。";
          break;
        case "Room":
          target = p.room;
          write = p.confirmRoom;
          classification = write ? "已确认值" : "待确认 / 不写入";
          reason = write
            ? "机房标识已勾选确认；配方字段Room仍关联实时对象room。"
            : "机房标识仅作为当前项目说明，未授权写入配方。";
          displayPrefix = write ? "" : "候选 ";
          break;
        case "ALM_Comdelay":
          target = p.alarmDelay;
          write = p.confirmAlarmDelay;
          classification = write ? "已确认值" : "待确认 / 不写入";
          reason = write
            ? "通讯报警延时已勾选确认。"
            : "配方模板100与数据库初值60不一致，未确认前禁止二选一。";
          displayPrefix = write ? "" : "候选 ";
          break;
        default:
          break;
      }

      return {
        ...field,
        target,
        write,
        classification,
        reason,
        displayPrefix,
        requiresChange: write && String(target) !== String(field.baseline_recipe_value),
      };
    });
  }

  function dynamicTargetMap(derived) {
    const map = { ...derived.flat };
    for (const family of ["AA", "AB", "BA", "BB"]) {
      derived.headArrays[family].forEach((value, index) => {
        map[`CJX_${family}${String(index + 1).padStart(2, "0")}`] = value;
      });
    }
    return map;
  }

  function jgObjectName(columnKey, index) {
    const suffix = columnKey === "B" ? "_B" : "";
    return `JG_DL${String(index).padStart(2, "0")}${suffix}`;
  }

  function dynamicJgProjection(derived) {
    const projection = {};
    for (const columnKey of ["A", "B"]) {
      const family = columnKey === "A" ? derived.activityDomain.objectFamilies.JG_DL : derived.activityDomain.objectFamilies.JG_DL_B;
      const enabled = family.active;
      const values = enabled ? currentRouteValues(columnKey, "A").slice(0, 50) : [];
      while (values.length < 50) values.push(0);
      values.forEach((targetValue, index) => {
        const objectName = jgObjectName(columnKey, index + 1);
        projection[objectName] = {
          objectName,
          column: columnKey === "A" ? "COL-A" : "COL-B",
          beforeValue: DATABASE_BASELINE[objectName] ?? 0,
          targetValue,
          active: enabled,
          inactiveReason: enabled ? null : family.inactiveReason,
          effectiveReaders: family.readers || [],
          manualAction: enabled,
        };
      });
    }
    return projection;
  }

  function dynamicJgDlActions(derived) {
    return Object.values(dynamicJgProjection(derived)).filter(
      (row) => row.active && String(row.beforeValue) !== String(row.targetValue),
    );
  }

  function databaseRows(derived, recipes) {
    const targets = dynamicTargetMap(derived);
    const jgTargets = dynamicJgProjection(derived);
    const recipesByObject = Object.fromEntries(recipes.map((row) => [row.data_object_name, row]));
    const mappingReady = derived.circuitMapping.ready;

    return source.databaseChanges.map((row) => {
      const next = { ...row };
      if (recipesByObject[row.object_name]) {
        const recipe = recipesByObject[row.object_name];
        next.target_value = recipe.target;
        next.write_allowed = recipe.write;
        next.classification = recipe.classification;
        next.reason = `与配方字段“${recipe.recipe_field}”保持同一目标：${recipe.reason}`;
        next.requires_change_from_extracted_initial =
          recipe.write && String(recipe.target) !== String(row.before_value);
      } else if (Object.prototype.hasOwnProperty.call(jgTargets, row.object_name)) {
        const projection = jgTargets[row.object_name];
        next.target_value = projection.active ? projection.targetValue : row.before_value;
        next.write_allowed = projection.active && mappingReady;
        next.classification = !projection.active
          ? "非活动域 / 不写入"
          : mappingReady
            ? "输出回路映射值"
            : "映射待补齐 / 不写入";
        next.operation = "edit_initial_value";
        next.apply_mode = projection.active ? "gui_manual" : "not_applicable";
        next.reason = !projection.active
          ? "单屏单列时jgls=0，B列报警描述脚本触发条件jgls=1不成立；该对象无有效读取者。"
          : mappingReady
            ? "由参数区的机柜与插接箱输出回路映射实时生成。"
            : "A/B路映射仍有缺失或重复，完成映射前禁止写入。";
        next.requires_change_from_extracted_initial =
          projection.active && mappingReady && String(next.target_value) !== String(next.before_value);
      } else if (Object.prototype.hasOwnProperty.call(targets, row.object_name)) {
        next.target_value = targets[row.object_name];
        next.write_allowed = true;
        next.classification = "项目派生值";
        next.operation = "edit_initial_value";
        next.apply_mode = "gui_manual";
        next.reason = "由当前拓扑参数即时派生；按对象名和对象ID回读，无需额外按钮。";
        next.requires_change_from_extracted_initial =
          String(next.target_value) !== String(next.before_value);
      } else if (
        !mappingReady &&
        (row.category === "jg_dl_mapping" || row.category === "cabinet_label")
      ) {
        next.target_value = null;
        next.write_allowed = false;
        next.classification = "需补齐输出映射";
        next.reason = "参数区的机柜与插接箱输出回路映射仍有缺失或重复，完成前禁止沿用旧值。";
        next.requires_change_from_extracted_initial = false;
      }
      const ownership = OWNERSHIP_BY_OBJECT[row.object_name] || {
        owner: "manual_initial",
        ownerLabel: "人工初值输入",
        displayStage: "database",
        reason: "未找到自动写入关系。",
      };
      next.owner = ownership.owner;
      next.ownerLabel = ownership.ownerLabel;
      next.displayStage = ownership.displayStage;
      next.automaticSources = ownership.automaticSources || [];
      next.ownershipReason = ownership.reason;
      next.needsAction = Boolean(
        ownership.owner === "manual_initial" &&
          ownership.displayStage === "database" &&
          next.write_allowed &&
          next.requires_change_from_extracted_initial,
      );
      return next;
    });
  }

  function manualStepState(derived) {
    const recipes = recipeRows(derived);
    const dualLoop = dualLoopConfiguration(derived);
    const database = databaseRows(derived, recipes).filter((row) => row.needsAction);
    const packageResult = currentCodePackage(derived);
    const extension = packageResult.typeExtension;
    const typeStrategyActions = typeExtensionActionsForSurface(extension, "strategy");
    const typeWindowActions = typeExtensionActionsForSurface(extension, "window");
    const protocolUpload = protocolAlarmUploadFile(derived);
    const deviceActions = dynamicDeviceActions(derived);
    const windowGui = currentWindowGuiPlan(derived);
    return {
      recipe: { count: recipes.filter((row) => row.requiresChange).length },
      database: { count: database.length + dualLoop.actions.length },
      device: {
        count: Math.max(1, deviceActions.length),
        blocked: protocolViewState(derived).status === "failed" ? 1 : 0,
      },
      jgdl: { count: dynamicJgDlActions(derived).length },
      backend: {
        count: packageResult.backend.length + typeStrategyActions.length,
        blocked:
          extension.blockedActions.length +
          (packageResult.blockedByType || packageResult.dependentReady
            ? 0
            : packageResult.dependentIssues.length),
      },
      alarm: {
        count: packageResult.alarm.length + (protocolUpload ? 1 : 0),
      },
      window: {
        count: packageResult.window.length + windowGui.actions.length + typeWindowActions.length,
        blocked: packageResult.blockedByType
          ? 0
          : packageResult.windowReady
            ? 0
            : packageResult.dependentIssues.length,
      },
    };
  }

  function activeSteps(derived) {
    const status = manualStepState(derived);
    return STEPS.filter((step) => {
      const item = status[step.id] || { count: 0, blocked: 0 };
      if (item.visible === false) return false;
      return Number(item.count || 0) > 0 || Number(item.blocked || 0) > 0;
    });
  }

  function renderWorkflow(derived) {
    const steps = activeSteps(derived);
    els.workflowTrack.innerHTML = steps
      .map(
        (step, index) => `
        <button type="button" class="step-tab${state.selectedStepId === step.id ? " is-active" : ""}${state.visited.has(step.id) ? " is-visited" : ""}" data-step-id="${escapeHtml(step.id)}" aria-current="${state.selectedStepId === step.id ? "step" : "false"}">
          <span class="step-number">${String(index + 1).padStart(2, "0")}</span>
          <span class="step-label">${escapeHtml(step.label)}</span>
        </button>`,
      )
      .join("");
  }

  function renderCapacity(derived) {
    const failing = derived.checks.filter((item) => !item.pass);
    els.capacityRibbon.hidden = derived.withinTemplate;
    if (derived.withinTemplate) {
      els.capacityRibbon.innerHTML = "";
      return;
    }
    els.capacityRibbon.innerHTML = `
      <div class="capacity-main is-expand">
        <span class="capacity-light" aria-hidden="true"></span>
        <div><strong>当前数量超过模板范围</strong><small>${failing.map((item) => item.label).join("、")}需要先扩展</small></div>
      </div>
      <details class="capacity-details">
        <summary>查看超限项目</summary>
        <div class="capacity-metrics">${derived.checks
          .filter((check) => !check.pass)
          .map(
            (check) => `<div class="capacity-metric is-fail"><span>${escapeHtml(check.label)} · ${escapeHtml(check.limit)}</span><strong>${escapeHtml(check.value)} 超限</strong></div>`,
          )
          .join("")}</div>
      </details>`;
  }

  function hero(stepRef, statusText, pending = false) {
    const step = typeof stepRef === "number" ? STEPS[stepRef] : STEPS.find((item) => item.id === stepRef);
    if (!step) return "";
    const steps = activeSteps(deriveProject());
    const stepIndex = Math.max(0, steps.findIndex((item) => item.id === step.id));
    return `
      <header class="step-hero">
        <div class="step-index"><span>${String(stepIndex + 1).padStart(2, "0")}</span><small>/ ${String(steps.length).padStart(2, "0")}</small></div>
        <div>
          <h2>${escapeHtml(step.title)}</h2>
          <p>${escapeHtml(step.description)}</p>
        </div>
        <span class="step-status${pending ? " is-pending" : ""}">${escapeHtml(statusText)}</span>
      </header>`;
  }

  function instruction(location, action) {
    return `
      <div class="instruction-strip">
        <strong>在MCGS中</strong>
        <p><span class="mono">${escapeHtml(location)}</span><br />${escapeHtml(action)}</p>
      </div>`;
  }

  function renderTopology(derived) {
    const renderColumn = (column, label, baseA, baseB) => {
      if (!column.count) return "";
      const nodes = column.types
        .map(
          (typeId, index) => {
            const label = typeDisplayLabel(typeId);
            return `<span class="box-node" title="第${index + 1}箱：${escapeHtml(label)}">${index + 1}</span>`;
          },
        )
        .join("");
      return `
        <div class="topology-column">
          <div class="column-tag">${escapeHtml(label)}</div>
          <div class="route-pair">
            <div class="route-line">
              <span class="route-code">A</span>
              <div class="route-bus">${nodes}</div>
              <span class="route-meta">${baseA}起 · ${column.boardCount}板</span>
            </div>
            <div class="route-line">
              <span class="route-code">B</span>
              <div class="route-bus">${nodes}</div>
              <span class="route-meta">${baseB}起 · ${column.boardCount}板</span>
            </div>
          </div>
        </div>`;
    };

    return `<div class="topology-board">
      ${renderColumn(derived.columnA, "第一物理列", 101, 201)}
      ${renderColumn(derived.columnB, "第二物理列", 301, 401)}
    </div>`;
  }

  function renderRuntimeFlow() {
    const runtime = source.runtimeModel;
    const steps = runtime.startupFlow.triggerChain;
    const continuous = runtime.continuousRuntime;
    return `<div class="runtime-overview">
      <div class="runtime-band">
        <div class="runtime-band-title"><span>上电一次</span><strong>启动触发链</strong></div>
        <div class="runtime-flow">
          ${steps
            .map(
              (step, index) => `${index ? '<span class="runtime-arrow" aria-hidden="true">→</span>' : ""}
                <div class="runtime-node">
                  <span>${String(step.order).padStart(2, "0")}</span>
                  <strong>${escapeHtml(step.strategy)}</strong>
                  <small>${escapeHtml(step.role)}</small>
                </div>`,
            )
            .join("")}
        </div>
        <p class="runtime-note">${escapeHtml(runtime.startupFlow.setStgySemantics)}</p>
      </div>
      <div class="runtime-band">
        <div class="runtime-band-title"><span>持续运行</span><strong>自动策略</strong></div>
        <div class="runtime-lanes">
          <div><strong>后台任务</strong><span>${continuous.background[0]?.execution?.cycle_interval_ms || 0}ms</span></div>
          <div><strong>循环策略</strong><span>${continuous.loops.length}个</span></div>
          <div><strong>事件策略</strong><span>${continuous.events.length}个</span></div>
          <div><strong>报警策略</strong><span>${continuous.alarms.length}个</span></div>
        </div>
      </div>
    </div>`;
  }

  function routeStatusDescription(columnKey, busPath) {
    const config = columnMappingConfig(columnKey);
    const status = routeMappingStatus(columnKey, busPath);
    if (status.valid) return `已覆盖${status.mappedCount}个机柜`;
    const parts = [];
    if (status.missing.length) {
      parts.push(`缺少 ${status.missing.map((value) => `${config.cabinetPrefix}${String(value).padStart(2, "0")}`).join("、")}`);
    }
    return parts.join("；") || "尚未设置";
  }

  function renderMappingOverview(derived) {
    const columns = derived.hasSecondColumn ? ["A", "B"] : ["A"];
    return `<div class="mapping-overview">
      <div class="mapping-diagnostics">
        ${columns
          .flatMap((columnKey) =>
            ["A", "B"].map((busPath) => {
              const config = columnMappingConfig(columnKey);
              const status = routeMappingStatus(columnKey, busPath);
              return `<div class="mapping-diagnostic${status.valid ? " is-valid" : " is-warning"}">
                <span>${config.label} · ${busPath}路</span>
                <strong>${status.mappedCount}/${status.cabinetCount}</strong>
                <small>${escapeHtml(routeStatusDescription(columnKey, busPath))}</small>
              </div>`;
            }),
          )
          .join("")}
      </div>
      <div class="mapping-board">
        ${columns
          .map(
            (columnKey) =>
              mappingLane(columnKey, "A", columnMappingConfig(columnKey).label) +
              mappingLane(columnKey, "B", columnMappingConfig(columnKey).label),
          )
          .join("")}
      </div>
    </div>`;
  }

  function renderParameters(derived) {
    const p = state.params;
    const dualLoop = dualLoopConfiguration(derived);
    const pendingCount = [
      !p.confirmStation,
      p.featureTemperature === "preserve",
      p.featureLeakage === "preserve",
      p.featureSpd === "preserve",
      p.featurePower === "preserve",
      !p.confirmRoom,
      !p.confirmAlarmDelay,
      !derived.circuitMapping.ready,
      !dualLoop.complete,
    ].filter(Boolean).length;

    root.innerHTML =
      hero("parameters", pendingCount ? `${pendingCount}类参数待确认` : "参数已确认", pendingCount > 0) +
      instruction(
        "点击右上角“编辑项目参数”",
        "先填项目、数量、箱型和动环参数，再直接在下方接线画布设置机柜与输出回路。所有结果都会即时更新，不需要重算。",
      ) +
      `<section class="project-strip" aria-label="当前项目轮廓">
        <div class="project-strip-title">
          <span class="rail-caption">当前装配对象</span>
          <strong>${escapeHtml(p.projectName)}</strong>
        </div>
        <div><span>屏幕</span><strong>${p.screenMode === "single_screen_single_column" ? "单屏单列" : "单屏双列"}</strong></div>
        <div><span>第一列</span><strong>${derived.columnA.count}箱 · ${derived.columnA.boardCount}板 · ${p.cabinetCountA}柜</strong></div>
        ${derived.hasSecondColumn ? `<div><span>第二列</span><strong>${derived.columnB.count}箱 · ${derived.columnB.boardCount}板 · ${p.cabinetCountB}柜</strong></div>` : ""}
        <div><span>上传</span><strong>${p.uploadProtocol === "modbus_rtu_forwarder" ? "Modbus-RTU" : "TCP/IP"}</strong></div>
        <button type="button" class="button button-secondary button-small" data-open-parameters>编辑参数</button>
      </section>
      <section class="wiring-stage">
        <div class="wiring-stage-heading">
          <div>
            <span class="rail-caption">所见即所得接线画布</span>
            <h3>插接箱输出 → 机柜</h3>
            <p>每个输出下拉框就是一个真实接线关系；完整、缺失和重复会在本画布即时标出。</p>
          </div>
          <span class="status-tag ${derived.circuitMapping.ready ? "is-ready" : "is-pending"}">${derived.circuitMapping.ready ? "映射已闭合" : "映射待补齐"}</span>
        </div>
        <div class="wiring-columns">
          ${circuitColumnEditorHtml("A")}
          ${derived.hasSecondColumn ? circuitColumnEditorHtml("B") : ""}
        </div>
      </section>
      <details class="section-block disclosure-block">
        <summary><span><strong>查看程序为什么只列这些人工操作</strong><small>启动链、持续策略和自动派生边界</small></span></summary>
        ${renderRuntimeFlow()}
        <div class="manual-scope">
          <strong>人工清单边界</strong>
          <p>只有“目标值与模板不同、且没有自动写入者”的项目才进入后续步骤。<span class="mono">CJX_Class</span>、头板卡数组、<span class="mono">jgls</span>、设备逐台启停和通讯报警由运行策略接管。</p>
        </div>
      </details>
      <section class="section-block">
        <p class="notice${derived.withinTemplate ? "" : " is-danger"}">${derived.withinTemplate ? "当前数量没有突破模板容量。确认接线后点击“生成执行清单”，第一项实际修改工作是配方。" : "当前数量已突破模板容量。仍可查看派生结果，但在扩展策略、数据库、设备或窗口结构前不能直接复制为正式代码。"}${dualLoop.missingSlots.length ? ` 另有${dualLoop.missingSlots.length}个一拖六类型槽尚未确认第二回路温度是独立还是共用。` : ""}</p>
      </section>`;
  }

  function renderRecipe(derived) {
    const rows = recipeRows(derived);
    const actions = rows.filter((row) => row.requiresChange);
    const allAssignments = actions
      .map((row) => `${row.recipe_field}=${assignmentValue(row.target)}`)
      .join("\n");

    root.innerHTML =
      hero("recipe", `${actions.length}项需要修改`, false) +
      instruction(
        "配方组“设置” → 配方“项目信息”",
        "只修改下表字段，其他字段保持模板原样。",
      ) +
      `<section class="section-block">
        <div class="section-heading">
          <div><h3>必须修改的配方字段</h3><p>表格只呈现相对模板发生变化的值；0仍是有效数值。</p></div>
          ${actions.length ? copyButton(allAssignments, "复制核对清单", { className: "button button-secondary button-small" }) : ""}
        </div>
        ${actions.length ? `<div class="table-wrap">
          <table>
            <thead><tr><th>字段</th><th>业务含义</th><th>模板值</th><th>目标值</th><th>MCGS位置</th><th>复制</th></tr></thead>
            <tbody>
              ${actions
                .map(
                  (row) => `<tr>
                    <td><span class="cell-object">${escapeHtml(row.recipe_field)}</span></td>
                    <td>${escapeHtml(row.semantic)}</td>
                    <td class="cell-value">${escapeHtml(formatValue(row.baseline_recipe_value, true))}</td>
                    <td class="cell-value value-target">${escapeHtml(formatValue(row.target, true))}</td>
                    <td class="cell-reason">设置 → 项目信息 → ${escapeHtml(row.recipe_field)}</td>
                    <td class="cell-actions">${copyButton(assignmentValue(row.target), "复制目标值")}</td>
                  </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>` : '<div class="empty-state"><div><strong>配方无需修改</strong><span>当前目标与模板一致。</span></div></div>'}
      </section>`;
  }

  function databaseRowHtml(row) {
    return `<tr>
      <td><span class="cell-object">${escapeHtml(row.object_name)}</span></td>
      <td>${escapeHtml(row.mcgs_type_name || row.data_type)}</td>
      <td class="cell-value">${escapeHtml(formatValue(row.before_value, true))}</td>
      <td class="cell-value value-target">${escapeHtml(formatValue(row.target_value, true))}</td>
      <td class="cell-reason">实时数据库 → ${escapeHtml(row.object_name)} → 基本属性 → 初值</td>
      <td class="cell-actions">${copyButton(assignmentValue(row.target_value), "复制目标值")}</td>
    </tr>`;
  }

  function renderDatabase(derived) {
    const recipes = recipeRows(derived);
    const allRows = databaseRows(derived, recipes);
    const dualLoop = dualLoopConfiguration(derived);
    const rows = [...allRows.filter((row) => row.needsAction), ...dualLoop.actions];
    const assignments = rows
      .map((row) => `${row.object_name}=${assignmentValue(row.target_value)}`)
      .join("\n");

    root.innerHTML =
      hero("database", dualLoop.complete ? `${rows.length}项需要修改` : `${dualLoop.missingSlots.length}项温度方式待选择`, !dualLoop.complete) +
      instruction(
        "实时数据库 → 按对象名精确定位 → 基本属性 / 初值",
        "只修改下表对象。配方关联对象、布局派生值和头板卡数组会在启动时自动生成，不再重复修改。",
      ) +
      (dualLoop.complete
        ? ""
        : `<section class="section-block"><p class="notice is-warning"><strong>请先选择第二回路温度方式：</strong>${escapeHtml(dualLoop.missingSlots.map((item) => item.label).join("、"))}。</p><button type="button" class="button button-secondary" data-go-config>返回项目配置</button></section>`) +
      `<section class="section-block">
        <div class="section-heading"><div><h3>必须修改的数据库输入</h3><p>表中每一行都是需要亲手改的对象。</p></div>${rows.length ? copyButton(assignments, "复制核对清单", { className: "button button-secondary button-small" }) : ""}</div>
        ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>对象</th><th>类型</th><th>模板初值</th><th>目标值</th><th>MCGS位置</th><th>复制</th></tr></thead><tbody>${rows.map(databaseRowHtml).join("")}</tbody></table></div>` : '<div class="empty-state"><div><strong>数据库无人工初值</strong><span>当前变化均由配方或运行策略生成。</span></div></div>'}
      </section>`;
  }

  function deviceValue(value) {
    if (typeof value === "boolean") return value ? "启用 / true" : "停用 / false";
    if (value && typeof value === "object" && value.project_specific_expected_count) {
      return `${value.project_specific_expected_count}点通道表`;
    }
    return formatValue(value, true);
  }

  function deviceCopyValue(row) {
    if (row.property === "formal_channel_table") return row.new.source_csv;
    return assignmentValue(row.new);
  }

  function activeColumnSpecs(derived) {
    const specs = [
      {
        key: "A",
        label: "第一物理列",
        typeIds: state.typesA.slice(0, state.params.boxCountA),
        cabinetCount: state.params.cabinetCountA,
        relayCount: state.params.relayCountA,
        boardCount: derived.columnA.boardCount,
        outputCount: derived.columnA.outputCount,
      },
    ];
    if (derived.hasSecondColumn) {
      specs.push({
        key: "B",
        label: "第二物理列",
        typeIds: state.typesB.slice(0, state.params.boxCountB),
        cabinetCount: state.params.cabinetCountB,
        relayCount: state.params.relayCountB,
        boardCount: derived.columnB.boardCount,
        outputCount: derived.columnB.outputCount,
      });
    }
    return specs;
  }

  function representativeProtocolColumn(derived) {
    return activeColumnSpecs(derived)
      .slice()
      .sort(
        (left, right) =>
          right.boardCount - left.boardCount ||
          right.outputCount - left.outputCount ||
          right.typeIds.length - left.typeIds.length,
      )[0];
  }

  function protocolConfigForProject(derived) {
    const activeColumns = activeColumnSpecs(derived);
    const protocolColumn = representativeProtocolColumn(derived);
    const maxCabinetCount = Math.max(...activeColumns.map((column) => column.cabinetCount), 0);
    const maxRelayCount = Math.max(...activeColumns.map((column) => column.relayCount), 0);
    const secondLoopTemperature = core.protocolSecondLoopProjection(
      (derived.hasSecondColumn ? ["A", "B"] : ["A"])
        .flatMap((columnKey) => boardTopology(columnKey).rows),
    );
    const customProtocolTypes = Object.fromEntries(
      BASELINE_TYPE_IDS.filter((typeId) => replacementSelection(typeId)).map((typeId) => {
        const type = getType(typeId);
        return [
          typeId,
          {
            typeCode: type.protocol_type_code,
            layoutPattern: type.protocol_layout_pattern,
          },
        ];
      }),
    );
    return core.buildProtocolConfig({
      projectName: state.params.projectName,
      projectCode: `${state.params.room || "MCGS"}-${core.fingerprint({
        screenMode: state.params.screenMode,
        columns: activeColumnSpecs(derived),
      }).replace("FNV1A-", "")}`,
      uploadProtocol: state.params.uploadProtocol,
      baudRate: state.params.baudRate,
      stationAddress: state.params.stationAddress,
      tcpPort: state.params.tcpPort,
      tcpBindIp: state.params.tcpBindIp || null,
      tcpipUpload: {
        listen_port: state.params.tcpPort,
        bind_ip: state.params.tcpBindIp || null,
        station_address: state.params.stationAddress,
      },
      protocolColumn,
      representativeColumn: protocolColumn,
      maxCabinetCount,
      relayCounts: { A: maxRelayCount, B: maxRelayCount },
      secondLoopTemperature,
      customProtocolTypes,
    });
  }

  function projectSignature(derived) {
    let protocolConfig = null;
    let protocolConfigError = null;
    try {
      protocolConfig = protocolConfigForProject(derived);
    } catch (error) {
      protocolConfigError = String(error.message || error);
    }
    return core.fingerprint({
      params: state.params,
      typesA: state.typesA,
      typesB: derived.hasSecondColumn ? state.typesB : [],
      secondLoopTemperatureModes: Object.fromEntries(
        Object.entries(state.secondLoopTemperatureModes)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, value]) => [key, value]),
      ),
      mappings: circuitMappingSnapshot(derived),
      protocolConfig,
      protocolConfigError,
    });
  }

  function protocolViewState(derived) {
    const signature = projectSignature(derived);
    if (state.protocol.status === "generating") return { status: "generating", signature };
    if (state.protocol.status === "failed" && state.protocol.signature === signature) {
      return { status: "failed", signature };
    }
    if (state.protocol.result && state.protocol.signature === signature) {
      return { status: "generated", signature };
    }
    if (state.protocol.result) return { status: "stale", signature };
    return { status: "idle", signature };
  }

  function artifactDownload(result, key) {
    return core.protocolArtifactDownload(result, key);
  }

  function protocolBundleStatus(result) {
    return core.protocolBundleStatus(result);
  }

  function dynamicDeviceActions(derived) {
    const p = state.params;
    const view = protocolViewState(derived);
    const rows = core
      .buildManualDeviceInterfaceActions(source.runtimeModel.manualDeviceActions, {
        hasSecondColumn: derived.hasSecondColumn,
        screenLinkEnabled: false,
      })
      .map((row) => ({
        targetPath: row.targetPath,
        property: row.property,
        old: row.old,
        new: row.new,
        reason:
          row.targetId === "mcgs:interface:SerialPort_B"
            ? "单屏单列不使用第二物理列串口，父接口初始状态需设为停止。"
            : "当前项目没有屏间TCP互传，父接口初始状态需设为停止；它不是动环TCP/IP上传设备。",
      }));
    if (view.status === "generated") {
      rows.push({
        targetPath:
          p.uploadProtocol === "modbus_rtu_forwarder"
            ? "设备窗口/COM4/upload/设备信息/导入通道表"
            : "设备窗口/数据上传_以太网/设备信息/导入通道表",
        property: "formal_channel_table",
        old: "模板通道表",
        new: `${state.protocol.result?.program_upload?.point_count || "已生成"}点项目通道表`,
        reason: "三件套同源生成；这是设备窗口无法由运行策略替代的导入动作。",
        download: artifactDownload(state.protocol.result, "program_upload"),
      });
    }
    if (p.uploadProtocol === "modbus_rtu_forwarder") {
      if (String(p.serialPort || "COM4").toUpperCase() !== "COM4") {
        rows.push({
          targetPath: "设备窗口/COM4/参数设置/串口号",
          property: "serial_port",
          old: "COM4",
          new: p.serialPort,
          reason: "项目串口与模板COM4不同，父接口参数必须手工回读并修改。",
        });
      }
      if (Number(p.baudRate) !== 9600) {
        rows.push({
          targetPath: "设备窗口/COM4/参数设置/波特率",
          property: "baud_rate",
          old: 9600,
          new: p.baudRate,
          reason: "项目波特率与模板不同，运行策略不会修改父接口串口参数。",
        });
      }
      if (p.confirmStation && Number(p.stationAddress) !== 1) {
        rows.push({
          targetPath: "设备窗口/COM4/upload/驱动属性/设备地址",
          property: "device_address",
          old: 1,
          new: p.stationAddress,
          reason: "已确认的动环从站地址与模板不同。",
        });
      }
    }
    return rows;
  }

  function protocolStatusHtml(derived) {
    const view = protocolViewState(derived);
    const result = state.protocol.result;
    const buttonLabel = view.status === "generated" ? "重新生成动环三件套" : "生成动环三件套";
    const disabled = view.status === "generating" ? " disabled" : "";
    let statusHtml = '<span class="status-tag is-pending">尚未生成</span>';
    if (view.status === "generating") statusHtml = '<span class="status-tag is-pending">正在生成</span>';
    if (view.status === "stale") statusHtml = '<span class="status-tag is-pending">参数已变化</span>';
    if (view.status === "failed") statusHtml = '<span class="status-tag is-danger">生成失败</span>';
    if (view.status === "generated") {
      const label = result?.delivery_status?.label || result?.delivery_status?.status || "生成成功";
      statusHtml = `<span class="status-tag is-ready">${escapeHtml(label)}</span>`;
    }
    const downloads = view.status === "generated"
      ? [
          ["excel", "下载动环通讯协议"],
          ["program_upload", "下载设备导入表"],
          ["alarm_code", "下载报警状态字代码"],
        ]
          .map(([key, label]) => {
            const href = artifactDownload(result, key);
            return href ? `<a class="button button-secondary button-small" href="${escapeHtml(href)}" download>${escapeHtml(label)}</a>` : "";
          })
          .join("")
      : "";
    const detail = view.status === "failed"
      ? `<p class="notice is-danger"><strong>具体原因：</strong>${escapeHtml(state.protocol.error)}</p>`
      : view.status === "stale"
        ? '<p class="notice is-warning">当前页面参数已变化。旧文件仍保留，但不会再作为本项目当前成果；点击按钮按当前参数重新生成。</p>'
        : view.status === "generated"
          ? '<p class="notice">三个文件已按当前项目参数生成，可以直接下载。</p>'
          : '<p class="notice">一次生成动环协议、设备导入表和报警状态字代码。</p>';
    return `<section class="section-block protocol-studio-card">
      <div class="section-heading">
        <div><h3>生成动环文件</h3><p>生成结果与第一页的箱型、数量和上传方式一致。</p></div>
        ${statusHtml}
      </div>
      <div class="protocol-actions">
        <button type="button" class="button button-primary" data-generate-protocol${disabled}>${escapeHtml(view.status === "generating" ? "正在生成…" : buttonLabel)}</button>
        ${downloads}
      </div>
      ${detail}
    </section>`;
  }

  function renderDevice(derived) {
    const rows = dynamicDeviceActions(derived);
    const protocol = protocolViewState(derived);
    const actionCount = rows.length + (protocol.status === "generated" ? 0 : 1);

    root.innerHTML =
      hero("device", `${actionCount}项需要操作`, protocol.status !== "generated") +
      instruction(
        "设备窗口 → 对应父接口 / 子设备 → 设备属性与通道",
        "只执行下表中与当前项目不同的设置；动环文件可在本页一次生成。",
      ) +
      `${protocolStatusHtml(derived)}
      <section class="section-block">
        <div class="section-heading"><div><h3>必须执行的设备操作</h3><p>只显示当前项目确实不能由运行策略完成的动作。</p></div></div>
        ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>MCGS位置</th><th>模板值</th><th>目标</th><th>为什么必须手工</th><th>操作</th></tr></thead><tbody>
          ${rows
            .map(
              (row) => `<tr>
                <td><span class="cell-object">${escapeHtml(row.targetPath)}</span></td>
                <td>${escapeHtml(deviceValue(row.old))}</td>
                <td class="value-target">${escapeHtml(deviceValue(row.new))}</td>
                <td class="cell-reason">${escapeHtml(row.reason)}</td>
                 <td>${row.download ? `<a class="button button-secondary button-small" href="${escapeHtml(row.download)}" download>下载设备导入表</a>` : copyButton(String(row.new), "复制目标值")}</td>
              </tr>`,
            )
            .join("")}
        </tbody></table></div>` : '<div class="empty-state"><div><strong>当前没有设备层手工修改</strong><span>生成三件套后，设备导入表会作为唯一导入动作出现在这里；与模板相同的父接口参数不会重复显示。</span></div></div>'}
      </section>`;
  }

  function mappingLane(columnKey, busPath, label) {
    const config = columnMappingConfig(columnKey);
    const boxes = new Map();
    for (const slot of outputSlots(columnKey)) {
      if (!boxes.has(slot.boxPosition)) boxes.set(slot.boxPosition, []);
      boxes.get(slot.boxPosition).push(slot);
    }
    return `<div class="mapping-lane">
      <div class="mapping-lane-label">${escapeHtml(label)}<br />${escapeHtml(busPath)}路</div>
      <div class="mapping-slots">
        ${Array.from(boxes.entries())
          .map(
            ([boxPosition, slots]) => {
              const boxName = `C${config.boxBase[busPath] + boxPosition}`;
              return `<div class="mapping-box" style="--branch-count:${slots.length}" title="${boxName}">
              ${slots
                .map(
                  (slot) => {
                    const cabinetIndex = mappingValue(columnKey, busPath, slot.key);
                    const cabinetId = `${config.cabinetPrefix}${String(cabinetIndex).padStart(2, "0")}`;
                    return `<div class="mapping-phase${cabinetIndex === 0 ? " is-spare" : ""}">
                    <small>${boxName}<br />${escapeHtml(branchLabel(slot))}</small>
                    <strong>${escapeHtml(cabinetIndex === 0 ? "备用" : cabinetId)}</strong>
                  </div>`;
                  }
                )
                .join("")}
            </div>`;
            },
          )
          .join("")}
      </div>
    </div>`;
  }

  function jgTable(columnKey, actions) {
    const rows = actions.filter((row) => row.column === columnKey);
    return `<details class="data-group"${columnKey === "COL-A" ? " open" : ""}>
      <summary><span>${columnKey === "COL-A" ? "第一物理列" : "第二物理列"}<span class="group-count">${rows.length}项实际变化</span></span></summary>
      <div class="table-wrap"><table><thead><tr><th>变量</th><th>模板初值</th><th>目标值</th><th>含义</th><th>复制</th></tr></thead><tbody>
        ${rows
          .map(
            (row) => `<tr>
              <td class="cell-object">${escapeHtml(row.objectName)}</td>
              <td class="cell-value">${escapeHtml(formatValue(row.beforeValue))}</td>
              <td class="cell-value value-target">${escapeHtml(formatValue(row.targetValue))}</td>
              <td>${row.targetValue === 0 ? "备用 / 未使用" : `机柜索引 ${row.targetValue}`}</td>
               <td>${copyButton(String(row.targetValue), "复制目标值")}</td>
            </tr>`,
          )
          .join("")}
      </tbody></table></div>
    </details>`;
  }

  function renderJgDl(derived) {
    const valid = derived.circuitMapping.ready;
    const actions = valid ? dynamicJgDlActions(derived) : [];
    const assignments = actions.map((row) => `${row.objectName}=${row.targetValue}`).join("\n");
    root.innerHTML =
      hero("jgdl", valid ? `${actions.length}项需要写入` : "请先补全第一页接线关系", !valid) +
      instruction(
        derived.hasSecondColumn
          ? "实时数据库 → JG_DL01…50 / JG_DL01_B…50 → 基本属性 → 初值"
          : "实时数据库 → JG_DL01…50 → 基本属性 → 初值",
        "按对象名定位，只改下表中的目标值；0表示这个输出备用。",
      ) +
      ` ${
        valid
          ? `<section class="section-block"><div class="section-heading"><div><h3>需要写入的机柜对应值</h3><p>每一行都给出MCGS对象名和可以直接复制的目标值。</p></div>${actions.length ? copyButton(assignments, "复制核对清单", { className: "button button-secondary button-small" }) : ""}</div>${actions.length ? `<div class="group-stack">${jgTable("COL-A", actions)}${derived.hasSecondColumn ? jgTable("COL-B", actions) : ""}</div>` : ""}</section>`
          : ""
      }`;
  }

  function triggerText(file) {
    const expression = file.trigger?.expression;
    return expression === "" || expression === null || expression === undefined
      ? "留空（默认成立）"
      : expression;
  }

  function codePreview(content) {
    const lines = content.split(/\r?\n/);
    const preview = lines.slice(0, 13).join("\n");
    return preview + (lines.length > 13 ? "\n…" : "");
  }

  function splitCodeBlocks(content) {
    const pattern = /^' ===== (.+?) =====\s*$/gm;
    const matches = Array.from(content.matchAll(pattern));
    if (!matches.length) return [];
    return matches.map((match, index) => {
      const start = match.index;
      const end = index + 1 < matches.length ? matches[index + 1].index : content.length;
      return { label: match[1], content: content.slice(start, end).trim() };
    });
  }

  function codeCard(file, locked = false) {
    codeStore.set(file.id, file);
    const actionableTrigger = core.actionableTriggerExpression(triggerText(file));
    const wholeCopy =
      !locked && file.copyMode === "whole"
        ? copyButton(file.content, "复制完整代码", {
            className: "button button-primary button-small",
          })
        : "";
    const blocks = file.copyMode === "blocks" ? splitCodeBlocks(file.content) : [];
    const blockButtons = !locked && blocks.length
      ? `<div class="block-copies"><span class="muted">按目标逐块复制：</span>${blocks
          .map((block) => copyButton(block.content, block.label, { title: `复制${block.label}` }))
          .join("")}</div>`
      : "";
    return `<article class="code-card${file.stage === "alarm" ? " is-alarm" : ""}${locked ? " is-locked" : ""}">
      <div class="code-title">
        <h3>${escapeHtml(file.scriptName)}</h3>
      </div>
      <div class="code-actions">
        ${wholeCopy}
        ${locked ? '<span class="status-tag is-pending">当前映射禁止复制</span>' : `<button type="button" class="button button-secondary button-small" data-view-code-id="${escapeHtml(file.id)}">${file.copyMode === "blocks" ? "查看完整汇总" : "查看完整代码"}</button>`}
      </div>
      <div class="code-meta">
        <span>到哪里改：<strong>${escapeHtml(file.target)}</strong></span>
        ${actionableTrigger ? `<span>触发条件：<code>${escapeHtml(actionableTrigger)}</code></span>` : ""}
      </div>
      <p class="code-note"><strong>怎么改：</strong>${escapeHtml(file.note)}</p>
      ${blockButtons}
    </article>`;
  }

  function codeGroup(title, subtitle, files, open = false, locked = false) {
    return `<details class="data-group"${open ? " open" : ""}>
      <summary><span>${escapeHtml(title)}<span class="group-count">${files.length}份代码 · ${escapeHtml(subtitle)}</span></span></summary>
      <div class="section-block code-list">${files.map((file) => codeCard(file, locked)).join("")}</div>
    </details>`;
  }

  function generatedFile({
    id,
    stage,
    strategy,
    scriptName,
    target,
    content,
    copyMode = "whole",
    trigger = "1",
    execution = { mode: "被调用时执行" },
    note = "由当前项目参数和输出映射即时生成。",
  }) {
    const normalized = String(content || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n").trimEnd() + "\n";
    return {
      id,
      stage,
      strategy,
      scriptName,
      target,
      content: normalized,
      copyMode,
      trigger: { expression: trigger },
      execution,
      note,
      lines: normalized.split("\n").length - 1,
      bytes: new TextEncoder().encode(normalized).length,
      fingerprint: core.fingerprint({ id, target, normalized }),
      generated: true,
    };
  }

  function columnCodeConfig(columnKey, derived) {
    const second = columnKey === "B";
    return {
      columnKey,
      label: second ? "第二物理列" : "第一物理列",
      cabinetPrefix: second ? "B" : "A",
      cabinetCount: second ? state.params.cabinetCountB : state.params.cabinetCountA,
      boxCount: second ? state.params.boxCountB : state.params.boxCountA,
      types: second ? state.typesB : state.typesA,
      column: second ? derived.columnB : derived.columnA,
      headA: second ? derived.headArrays.BA : derived.headArrays.AA,
      headB: second ? derived.headArrays.BB : derived.headArrays.AB,
      headFamily: second ? "BA" : "AA",
      boxBase: second ? { A: 300, B: 400 } : { A: 100, B: 200 },
      strategyPrefix: second ? "B" : "A",
      metricFamilies: second
        ? { I: ["IBA", "IBB", "IB"], P: ["PBA", "PBB", "PB"], E: ["EBA", "EBB", "EB"], K: ["KBA", "KBB"] }
        : { I: ["IAA", "IAB", "IA"], P: ["PAA", "PAB", "PA"], E: ["EAA", "EAB", "EA"], K: ["KAA", "KAB"] },
    };
  }

  function branchElectricalDescriptor(typeId, branchNo) {
    const type = getType(typeId);
    const descriptor = type.electrical_branches?.[Number(branchNo) - 1];
    return descriptor
      ? {
          boardOffset: descriptor.boardOffset,
          loop: descriptor.loop,
          mode: descriptor.mode,
          phaseIndex: descriptor.phaseIndex,
          switchBits: [...descriptor.switchBits],
          boardTemplateId: descriptor.boardTemplateId,
        }
      : null;
  }

  function metricSource(columnKey, typeId, branchNo, metric, boardHead) {
    const descriptor = branchElectricalDescriptor(typeId, branchNo);
    if (!descriptor) throw new Error(`类型${typeId}的电气源规则尚未确认`);
    const address = boardHead + descriptor.boardOffset;
    const suffix = descriptor.loop === 2 ? "_2" : "";
    if (metric === "K") {
      return core.switchReadAnyExpression(
        columnKey,
        `StateC${address}${suffix}`,
        descriptor.switchBits,
      );
    }
    const prefix = metric;
    if (descriptor.mode === "single") {
      return `${prefix}${["a", "b", "c"][descriptor.phaseIndex]}${address}${suffix}`;
    }
    return `${prefix}a${address}${suffix} + ${prefix}b${address}${suffix} + ${prefix}c${address}${suffix}`;
  }

  function boxWindowName(columnKey, boxPosition) {
    const config = columnMappingConfig(columnKey);
    const typeId = config.types[boxPosition - 1] || "3x1P";
    const type = getType(typeId);
    if (isSinglePhaseTriplet(typeId)) {
      const boxSlots = outputSlots(columnKey).filter((slot) => slot.boxPosition === boxPosition);
      const same = boxSlots.every(
        (slot) => mappingValue(columnKey, "A", slot.key) === mappingValue(columnKey, "B", slot.key),
      );
      return same ? "插接箱" : "插接箱_AB路不同";
    }
    return type?.windows?.[0] || "待创建窗口";
  }

  function currentProgramDiffPlan(derived) {
    const columns = {};
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const config = columnCodeConfig(columnKey, derived);
      columns[columnKey === "A" ? "COL-A" : "COL-B"] = {
        boxCount: config.boxCount,
        cabinetCount: config.cabinetCount,
        boxes: core.groupSlotsByBox(outputSlots(columnKey)).map((slots) => ({
          position: slots[0]?.boxPosition || 0,
          typeId: slots[0]?.typeId || "",
          windowName: boxWindowName(columnKey, slots[0]?.boxPosition || 0),
          routeA: slots.map((slot) => mappingValue(columnKey, "A", slot.key)),
          routeB: slots.map((slot) => mappingValue(columnKey, "B", slot.key)),
        })),
      };
    }
    return core.buildProgramDiffPlan({
      hasSecondColumn: derived.hasSecondColumn,
      columns,
    });
  }

  function localRoutePairingIssues(derived) {
    const issues = [];
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const byBox = core.groupSlotsByBox(outputSlots(columnKey));
      for (const slots of byBox) {
        const position = slots[0]?.boxPosition;
        const typeId = slots[0]?.typeId;
        const aValues = slots.map((slot) => mappingValue(columnKey, "A", slot.key)).filter(Boolean).sort((a, b) => a - b);
        const bValues = slots.map((slot) => mappingValue(columnKey, "B", slot.key)).filter(Boolean).sort((a, b) => a - b);
        if (aValues.join(",") !== bValues.join(",")) {
          issues.push(`${columnMappingConfig(columnKey).label}第${position}箱：A/B路在该箱内不是同一组机柜`);
        }
        if (!isSinglePhaseTriplet(typeId)) {
          const branchMismatch = slots.some(
            (slot) => mappingValue(columnKey, "A", slot.key) !== mappingValue(columnKey, "B", slot.key),
          );
          if (branchMismatch) {
            issues.push(`${columnMappingConfig(columnKey).label}第${position}箱（${typeId}）：三相分路要求A/B路同分路对应同一机柜`);
          }
        }
      }
    }
    return Array.from(new Set(issues));
  }

  function dynamicPackageIssues(derived) {
    const issues = [];
    if (!derived.circuitMapping.ready) issues.push("A/B路机柜映射仍有缺失或重复");
    if (!derived.withinTemplate) issues.push("至少一项容量超过现有模板结构");
    const dualLoop = dualLoopConfiguration(derived);
    if (!dualLoop.complete) issues.push("第二回路温度来源尚未全部选择");
    issues.push(...localRoutePairingIssues(derived));
    return Array.from(new Set(issues));
  }

  function alarmDescriptionColumnInput(derived, columnKey) {
    const config = columnCodeConfig(columnKey, derived);
    const templateKey = columnKey === "A" ? "columnA" : "columnB";
    const template = source.alarmTemplates?.[templateKey];
    const issues = [];
    if (!template?.content) {
      issues.push(`${config.label}缺少完整报警描述基线脚本${columnKey === "A" ? "05" : "06"}`);
      return { columnKey, config, template, boxDetails: [], boardPatches: [], issues };
    }

    const boxDetails = [];
    const boardPatches = [];
    for (const slots of core.groupSlotsByBox(outputSlots(columnKey))) {
      const position = slots[0]?.boxPosition || 0;
      const typeId = slots[0]?.typeId || "";
      if (!isSinglePhaseTriplet(typeId)) continue;
      const aValues = slots.map((slot) => mappingValue(columnKey, "A", slot.key));
      const bValues = slots.map((slot) => mappingValue(columnKey, "B", slot.key));
      try {
        const selectors = core.alarmSelectorPermutation(aValues, bValues);
        const changed = selectors.some((selector, index) => selector !== index + 1);
        const boardNo = Number(config.headB[position - 1] || 0);
        if (boardNo <= 0) throw new Error(`${config.label}第${position}箱缺少B路头板卡地址`);
        boxDetails.push({
          boxPosition: position,
          boardNo,
          aValues,
          bValues,
          selectors,
          changed,
        });
        if (changed) boardPatches.push({ boxPosition: position, boardNo, selectors });
      } catch (error) {
        issues.push(`${config.label}第${position}个3x1P箱无法生成报警机柜选择器：${String(error.message || error)}`);
      }
    }
    return { columnKey, config, template, boxDetails, boardPatches, issues };
  }

  function buildAlarmDescriptionPlan(derived, baselineOverrides = {}) {
    const columns = [];
    const files = [];
    const issues = [];
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const input = alarmDescriptionColumnInput(derived, columnKey);
      const { config, template, boxDetails, boardPatches } = input;
      if (input.issues.length) {
        issues.push(...input.issues);
        continue;
      }
      const override = baselineOverrides[columnKey];
      const baselineContent = String(override?.patchedContent || override?.content || template.content);
      const mergedTypeExtension = Boolean(override && baselineContent !== template.content);
      let patchResult = { text: baselineContent, boards: [], changes: [], matchedLines: 0, changedLines: 0 };
      if (boardPatches.length) {
        try {
          patchResult = core.patchAlarmDescriptionSelectors(baselineContent, boardPatches);
        } catch (error) {
          issues.push(`${config.label}报警描述完整基线变换失败：${String(error.message || error)}`);
          continue;
        }
      }

      const columnSummary = {
        columnKey: columnKey === "A" ? "COL-A" : "COL-B",
        label: config.label,
        scriptNo: template.scriptNo,
        target: template.target,
        threeByOneBoxes: boxDetails.length,
        changedBoxes: boardPatches.length,
        changedLines: patchResult.changedLines,
        modified: patchResult.changedLines > 0,
        mergedTypeExtension,
        boxes: boxDetails,
      };
      columns.push(columnSummary);

      if (columnSummary.modified) {
        const file = generatedFile({
          id: `GEN-ALARM-DESCRIPTION-${String(template.scriptNo).padStart(2, "0")}`,
          stage: "alarm",
          strategy: "修改机柜号及报警",
          scriptName: `${String(template.scriptNo).padStart(2, "0")}_修改报警描述-${columnKey === "A" ? "A列" : "B列"}`,
          target: template.target,
          content: patchResult.text,
          trigger: columnKey === "A" ? "1" : "jgls=1",
          execution: { mode: "被调用时执行" },
          note: mergedTypeExtension
            ? `已把新箱型边界和当前3x1P箱内A/B路机柜选择合成同一份代码；共修改${patchResult.changedLines}处机柜选择，请只复制这份整段替换。`
            : `已按当前3x1P箱内A/B路机柜对应关系修改${patchResult.changedLines}处机柜选择；请整段替换。`,
        });
        file.changeSummary = {
          column: columnSummary.columnKey,
          changedBoxes: boardPatches.length,
          changedLines: patchResult.changedLines,
          matchedLines: patchResult.matchedLines,
          boards: patchResult.boards,
          mergedTypeExtension,
        };
        files.push(file);
      }
    }
    return { ready: issues.length === 0, issues, columns, files };
  }

  function initializationCommentForType(typeId) {
    const type = getType(typeId);
    if (type.phase_mode === "single_phase_triplet") {
      return "3*1P插接箱，一块一拖三单相板卡";
    }
    const countWord = { 1: "一", 2: "两", 3: "三", 4: "四" };
    const labels = {
      board_1to3_3phase: "一拖三板卡",
      board_1to6_3phase_dual: "一拖六双回路板卡",
      board_1to3_single_phase_triplet: "一拖三单相板卡",
    };
    const groups = [];
    for (const templateId of type.board_template_ids) {
      const current = groups[groups.length - 1];
      if (current?.templateId === templateId) current.count += 1;
      else groups.push({ templateId, count: 1 });
    }
    const composition = groups
      .map((group) => `${countWord[group.count] || group.count}块${labels[group.templateId] || group.templateId}`)
      .join("+");
    return `${type.protocol_type_code}插接箱，${composition}`;
  }

  function generateInitializationFiles(derived) {
    const files = [];
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const column = columnKey === "A" ? derived.columnA : derived.columnB;
      const usedSlots = Array.from(
        new Set(column.types.filter((typeId) => replacementSelection(typeId))),
      );
      if (!usedSlots.length) continue;
      const classBoardCounts = {};
      for (const slotId of usedSlots) {
        const slotIndex = BASELINE_TYPE_IDS.indexOf(slotId);
        const classNo = slotIndex + (columnKey === "A" ? 1 : 5);
        classBoardCounts[classNo] = {
          boardCount: getType(slotId).board_count,
          comment: initializationCommentForType(slotId),
        };
      }
      const template = source.initializationTemplates?.[columnKey === "A" ? "columnA" : "columnB"];
      if (!template?.content) {
        throw new Error(`${columnKey === "A" ? "第一" : "第二"}物理列缺少系统初始化完整基线脚本`);
      }
      const patched = core.patchInitializationBoardIncrements(
        template.content,
        classBoardCounts,
      );
      if (!patched.changedLines) continue;
      const slotSummary = usedSlots
        .map((slotId) => {
          const type = getType(slotId);
          return `${slotId}槽→${type.protocol_type_code}/${type.protocol_layout_pattern}（${type.board_count}板）`;
        })
        .join("；");
      files.push(
        generatedFile({
          id: `GEN-INITIALIZATION-${columnKey}`,
          stage: "backend",
          strategy: "系统初始化",
          scriptName: `${String(template.scriptNo).padStart(2, "0")}_布局判断-${columnKey === "A" ? "A列" : "B列"}`,
          target: template.target,
          content: patched.text,
          trigger: "被启动策略调用",
          execution: { mode: "被调用时执行" },
          note: `已同步修改${patched.incrementChanges}处板卡步长和${patched.commentChanges}处箱型注释：${slotSummary}。`,
        }),
      );
      files[files.length - 1].changeSummary = {
        incrementChanges: patched.incrementChanges,
        commentChanges: patched.commentChanges,
        classes: patched.classTargets,
      };
    }
    return files;
  }

  function generateBackendAggregation(derived) {
    const lines = [
      `' 当前项目生成：${state.params.projectName}`,
      `' 目标：运行策略/后台任务/脚本04`,
      "",
      "I1 = Ia1 + Ib1 + Ic1",
      "I2 = Ia2 + Ib2 + Ic2",
      "I3 = Ia3 + Ib3 + Ic3",
      "I4 = Ia4 + Ib4 + Ic4",
      "I_sum = I1 + I2 + I3 + I4",
      "P_sum = P1 + P2 + P3 + P4",
      "E_sum = E1 + E2 + E3 + E4",
      "",
    ];

    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const config = columnCodeConfig(columnKey, derived);
      const columnLines = [`'${config.label}`];
      for (const metric of ["I", "P", "E"]) {
        const [familyA, familyB, totalFamily] = config.metricFamilies[metric];
        for (const [busPath, family, heads] of [
          ["A", familyA, config.headA],
          ["B", familyB, config.headB],
        ]) {
          columnLines.push("", `'${metric}：${busPath}路小计`);
          const grouped = new Map();
          for (const slot of outputSlots(columnKey)) {
            const cabinet = mappingValue(columnKey, busPath, slot.key);
            if (!cabinet) continue;
            const sourceTerm = metricSource(columnKey, slot.typeId, slot.branchNo, metric, heads[slot.boxPosition - 1]);
            if (!grouped.has(cabinet)) grouped.set(cabinet, []);
            grouped.get(cabinet).push(sourceTerm);
          }
          for (let cabinet = 1; cabinet <= core.TEMPLATE_LIMITS.metricCabinets; cabinet += 1) {
            const terms = grouped.get(cabinet) || [];
            columnLines.push(`${family}${String(cabinet).padStart(2, "0")}=${terms.length ? terms.join(" + ") : "0"}`);
          }
        }
        columnLines.push("", `'${metric}：列内总计`);
        for (let cabinet = 1; cabinet <= core.TEMPLATE_LIMITS.metricCabinets; cabinet += 1) {
          const index = String(cabinet).padStart(2, "0");
          columnLines.push(`${totalFamily}${index} = ${familyA}${index} + ${familyB}${index}`);
        }
      }
      const [switchA, switchB] = config.metricFamilies.K;
      for (const [busPath, family, heads] of [
        ["A", switchA, config.headA],
        ["B", switchB, config.headB],
      ]) {
        columnLines.push("", `'K：${busPath}路开关状态`);
        const switchMappings = [];
        for (const slot of outputSlots(columnKey)) {
          const cabinet = mappingValue(columnKey, busPath, slot.key);
          if (!cabinet) continue;
          const descriptor = branchElectricalDescriptor(slot.typeId, slot.branchNo);
          if (!descriptor) throw new Error(`类型${slot.typeId}的电气源规则尚未确认`);
          const address = heads[slot.boxPosition - 1] + descriptor.boardOffset;
          switchMappings.push({
            cabinetIndex: cabinet,
            objectName: `StateC${address}${descriptor.loop === 2 ? "_2" : ""}`,
            bitNos: descriptor.switchBits,
          });
        }
        const expressions = core.aggregateCabinetSwitchExpressions(columnKey, switchMappings);
        const switchLimit = core.TEMPLATE_LIMITS.switchCabinets[columnKey === "B" ? "COL-B" : "COL-A"];
        for (let cabinet = 1; cabinet <= switchLimit; cabinet += 1) {
          columnLines.push(`${family}${String(cabinet).padStart(2, "0")}=${expressions[cabinet] || "0"}`);
        }
      }
      if (columnKey === "B") {
        lines.push("IF jgls = 1 THEN", ...columnLines.map((line) => (line ? `\t${line}` : "")), "ENDIF", "");
      } else {
        lines.push(...columnLines, "");
      }
    }
    return generatedFile({
      id: "GEN-BACKGROUND-04",
      stage: "backend",
      strategy: "后台任务",
      scriptName: "机柜电流、功率、电能与开关状态",
      target: "运行策略 → 后台任务 → 脚本04",
      content: lines.join("\n"),
      trigger: "1",
      execution: { mode: "循环运行", cycle_interval_ms: 1000 },
      note: "I/P/E/K全部从同一份输出回路映射生成；未接输出显式写0。",
    });
  }

  function cabinetExpression(prefix, index) {
    return index > 0 ? `Cabinet_${prefix}${String(index).padStart(2, "0")}` : '"备用"';
  }

  function secondLoopRuntimeValue(columnKey, boxPosition, boardOffset) {
    const row = boardTopology(columnKey).rows.find(
      (item) =>
        Number(item.box_position) === Number(boxPosition) &&
        Number(item.board_offset) === Number(boardOffset),
    );
    const runtimeFlag = core.secondLoopRuntimeFlag(row?.target_value, Boolean(row?.second_loop));
    if (runtimeFlag !== null) return runtimeFlag;
    throw new Error(
      `${columnMappingConfig(columnKey).label}第${boxPosition}箱板卡${Number(boardOffset) + 1}尚未选择第二回路温度来源`,
    );
  }

  function generateOpenBoxFile(columnKey, boxPosition, derived) {
    const config = columnCodeConfig(columnKey, derived);
    const slots = outputSlots(columnKey).filter((slot) => slot.boxPosition === boxPosition);
    const typeId = slots[0]?.typeId || "3x1P";
    const boxNumber = config.boxBase.A + boxPosition;
    const headObject = `CJX_${config.headFamily}${String(boxPosition).padStart(2, "0")}`;
    const lines = [
      `' 当前项目生成：${state.params.projectName}`,
      `' ${config.label}第${boxPosition}箱 / ${typeDisplayLabel(typeId)}`,
      `N_CJX = ${boxNumber}`,
      `N_BK_BAK = ${headObject}`,
      "",
    ];
    if (isSinglePhaseTriplet(typeId)) {
      lines.push("Second_loopT = 0    '本箱没有第二回路", "");
      const same = slots.every(
        (slot) => mappingValue(columnKey, "A", slot.key) === mappingValue(columnKey, "B", slot.key),
      );
      if (same) {
        slots.forEach((slot, index) => {
          lines.push(`Cabinet_${index + 1} = ${cabinetExpression(config.cabinetPrefix, mappingValue(columnKey, "A", slot.key))}`);
        });
      } else {
        lines.push("IF Disabled = 0 THEN", "\t'点插接箱；Cabinet_1~3为A路L1~L3，Cabinet_4~6为B路L1~L3");
        slots.forEach((slot, index) => {
          lines.push(`\tCabinet_${index + 1} = ${cabinetExpression(config.cabinetPrefix, mappingValue(columnKey, "A", slot.key))}`);
        });
        slots.forEach((slot, index) => {
          lines.push(`\tCabinet_${index + 4} = ${cabinetExpression(config.cabinetPrefix, mappingValue(columnKey, "B", slot.key))}`);
        });
        lines.push("ENDIF", "");
        for (const slot of slots) {
          const cabinet = mappingValue(columnKey, "A", slot.key);
          if (!cabinet) continue;
          const bSlot = slots.find((candidate) => mappingValue(columnKey, "B", candidate.key) === cabinet);
          lines.push(
            `IF Disabled = ${core.branchDisabledMask(slot.branchNo)} THEN`,
            "\t'点机柜",
            `\tN_CJX_Text = !Str(N_CJX) + "插接箱L${slot.branchNo} 和 " + !Str(N_CJX+100) + "插接箱L${bSlot.branchNo}"`,
            `\tPhase_Sel = ${slot.branchNo}`,
            `\tPhase_Sel_B = ${bSlot.branchNo}`,
            `\tCabinet = ${cabinetExpression(config.cabinetPrefix, cabinet)}`,
            "ENDIF",
            "",
          );
        }
      }
    } else {
      slots.forEach((slot, index) => {
        const cabinet = mappingValue(columnKey, "A", slot.key);
        lines.push(`Cabinet_${index + 1} = ${cabinetExpression(config.cabinetPrefix, cabinet)}`);
      });
      slots.forEach((slot, index) => {
        lines.push(
          `JG_pointer_${index + 1} = ${core.cabinetDataPointer(columnKey, mappingValue(columnKey, "A", slot.key))}`,
        );
      });
      lines.push("");
      for (const slot of slots) {
        const descriptor = branchElectricalDescriptor(typeId, slot.branchNo);
        const disabled = slot.branchNo === 1 ? "Disabled <= 1" : `Disabled = ${core.branchDisabledMask(slot.branchNo)}`;
        lines.push(
          `IF ${disabled} THEN`,
          `\tCJXchannelFlag = ${slot.branchNo}`,
          `\tN_CJX_BAK = N_BK_BAK${descriptor.boardOffset ? ` + ${descriptor.boardOffset}` : ""}`,
          `\tSecond_loopT = ${secondLoopRuntimeValue(columnKey, boxPosition, descriptor.boardOffset)}    '${secondLoopRuntimeValue(columnKey, boxPosition, descriptor.boardOffset) ? "第二回路独立测温" : "第二回路复用第一回路温度或本板无第二回路"}`,
        );
        if (getType(typeId).has_dual_loop_board) lines.push(`\tCJX_branch = ${descriptor.loop}`);
        lines.push(
          `\tCabinet = Cabinet_${slot.branchNo}`,
          `\tJG_pointer = JG_pointer_${slot.branchNo}`,
          "ENDIF",
          "",
        );
      }
    }
    const strategy = `打开${config.strategyPrefix}${boxPosition}插接箱`;
    return generatedFile({
      id: `GEN-OPEN-${config.strategyPrefix}-${String(boxPosition).padStart(2, "0")}`,
      stage: "backend",
      strategy,
      scriptName: `${strategy}（${typeDisplayLabel(typeId)}）`,
      target: `运行策略 → ${strategy} → 脚本01`,
      content: lines.join("\n"),
      trigger: "1",
      note: `窗口目标：${boxWindowName(columnKey, boxPosition)}；机柜标签、分路和JG_pointer均来自当前映射。`,
    });
  }

  function generateOpenBoxStrategies(derived, diffPlan = currentProgramDiffPlan(derived)) {
    return diffPlan.open_strategies.map((item) =>
      generateOpenBoxFile(item.column === "COL-B" ? "B" : "A", item.position, derived),
    );
  }

  function generateWindowFiles(derived, diffPlan = currentProgramDiffPlan(derived)) {
    const boxBlocks = [];
    const cabinetBlocks = [];
    const boxActionKeys = new Set(
      diffPlan.window.box_buttons.map((item) => `${item.column}|${item.position}`),
    );
    const cabinetActionKeys = new Set(
      diffPlan.window.cabinet_buttons.map((item) => `${item.column}|${item.cabinet}`),
    );
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const config = columnCodeConfig(columnKey, derived);
      const columnId = columnKey === "B" ? "COL-B" : "COL-A";
      for (let position = 1; position <= config.boxCount; position += 1) {
        if (!boxActionKeys.has(`${columnId}|${position}`)) continue;
        boxBlocks.push(
          `' ===== ${config.label}插接箱位置${String(position).padStart(2, "0")} =====\nDisabled = 0\n!SetStgyMode(打开${config.strategyPrefix}${position}插接箱)\n!SetWindow(${boxWindowName(columnKey, position)},1)`,
        );
      }
      for (let cabinet = 1; cabinet <= config.cabinetCount; cabinet += 1) {
        if (!cabinetActionKeys.has(`${columnId}|${cabinet}`)) continue;
        const slot = outputSlots(columnKey).find(
          (candidate) => mappingValue(columnKey, "A", candidate.key) === cabinet,
        );
        if (!slot) continue;
        const disabled = core.branchDisabledMask(slot.branchNo);
        cabinetBlocks.push(
          `' ===== 机柜${config.cabinetPrefix}${String(cabinet).padStart(2, "0")}；${config.label}插接箱位置${String(slot.boxPosition).padStart(2, "0")} =====\nDisabled = ${disabled}\n!SetStgyMode(打开${config.strategyPrefix}${slot.boxPosition}插接箱)\n!SetWindow(${boxWindowName(columnKey, slot.boxPosition)},1)`,
        );
      }
    }
    const files = [];
    if (boxBlocks.length) {
      files.push(generatedFile({
        id: "GEN-WINDOW-BOX-BUTTONS",
        stage: "window",
        strategy: "主系统图",
        scriptName: "插接箱按钮动作",
        target: "用户窗口 → 主系统图 → 插接箱按钮 → 动作脚本",
        content: `' 每次只复制一个编号区块\n\n${boxBlocks.join("\n\n")}`,
        copyMode: "blocks",
        note: "窗口名由每个位置的箱型和A/B路相位关系决定。",
      }));
    }
    if (cabinetBlocks.length) {
      files.push(generatedFile({
        id: "GEN-WINDOW-CABINET-BUTTONS",
        stage: "window",
        strategy: "主系统图",
        scriptName: "机柜按钮动作",
        target: "用户窗口 → 主系统图 → 机柜按钮 → 动作脚本",
        content: `' 每次只复制一个机柜区块\n\n${cabinetBlocks.join("\n\n")}`,
        copyMode: "blocks",
        note: "Disabled、打开策略和窗口名均由同一份机柜输出映射生成。",
      }));
    }
    return files;
  }

  function currentCodePackage(derived) {
    const extension = typeExtensionPlanV2(derived);
    const typeBlockers = extension.enabled ? extension.blockedActions : [];
    const blockedByType = typeBlockers.length > 0;
    const initialization = blockedByType ? [] : generateInitializationFiles(derived);
    const dependentIssues = [
      ...dynamicPackageIssues(derived),
      ...typeBlockers.map((item) => `${item.title}：${item.reason}`),
    ];
    const dependentReady = dependentIssues.length === 0;
    const diffPlan = dependentReady ? currentProgramDiffPlan(derived) : null;
    const dependentBackend = dependentReady
      ? [
          ...(diffPlan.backend_needs_change ? [generateBackendAggregation(derived)] : []),
          ...generateOpenBoxStrategies(derived, diffPlan),
        ]
      : [];
    const windowFiles = dependentReady ? generateWindowFiles(derived, diffPlan) : [];
    const alarmPlan = dependentReady
      ? buildAlarmDescriptionPlan(derived, extension.descriptionOverrides)
      : { ready: false, issues: [...dependentIssues], columns: [], files: [] };
    const alarmIssues = alarmPlan.ready ? [] : alarmPlan.issues;
    const issues = Array.from(new Set([...dependentIssues, ...alarmIssues]));
    return {
      ready: dependentReady && alarmPlan.ready,
      dependentReady,
      initializationReady: true,
      issues,
      dependentIssues,
      backend: [...initialization, ...dependentBackend],
      initialization,
      dependentBackend,
      alarm: alarmPlan.ready ? alarmPlan.files : [],
      alarmReady: alarmPlan.ready,
      window: windowFiles,
      windowReady: dependentReady,
      alarmPlan,
      diffPlan,
      blockedByType,
      typeExtension: extension,
    };
  }

  function renderBackend(derived) {
    const packageResult = currentCodePackage(derived);
    const files = packageResult.backend;
    const typePlan = packageResult.typeExtension;
    const typeStrategyActions = typeExtensionActionsForSurface(typePlan, "strategy");
    const typeBlockedCount = typePlan.blockedActions.length;
    const initialization = packageResult.initialization;
    const background = packageResult.dependentBackend.filter((file) => file.strategy === "后台任务");
    const openA = packageResult.dependentBackend.filter((file) => /^打开A\d+插接箱$/.test(file.strategy));
    const openB = packageResult.dependentBackend.filter((file) => /^打开B\d+插接箱$/.test(file.strategy));
    const totalActions = files.length + typeStrategyActions.length;
    const statusText = typeBlockedCount
      ? `${typeBlockedCount}项箱型相关代码尚不能安全生成`
      : packageResult.dependentReady
        ? `${totalActions}份当前项目代码`
        : `${initialization.length + typeStrategyActions.length}份可先修改，其他代码等待接线`;
    root.innerHTML =
      hero("backend", statusText, !packageResult.dependentReady || typeBlockedCount > 0) +
      instruction(
        "运行策略 → 精确策略名 → 精确脚本序号",
        "按卡片位置打开脚本，整段替换为当前项目代码。只有卡片明确写出触发条件变化时才需要修改条件。",
      ) +
      `<section class="section-block">
        <p class="notice${packageResult.dependentReady && typeBlockedCount === 0 ? "" : " is-warning"}">${typeBlockedCount
          ? "已验证的箱型相关修改会在下方显示；尚未验证的部分只列出阻断原因，不生成猜测代码。"
          : packageResult.dependentReady
            ? "下面所有代码已经按第一页的箱型和A/B路接线生成。"
            : `系统初始化不依赖机柜接线，仍可先复制。其余代码还需要：${packageResult.dependentIssues.join("；")}。`}</p>
      </section>
      <section class="section-block"><div class="group-stack">
        ${initialization.length ? codeGroup("类型槽初始化", "只改Class板卡地址增量 · 完整替换", initialization, true, false) : ""}
        ${background.length ? codeGroup("后台机柜聚合", "I/P/E/K与机柜映射同源", background, true, false) : ""}
        ${openA.length ? codeGroup(`第一物理列打开策略`, `${openA.length}个策略 · 完整替换脚本01`, openA, true, false) : ""}
        ${openB.length ? codeGroup("第二物理列打开策略", `${openB.length}个策略 · 完整替换脚本01`, openB, false, false) : ""}
      </div></section>
      ${typeExtensionSurfaceHtml(typePlan, "strategy")}`;
  }

  function protocolAlarmUploadFile(derived) {
    const view = protocolViewState(derived);
    if (view.status !== "generated" || !state.protocol.alarmCode) return null;
    return generatedFile({
      id: "GEN-PROTOCOL-ALARM-UPLOAD",
      stage: "alarm",
      strategy: "报警状态字上传",
      scriptName: "本项目报警状态字上传代码",
      target: "运行策略 → 项目报警状态字上传脚本 → 完整替换",
      content: state.protocol.alarmCode,
      trigger: "按模板原上传策略保持",
      note: "已按当前项目的报警点顺序生成，整段替换原报警状态字上传代码。",
    });
  }

  function renderAlarm(derived) {
    const packageResult = currentCodePackage(derived);
    const descriptionFiles = packageResult.alarm || [];
    const uploadFile = protocolAlarmUploadFile(derived);
    const files = [...descriptionFiles, ...(uploadFile ? [uploadFile] : [])];
    const changedBoxes = (packageResult.alarmPlan?.columns || []).reduce((sum, item) => sum + item.changedBoxes, 0);
    root.innerHTML =
      hero("alarm", `${files.length}份代码需要替换`, !packageResult.alarmReady) +
      instruction(
        "运行策略 → 报警状态字上传 / 修改机柜号及报警",
        "按卡片写明的位置打开脚本，复制完整代码并整段替换。",
      ) +
      `${descriptionFiles.length ? `<section class="section-block"><div class="group-stack">${codeGroup("报警描述替换代码", `${changedBoxes}个插接箱对应关系变化`, descriptionFiles, true, false)}</div></section>` : ""}
      ${uploadFile ? `<section class="section-block code-list">${codeCard(uploadFile, false)}</section>` : ""}`;
  }

  function guiStepHtml(step) {
    return `<div class="gui-step">
      <div class="gui-step-no">${String(step.step_no).padStart(2, "0")}</div>
      <div><strong>${escapeHtml(step.module)}</strong><p>${escapeHtml(step.instruction)}</p></div>
      <span class="status-tag is-pending">需要操作</span>
    </div>`;
  }

  function currentWindowGuiPlan(derived) {
    return core.buildWindowGuiPlan({
      hasSecondColumn: derived.hasSecondColumn,
      columns: {
        "COL-A": {
          boxCount: state.params.boxCountA,
          cabinetCount: state.params.cabinetCountA,
          relayCount: state.params.relayCountA,
        },
        "COL-B": {
          boxCount: state.params.boxCountB,
          cabinetCount: state.params.cabinetCountB,
          relayCount: state.params.relayCountB,
        },
      },
    });
  }

  function renderWindow(derived) {
    const packageResult = currentCodePackage(derived);
    const files = packageResult.window;
    const typePlan = packageResult.typeExtension;
    const typeWindowActions = typeExtensionActionsForSurface(typePlan, "window");
    const guiPlan = currentWindowGuiPlan(derived);
    const buttonChanges =
      (packageResult.diffPlan?.window?.box_buttons?.length || 0) +
      (packageResult.diffPlan?.window?.cabinet_buttons?.length || 0);
    const totalActions = buttonChanges + guiPlan.actions.length + typeWindowActions.length;
    root.innerHTML =
      hero(
        "window",
        totalActions > 0 ? `${totalActions}项需要修改` : packageResult.windowReady ? "无需修改" : "请先补全第一页接线关系",
        !packageResult.windowReady,
      ) +
      instruction(
        "用户窗口 → 主系统图 → 目标按钮 → 动作脚本",
        "只处理下面列出的按钮或新增控件；模板中已经正确的内容不用动。",
      ) +
      `${packageResult.windowReady && files.length ? `<section class="section-block code-list">${files.map((file) => codeCard(file, false)).join("")}</section>` : ""}
      ${guiPlan.actions.length ? `<section class="section-block">
        <div class="section-heading"><div><h3>还需要在画面中新增的控件</h3><p>进入对应窗口后先按Ctrl+F6解除固化；同坐标叠层要整组保留。</p></div></div>
        <div class="gui-step-list">${guiPlan.actions.map(guiStepHtml).join("")}</div>
      </section>` : ""}
      ${typeExtensionSurfaceHtml(typePlan, "window")}`;
  }

  function circuitMappingSnapshot(derived) {
    const columns = derived.hasSecondColumn ? ["A", "B"] : ["A"];
    return columns.flatMap((columnKey) =>
      ["A", "B"].map((busPath) => ({
        column: columnKey === "A" ? "COL-A" : "COL-B",
        bus_path: busPath,
        values: currentRouteValues(columnKey, busPath),
        outputs: outputSlots(columnKey).map((slot) => ({
          box_position: slot.boxPosition,
          branch_no: slot.branchNo,
          type_id: slot.typeId,
          cabinet_index: mappingValue(columnKey, busPath, slot.key),
        })),
        validation: routeMappingStatus(columnKey, busPath),
      })),
    );
  }

  const NEW_TYPE_IMPACTS = [
    {
      id: "TXT-036",
      module: "模板槽身份 / 目标电气结构",
      targets: "被替换的CJX_Class槽，以及所有实际使用该槽的箱位、策略、窗口、变量和设备引用",
      action: "保留Class、Layout位和窗口入口的模板身份；把所有活动箱位统一解释为所选板卡组合，并记录基线、目标和使用位置。",
      automation: "同一模板槽只有一个项目目标结构；仅活动箱位使用了非基线组合时才出现替换步骤，不再用旧类型同槽模型阻断安全代码生成。",
    },
    {
      id: "TXT-037",
      module: "系统初始化 / 布局判断",
      targets: "系统初始化脚本02、03；Layout、Layout_sub、CJX_Class、CJX_AA/AB/BA/BB",
      action: "把被替换类型的板卡地址增量改为新板卡数，并逐箱回读四路头板卡地址。",
      automation: "以完整基线脚本及其SHA-256为底稿，只修改目标Class附近的n=n+板卡数；装配台直接给完整可复制稿和改动行数。",
    },
    {
      id: "TXT-038",
      module: "分合闸报警开关",
      targets: "修改机柜号及报警脚本03、04",
      action: "按新类型板卡、分路、相位与StateC位号重建报警使能和位映射。",
      automation: "StateC规则明确后可生成代码。",
    },
    {
      id: "TXT-039",
      module: "报警描述",
      targets: "修改机柜号及报警脚本05、06",
      action: "修改new_CJX/BK_pointer推进、JG_DL读取次数、机柜名和描述模板。",
      automation: "需完整分路/第二回路/JG_DL遍历规则，禁止套用6或9等案例常量。",
    },
    {
      id: "TXT-040",
      module: "报警限值与功率限值",
      targets: "修改报警限值、修改功率报警限值",
      action: "按有效分路数×每分路相数和第二回路生成限值对象范围。",
      automation: "电气模型明确后可生成变量清单与代码。",
    },
    {
      id: "TXT-041",
      module: "温升柱图",
      targets: "窗口“温升柱图”、策略“温升柱图最大值获取”",
      action: "增加新类型分支、比较次数、温度点顺序和指针步长。",
      automation: "需温度点布局；窗口结构必须GUI扩展。",
    },
    {
      id: "TXT-042",
      module: "限值表格与保存",
      targets: "刷新限值设置表格、手动调用、窗口“限值设置_新”保存按钮",
      action: "同步Branch_number、Exsist_2、分路和第二回路判断。",
      automation: "可生成脚本分支；控件动作必须逐对象回读。",
    },
    {
      id: "TXT-043",
      module: "限值设置保存按钮",
      targets: "窗口“限值设置_新”保存按钮的CJX_Class分支",
      action: "同步Branch_number、Exsist_2、限值组与备份组指针增量，确保只保存可见分路。",
      automation: "可按结构化分路规则生成候选脚本；按钮私有动作必须GUI回读。",
    },
    {
      id: "TXT-044",
      module: "电量归零",
      targets: "策略“电量归零显示框”、窗口“电量归零”",
      action: "按实际板卡数显示板卡1～N，隐藏多余入口并核对每个归零对象。",
      automation: "板卡数明确后可生成清单；窗口元素和动作仍需GUI处理。",
    },
    {
      id: "CROSS-001",
      module: "实时数据库、组对象与采集优化",
      targets: "新点变量、StateC/StateC_2、报警对象、索引组、BK_Branch_list及指针对象",
      action: "从设备点集建立变量/报警/组成员清单，保持组顺序和对象ID边界，并检查指针采集优化设置。",
      automation: "必须依据设备信息导出和原生对象证据扩展；不能凭变量名猜对象结构。",
    },
    {
      id: "CROSS-002",
      module: "设备点表、第二回路与通讯防误判",
      targets: "设备窗口点位、BK_Branch_list、后台脚本02/03、通讯错误判断、关闭多余采集设备",
      action: "导入新点集，定义每板回路1/2和温度共享，验证停用设备不报警、通讯失败时两回路均正确清零。",
      automation: "装配台收集规则和生成期望矩阵；设备树结构与点表必须GUI导入/回读。",
    },
    {
      id: "CROSS-003",
      module: "打开策略、画面取数与窗口生命周期",
      targets: "打开A/B插接箱策略、插接箱画面数据获取、普通/测温窗口、主系统图按钮",
      action: "生成板卡偏移、回路、Disabled、JG_pointer和窗口动作；核对启动/循环/退出复位及全部硬编码窗口名。",
      automation: "明确分路结构后可生成候选策略和按钮代码；新窗口、叠层控件与固化状态必须GUI扩展。",
    },
    {
      id: "CROSS-004",
      module: "后台机柜聚合",
      targets: "后台任务脚本04的I/P/E/K公式",
      action: "从同一份circuit_mappings按新类型电气源规则生成机柜小计和总计。",
      automation: "电气模型、StateC规则明确后可生成。",
    },
    {
      id: "CROSS-005",
      module: "动环三件套",
      targets: "动环协议、设备导入CSV、报警状态字上传代码",
      action: "增加动环type_code、layout_pattern、点表和状态字位定义后调用统一生成器。",
      automation: "参数齐全后由已集成协议工具一次生成并验证。",
    },
    {
      id: "CROSS-006",
      module: "概览、历史、颜色和温度显示",
      targets: "电力概览/刷新策略、颜色规则、普通/测温窗口多余温度点、历史与概览入口",
      action: "检查混合相制与名称解析，应用项目颜色表，隐藏无来源温度并核对历史/概览对象范围。",
      automation: "名称和温度顺序可生成核对表；坐标、颜色和控件可见性必须GUI确认。",
    },
    {
      id: "CROSS-007",
      module: "端到端回归",
      targets: "配方→启动链→设备→后台→报警→窗口→动环上传",
      action: "MCP副本Save As、重提取、编译、仿真，逐分路/逐相/逐报警位抽检。",
      automation: "静态检查可自动；MCGS运行与现场验证必须人工完成。",
    },
    {
      id: "CROSS-008",
      module: "板卡地址、跳线与Address_Skew",
      targets: "头板卡地址、Address_Skew、板卡间跳线和地址偏移短接线",
      action: "逐板记录物理地址与跳线关系；只有实际存在地址偏移时才改Address_Skew，并与四组头板卡数组和设备站号交叉核对。",
      automation: "可从结构化地址表生成期望值；物理跳线方向必须现场或图纸确认。",
    },
    {
      id: "CROSS-009",
      module: "通讯拓扑、状态模式与性能参数",
      targets: "AB_together、SerialPort_A/B、第二COM口、Comm_mode、ReturnMain_Timer、采集周期/等待时间、I_H/I_HS及功率过滤上限",
      action: "确认AB路共口还是分口、板卡是否带秒计数器和设备规模；再决定父接口启停、通讯判断、首次通讯保护、采集周期与异常数据上限。",
      automation: "设备数量和确认值可生成建议表；COM口物理接法、板卡能力和现场时序必须确认后才能写入。",
    },
    {
      id: "CROSS-010",
      module: "第二回路、DO下发与RT温度方向",
      targets: "Second_loopT、CJX_branch、BK_Branch_list、配地址DO输出、RT1~RT8、修改温度报警限值",
      action: "逐板定义回路1/2、温度共用或独立、三相/单相组合以及RT点正反序；同步修改窗口退出复位、画面取数、DO下发和温度报警对象。",
      automation: "结构化回路表可生成变量、代码和点位对账；真实接线方向必须以点表或现场为准。",
    },
    {
      id: "CROSS-011",
      module: "报警双组、颜色、历史与存盘",
      targets: "蜂鸣器报警组、报警显示组、插接箱颜色、历史存盘组对象、历史表格和多余温度通道",
      action: "同一报警同时核对蜂鸣器组与显示组；按项目颜色表处理窗口，隐藏无来源温度；删除历史成员前同步核对历史窗口表格绑定。",
      automation: "可生成组成员差异和引用清单；颜色、控件可见性及删除动作必须GUI回读。",
    },
    {
      id: "CROSS-012",
      module: "始端箱、电源模块与特殊概览结构",
      targets: "无始端箱场景、尾端级联24V电源、电源模块判断、电力概览初始化与名称解析",
      action: "确认每路是否有始端箱和尾端电源；没有则同步收敛配地址、设备、报警和窗口入口。混合相制或名称结构变化时同步修改电力概览初始化与刷新判断。",
      automation: "项目拓扑明确后可生成影响清单；是否有实物和名称结构必须由图纸/现场确认。",
    },
  ];

  function typeExtensionPlan(derived) {
    const topologyByColumn = {
      "COL-A": boardTopology("A"),
      "COL-B": derived.hasSecondColumn ? boardTopology("B") : null,
    };
    const allPositions = [
      ...state.typesA.slice(0, state.params.boxCountA).map((typeId, index) => ({ column: "COL-A", position: index + 1, typeId })),
      ...(derived.hasSecondColumn
        ? state.typesB.slice(0, state.params.boxCountB).map((typeId, index) => ({ column: "COL-B", position: index + 1, typeId }))
        : []),
    ];
    const slotIds = Array.from(
      new Set(
        allPositions
          .filter((item) => replacementSelection(item.typeId))
          .map((item) => item.typeId),
      ),
    );
    const replacements = slotIds.map((slotId) => {
      const baselineSelection = core.PROTOCOL_TYPE_MAP[slotId];
      const baseline = core.protocolLayoutDescriptor(
        state.protocolCatalog,
        baselineSelection.typeCode,
        baselineSelection.layoutPattern,
      );
      const target = protocolDescriptorForType(slotId);
      const positions = allPositions
        .filter((item) => item.typeId === slotId)
        .map((position) => ({
          ...position,
          boards: (topologyByColumn[position.column]?.rows || []).filter(
            (row) => row.box_position === position.position,
          ),
        }));
      const unresolvedBoards = positions.flatMap((position) =>
        position.boards.filter((board) => board.second_loop && board.status === "unresolved"),
      );
      return {
        slotId,
        classA: TYPES[slotId]?.class_by_column?.["COL-A"] || "",
        classB: TYPES[slotId]?.class_by_column?.["COL-B"] || "",
        baseline,
        target,
        positions,
        temperatureModeComplete: unresolvedBoards.length === 0,
        unresolvedBoards,
      };
    });
    const usedPositions = replacements.flatMap((item) => item.positions);
    const missing = replacements
      .flatMap((item) => item.unresolvedBoards)
      .map(
        (board) =>
          `${board.column === "COL-A" ? "第一" : "第二"}物理列第${String(board.box_position).padStart(2, "0")}箱·板卡${board.board_ordinal}温度方式`,
      );
    return {
      enabled: replacements.length > 0,
      used: replacements.length > 0,
      replacements,
      usedPositions,
      missing,
      complete: replacements.length > 0 && missing.length === 0,
    };
  }

  function typeExtensionPlanV2(derived) {
    const base = typeExtensionPlan(derived);
    const extensionPlans = base.replacements.map((replacement) => {
      if (!typeExtensionCore) {
        return {
          slotId: replacement.slotId,
          schemaVersion: "mcgs-type-extension-plan/1.0",
          status: "blocked",
          manualActions: [],
          blockedActions: [
            {
              id: "TYPE-CORE-MISSING",
              title: `${replacement.slotId}槽专项修改稿`,
              location: "运行策略 → 因箱型变化",
              reason: "箱型专项生成模块未载入。",
            },
          ],
          sourceEvidence: [],
        };
      }
      return {
        slotId: replacement.slotId,
        ...typeExtensionCore.buildTypeExtensionActions({
          slotId: replacement.slotId,
          hasSecondColumn: derived.hasSecondColumn,
          target: replacement.target,
          positions: replacement.positions,
          sources: typeExtensionSources,
        }),
      };
    });
    const allManualActions = extensionPlans.flatMap((item) => item.manualActions || []);
    const descriptionOverrides = {};
    const mergedDescriptionColumns = [];
    for (const columnKey of derived.hasSecondColumn ? ["A", "B"] : ["A"]) {
      const action = allManualActions.find((item) => item.id === `TYPE-DESCRIPTION-${columnKey}`);
      if (!action?.patchedContent) continue;
      const alarmInput = alarmDescriptionColumnInput(derived, columnKey);
      if (alarmInput.issues.length === 0 && alarmInput.boardPatches.length > 0) {
        descriptionOverrides[columnKey] = action;
        mergedDescriptionColumns.push(columnKey);
      }
    }
    const mergedIds = new Set(mergedDescriptionColumns.map((columnKey) => `TYPE-DESCRIPTION-${columnKey}`));
    const manualActions = allManualActions.filter((item) => !mergedIds.has(item.id));
    const blockedActions = extensionPlans.flatMap((item) => item.blockedActions || []);
    return {
      ...base,
      schemaVersion: "mcgs-type-extension-ui-plan/2.0",
      extensionPlans,
      descriptionOverrides,
      mergedDescriptionColumns,
      manualActions,
      blockedActions,
      complete: base.complete && blockedActions.length === 0,
    };
  }

  function typeActionCodeFile(action) {
    if (!action.patchedContent) return null;
    return generatedFile({
      id: `TYPE-ACTION-${action.id}`,
      stage: "type-extension",
      strategy: action.title,
      scriptName: action.title,
      target: action.location,
      content: action.patchedContent,
      trigger: "保持原脚本触发条件",
      execution: { mode: "保持原策略运行参数" },
      note: action.instruction,
    });
  }

  function typeManualActionHtml(action, index) {
    const codeFile = typeActionCodeFile(action);
    if (codeFile) return codeCard(codeFile, false);
    const operations = Array.isArray(action.guiOperations) ? action.guiOperations : [];
    const copyTextValue = action.content || operations.map((item, itemIndex) => `${itemIndex + 1}. ${item}`).join("\n");
    return `<article class="manual-action-card">
      <header class="manual-action-header">
        <span class="manual-action-index">${String(index + 1).padStart(2, "0")}</span>
        <div><p>${escapeHtml(action.location)}</p><h4>${escapeHtml(action.title)}</h4></div>
      </header>
      <p class="manual-action-instruction">${escapeHtml(action.instruction)}</p>
      ${operations.length ? `<ol class="operation-list">${operations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>` : ""}
      ${action.content ? `<pre class="copy-value"><code>${escapeHtml(action.content)}</code></pre>` : ""}
      ${copyTextValue ? copyButton(copyTextValue, action.content ? "复制修改值" : "复制操作清单", { className: "button button-secondary button-small" }) : ""}
    </article>`;
  }

  function isWindowTypeAction(action) {
    return action?.category === "用户窗口" || /^用户窗口\s*→/.test(String(action?.location || ""));
  }

  function typeExtensionActionsForSurface(plan, surface) {
    const actions = Array.isArray(plan?.manualActions) ? plan.manualActions : [];
    return actions.filter((action) =>
      surface === "window" ? isWindowTypeAction(action) : !isWindowTypeAction(action),
    );
  }

  function typeReplacementLedgerHtml(plan) {
    if (!plan?.enabled || !plan.replacements?.length) return "";
    return `<div class="replacement-ledger">
      <div class="replacement-cards">
        ${plan.replacements
          .map(
            (item) => `<article class="replacement-card">
              <span class="replacement-slot">模板 ${escapeHtml(item.slotId)}</span>
              <div class="replacement-flow"><strong>${escapeHtml(item.baseline.typeCode)} / ${escapeHtml(item.baseline.layoutPattern)}</strong><span>→</span><strong>${escapeHtml(item.target.typeCode)} / ${escapeHtml(item.target.layoutPattern)}</strong></div>
              <p>${item.baseline.boardCount}板/${item.baseline.branchCount}输出 → ${item.target.boardCount}板/${item.target.branchCount}输出</p>
              <small>使用位置：${escapeHtml(item.positions.map((position) => `${position.column === "COL-A" ? "第一" : "第二"}物理列第${position.position}箱`).join("、"))}</small>
            </article>`,
          )
          .join("")}
      </div>
      ${plan.missing?.length ? `<p class="notice is-warning"><strong>先返回第一页选择：</strong>${escapeHtml(plan.missing.join("、"))}</p><button type="button" class="button button-secondary" data-go-config>返回项目配置</button>` : ""}
    </div>`;
  }

  function typeExtensionSurfaceHtml(plan, surface) {
    const actions = typeExtensionActionsForSurface(plan, surface);
    const showBlocked = surface === "strategy" && plan?.blockedActions?.length;
    if (!actions.length && !showBlocked) return "";
    const actionGroups = Array.from(
      actions.reduce((map, action) => {
        const key = action.category || (surface === "window" ? "用户窗口" : "运行策略");
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(action);
        return map;
      }, new Map()),
    );
    const heading = surface === "window" ? "因箱型变化需要修改的窗口" : "因箱型变化需要修改的策略";
    const detail = surface === "window"
      ? "箱型只是变化原因；这里按实际窗口和控件位置执行。"
      : "这是运行策略修改中的一个子类，不再单独占用流程步骤。";
    return `<section class="section-block type-change-section">
      <div class="section-heading"><div><h3>${heading}</h3><p>${detail}</p></div></div>
      ${surface === "strategy" ? typeReplacementLedgerHtml(plan) : ""}
      ${actionGroups
        .map(
          ([category, groupActions]) => `<div class="type-change-group"><div class="section-heading"><div><h4>因箱型变化 · ${escapeHtml(category)}</h4><p>${groupActions.length}项当前项目必须修改的内容</p></div></div><div class="manual-action-list">${groupActions.map(typeManualActionHtml).join("")}</div></div>`,
        )
        .join("")}
      ${showBlocked ? `<div class="type-change-group"><div class="section-heading"><div><h4>尚不能安全生成</h4><p>下面只列明确缺口，不提供未经验证的代码。</p></div></div><div class="question-list">${plan.blockedActions.map((item, index) => `<div class="question-item"><div class="gui-step-no">${index + 1}</div><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.location)}：${escapeHtml(item.reason)}</p></div><span class="status-tag is-danger">阻断</span></div>`).join("")}</div></div>` : ""}
    </section>`;
  }

  function snapshotText(derived) {
    const recipeActions = recipeRows(derived)
      .filter((row) => row.requiresChange)
      .map((row) => ({
        order: row.order,
        field: row.recipe_field,
        template: row.baseline_recipe_value,
        target: row.target,
      }));
    const databaseActions = databaseRows(derived, recipeRows(derived))
      .filter((row) => row.needsAction)
      .map((row) => ({
        object_name: row.object_name,
        object_id: row.object_id,
        template: row.before_value,
        target: row.target_value,
      }));
    const codePackage = currentCodePackage(derived);
    const protocol = protocolViewState(derived);
    const protocolAlarmFile = protocolAlarmUploadFile(derived);
    const windowGuiPlan = currentWindowGuiPlan(derived);
    const currentCodeFiles = [
      ...codePackage.backend,
      ...codePackage.alarm,
      ...codePackage.window,
      ...(protocolAlarmFile ? [protocolAlarmFile] : []),
    ];
    const jgProjection = Object.values(dynamicJgProjection(derived));
    const dualLoop = dualLoopConfiguration(derived);
    return JSON.stringify(
      {
        schema_version: "mcgs-workflow-ui-snapshot/4.0",
        project_signature: projectSignature(derived),
        project: state.params,
        box_types: { column_a: state.typesA, column_b: derived.hasSecondColumn ? state.typesB : [] },
        circuit_mappings: circuitMappingSnapshot(derived),
        circuit_mapping_ready: derived.circuitMapping.ready,
        derived_values: derived.flat,
        head_board_arrays: derived.headArrays,
        capacity_checks: derived.checks,
        activity_domain: derived.activityDomain,
        second_loop_temperature: {
          schema_version: "mcgs-second-loop-temperature/1.0",
          route_scope: "paired_routes_per_physical_column",
          encoding: {
            none: 0,
            independent_temperature: 1,
            shared_temperature: 2,
          },
          board_projection: dualLoop.rows.map((row) => ({
            configuration_key: row.configuration_key,
            topology_fingerprint: row.topology_fingerprint,
            column: row.column,
            route_ids: row.route_ids,
            box_position: row.box_position,
            board_offset: row.board_offset,
            board_index: row.board_index,
            board_template_id: row.board_template_id,
            object_name: row.object_name,
            object_id: row.object_id,
            temperature_mode: row.temperature_mode,
            target_value: row.target_value,
            status: row.status,
            manual_action: row.needsAction,
          })),
          unresolved: dualLoop.missingSlots.map((item) => ({
            configuration_key: item.configuration_key,
            label: item.label,
            positions: item.positions,
          })),
        },
        inactive_objects: jgProjection
          .filter((row) => !row.active)
          .map((row) => ({
            object_name: row.objectName,
            active: false,
            inactive_reason: row.inactiveReason,
            effective_readers: row.effectiveReaders,
            manual_action: false,
          })),
        manual_actions: {
          recipe: recipeActions,
          database_initial_values: databaseActions,
          bk_branch_list: dualLoop.actions.map((row) => ({
            configuration_key: row.configuration_key,
            route_ids: row.route_ids,
            object_name: row.object_name,
            object_id: row.object_id,
            template: row.before_value,
            target: row.target_value,
            column: row.column,
            box_position: row.box_position,
            board_offset: row.board_offset,
            board_index: row.board_index,
            temperature_mode: row.temperature_mode,
          })),
          jg_dl: derived.circuitMapping.ready ? dynamicJgDlActions(derived) : [],
          device: dynamicDeviceActions(derived),
          window_gui: windowGuiPlan.actions,
          code_files: currentCodeFiles.map((file) => ({
                id: file.id,
                stage: file.stage,
                strategy: file.strategy,
                target: file.target,
                fingerprint: file.fingerprint,
                lines: file.lines,
                generated_from: "current_project_parameters",
              })),
          alarm_description: codePackage.ready
            ? codePackage.alarm.map((file) => ({
                id: file.id,
                target: file.target,
                fingerprint: file.fingerprint,
                change_summary: file.changeSummary,
              }))
            : [],
        },
        window_gui_plan: {
          schema_version: windowGuiPlan.schema_version,
          totals: windowGuiPlan.totals,
          columns: windowGuiPlan.columns,
          expected_object_counts: windowGuiPlan.expected_object_counts,
          manual_changes: windowGuiPlan.actions,
          automatic_actions: windowGuiPlan.automatic_actions,
          release_validation: windowGuiPlan.release_validation,
          internal_evidence: windowGuiPlan.internal_evidence,
        },
        automatic_exclusions: source.runtimeModel.excludedCounts,
        generation: {
          code_package_ready: codePackage.ready,
          dependent_code_ready: codePackage.dependentReady,
          initialization_code_ready: codePackage.initializationReady,
          blockers: codePackage.issues,
          alarm_description: {
            ready: codePackage.alarmPlan?.ready || false,
            issues: codePackage.alarmPlan?.issues || [],
            columns: (codePackage.alarmPlan?.columns || []).map((item) => ({
              column: item.columnKey,
              script_no: item.scriptNo,
              modified: item.modified,
              changed_boxes: item.changedBoxes,
              changed_lines: item.changedLines,
            })),
          },
          protocol_status: protocol.status,
          protocol_run_id: protocol.status === "generated" ? state.protocol.result?.run_id || null : null,
          protocol_delivery_status:
            protocol.status === "generated" ? state.protocol.result?.delivery_status || null : null,
        },
        type_extension: typeExtensionPlanV2(derived),
      },
      null,
      2,
    );
  }

  function renderValidation(derived) {
    const pending = [];
    const addPending = (id, question, blocks) => pending.push({ question_id: id, question, blocks, status: "open" });
    if (!state.params.confirmStation) addPending("CUR-UQ-001", "动环从站地址尚未勾选确认为正式项目值。", ["配方通讯地址", "upload设备地址", "现场轮询"]);
    if (state.params.featureTemperature === "preserve") addPending("CUR-UQ-002", "温度测量开关仍保持模板值。", ["配方TempEnable", "温度报警"]);
    if (state.params.featureLeakage === "preserve") addPending("CUR-UQ-003", "漏电流测量开关仍保持模板值。", ["配方InEnable", "漏电流报警"]);
    if (state.params.featureSpd === "preserve") addPending("CUR-UQ-004", "SPD监测开关仍保持模板值。", ["配方SPDEnable", "浪涌报警"]);
    if (state.params.featurePower === "preserve") addPending("CUR-UQ-005", "功率报警开关仍保持模板值。", ["配方PHEnable", "功率报警"]);
    if (!state.params.confirmRoom) addPending("CUR-UQ-006", "机房标识尚未授权写入配方Room。", ["配方Room", "报警/显示名称"]);
    if (!state.params.confirmAlarmDelay) addPending("CUR-UQ-007", "通讯报警延时尚未确认。", ["配方ALM_Comdelay", "通讯报警时序"]);
    if (!derived.circuitMapping.ready) addPending("CUR-UQ-008", "机柜与A/B路输出映射尚未闭合。", ["JG_DL", "后台聚合", "打开策略", "窗口按钮"]);
    const dualLoop = dualLoopConfiguration(derived);
    if (!dualLoop.complete) addPending("CUR-UQ-009", `一拖六板卡仍缺：${dualLoop.missingSlots.map((item) => `${item.label}温度独立/共用`).join("、")}。`, ["BK_Branch_list", "第二回路温度", "报警限值"]);
    const staticStatus = source.validationReport.status || "静态验证已完成";
    const codePackage = currentCodePackage(derived);
    const protocol = protocolViewState(derived);
    const codeCount = codePackage.ready
      ? codePackage.backend.length +
        codePackage.alarm.length +
        codePackage.window.length +
        (protocol.status === "generated" && state.protocol.alarmCode ? 1 : 0)
      : 0;
    const checks = [
      {
        title: "基线与副本",
        text: "只在MCP工作副本中操作，记录打开前哈希和.ldb；不覆盖模板基线。",
        pass: false,
      },
      {
        title: "配方与数据库回读",
        text: "回读人工修改项，并验证配方加载后关联对象、Layout/CJX_Class和四组头板卡数组已自动生成。",
        pass: false,
      },
      {
        title: "设备与通讯",
        text: "回读本项目实际父接口参数和upload通道数，再验证启动策略已按N_BK/N_ZJ/jgls自动完成设备启停与通讯报警。",
        pass: false,
      },
      {
        title: "策略脚本",
        text: "逐份核对策略运行参数、触发条件、脚本首尾、完整字符数以及长脚本关键计数。",
        pass: false,
      },
      {
        title: "用户窗口",
        text: "逐点点击插接箱、机柜和中继；关闭窗口后核对Disabled、CJX_blend、Display_branch和Second_loopT复位。",
        pass: false,
      },
      {
        title: "Save As与重提取",
        text: "另存为新MCP，重新全量提取五大模块并与目标表对账；随后执行编译、仿真和现场门禁。",
        pass: false,
      },
    ];

    root.innerHTML =
      hero(9, pending.length ? `${pending.length}个项目问题待闭环` : "参数门禁已通过", pending.length > 0) +
      instruction(
        "MCP工作副本 → Save As → 重新打开 → 编译 / 运行 / 重提取",
        "静态文件正确不等于MCGS运行通过。只有GUI另存、回读、仿真和现场验证完成后，才能升级结论。",
      ) +
      `<section class="section-block">
        <div class="summary-grid">
          <div class="summary-cell"><span>结构化源包</span><strong>${escapeHtml(staticStatus)}</strong></div>
          <div class="summary-cell"><span>MCP修改状态</span><strong>未在本前端写入</strong></div>
          <div class="summary-cell"><span>容量结论</span><strong>${derived.withinTemplate ? "模板内" : "需扩展"}</strong></div>
          <div class="summary-cell"><span>当前项目代码</span><strong>${codeCount}份</strong></div>
        </div>
      </section>
      <section class="section-block">
        <div class="section-heading"><div><h3>必须执行的回读顺序</h3><p>本前端不把这些步骤伪装成已经完成。</p></div>${copyButton(snapshotText(derived), "复制本次项目快照", { className: "button button-primary button-small" })}</div>
        <div class="check-list">
          ${checks
            .map(
              (item, index) => `<div class="check-item">
                <span class="check-mark is-pending">${index + 1}</span>
                <div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.text)}</p></div>
                <span class="status-tag is-pending">待执行</span>
              </div>`,
            )
            .join("")}
        </div>
      </section>
      <section class="section-block">
        <div class="section-heading"><div><h3>当前项目仍未确认的问题</h3><p>这里只列当前表单和生成门禁发现的问题。</p></div></div>
        <div class="question-list">
          ${pending.length ? pending
            .map(
              (item) => `<div class="question-item">
                <div class="gui-step-no">${escapeHtml(item.question_id.replace("CUR-UQ-", "Q"))}</div>
                <div><strong>${escapeHtml(item.question)}</strong><p>影响：${escapeHtml(item.blocks.join("、"))}</p></div>
                <span class="status-tag is-pending">${escapeHtml(item.status)}</span>
              </div>`,
            )
            .join("") : '<div class="empty-state"><div><strong>当前项目参数问题已清零</strong><span>仍需执行MCP副本回读、编译、仿真与现场验证。</span></div></div>'}
        </div>
      </section>
      <section class="section-block"><p class="notice is-warning"><strong>当前硬边界：</strong>装配台按当前项目参数生成清单、策略、窗口按钮和动环三件套，但不会直接写入MCP；静态生成通过也不能替代MCGS副本Save As、回读、编译、仿真和现场验收。</p></section>`;
  }

  function renderStep(derived) {
    copyStore = new Map();
    codeStore = new Map();
    copyCounter = 0;
    if (els.codeDialog.open) els.codeDialog.close();
    const steps = activeSteps(derived);
    let selectedIndex = steps.findIndex((step) => step.id === state.selectedStepId);
    if (selectedIndex < 0) {
      state.selectedStepId = steps[0]?.id || "recipe";
      selectedIndex = 0;
    }
    switch (state.selectedStepId) {
      case "recipe":
        renderRecipe(derived);
        break;
      case "database":
        renderDatabase(derived);
        break;
      case "device":
        renderDevice(derived);
        break;
      case "jgdl":
        renderJgDl(derived);
        break;
      case "backend":
        renderBackend(derived);
        break;
      case "alarm":
        renderAlarm(derived);
        break;
      case "window":
        renderWindow(derived);
        break;
      default:
        renderRecipe(derived);
    }
    els.stepPosition.textContent = `第 ${selectedIndex + 1} / ${steps.length} 步`;
    els.previousStep.disabled = selectedIndex === 0;
    els.nextStep.disabled = selectedIndex === steps.length - 1;
    els.nextStep.textContent = "下一类";
  }

  function configurationIssues(derived) {
    const dualLoop = dualLoopConfiguration(derived);
    const issues = [];
    if (!String(state.params.projectName || "").trim()) issues.push("尚未填写项目名称");
    if (!derived.circuitMapping.ready) issues.push("输出与机柜对应关系未填完整");
    if (!dualLoop.complete) {
      issues.push(`${dualLoop.missingSlots.map((item) => item.label).join("、")}未选择温度方式`);
    }
    if (!derived.withinTemplate) {
      issues.push(`${derived.checks.filter((item) => !item.pass).map((item) => item.label).join("、")}超过模板范围`);
    }
    if (state.params.uploadProtocol === "modbus_rtu_forwarder" && !state.params.serialPort) {
      issues.push("尚未填写上传串口");
    }
    return issues;
  }

  function renderConfigurationStatus(derived) {
    const issues = configurationIssues(derived);
    if (els.configurationStatus) {
      els.configurationStatus.classList.toggle("is-ready", issues.length === 0);
      els.configurationStatus.classList.toggle("is-pending", issues.length > 0);
      els.configurationStatus.innerHTML = issues.length
        ? `<span>还需完成</span><strong>${issues.length}项</strong>`
        : `<span>项目配置</span><strong>已完整</strong>`;
    }
    if (els.configurationErrors) {
      els.configurationErrors.innerHTML = issues.length
        ? `<strong>还需完成：</strong>${escapeHtml(issues.join("；"))}`
        : `<strong>可以生成：</strong>修改清单会只显示当前项目真正需要操作的内容。`;
      els.configurationErrors.classList.toggle("is-ready", issues.length === 0);
    }
  }

  function updateSnapshotOnly() {
    const derived = deriveProject();
    renderConfigurationStatus(derived);
    els.headerProjectName.textContent = state.params.projectName || "新项目";
    els.agentProjectSnapshot.textContent = snapshotText(derived);
  }

  function renderEverything() {
    const derived = deriveProject();
    els.headerProjectName.textContent = state.params.projectName || "新项目";
    const configuring = state.selectedStepId === "parameters";
    els.configurationView.hidden = !configuring;
    els.executionView.hidden = configuring;
    if (configuring) {
      renderConfigurationStatus(derived);
    } else {
      const steps = activeSteps(derived);
      if (!steps.some((step) => step.id === state.selectedStepId)) {
        state.selectedStepId = steps[0]?.id || "recipe";
      }
      renderWorkflow(derived);
      renderCapacity(derived);
      renderStep(derived);
    }
    els.agentProjectSnapshot.textContent = snapshotText(derived);
  }

  function goToStep(stepRef, scroll = true) {
    const derived = deriveProject();
    if (stepRef === "parameters") {
      state.selectedStepId = "parameters";
      renderEverything();
      if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const steps = activeSteps(derived);
    const currentIndex = Math.max(0, steps.findIndex((step) => step.id === state.selectedStepId));
    let nextStep = null;
    if (typeof stepRef === "string") nextStep = steps.find((step) => step.id === stepRef) || null;
    else {
      const nextIndex = Math.min(steps.length - 1, Math.max(0, Number(stepRef)));
      nextStep = steps[nextIndex] || steps[currentIndex];
    }
    state.selectedStepId = nextStep.id;
    state.visited.add(nextStep.id);
    renderEverything();
    if (scroll) {
      document.querySelector(".execution-header")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function showCodeDialog(file) {
    state.dialogCode = file.content;
    state.dialogCopyMode = file.copyMode;
    els.codeDialogTitle.textContent = file.scriptName;
    els.codeDialogTarget.textContent = file.target;
    els.codeDialogMeta.textContent = "请整段复制到上方所示位置";
    els.codeDialogContent.textContent = file.content;
    els.copyDialogCode.textContent = file.copyMode === "blocks" ? "复制整份汇总" : "复制完整代码";
    els.codeDialog.showModal();
  }

  async function generateProtocolTriplet() {
    readFormIntoState();
    const derived = deriveProject();
    const signature = projectSignature(derived);
    let config;
    try {
      config = protocolConfigForProject(derived);
    } catch (error) {
      state.protocol = {
        ...state.protocol,
        status: "failed",
        signature,
        error: String(error.message || error),
      };
      renderEverything();
      showToast("动环三件套参数不完整");
      return;
    }

    state.protocol = {
      ...state.protocol,
      status: "generating",
      signature,
      error: "",
    };
    renderEverything();
    try {
      const response = await apiFetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }
      if (!response.ok) {
        const detail = payload?.detail;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || payload || `HTTP ${response.status}`));
      }
      const bundleStatus = protocolBundleStatus(payload);
      if (!bundleStatus.ok) {
        throw new Error(`三件套未完整生成：${bundleStatus.issues.join("、")}`);
      }
      const alarmUrl = artifactDownload(payload, "alarm_code");
      let alarmCode = "";
      if (alarmUrl) {
        const alarmResponse = await apiFetch(alarmUrl);
        if (!alarmResponse.ok) throw new Error(`报警状态字代码下载失败：HTTP ${alarmResponse.status}`);
        alarmCode = await alarmResponse.text();
      }
      state.protocol = {
        status: "generated",
        signature,
        result: payload,
        alarmCode,
        error: "",
      };
      renderEverything();
      showToast("动环协议、设备导入表和报警状态字代码已生成");
    } catch (error) {
      if (error?.code === "password_change_required" || error?.code === "auth_required") {
        state.protocol = {
          ...state.protocol,
          status: "idle",
          error: "",
        };
        renderEverything();
        showToast(error.message);
        return;
      }
      state.protocol = {
        ...state.protocol,
        status: "failed",
        signature,
        error: `${String(error.message || error)}。请重新打开装配台后再试。`,
      };
      renderEverything();
      showToast("动环三件套生成失败，已列明具体原因");
    }
  }

  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    readFormIntoState();
    reconcileSecondLoopTemperatureModes();
    renderCircuitEditors();
    const derived = deriveProject();
    const issues = configurationIssues(derived);
    if (issues.length) {
      state.selectedStepId = "parameters";
      renderEverything();
      if (!state.params.projectName) document.getElementById("project-name")?.focus();
      showToast(`还有${issues.length}项配置未完成`);
      return;
    }
    const firstStep = activeSteps(derived)[0]?.id || "device";
    goToStep(firstStep);
    showToast("已按当前项目生成修改清单");
  });

  els.form.addEventListener("input", (event) => {
    const target = event.target;
    if (target.matches("[data-second-loop-mode]")) {
      const key = target.dataset.configurationKey;
      const mode = String(target.value || "");
      if (mode) {
        state.secondLoopTemperatureModes[key] = {
          mode,
          topologyFingerprint: target.dataset.topologyFingerprint,
        };
      } else {
        delete state.secondLoopTemperatureModes[key];
      }
      updateSnapshotOnly();
      return;
    }
    if (target.matches("[data-circuit-column]")) {
      setMappingValue(
        target.dataset.circuitColumn,
        target.dataset.circuitRoute,
        target.dataset.circuitKey,
        target.value,
      );
      target.closest(".circuit-output")?.classList.toggle("is-spare", Number(target.value) === 0);
      updateCircuitStatus(target.dataset.circuitColumn);
      updateSnapshotOnly();
      return;
    }
    if (target.matches("[data-position-column]")) {
      const index = Number(target.dataset.positionIndex);
      if (target.dataset.positionColumn === "A") state.typesA[index] = target.value;
      else state.typesB[index] = target.value;
      els.boxTypeA.value = commonType(state.typesA);
      els.boxTypeB.value = commonType(state.typesB);
      readFormIntoState();
      const columnKey = target.dataset.positionColumn;
      renderCircuitColumn(
        columnKey,
        columnKey === "A" ? els.circuitMappingA : els.circuitMappingB,
        columnKey === "A" ? els.circuitStatusA : els.circuitStatusB,
      );
    } else {
      readFormIntoState(target.name || "");
      const structural = [
        "screenMode",
        "boxCountA",
        "boxCountB",
        "cabinetCountA",
        "cabinetCountB",
        "boxTypeA",
        "boxTypeB",
      ].includes(target.name) || String(target.name || "").startsWith("replacement_");
      if (structural) renderCircuitEditors();
    }
    updateSnapshotOnly();
  });

  els.form.addEventListener("click", (event) => {
    const button = event.target.closest("[data-mapping-action]");
    if (!button) return;
    const message = applyMappingAction(button.dataset.mappingColumn, button.dataset.mappingAction);
    const columnKey = button.dataset.mappingColumn;
    renderCircuitColumn(
      columnKey,
      columnKey === "A" ? els.circuitMappingA : els.circuitMappingB,
      columnKey === "A" ? els.circuitStatusA : els.circuitStatusB,
    );
    updateSnapshotOnly();
    showToast(message);
  });

  els.returnToConfig?.addEventListener("click", () => goToStep("parameters"));

  els.workflowTrack.addEventListener("click", (event) => {
    const button = event.target.closest("[data-step-id]");
    if (button) goToStep(button.dataset.stepId, false);
  });

  els.previousStep.addEventListener("click", () => {
    const steps = activeSteps(deriveProject());
    const index = steps.findIndex((step) => step.id === state.selectedStepId);
    if (index <= 0) goToStep("parameters");
    else goToStep(index - 1);
  });
  els.nextStep.addEventListener("click", () => {
    const steps = activeSteps(deriveProject());
    const index = steps.findIndex((step) => step.id === state.selectedStepId);
    goToStep(index + 1);
  });

  root.addEventListener("click", (event) => {
    const openParametersTarget = event.target.closest("[data-open-parameters]");
    if (openParametersTarget) {
      goToStep("parameters");
      return;
    }
    const goConfigTarget = event.target.closest("[data-go-config]");
    if (goConfigTarget) {
      goToStep("parameters");
      return;
    }
    const mappingTarget = event.target.closest("[data-mapping-action]");
    if (mappingTarget) {
      const message = applyMappingAction(
        mappingTarget.dataset.mappingColumn,
        mappingTarget.dataset.mappingAction,
      );
      renderEverything();
      showToast(message);
      return;
    }
    const generateTarget = event.target.closest("[data-generate-protocol]");
    if (generateTarget) {
      generateProtocolTriplet();
      return;
    }
    const copyTarget = event.target.closest("[data-copy-key]");
    if (copyTarget) {
      const text = copyStore.get(copyTarget.dataset.copyKey);
      if (text !== undefined) copyText(text);
      return;
    }
    const viewTarget = event.target.closest("[data-view-code-id]");
    if (viewTarget) {
      const file = codeStore.get(viewTarget.dataset.viewCodeId) || source.codeFiles.find((item) => item.id === viewTarget.dataset.viewCodeId);
      if (file) showCodeDialog(file);
    }
  });

  els.closeCodeDialog.addEventListener("click", () => els.codeDialog.close());
  els.copyDialogCode.addEventListener("click", () =>
    copyText(state.dialogCode, state.dialogCopyMode === "blocks" ? "已复制整份汇总" : "已复制完整代码"),
  );
  els.codeDialog.addEventListener("click", (event) => {
    if (event.target === els.codeDialog) els.codeDialog.close();
  });
  window.MCGS_WORKFLOW = Object.freeze({
    getSnapshot: () => JSON.parse(snapshotText(deriveProject())),
  });

  initializeTypeSelectors();
  loadBlankProject();
  loadProtocolCatalog();
})();
