(function (global) {
  "use strict";

  const PROTOCOL_TYPE_MAP = Object.freeze({
    "3x1P": Object.freeze({ typeCode: "1P*3", layoutPattern: "1" }),
    "2x6": Object.freeze({ typeCode: "3P*4", layoutPattern: "2+2" }),
    "3x3": Object.freeze({ typeCode: "3P*3", layoutPattern: "1+1+1" }),
    "4x3": Object.freeze({ typeCode: "3P*4", layoutPattern: "1+1+1+1" }),
  });

  const PROTOCOL_BOARD_TEMPLATES = Object.freeze({
    board_1to3_3phase: Object.freeze({
      id: "board_1to3_3phase",
      label: "一拖三三相板",
      phaseMode: "three_phase",
      branches: Object.freeze([
        Object.freeze({ loop: 1, mode: "three", phaseIndex: null, switchBits: Object.freeze([0, 1, 2]) }),
      ]),
    }),
    board_1to6_3phase_dual: Object.freeze({
      id: "board_1to6_3phase_dual",
      label: "一拖六双回路板",
      phaseMode: "three_phase",
      branches: Object.freeze([
        Object.freeze({ loop: 1, mode: "three", phaseIndex: null, switchBits: Object.freeze([0, 1, 2]) }),
        Object.freeze({ loop: 2, mode: "three", phaseIndex: null, switchBits: Object.freeze([0, 1, 2]) }),
      ]),
    }),
    board_1to3_single_phase_triplet: Object.freeze({
      id: "board_1to3_single_phase_triplet",
      label: "一拖三单相板",
      phaseMode: "single_phase_triplet",
      branches: Object.freeze([
        Object.freeze({ loop: 1, mode: "single", phaseIndex: 0, switchBits: Object.freeze([0]) }),
        Object.freeze({ loop: 1, mode: "single", phaseIndex: 1, switchBits: Object.freeze([1]) }),
        Object.freeze({ loop: 1, mode: "single", phaseIndex: 2, switchBits: Object.freeze([2]) }),
      ]),
    }),
  });

  // 与动环协议工作台 /api/bootstrap 的 box_types 契约一致。在线目录加载失败时，
  // 仍可使用这份已验证的物理类型/板卡组合，不把网络状态变成项目建模阻塞项。
  const FALLBACK_PROTOCOL_TYPE_CATALOG = Object.freeze([
    Object.freeze({
      type_code: "3P*1",
      label: "三相 1 回路（3P*1）",
      short_label: "3P*1",
      phase_mode: "three_phase",
      branch_count: 1,
      default_layout_pattern: "1",
      allowed_layout_patterns: Object.freeze([
        Object.freeze({ pattern: "1", label: "1 块单回路板（1）", board_count: 1, branch_count: 1, board_template_ids: Object.freeze(["board_1to3_3phase"]) }),
      ]),
    }),
    Object.freeze({
      type_code: "3P*2",
      label: "三相 2 回路（3P*2）",
      short_label: "3P*2",
      phase_mode: "three_phase",
      branch_count: 2,
      default_layout_pattern: "1+1",
      allowed_layout_patterns: Object.freeze([
        Object.freeze({ pattern: "1+1", label: "2 块单回路板（1+1）", board_count: 2, branch_count: 2, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "2", label: "1 块双回路板（2）", board_count: 1, branch_count: 2, board_template_ids: Object.freeze(["board_1to6_3phase_dual"]) }),
      ]),
    }),
    Object.freeze({
      type_code: "3P*3",
      label: "三相 3 回路（3P*3）",
      short_label: "3P*3",
      phase_mode: "three_phase",
      branch_count: 3,
      default_layout_pattern: "1+1+1",
      allowed_layout_patterns: Object.freeze([
        Object.freeze({ pattern: "1+1+1", label: "3 块单回路板（1+1+1）", board_count: 3, branch_count: 3, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to3_3phase", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "2+1", label: "1 块双回路板 + 1 块单回路板（2+1）", board_count: 2, branch_count: 3, board_template_ids: Object.freeze(["board_1to6_3phase_dual", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "1+2", label: "1 块单回路板 + 1 块双回路板（1+2）", board_count: 2, branch_count: 3, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to6_3phase_dual"]) }),
      ]),
    }),
    Object.freeze({
      type_code: "3P*4",
      label: "三相 4 回路（3P*4）",
      short_label: "3P*4",
      phase_mode: "three_phase",
      branch_count: 4,
      default_layout_pattern: "1+1+1+1",
      allowed_layout_patterns: Object.freeze([
        Object.freeze({ pattern: "1+1+1+1", label: "4 块单回路板（1+1+1+1）", board_count: 4, branch_count: 4, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to3_3phase", "board_1to3_3phase", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "2+1+1", label: "1 块双回路板 + 2 块单回路板（2+1+1）", board_count: 3, branch_count: 4, board_template_ids: Object.freeze(["board_1to6_3phase_dual", "board_1to3_3phase", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "1+2+1", label: "单回路板 + 双回路板 + 单回路板（1+2+1）", board_count: 3, branch_count: 4, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to6_3phase_dual", "board_1to3_3phase"]) }),
        Object.freeze({ pattern: "1+1+2", label: "2 块单回路板 + 1 块双回路板（1+1+2）", board_count: 3, branch_count: 4, board_template_ids: Object.freeze(["board_1to3_3phase", "board_1to3_3phase", "board_1to6_3phase_dual"]) }),
        Object.freeze({ pattern: "2+2", label: "2 块双回路板（2+2）", board_count: 2, branch_count: 4, board_template_ids: Object.freeze(["board_1to6_3phase_dual", "board_1to6_3phase_dual"]) }),
      ]),
    }),
    Object.freeze({
      type_code: "1P*3",
      label: "单相 3 回路（1P*3）",
      short_label: "1P*3",
      phase_mode: "single_phase_triplet",
      branch_count: 3,
      default_layout_pattern: "1",
      allowed_layout_patterns: Object.freeze([
        Object.freeze({ pattern: "1", label: "1 块三单相板（1）", board_count: 1, branch_count: 3, board_template_ids: Object.freeze(["board_1to3_single_phase_triplet"]) }),
      ]),
    }),
  ]);

  const TEMPLATE_LIMITS = Object.freeze({
    metricCabinets: 25,
    switchCabinets: Object.freeze({
      "COL-A": 20,
      "COL-B": 19,
    }),
  });

  const WINDOW_TEMPLATE_BASELINE = Object.freeze({
    "COL-A": Object.freeze({
      label: "第一物理列",
      mainWindow: "主系统图",
      boxPrefix: "A",
      cabinetPrefix: "A",
      relayBases: Object.freeze([100, 200]),
      temperatureBase: 100,
      boxButtons: 8,
      cabinetButtons: 16,
      relaysPerBus: 3,
      temperatureBoxes: 10,
      topLevelElements: 241,
      boxCloneElements: 2,
      cabinetCloneElements: 8,
    }),
    "COL-B": Object.freeze({
      label: "第二物理列",
      mainWindow: "主系统图_B列",
      boxPrefix: "B",
      cabinetPrefix: "B",
      relayBases: Object.freeze([300, 400]),
      temperatureBase: 300,
      boxButtons: 6,
      cabinetButtons: 16,
      relaysPerBus: 3,
      temperatureBoxes: 10,
      topLevelElements: 241,
      boxCloneElements: 2,
      cabinetCloneElements: 8,
    }),
    temperatureWindow: Object.freeze({
      name: "温升柱图",
      topLevelElements: 252,
    }),
  });

  // 固定模板中已经存在的业务绑定。这里只描述用户是否需要重新修改，
  // 不参与运行时计算，也不把模板中未启用的第二物理列误判为人工任务。
  const PROGRAM_TEMPLATE_BASELINE = Object.freeze({
    boxCount: 7,
    cabinetCount: 20,
    typeId: "3x1P",
    boxWindow: "插接箱",
  });

  function baselineBoxCabinets(columnKey, boxPosition) {
    const column = columnKey === "COL-B" ? "COL-B" : "COL-A";
    const position = Math.max(1, Math.trunc(Number(boxPosition) || 1));
    if (position > PROGRAM_TEMPLATE_BASELINE.boxCount) return [0, 0, 0];
    if (column === "COL-B") {
      const start = (position - 1) * 3 + 1;
      return [start, start + 1, start + 2].map((value) =>
        value <= PROGRAM_TEMPLATE_BASELINE.cabinetCount ? value : 0,
      );
    }
    const start = (position - 1) * 3 + 1;
    return [start + 2, start + 1, start].map((value) =>
      value <= PROGRAM_TEMPLATE_BASELINE.cabinetCount ? value : 0,
    );
  }

  function normalizedProgramColumn(columnKey, input = {}) {
    const boxes = Array.isArray(input.boxes) ? input.boxes : [];
    return {
      columnKey: columnKey === "COL-B" ? "COL-B" : "COL-A",
      boxCount: Math.max(0, Math.trunc(Number(input.boxCount) || 0)),
      cabinetCount: Math.max(0, Math.trunc(Number(input.cabinetCount) || 0)),
      boxes: boxes.map((box, index) => ({
        position: Math.max(1, Math.trunc(Number(box.position) || index + 1)),
        typeId: String(box.typeId || ""),
        windowName: String(box.windowName || ""),
        routeA: Array.isArray(box.routeA) ? box.routeA.map((value) => Number(value) || 0) : [],
        routeB: Array.isArray(box.routeB) ? box.routeB.map((value) => Number(value) || 0) : [],
      })),
    };
  }

  function boxMatchesOpenBaseline(columnKey, box) {
    if (box.typeId !== PROGRAM_TEMPLATE_BASELINE.typeId) return false;
    if (box.windowName !== PROGRAM_TEMPLATE_BASELINE.boxWindow) return false;
    const expected = baselineBoxCabinets(columnKey, box.position);
    return stableStringify(box.routeA) === stableStringify(expected) &&
      stableStringify(box.routeB) === stableStringify(expected);
  }

  function cabinetBinding(columnKey, boxes, cabinet) {
    for (const box of boxes) {
      const branchIndex = box.routeA.findIndex((value) => value === cabinet);
      if (branchIndex < 0) continue;
      return {
        boxPosition: box.position,
        branchNo: branchIndex + 1,
        disabled: branchDisabledMask(branchIndex + 1),
        windowName: box.windowName,
      };
    }
    return null;
  }

  function baselineCabinetBinding(columnKey, cabinet) {
    for (let position = 1; position <= PROGRAM_TEMPLATE_BASELINE.boxCount; position += 1) {
      const values = baselineBoxCabinets(columnKey, position);
      const branchIndex = values.indexOf(cabinet);
      if (branchIndex >= 0) {
        return {
          boxPosition: position,
          branchNo: branchIndex + 1,
          disabled: branchDisabledMask(branchIndex + 1),
          windowName: PROGRAM_TEMPLATE_BASELINE.boxWindow,
        };
      }
    }
    return null;
  }

  function buildProgramDiffPlan(spec = {}) {
    const hasSecondColumn = Boolean(spec.hasSecondColumn);
    const activeKeys = hasSecondColumn ? ["COL-A", "COL-B"] : ["COL-A"];
    const columns = {};
    let backendNeedsChange = false;
    const openStrategies = [];
    const boxButtons = [];
    const cabinetButtons = [];

    for (const columnKey of activeKeys) {
      const column = normalizedProgramColumn(columnKey, spec.columns?.[columnKey]);
      columns[columnKey] = column;
      const baselineTopology =
        column.boxCount === PROGRAM_TEMPLATE_BASELINE.boxCount &&
        column.cabinetCount === PROGRAM_TEMPLATE_BASELINE.cabinetCount &&
        column.boxes.length === PROGRAM_TEMPLATE_BASELINE.boxCount &&
        column.boxes.every((box) => boxMatchesOpenBaseline(columnKey, box));
      if (!baselineTopology) backendNeedsChange = true;

      for (const box of column.boxes) {
        if (!boxMatchesOpenBaseline(columnKey, box)) {
          openStrategies.push({ column: columnKey, position: box.position });
        }
        const baselineButtonCount = WINDOW_TEMPLATE_BASELINE[columnKey].boxButtons;
        if (
          box.position > baselineButtonCount ||
          box.windowName !== PROGRAM_TEMPLATE_BASELINE.boxWindow
        ) {
          boxButtons.push({ column: columnKey, position: box.position });
        }
      }

      for (let cabinet = 1; cabinet <= column.cabinetCount; cabinet += 1) {
        const target = cabinetBinding(columnKey, column.boxes, cabinet);
        if (!target) continue;
        const baseline = baselineCabinetBinding(columnKey, cabinet);
        const baselineButtonCount = WINDOW_TEMPLATE_BASELINE[columnKey].cabinetButtons;
        if (
          cabinet > baselineButtonCount ||
          stableStringify(target) !== stableStringify(baseline)
        ) {
          cabinetButtons.push({ column: columnKey, cabinet, ...target });
        }
      }
    }

    return {
      schema_version: "mcgs-program-diff-plan/1.0",
      has_second_column: hasSecondColumn,
      backend_needs_change: backendNeedsChange,
      open_strategies: openStrategies,
      window: {
        box_buttons: boxButtons,
        cabinet_buttons: cabinetButtons,
      },
      columns,
    };
  }

  function groupSlotsByBox(slots) {
    const groups = [];
    const byPosition = new Map();
    for (const slot of slots || []) {
      if (!byPosition.has(slot.boxPosition)) {
        const group = [];
        byPosition.set(slot.boxPosition, group);
        groups.push(group);
      }
      byPosition.get(slot.boxPosition).push(slot);
    }
    return groups;
  }

  function reverseFill(slots, cabinetCount) {
    const limit = Math.max(0, Math.trunc(Number(cabinetCount) || 0));
    const result = {};
    let cursor = 1;
    for (const group of groupSlotsByBox(slots)) {
      const block = group.map(() => {
        const value = cursor <= limit ? cursor : 0;
        cursor += 1;
        return value;
      });
      block.reverse();
      group.forEach((slot, index) => {
        result[slot.key] = block[index];
      });
    }
    return result;
  }

  function alarmSelectorPermutation(aRouteValues, bRouteValues) {
    const aValues = Array.from(aRouteValues || [], (value) => Math.trunc(Number(value) || 0));
    const bValues = Array.from(bRouteValues || [], (value) => Math.trunc(Number(value) || 0));
    if (aValues.length !== 3 || bValues.length !== 3) {
      throw new RangeError("3x1P报警机柜选择器要求A/B路各有3个相位值");
    }

    const used = new Set();
    const selectors = [null, null, null];
    for (let phaseIndex = 0; phaseIndex < 3; phaseIndex += 1) {
      if (aValues[phaseIndex] === bValues[phaseIndex]) {
        selectors[phaseIndex] = phaseIndex + 1;
        used.add(phaseIndex);
      }
    }
    for (let phaseIndex = 0; phaseIndex < 3; phaseIndex += 1) {
      if (selectors[phaseIndex] !== null) continue;
      const value = bValues[phaseIndex];
      const candidates = [];
      for (let index = 0; index < aValues.length; index += 1) {
        if (aValues[index] === value && !used.has(index)) candidates.push(index);
      }
      if (!candidates.length) {
        throw new Error(
          `3x1P箱内A/B路机柜集合不一致：A=[${aValues.join(",")}], B=[${bValues.join(",")}]`,
        );
      }
      const selected = candidates[0];
      used.add(selected);
      selectors[phaseIndex] = selected + 1;
    }
    return selectors;
  }

  function patchAlarmDescriptionSelectors(templateText, boardPatches) {
    const text = String(templateText || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n");
    const patches = new Map();
    for (const patch of boardPatches || []) {
      const boardNo = Math.trunc(Number(patch?.boardNo) || 0);
      const selectors = Array.from(patch?.selectors || [], (value) => Math.trunc(Number(value) || 0));
      if (boardNo <= 0 || selectors.length !== 3 || selectors.some((value) => value < 1 || value > 3)) {
        throw new RangeError(`报警描述板卡补丁无效：board=${patch?.boardNo}, selectors=${selectors.join("/")}`);
      }
      if (patches.has(boardNo)) throw new Error(`报警描述板卡补丁重复：${boardNo}`);
      patches.set(boardNo, {
        boardNo,
        selectors,
        boxPosition: Math.trunc(Number(patch?.boxPosition) || 0),
      });
    }

    const lines = text.split("\n");
    const callPattern = /^(\s*!SetAlmInfo\(\s*)(PF|P|I|U)([abc])(\d+)(\s*,\s*\d+\s*,)/i;
    const selectorPattern = /ALM_Cabinet([123])/;
    const expectedByPhase = Object.freeze({ a: 1, b: 2, c: 3 });
    const boardStats = new Map(
      Array.from(patches.values(), (patch) => [
        patch.boardNo,
        {
          boardNo: patch.boardNo,
          boxPosition: patch.boxPosition,
          selectors: [...patch.selectors],
          matchedLines: 0,
          changedLines: 0,
        },
      ]),
    );
    const changes = [];

    lines.forEach((line, index) => {
      const call = line.match(callPattern);
      if (!call) return;
      const phase = call[3].toLowerCase();
      const boardNo = Number(call[4]);
      const patch = patches.get(boardNo);
      if (!patch) return;

      const selectorMatch = line.match(selectorPattern);
      if (!selectorMatch) {
        throw new Error(`报警描述第${index + 1}行缺少ALM_Cabinet选择器：${line}`);
      }
      const sourceSelector = Number(selectorMatch[1]);
      if (sourceSelector !== expectedByPhase[phase]) {
        throw new Error(
          `报警描述完整基线第${index + 1}行已偏离1/2/3相位选择器：${sourceSelector} != ${expectedByPhase[phase]}`,
        );
      }
      const targetSelector = patch.selectors[expectedByPhase[phase] - 1];
      const stats = boardStats.get(boardNo);
      stats.matchedLines += 1;
      if (sourceSelector === targetSelector) return;

      const targetLine = line.replace(selectorPattern, `ALM_Cabinet${targetSelector}`);
      lines[index] = targetLine;
      stats.changedLines += 1;
      changes.push({
        line: index + 1,
        boardNo,
        boxPosition: patch.boxPosition,
        phase: phase.toUpperCase(),
        sourceSelector,
        targetSelector,
        sourceLine: line,
        targetLine,
      });
    });

    const boards = Array.from(boardStats.values());
    for (const board of boards) {
      if (board.matchedLines !== 18) {
        throw new Error(`报警描述板卡${board.boardNo}应命中18行，实际${board.matchedLines}行`);
      }
    }
    return {
      text: lines.join("\n"),
      boards,
      changes,
      matchedLines: boards.reduce((sum, item) => sum + item.matchedLines, 0),
      changedLines: changes.length,
    };
  }

  function branchDisabledMask(branchNo) {
    const branch = Math.trunc(Number(branchNo) || 0);
    if (branch < 1 || branch > 31) {
      throw new RangeError(`分路号必须在1到31之间，当前为${branchNo}`);
    }
    return 2 ** (branch - 1);
  }

  function cabinetDataPointer(columnKey, cabinetIndex) {
    const cabinet = Math.trunc(Number(cabinetIndex) || 0);
    if (cabinet <= 0) return 0;
    if (columnKey === "B" || columnKey === "COL-B") return cabinet + 100;
    return cabinet;
  }

  function switchReadExpression(columnKey, objectName, bitNo) {
    const bit = Math.trunc(Number(bitNo) || 0);
    if (bit < 0 || bit > 31) {
      throw new RangeError(`状态位必须在0到31之间，当前为${bitNo}`);
    }
    if (columnKey === "B" || columnKey === "COL-B") {
      return `!BitAnd(${objectName},${2 ** bit})`;
    }
    return `!BitTest(${objectName},${bit})`;
  }

  function switchReadAnyExpression(columnKey, objectName, bitNos) {
    const bits = Array.from(new Set(Array.from(bitNos || [], (value) => Math.trunc(Number(value)))));
    if (!bits.length || bits.some((bit) => !Number.isInteger(bit) || bit < 0 || bit > 31)) {
      throw new RangeError(`状态位集合无效：${Array.from(bitNos || []).join("/")}`);
    }
    return bits.map((bit) => switchReadExpression(columnKey, objectName, bit)).join(" OR ");
  }

  function cabinetCoverageStatus(values, cabinetCount, enabled = true) {
    const count = Math.max(0, Math.trunc(Number(cabinetCount) || 0));
    const assignments = Array.from(values || [], (value) => Math.trunc(Number(value) || 0)).filter(
      (value) => value > 0 && value <= count,
    );
    const counts = new Map();
    for (const value of assignments) counts.set(value, (counts.get(value) || 0) + 1);
    const uniqueCabinets = Array.from(counts.keys()).sort((left, right) => left - right);
    const missing = [];
    for (let value = 1; value <= count; value += 1) {
      if (!counts.has(value)) missing.push(value);
    }
    const duplicates = Array.from(counts.entries())
      .filter(([, assignmentCount]) => assignmentCount > 1)
      .map(([value]) => value)
      .sort((left, right) => left - right);
    return {
      mappedCount: uniqueCabinets.length,
      assignmentCount: assignments.length,
      cabinetCount: count,
      uniqueCabinets,
      missing,
      duplicates,
      valid: Boolean(enabled) && missing.length === 0 && uniqueCabinets.length === count,
    };
  }

  function aggregateCabinetSwitchExpressions(columnKey, mappings) {
    const grouped = new Map();
    for (const mapping of Array.from(mappings || [])) {
      const cabinetIndex = Math.trunc(
        Number(mapping?.cabinetIndex ?? mapping?.cabinet_index ?? mapping?.cabinet) || 0,
      );
      if (cabinetIndex <= 0) continue;
      const objectName = String(mapping?.objectName ?? mapping?.object_name ?? "").trim();
      if (!objectName) throw new TypeError(`机柜${cabinetIndex}缺少状态字对象名`);
      const rawBits = mapping?.bitNos ?? mapping?.bit_nos ?? mapping?.switchBits ?? mapping?.switch_bits;
      const bits = Array.from(new Set(Array.from(rawBits || [], (value) => Math.trunc(Number(value)))));
      if (!bits.length || bits.some((bit) => !Number.isInteger(bit) || bit < 0 || bit > 31)) {
        throw new RangeError(`机柜${cabinetIndex}状态位集合无效：${Array.from(rawBits || []).join("/")}`);
      }
      if (!grouped.has(cabinetIndex)) grouped.set(cabinetIndex, new Map());
      const terms = grouped.get(cabinetIndex);
      for (const bit of bits) {
        const key = `${objectName}\u0000${bit}`;
        if (!terms.has(key)) terms.set(key, switchReadExpression(columnKey, objectName, bit));
      }
    }
    return Object.fromEntries(
      Array.from(grouped.entries())
        .sort(([left], [right]) => left - right)
        .map(([cabinetIndex, terms]) => [String(cabinetIndex), Array.from(terms.values()).join(" OR ")]),
    );
  }

  function patchInitializationBoardIncrements(templateText, classBoardCounts) {
    const text = String(templateText || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n");
    const targets = Object.fromEntries(
      Object.entries(classBoardCounts || {}).map(([classNo, rawTarget]) => {
        const normalizedClass = Math.trunc(Number(String(classNo).replace(/^CJX_Class/i, "")) || 0);
        const normalizedCount = Math.trunc(
          Number(
            rawTarget && typeof rawTarget === "object"
              ? rawTarget.boardCount ?? rawTarget.board_count
              : rawTarget,
          ) || 0,
        );
        const comment =
          rawTarget && typeof rawTarget === "object"
            ? String(rawTarget.comment || "").trim().replace(/^'+\s*/, "")
            : "";
        if (normalizedClass < 1 || normalizedClass > 8 || normalizedCount < 1 || normalizedCount > 8) {
          throw new RangeError(`Class槽板卡数无效：${classNo}=${normalizedCount}`);
        }
        return [normalizedClass, { boardCount: normalizedCount, comment }];
      }),
    );
    const lines = text.split("\n");
    const changes = [];
    const claimedLines = new Set();

    lines.forEach((line, classIndex) => {
      const classMatch = line.match(/CJX_Class([1-8])\s*=/i);
      if (!classMatch) return;
      const classNo = Number(classMatch[1]);
      if (!Object.prototype.hasOwnProperty.call(targets, classNo)) return;
      const candidates = [];
      for (let index = Math.max(0, classIndex - 2); index <= Math.min(lines.length - 1, classIndex + 2); index += 1) {
        if (/\bn\s*=\s*n\s*\+\s*\d+\b/i.test(lines[index])) candidates.push(index);
      }
      const incrementIndex = candidates.find((index) => !claimedLines.has(index));
      if (incrementIndex === undefined) {
        throw new Error(`CJX_Class${classNo}第${classIndex + 1}行附近未找到唯一板卡增量`);
      }
      const sourceLine = lines[incrementIndex];
      const incrementLine = sourceLine.replace(
        /(\bn\s*=\s*n\s*\+\s*)\d+/i,
        `$1${targets[classNo].boardCount}`,
      );
      const targetLine = targets[classNo].comment
        ? `${incrementLine.replace(/\s*'.*$/, "").trimEnd()}\t'${targets[classNo].comment}`
        : incrementLine;
      claimedLines.add(incrementIndex);
      if (targetLine === sourceLine) return;
      lines[incrementIndex] = targetLine;
      const sourceCount = Number(sourceLine.match(/\bn\s*=\s*n\s*\+\s*(\d+)/i)?.[1] || 0);
      const sourceComment = String(sourceLine.match(/'\s*(.*)$/)?.[1] || "").trim();
      changes.push({
        line: incrementIndex + 1,
        classNo,
        boardCount: targets[classNo].boardCount,
        comment: targets[classNo].comment || sourceComment,
        incrementChanged: sourceCount !== targets[classNo].boardCount,
        commentChanged:
          Boolean(targets[classNo].comment) && sourceComment !== targets[classNo].comment,
        sourceLine,
        targetLine,
      });
    });

    for (const classNo of Object.keys(targets).map(Number)) {
      if (!lines.some((line) => new RegExp(`CJX_Class${classNo}\\s*=`, "i").test(line))) {
        throw new Error(`初始化脚本中不存在CJX_Class${classNo}`);
      }
    }
    return {
      text: lines.join("\n"),
      changes,
      changedLines: changes.length,
      incrementChanges: changes.filter((item) => item.incrementChanged).length,
      commentChanges: changes.filter((item) => item.commentChanged).length,
      classBoardCounts: Object.fromEntries(
        Object.entries(targets).map(([classNo, target]) => [classNo, target.boardCount]),
      ),
      classTargets: Object.fromEntries(
        Object.entries(targets).map(([classNo, target]) => [classNo, { ...target }]),
      ),
    };
  }

  function secondLoopConfigurationKey(columnKey, boxPosition, boardOffset) {
    const column = columnKey === "B" || columnKey === "COL-B" ? "COL-B" : "COL-A";
    const position = Math.trunc(Number(boxPosition) || 0);
    const offset = Math.trunc(Number(boardOffset) || 0);
    if (position < 1 || position > 99 || offset < 0 || offset > 99) {
      throw new RangeError(`第二回路配置位置无效：${column}/${boxPosition}/${boardOffset}`);
    }
    return `${column}|AB_PAIR|P${String(position).padStart(2, "0")}|B${String(offset).padStart(2, "0")}`;
  }

  function secondLoopModeValue(mode) {
    const normalized = String(mode || "").trim();
    if (normalized === "none") return 0;
    if (normalized === "independent" || normalized === "independent_temperature") return 1;
    if (normalized === "shared" || normalized === "shared_temperature") return 2;
    return null;
  }

  function secondLoopRuntimeFlag(targetValue, hasSecondLoop = true) {
    if (!hasSecondLoop) return 0;
    const value = Number(targetValue);
    if (value === 1) return 1;
    if (value === 2) return 0;
    return null;
  }

  function protocolSecondLoopProjection(rows) {
    return Array.from(rows || [])
      .filter((row) => row && row.second_loop)
      .map((row) => ({
        configuration_key: String(row.configuration_key || ""),
        column: row.column === "COL-B" ? "COL-B" : "COL-A",
        box_position: Number(row.box_position),
        board_index: Number(row.board_index),
        board_ordinal: Number(row.board_ordinal),
        temperature_mode: row.temperature_mode || null,
        mode_value: row.target_value === null ? null : Number(row.target_value),
        object_name: String(row.object_name || ""),
        route_a_board: Number(row.route_board_numbers?.A),
        route_b_board: Number(row.route_board_numbers?.B),
      }));
  }

  function protocolArtifactDownload(result, key) {
    return (
      result?.delivery_bundle?.files?.[key]?.download ||
      result?.downloads?.[key] ||
      null
    );
  }

  function protocolBundleStatus(result) {
    const issues = [];
    const delivery = result?.delivery_status;
    const bundle = result?.delivery_bundle;
    if (delivery?.status !== "deliverable" || delivery?.ok !== true) {
      issues.push("交付状态未通过");
    }
    if (bundle?.status !== "complete") issues.push("三文件交付包不完整");
    if (result?.validation?.status !== "passed") issues.push("协议校验未通过");
    if (result?.alarm_codegen?.status !== "generated") issues.push("报警状态字代码未生成");
    if (result?.program_upload?.status !== "generated") issues.push("设备导入表未生成");
    for (const key of ["excel", "alarm_code", "program_upload"]) {
      if (bundle?.files?.[key]?.status !== "generated" || !protocolArtifactDownload(result, key)) {
        issues.push(`${key}下载文件缺失`);
      }
    }
    return { ok: issues.length === 0, issues };
  }

  function buildBoardTopology(spec = {}) {
    const column = spec.columnKey === "B" || spec.columnKey === "COL-B" ? "COL-B" : "COL-A";
    const isSecond = column === "COL-B";
    const objectIdBase = isSecond ? 10915 : 10881;
    const suffix = isSecond ? "_B" : "";
    const routeBases = isSecond ? { A: 300, B: 400 } : { A: 100, B: 200 };
    const modes = spec.temperatureModes && typeof spec.temperatureModes === "object"
      ? spec.temperatureModes
      : {};
    const rows = [];
    let boardIndex = 0;

    for (const [boxOffset, box] of Array.from(spec.boxes || []).entries()) {
      const boxPosition = Math.trunc(Number(box?.boxPosition) || boxOffset + 1);
      const slotId = String(box?.slotId || box?.typeId || "");
      const typeCode = String(box?.typeCode || "");
      const layoutPattern = String(box?.layoutPattern || "");
      const boardTemplateIds = Array.from(box?.boardTemplateIds || [], (id) => String(id));
      boardTemplateIds.forEach((boardTemplateId, boardOffset) => {
        boardIndex += 1;
        const dual = boardTemplateId === "board_1to6_3phase_dual";
        const configurationKey = secondLoopConfigurationKey(column, boxPosition, boardOffset);
        const topologyFingerprint = [
          slotId,
          typeCode,
          layoutPattern,
          `B${String(boardOffset).padStart(2, "0")}`,
          boardTemplateId,
        ].join("|");
        const rawEntry = modes[configurationKey];
        const entryMode =
          rawEntry && typeof rawEntry === "object"
            ? rawEntry.topologyFingerprint === topologyFingerprint
              ? rawEntry.mode
              : null
            : rawEntry;
        const normalizedMode = !dual
          ? "none"
          : secondLoopModeValue(entryMode) === 1
            ? "independent_temperature"
            : secondLoopModeValue(entryMode) === 2
              ? "shared_temperature"
              : null;
        const targetValue = !dual ? 0 : secondLoopModeValue(normalizedMode);
        const routeBoardNumbers = {
          A: routeBases.A + boardIndex,
          B: routeBases.B + boardIndex,
        };
        rows.push({
          configuration_key: configurationKey,
          topology_fingerprint: topologyFingerprint,
          column,
          route_scope: "paired",
          route_ids: [`${column}/A`, `${column}/B`],
          box_position: boxPosition,
          slot_id: slotId,
          type_code: typeCode,
          layout_pattern: layoutPattern,
          board_offset: boardOffset,
          board_ordinal: boardOffset + 1,
          board_template_id: boardTemplateId,
          board_index: boardIndex,
          route_board_numbers: routeBoardNumbers,
          state_objects: dual
            ? [`StateC${routeBoardNumbers.A}_2`, `StateC${routeBoardNumbers.B}_2`]
            : [`StateC${routeBoardNumbers.A}`, `StateC${routeBoardNumbers.B}`],
          second_loop: dual,
          temperature_mode: normalizedMode,
          target_value: targetValue,
          object_name: `BK_Branch_list${String(boardIndex).padStart(2, "0")}${suffix}`,
          object_id: objectIdBase + boardIndex - 1,
          status: dual && targetValue === null ? "unresolved" : "resolved",
          manual_action: dual && targetValue !== null && targetValue !== 0,
        });
      });
    }

    return {
      schema_version: "mcgs-board-topology/1.0",
      column,
      route_scope: "paired_routes_per_physical_column",
      board_count: rows.length,
      within_capacity: rows.length <= 33,
      rows,
      unresolved: rows.filter((row) => row.status === "unresolved"),
      actions: rows.filter((row) => row.manual_action),
    };
  }

  function activityDomain(hasSecondColumn) {
    const secondActive = Boolean(hasSecondColumn);
    return {
      columns: {
        "COL-A": {
          active: true,
          guard: "1",
          reason: "第一物理列始终属于当前屏的活动域。",
        },
        "COL-B": {
          active: secondActive,
          guard: "jgls=1",
          reason: secondActive
            ? "单屏双列，系统初始化令jgls=1。"
            : "单屏单列，系统初始化令jgls=0；第二物理列策略、设备和报警路径不可达。",
        },
      },
      strategyScripts: {
        alarmDescriptionA: {
          target: "修改机柜号及报警/脚本05",
          active: true,
          trigger: "1",
        },
        alarmDescriptionB: {
          target: "修改机柜号及报警/脚本06",
          active: secondActive,
          trigger: "jgls=1",
        },
        closeDevicesB: {
          target: "关闭多余采集设备/B列脚本",
          active: secondActive,
          trigger: "jgls=1",
        },
      },
      objectFamilies: {
        JG_DL: { active: true, readers: ["JG_DL_Group", "修改机柜号及报警/脚本05"] },
        JG_DL_B: {
          active: secondActive,
          readers: secondActive ? ["JG_DL_Group_B", "修改机柜号及报警/脚本06"] : [],
          inactiveReason: secondActive ? null : "single_screen_single_column_jgls_0",
        },
      },
      deviceFamilies: {
        "COL-A": {
          active: true,
          parentInterface: "SerialPort_A",
          childInitialState: "mixed_by_template_and_startup_strategy",
        },
        "COL-B": {
          active: secondActive,
          parentInterface: "SerialPort_B",
          parentMayRemainStarted: true,
          childInitialState: secondActive ? "enabled_by_startup_strategy" : "stopped_in_template",
          inactiveReason: secondActive
            ? null
            : "S3/S4、C3xx/C4xx、Z3xx/Z4xx在模板中的初始工作状态为停止；jgls=0时B列启用脚本不可达。",
        },
      },
    };
  }

  function nonNegativeInteger(value) {
    return Math.max(0, Math.trunc(Number(value) || 0));
  }

  function numberedIds(prefix, start, end, pad = 0) {
    const first = Math.max(1, nonNegativeInteger(start));
    const last = nonNegativeInteger(end);
    if (last < first) return [];
    const result = [];
    for (let index = first; index <= last; index += 1) {
      result.push(`${prefix}${String(index).padStart(pad, "0")}`);
    }
    return result;
  }

  function relayIds(base, start, end) {
    const first = Math.max(1, nonNegativeInteger(start));
    const last = nonNegativeInteger(end);
    if (last < first) return [];
    const result = [];
    for (let index = first; index <= last; index += 1) result.push(`Z${base + index}`);
    return result;
  }

  function compactIdList(ids) {
    const values = Array.from(ids || []);
    if (!values.length) return "无";
    const parsed = values.map((value) => {
      const match = String(value).match(/^(.*?)(\d+)$/);
      return match ? { text: String(value), prefix: match[1], number: Number(match[2]) } : null;
    });
    if (parsed.some((item) => item === null)) return values.join("、");
    const groups = [];
    let current = { start: parsed[0], end: parsed[0] };
    for (let index = 1; index < parsed.length; index += 1) {
      const item = parsed[index];
      if (item.prefix === current.end.prefix && item.number === current.end.number + 1) {
        current.end = item;
      } else {
        groups.push(current);
        current = { start: item, end: item };
      }
    }
    groups.push(current);
    return groups
      .map((group) =>
        group.start.text === group.end.text ? group.start.text : `${group.start.text}~${group.end.text}`,
      )
      .join("、");
  }

  function buildColumnWindowPlan(columnKey, input, active) {
    const baseline = WINDOW_TEMPLATE_BASELINE[columnKey];
    const boxCount = active ? nonNegativeInteger(input?.boxCount) : 0;
    const cabinetCount = active ? nonNegativeInteger(input?.cabinetCount) : 0;
    const relayCount = active ? nonNegativeInteger(input?.relayCount) : 0;
    const boxTargets = numberedIds(baseline.boxPrefix, 1, boxCount);
    const boxClones = numberedIds(
      baseline.boxPrefix,
      baseline.boxButtons + 1,
      boxCount,
    );
    const boxHides = active
      ? numberedIds(baseline.boxPrefix, boxCount + 1, baseline.boxButtons)
      : [];
    const cabinetTargets = numberedIds(baseline.cabinetPrefix, 1, cabinetCount, 2);
    const cabinetClones = numberedIds(
      baseline.cabinetPrefix,
      baseline.cabinetButtons + 1,
      cabinetCount,
      2,
    );
    const cabinetHides = active
      ? numberedIds(baseline.cabinetPrefix, cabinetCount + 1, baseline.cabinetButtons, 2)
      : [];
    const relayTargets = baseline.relayBases.flatMap((base) => relayIds(base, 1, relayCount));
    const relayClones = baseline.relayBases.flatMap((base) =>
      relayIds(base, baseline.relaysPerBus + 1, relayCount),
    );
    const relayHides = active
      ? baseline.relayBases.flatMap((base) => relayIds(base, relayCount + 1, baseline.relaysPerBus))
      : [];
    const temperatureTargets = numberedIds("", baseline.temperatureBase + 1, baseline.temperatureBase + boxCount);
    const temperatureClones = numberedIds(
      "",
      baseline.temperatureBase + baseline.temperatureBoxes + 1,
      baseline.temperatureBase + boxCount,
    );
    const temperatureHides = active
      ? numberedIds(
          "",
          baseline.temperatureBase + boxCount + 1,
          baseline.temperatureBase + baseline.temperatureBoxes,
        )
      : numberedIds(
          "",
          baseline.temperatureBase + 1,
          baseline.temperatureBase + baseline.temperatureBoxes,
        );
    const knownElementCount =
      baseline.topLevelElements +
      boxClones.length * baseline.boxCloneElements +
      cabinetClones.length * baseline.cabinetCloneElements;
    return {
      column: columnKey,
      active,
      label: baseline.label,
      main_window: baseline.mainWindow,
      counts: { boxes: boxCount, cabinets: cabinetCount, relays_per_bus: relayCount },
      baseline: {
        box_buttons: baseline.boxButtons,
        cabinet_buttons: baseline.cabinetButtons,
        relays_per_bus: baseline.relaysPerBus,
        temperature_boxes: baseline.temperatureBoxes,
        top_level_elements: baseline.topLevelElements,
      },
      box_buttons: { target: boxTargets, clone: boxClones, hide: boxHides },
      cabinet_buttons: { target: cabinetTargets, clone: cabinetClones, hide: cabinetHides },
      relays: { target: relayTargets, clone: relayClones, hide: relayHides },
      temperature_boxes: {
        target: active ? temperatureTargets : [],
        clone: active ? temperatureClones : [],
        hide: temperatureHides,
      },
      expected_main_window_objects: {
        exact: !active || relayClones.length === 0,
        value: !active || relayClones.length === 0 ? knownElementCount : null,
        known_minimum: knownElementCount,
        reason:
          relayClones.length === 0
            ? "隐藏/禁用不改变对象数；箱按钮每个新增2对象，机柜按钮每个新增8对象。"
            : "中继超过模板每路3个，需要在GUI中克隆完整复合组；先记录单组对象增量再确定最终对象数。",
      },
    };
  }

  function buildWindowGuiPlan(spec = {}) {
    const hasSecondColumn = Boolean(spec.hasSecondColumn);
    const columns = {
      "COL-A": buildColumnWindowPlan("COL-A", spec.columns?.["COL-A"], true),
      "COL-B": buildColumnWindowPlan("COL-B", spec.columns?.["COL-B"], hasSecondColumn),
    };
    const activeColumns = Object.values(columns).filter((column) => column.active);
    const actions = [];
    const automaticActions = [];
    const releaseValidation = [];
    const internalEvidence = [];
    const addManualAction = (module, instruction, scope = "all", reason = "模板中不存在目标结构") =>
      actions.push({
        step_no: actions.length + 1,
        module,
        instruction,
        scope,
        ownership: "manual_change",
        active: true,
        reason,
      });
    const addAutomatic = (module, scope, reason) =>
      automaticActions.push({ module, scope, ownership: "auto_derived", active: true, reason });

    for (const column of activeColumns) {
      if (column.box_buttons.clone.length) {
        const baseline = WINDOW_TEMPLATE_BASELINE[column.column];
        addManualAction(
          `${column.label}新增插接箱按钮`,
          `到哪里改：用户窗口 → ${column.main_window}。怎么改：从${baseline.boxPrefix}${baseline.boxButtons}完整双层按钮组克隆${compactIdList(column.box_buttons.clone)}，保留A/B路叠层、标签和透明点击层；随后粘贴“插接箱按钮动作”中同编号代码。`,
          column.column,
          `项目需要${column.counts.boxes}个按钮，模板只有${baseline.boxButtons}个。`,
        );
      } else {
        addAutomatic(
          `${column.label}插接箱数量显示`,
          column.column,
          `目标${column.counts.boxes}个未超过模板${column.baseline.box_buttons}个，现有数量变量和可见度动画负责裁剪。`,
        );
      }
      if (column.cabinet_buttons.clone.length) {
        const baseline = WINDOW_TEMPLATE_BASELINE[column.column];
        addManualAction(
          `${column.label}新增机柜按钮`,
          `到哪里改：用户窗口 → ${column.main_window}。怎么改：从${baseline.cabinetPrefix}${String(baseline.cabinetButtons).padStart(2, "0")}完整8对象复合组克隆${compactIdList(column.cabinet_buttons.clone)}，同步重绑Cabinet、I、KAA/KAB两层和点击热区；随后粘贴同编号“机柜按钮动作”。`,
          column.column,
          `项目需要${column.counts.cabinets}个机柜按钮，模板只有${baseline.cabinetButtons}个。`,
        );
      } else {
        addAutomatic(
          `${column.label}机柜数量显示`,
          column.column,
          `目标${column.counts.cabinets}个未超过模板${column.baseline.cabinet_buttons}个，现有数量变量和可见度动画负责裁剪。`,
        );
      }
      if (column.relays.clone.length) {
        addManualAction(
          `${column.label}新增中继控件`,
          `到哪里改：用户窗口 → ${column.main_window}。怎么改：从每路第3个中继的完整复合组克隆${compactIdList(column.relays.clone)}，同步修改标签、设备名、点击动作和状态绑定。`,
          column.column,
          `项目每路需要${column.counts.relays_per_bus}个中继，模板每路只有${column.baseline.relays_per_bus}个。`,
        );
      } else {
        addAutomatic(
          `${column.label}中继数量显示`,
          column.column,
          `目标每路${column.counts.relays_per_bus}个未超过模板${column.baseline.relays_per_bus}个，现有数量变量和可见度动画负责裁剪。`,
        );
      }
      if (column.temperature_boxes.clone.length) {
        addManualAction(
          `${column.label}新增温升入口`,
          `到哪里改：用户窗口 → 温升柱图。怎么改：从本列第10组完整克隆${compactIdList(column.temperature_boxes.clone)}，柱条、数值、标签和透明按钮必须成组复制，并按同编号插接箱重绑。`,
          column.column,
          `项目需要${column.counts.boxes}组温升入口，模板只有${column.baseline.temperature_boxes}组。`,
        );
      } else {
        addAutomatic(
          `${column.label}温升入口数量`,
          column.column,
          `目标${column.counts.boxes}组未超过模板${column.baseline.temperature_boxes}组，现有可见度设置负责裁剪。`,
        );
      }
    }

    addAutomatic(
      "第二物理列入口",
      hasSecondColumn ? "COL-B" : "inactive-COL-B",
      "入口显示和目标窗口由jgls及现有窗口脚本接管。",
    );
    addAutomatic(
      "始端箱入口",
      "all",
      "入口目标由jgls选择始端箱或始端箱_双列。",
    );

    const totals = {
      boxes: activeColumns.reduce((sum, column) => sum + column.counts.boxes, 0),
      cabinets: activeColumns.reduce((sum, column) => sum + column.counts.cabinets, 0),
      relays: activeColumns.reduce((sum, column) => sum + column.counts.relays_per_bus * 2, 0),
      temperature_entries: activeColumns.reduce((sum, column) => sum + column.counts.boxes, 0),
    };
    releaseValidation.push({
      ownership: "release_validation",
      title: "窗口功能检查",
      instruction: `检查${totals.boxes}个插接箱、${totals.cabinets}个机柜、${totals.relays}个中继和${totals.temperature_entries}个温升入口。`,
    });

    const expectedObjectCounts = Object.values(columns).map((column) => ({
      window: column.main_window,
      ...column.expected_main_window_objects,
    }));
    const temperatureNeedsClone = Object.values(columns).some(
      (column) => column.active && column.temperature_boxes.clone.length > 0,
    );
    expectedObjectCounts.push({
      window: WINDOW_TEMPLATE_BASELINE.temperatureWindow.name,
      exact: !temperatureNeedsClone,
      value: temperatureNeedsClone ? null : WINDOW_TEMPLATE_BASELINE.temperatureWindow.topLevelElements,
      known_minimum: WINDOW_TEMPLATE_BASELINE.temperatureWindow.topLevelElements,
      reason: temperatureNeedsClone
        ? "存在第11个及以后温升组，需先在GUI记录完整组对象增量。"
        : "只调整现有对象的显示、绑定和动作，不改变对象数。",
    });
    internalEvidence.push({
      ownership: "internal_evidence",
      expected_object_counts: expectedObjectCounts,
      note: "用于Agent验证窗口结构，不进入用户操作清单。",
    });

    return {
      schema_version: "mcgs-window-gui-plan/2.0",
      has_second_column: hasSecondColumn,
      totals,
      columns,
      expected_object_counts: expectedObjectCounts,
      actions,
      automatic_actions: automaticActions,
      release_validation: releaseValidation,
      internal_evidence: internalEvidence,
    };
  }

  function stableStringify(value) {
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  function buildManualDeviceInterfaceActions(records, spec = {}) {
    const targetById = {
      "mcgs:interface:SerialPort_B": spec.hasSecondColumn ? 1 : 0,
      "mcgs:interface:通用TCPIP父设备1": spec.screenLinkEnabled ? 1 : 0,
    };
    return (Array.isArray(records) ? records : []).flatMap((record) => {
      if (
        !record ||
        record.surfaceKind !== "device_interface" ||
        record.property !== "initial_work_state" ||
        record.needsManualAction !== true ||
        record.changeRequired !== true ||
        (Array.isArray(record.automaticSources) && record.automaticSources.length > 0) ||
        !Object.prototype.hasOwnProperty.call(targetById, record.targetId)
      ) {
        return [];
      }
      const target = targetById[record.targetId];
      if (stableStringify(record.old) === stableStringify(target)) return [];
      return [{ ...record, new: target }];
    });
  }

  function actionableTriggerExpression(value) {
    const text = String(value ?? "").trim();
    const compact = text.replace(/\s+/g, "");
    if (!compact || compact === "1" || compact === "留空（默认成立）") return "";
    if (/^(保持原脚本触发条件|沿用原脚本触发条件|保持模板原触发条件|按模板原上传策略保持)$/.test(compact)) {
      return "";
    }
    return text;
  }

  function fingerprint(value) {
    const text = stableStringify(value);
    let hash = 0x811c9dc5;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    return `FNV1A-${(hash >>> 0).toString(16).padStart(8, "0").toUpperCase()}`;
  }

  function protocolSelectionKey(typeCode, layoutPattern) {
    const type = String(typeCode || "").trim();
    const layout = String(layoutPattern || "").trim();
    return type && layout ? `${type}|${layout}` : "";
  }

  function parseProtocolSelection(value) {
    const [typeCode = "", layoutPattern = ""] = String(value || "").split("|", 2);
    return { typeCode: typeCode.trim(), layoutPattern: layoutPattern.trim() };
  }

  function normalizeProtocolCatalog(boxTypes) {
    const candidate = Array.isArray(boxTypes) && boxTypes.length ? boxTypes : FALLBACK_PROTOCOL_TYPE_CATALOG;
    const normalized = candidate.map((type) => {
      const typeCode = String(type?.type_code || "").trim();
      const phaseMode = String(type?.phase_mode || "").trim();
      const layouts = Array.from(type?.allowed_layout_patterns || [], (layout) => ({
        pattern: String(layout?.pattern ?? layout?.value ?? "").trim(),
        value: String(layout?.value ?? layout?.pattern ?? "").trim(),
        label: String(layout?.label || layout?.help_text || layout?.pattern || "").trim(),
        short_label: String(layout?.short_label || layout?.pattern || "").trim(),
        help_text: String(layout?.help_text || layout?.label || "").trim(),
        board_count: Math.trunc(Number(layout?.board_count) || 0),
        branch_count: Math.trunc(Number(layout?.branch_count) || 0),
        board_template_ids: Array.from(layout?.board_template_ids || [], (id) => String(id)),
      }));
      if (!typeCode || !phaseMode || !layouts.length) {
        throw new Error(`动环箱型目录条目不完整：${typeCode || "未命名"}`);
      }
      for (const layout of layouts) {
        if (!layout.pattern || layout.board_count < 1 || layout.branch_count < 1 || !layout.board_template_ids.length) {
          throw new Error(`动环箱型${typeCode}的布局${layout.pattern || "未命名"}不完整`);
        }
      }
      return {
        type_code: typeCode,
        label: String(type?.label || typeCode),
        short_label: String(type?.short_label || typeCode),
        aliases: Array.from(type?.aliases || [], (alias) => String(alias)),
        phase_mode: phaseMode,
        branch_count: Math.trunc(Number(type?.branch_count) || layouts[0].branch_count),
        default_layout_pattern: String(type?.default_layout_pattern || layouts[0].pattern),
        allowed_layout_patterns: layouts,
        notes: String(type?.notes || ""),
        help_text: String(type?.help_text || type?.notes || ""),
      };
    });
    return normalized;
  }

  function findProtocolLayout(catalog, typeCode, layoutPattern) {
    const types = normalizeProtocolCatalog(catalog);
    const type = types.find((item) => item.type_code === String(typeCode));
    const layout = type?.allowed_layout_patterns.find(
      (item) => item.pattern === String(layoutPattern) || item.value === String(layoutPattern),
    );
    return type && layout ? { type, layout } : null;
  }

  function protocolLayoutDescriptor(catalog, typeCode, layoutPattern) {
    const found = findProtocolLayout(catalog, typeCode, layoutPattern);
    if (!found) throw new Error(`动环箱型组合不存在：${typeCode}/${layoutPattern}`);
    const branches = [];
    found.layout.board_template_ids.forEach((templateId, boardOffset) => {
      const board = PROTOCOL_BOARD_TEMPLATES[templateId];
      if (!board) throw new Error(`未知板卡模板：${templateId}`);
      board.branches.forEach((branch) => {
        branches.push({
          boardOffset,
          loop: branch.loop,
          mode: branch.mode,
          phaseIndex: branch.phaseIndex,
          switchBits: [...branch.switchBits],
          boardTemplateId: templateId,
          boardLabel: board.label,
        });
      });
    });
    if (branches.length !== found.layout.branch_count || branches.length !== found.type.branch_count) {
      throw new Error(
        `动环箱型${found.type.type_code}/${found.layout.pattern}输出数不一致：目录${found.layout.branch_count}，板卡展开${branches.length}`,
      );
    }
    if (found.layout.board_template_ids.length !== found.layout.board_count) {
      throw new Error(
        `动环箱型${found.type.type_code}/${found.layout.pattern}板卡数不一致：目录${found.layout.board_count}，模板${found.layout.board_template_ids.length}`,
      );
    }
    return {
      typeCode: found.type.type_code,
      typeLabel: found.type.label,
      phaseMode: found.type.phase_mode,
      layoutPattern: found.layout.pattern,
      layoutLabel: found.layout.label,
      boardCount: found.layout.board_count,
      branchCount: found.layout.branch_count,
      boardTemplateIds: [...found.layout.board_template_ids],
      hasDualLoopBoard: found.layout.board_template_ids.includes("board_1to6_3phase_dual"),
      branches,
    };
  }

  function compactSequences(typeIds, resolveProtocolType) {
    const sequences = [];
    for (const typeId of typeIds || []) {
      const descriptor = resolveProtocolType(typeId);
      if (!descriptor || !descriptor.typeCode || !descriptor.layoutPattern) {
        throw new Error(`插接箱类型${typeId}缺少动环类型代码或布局模式`);
      }
      const previous = sequences[sequences.length - 1];
      if (
        previous &&
        previous.type_code === descriptor.typeCode &&
        previous.layout_pattern === descriptor.layoutPattern
      ) {
        previous.count += 1;
      } else {
        sequences.push({
          type_code: descriptor.typeCode,
          count: 1,
          layout_pattern: descriptor.layoutPattern,
        });
      }
    }
    return sequences;
  }

  function buildProtocolConfig(spec) {
    const protocolColumn = spec.protocolColumn || spec.representativeColumn;
    if (!protocolColumn || !Array.isArray(protocolColumn.typeIds) || !protocolColumn.typeIds.length) {
      throw new Error("没有可用于生成动环协议的活动物理列");
    }
    const resolveProtocolType = (typeId) => {
      const custom = spec.customProtocolTypes?.[typeId];
      return custom || PROTOCOL_TYPE_MAP[typeId] || null;
    };
    const sequence = compactSequences(protocolColumn.typeIds, resolveProtocolType);
    const useRtuUpload = spec.uploadProtocol === "modbus_rtu_forwarder";
    const protocol = useRtuUpload ? "Modbus RTU" : "Modbus TCP/IP";
    const cabinetCount = Math.max(0, Number(spec.maxCabinetCount ?? protocolColumn.cabinetCount) || 0);
    const relayCounts = spec.relayCounts && typeof spec.relayCounts === "object" ? spec.relayCounts : {};
    const relayCountA = Math.max(
      0,
      Number((Array.isArray(relayCounts) ? relayCounts[0] : relayCounts.A ?? relayCounts.A_count) ?? protocolColumn.relayCount) || 0,
    );
    const relayCountB = Math.max(
      0,
      Number((Array.isArray(relayCounts) ? relayCounts[1] : relayCounts.B ?? relayCounts.B_count) ?? protocolColumn.relayCount) || 0,
    );
    const tcpipUpload = spec.tcpipUpload || spec.tcpIpUpload || spec.tcpip_upload || {};
    const uploadStationAddress = Number(
      useRtuUpload
        ? spec.stationAddress
        : tcpipUpload.station_address ?? spec.tcpStationAddress ?? spec.stationAddress,
    ) || 1;
    const tcpBindIp = Object.prototype.hasOwnProperty.call(tcpipUpload, "bind_ip")
      ? tcpipUpload.bind_ip
      : Object.prototype.hasOwnProperty.call(spec, "tcpBindIp")
        ? spec.tcpBindIp
        : null;
    const communication = {
      protocol,
      baud_rate: Number(spec.baudRate) || 9600,
      parity: "N",
      data_bits: 8,
      stop_bits: 1,
      default_screen_address: uploadStationAddress,
    };
    if (!useRtuUpload) {
      communication.tcpip_upload = {
        listen_port: Number(tcpipUpload.listen_port ?? spec.tcpListenPort ?? spec.tcpPort) || 502,
        bind_ip: tcpBindIp === null ? null : String(tcpBindIp),
        station_address: uploadStationAddress,
      };
    }
    const secondLoopTemperature = Array.isArray(spec.secondLoopTemperature)
      ? spec.secondLoopTemperature.map((item) =>
          item && typeof item === "object" && !Array.isArray(item) ? { ...item } : item,
        )
      : [];
    const programUpload = useRtuUpload
      ? {
          device_name: "upload",
          driver_component_name: "ModbusRTU上传",
          driver_library_path: "modbuscommslave_str.ui",
          driver_component_version: "7.105",
          encoding: "gb18030",
        }
      : {
          device_name: "数据上传_以太网",
          driver_component_name: "modbus_tcpip_forwarder",
          driver_library_path: "modbustcpipslave_str.ui",
          driver_component_version: "7.1.0.12",
          encoding: "gb18030",
        };
    return {
      workflow_version: "unified_protocol_v1",
      project: {
        name: spec.projectName || "未命名项目",
        code: spec.projectCode || fingerprint(spec).replace("FNV1A-", "MCGS-"),
        protocol_title: "动环通讯协议",
      },
      communication,
      program_upload: programUpload,
      protocol_layout: {
        measurement_layout_mode: "by_plug_box",
        main_base_address: 1000,
        embed_single_cabinet_in_base_sheet: true,
        alarm_start_box_first: true,
      },
      routes: {
        A: {
          start_boxes: { count: 1, instance_names: ["S1"] },
          plug_boxes: {
            board_number_start: 101,
            sequence,
          },
        },
        B: {
          start_boxes: { count: 1, instance_names: ["S2"] },
          plug_boxes: {
            board_number_start: 201,
            sequence: sequence.map((item) => ({ ...item })),
          },
        },
      },
      extensions: {
        single_cabinet: {
          enabled: cabinetCount > 0,
          cabinet_count: cabinetCount,
          base_address: 7000,
        },
        repeater: {
          enabled: relayCountA > 0 || relayCountB > 0,
          A_count: relayCountA,
          B_count: relayCountB,
          alias: "中继器",
          base_address: 5500,
        },
        second_loop_temperature: secondLoopTemperature,
        alarm_state_word: {
          enabled: true,
          base_address: 6000,
          word_mode: "16bit",
        },
      },
      profiles: {},
    };
  }

  const api = Object.freeze({
    FALLBACK_PROTOCOL_TYPE_CATALOG,
    PROTOCOL_BOARD_TEMPLATES,
    PROTOCOL_TYPE_MAP,
    PROGRAM_TEMPLATE_BASELINE,
    TEMPLATE_LIMITS,
    WINDOW_TEMPLATE_BASELINE,
    actionableTriggerExpression,
    activityDomain,
    alarmSelectorPermutation,
    branchDisabledMask,
    buildBoardTopology,
    aggregateCabinetSwitchExpressions,
    buildManualDeviceInterfaceActions,
    buildProgramDiffPlan,
    buildProtocolConfig,
    buildWindowGuiPlan,
    cabinetDataPointer,
    cabinetCoverageStatus,
    compactSequences,
    fingerprint,
    groupSlotsByBox,
    patchAlarmDescriptionSelectors,
    patchInitializationBoardIncrements,
    parseProtocolSelection,
    protocolArtifactDownload,
    protocolBundleStatus,
    protocolLayoutDescriptor,
    protocolSecondLoopProjection,
    protocolSelectionKey,
    normalizeProtocolCatalog,
    reverseFill,
    secondLoopConfigurationKey,
    secondLoopModeValue,
    secondLoopRuntimeFlag,
    stableStringify,
    switchReadExpression,
    switchReadAnyExpression,
  });

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.MCGS_WORKFLOW_CORE = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
