"use strict";

const assert = require("node:assert/strict");
const core = require("../../assembly_studio/static/workflow-core.js");
global.window = global;
require("../../assembly_studio/static/data.js");

function slots(boxCount, outputsPerBox) {
  const result = [];
  for (let boxPosition = 1; boxPosition <= boxCount; boxPosition += 1) {
    for (let branchNo = 1; branchNo <= outputsPerBox; branchNo += 1) {
      result.push({
        key: `P${String(boxPosition).padStart(2, "0")}-R${String(branchNo).padStart(2, "0")}`,
        boxPosition,
        branchNo,
      });
    }
  }
  return result;
}

function orderedValues(mapping, sourceSlots) {
  return sourceSlots.map((slot) => mapping[slot.key]);
}

const sixSlots = slots(2, 3);
assert.deepEqual(
  orderedValues(core.reverseFill(sixSlots, 6), sixSlots),
  [3, 2, 1, 6, 5, 4],
  "反序填充必须在每个插接箱的连续机柜块内反转",
);
assert.deepEqual(
  orderedValues(core.reverseFill(sixSlots, 5), sixSlots),
  [3, 2, 1, 0, 5, 4],
  "尾箱机柜不足时，空输出应留在反序后的前部",
);

assert.deepEqual(
  [1, 2, 3, 4].map((branch) => core.branchDisabledMask(branch)),
  [1, 2, 4, 8],
  "Disabled必须使用1/2/4/8位掩码，不能把第三分路写成3",
);
assert.equal(core.cabinetDataPointer("A", 7), 7);
assert.equal(core.cabinetDataPointer("B", 7), 107);
assert.equal(core.cabinetDataPointer("COL-B", 0), 0);
assert.equal(core.actionableTriggerExpression("保持原脚本触发条件"), "");
assert.equal(core.actionableTriggerExpression("按模板原上传策略保持"), "");
assert.equal(core.actionableTriggerExpression("1"), "");
assert.equal(core.actionableTriggerExpression("jgls=1"), "jgls=1");
assert.equal(core.switchReadExpression("A", "StateC101", 2), "!BitTest(StateC101,2)");
assert.equal(core.switchReadExpression("B", "StateC301", 2), "!BitAnd(StateC301,4)");
assert.equal(
  core.switchReadAnyExpression("A", "StateC101", [0, 1, 2]),
  "!BitTest(StateC101,0) OR !BitTest(StateC101,1) OR !BitTest(StateC101,2)",
  "三相回路开关状态必须在BIT0到BIT2任意一位为1时成立",
);
assert.equal(
  core.switchReadAnyExpression("B", "StateC301", [0, 1, 2]),
  "!BitAnd(StateC301,1) OR !BitAnd(StateC301,2) OR !BitAnd(StateC301,4)",
  "第二物理列保持模板BitAnd掩码写法",
);
assert.equal(
  core.switchReadAnyExpression("A", "StateC101_2", [0, 1, 2]),
  "!BitTest(StateC101_2,0) OR !BitTest(StateC101_2,1) OR !BitTest(StateC101_2,2)",
  "一拖六第二回路已归一化到StateC_2的BIT0到BIT2",
);
assert.deepEqual(
  core.aggregateCabinetSwitchExpressions("A", [
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [0] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [1] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [2] },
  ]),
  { 1: "!BitTest(StateC101,0) OR !BitTest(StateC101,1) OR !BitTest(StateC101,2)" },
  "三相同柜必须聚合为BIT0/1/2任意一位为1",
);
assert.deepEqual(
  core.aggregateCabinetSwitchExpressions("A", [
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [0] },
    { cabinetIndex: 2, objectName: "StateC101", bitNos: [1] },
    { cabinetIndex: 3, objectName: "StateC101", bitNos: [2] },
  ]),
  {
    1: "!BitTest(StateC101,0)",
    2: "!BitTest(StateC101,1)",
    3: "!BitTest(StateC101,2)",
  },
  "三相分接不同机柜时每柜保持单bit",
);
assert.deepEqual(
  core.aggregateCabinetSwitchExpressions("A", [
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [0, 0, 1] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [1, 2, 2] },
    { cabinetIndex: 0, objectName: "StateC101", bitNos: [3] },
  ]),
  { 1: "!BitTest(StateC101,0) OR !BitTest(StateC101,1) OR !BitTest(StateC101,2)" },
  "重复状态位必须去重，备用映射不得进入表达式",
);
assert.deepEqual(core.cabinetCoverageStatus([1, 1, 1], 1, true), {
  mappedCount: 1,
  assignmentCount: 3,
  cabinetCount: 1,
  uniqueCabinets: [1],
  missing: [],
  duplicates: [1],
  valid: true,
});
assert.equal(
  core.cabinetCoverageStatus([0, 1, 1], 2, true).valid,
  false,
  "唯一机柜集合没有覆盖1..cabinetCount时必须阻止生成",
);
assert.deepEqual(core.TEMPLATE_LIMITS.switchCabinets, { "COL-A": 20, "COL-B": 19 });

const oneToSixDescriptor = core.protocolLayoutDescriptor(
  core.FALLBACK_PROTOCOL_TYPE_CATALOG,
  "3P*2",
  "2",
);
assert.equal(oneToSixDescriptor.boardCount, 1);
assert.equal(oneToSixDescriptor.branchCount, 2);
assert.equal(oneToSixDescriptor.hasDualLoopBoard, true);
assert.deepEqual(
  oneToSixDescriptor.branches.map((item) => ({
    boardOffset: item.boardOffset,
    loop: item.loop,
    switchBits: item.switchBits,
  })),
  [
    { boardOffset: 0, loop: 1, switchBits: [0, 1, 2] },
    { boardOffset: 0, loop: 2, switchBits: [0, 1, 2] },
  ],
);

const initializationPatch = core.patchInitializationBoardIncrements(
  [
    "IF !BitTest(Layout_A,i) = 0 THEN",
    "  n=n+2",
    "  CJX_Class2=CJX_Class2+2^i",
    "ENDIF",
  ].join("\n"),
  { 2: 1 },
);
assert.equal(initializationPatch.changedLines, 1);
assert.match(initializationPatch.text, /n=n\+1/);

const realInitializationTemplate = global.MCGS_SOURCE.initializationTemplates.columnA.content;
const realClass2Patch = core.patchInitializationBoardIncrements(realInitializationTemplate, { 2: 1 });
const class2Occurrences = Array.from(realInitializationTemplate.matchAll(/CJX_Class2\s*=/g)).length;
assert.equal(class2Occurrences, 25, "完整脚本02应包含25个Class2箱位分支");
assert.equal(realClass2Patch.changedLines, class2Occurrences, "每个Class2箱位只改一处板卡地址增量");
assert.ok(
  realClass2Patch.changes.every(
    (change) =>
      change.classNo === 2 &&
      /n\s*=\s*n\s*\+\s*2/.test(change.sourceLine) &&
      /n\s*=\s*n\s*\+\s*1/.test(change.targetLine),
  ),
  "真实完整脚本只能把Class2对应的n=n+2定向改为n=n+1",
);

assert.deepEqual(core.alarmSelectorPermutation([1, 2, 3], [3, 2, 1]), [3, 2, 1]);
assert.deepEqual(core.alarmSelectorPermutation([3, 2, 1], [3, 2, 1]), [1, 2, 3]);
assert.deepEqual(core.alarmSelectorPermutation([0, 0, 0], [0, 0, 0]), [1, 2, 3]);
assert.deepEqual(
  core.alarmSelectorPermutation([1, 0, 0], [0, 0, 1]),
  [3, 2, 1],
  "重复的备用槽应优先保留同相选择器，避免无意义改动",
);
assert.throws(
  () => core.alarmSelectorPermutation([1, 2, 3], [1, 2, 4]),
  /机柜集合不一致/,
);

function miniatureAlarmTemplate(boardNo) {
  const lines = [];
  for (const [phase, selector] of [
    ["a", 1],
    ["b", 2],
    ["c", 3],
  ]) {
    for (const [prefix, alarmIndexes] of [
      ["PF", [0]],
      ["P", [0]],
      ["I", [0]],
      ["U", [0, 1, 2]],
    ]) {
      for (const alarmIndex of alarmIndexes) {
        lines.push(`!SetAlmInfo(${prefix}${phase}${boardNo},${alarmIndex},"("+ALM_Cabinet${selector}+"柜)")`);
      }
    }
  }
  lines.push(`!SetAlmInfo(PFa${boardNo}_2,0,"("+ALM_Cabinet1+"柜)")`);
  return lines.join("\n");
}

const alarmPatch = core.patchAlarmDescriptionSelectors(miniatureAlarmTemplate(201), [
  { boardNo: 201, boxPosition: 1, selectors: [3, 2, 1] },
]);
assert.equal(alarmPatch.matchedLines, 18);
assert.equal(alarmPatch.changedLines, 12);
assert.match(alarmPatch.text, /SetAlmInfo\(PFa201,0,"\("\+ALM_Cabinet3/);
assert.match(alarmPatch.text, /SetAlmInfo\(PFb201,0,"\("\+ALM_Cabinet2/);
assert.match(alarmPatch.text, /SetAlmInfo\(PFc201,0,"\("\+ALM_Cabinet1/);
assert.match(alarmPatch.text, /SetAlmInfo\(PFa201_2,0,"\("\+ALM_Cabinet1/);

const singleColumn = core.activityDomain(false);
assert.equal(singleColumn.columns["COL-B"].active, false);
assert.equal(singleColumn.strategyScripts.alarmDescriptionB.active, false);
assert.equal(singleColumn.objectFamilies.JG_DL_B.active, false);
assert.deepEqual(singleColumn.objectFamilies.JG_DL_B.readers, []);

const doubleColumn = core.activityDomain(true);
assert.equal(doubleColumn.columns["COL-B"].active, true);
assert.equal(doubleColumn.strategyScripts.alarmDescriptionB.active, true);

const manualDeviceRecords = global.MCGS_SOURCE.runtimeModel.manualDeviceActions;
const singleColumnDeviceInterfaces = core.buildManualDeviceInterfaceActions(manualDeviceRecords, {
  hasSecondColumn: false,
  screenLinkEnabled: false,
});
assert.deepEqual(
  singleColumnDeviceInterfaces.map((item) => [item.targetId, item.old, item.new]),
  [
    ["mcgs:interface:SerialPort_B", 1, 0],
    ["mcgs:interface:通用TCPIP父设备1", 1, 0],
  ],
  "单屏单列必须列出两个无法由运行策略替代的父接口停用动作",
);
const doubleColumnDeviceInterfaces = core.buildManualDeviceInterfaceActions(manualDeviceRecords, {
  hasSecondColumn: true,
  screenLinkEnabled: false,
});
assert.deepEqual(
  doubleColumnDeviceInterfaces.map((item) => [item.targetId, item.old, item.new]),
  [["mcgs:interface:通用TCPIP父设备1", 1, 0]],
  "单屏双列继续使用SerialPort_B，只停用未使用的屏间TCP父接口",
);
assert.equal(
  doubleColumnDeviceInterfaces.some((item) => item.surfaceKind === "device_channel_table"),
  false,
  "设备导入表必须等当前项目文件生成后再显示，不能复用示例项目静态目标",
);
assert.equal(doubleColumn.objectFamilies.JG_DL_B.active, true);
assert.ok(doubleColumn.objectFamilies.JG_DL_B.readers.length > 0);

const smallWindowPlan = core.buildWindowGuiPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": { boxCount: 2, cabinetCount: 6, relayCount: 2 },
    "COL-B": { boxCount: 10, cabinetCount: 19, relayCount: 2 },
  },
});
assert.deepEqual(smallWindowPlan.totals, {
  boxes: 2,
  cabinets: 6,
  relays: 4,
  temperature_entries: 2,
});
assert.deepEqual(smallWindowPlan.columns["COL-A"].box_buttons.hide, ["A3", "A4", "A5", "A6", "A7", "A8"]);
assert.deepEqual(smallWindowPlan.columns["COL-A"].cabinet_buttons.hide, [
  "A07",
  "A08",
  "A09",
  "A10",
  "A11",
  "A12",
  "A13",
  "A14",
  "A15",
  "A16",
]);
assert.equal(smallWindowPlan.columns["COL-A"].expected_main_window_objects.value, 241);
assert.equal(smallWindowPlan.columns["COL-B"].active, false);
assert.equal(smallWindowPlan.columns["COL-B"].expected_main_window_objects.value, 241);
const smallWindowText = smallWindowPlan.actions.map((item) => item.instruction).join("\n");
assert.equal(smallWindowText, "", "模板容量内的自动裁剪不得进入用户人工清单");
assert.equal(smallWindowPlan.actions.length, 0);
assert.ok(smallWindowPlan.automatic_actions.length > 0);
assert.match(
  smallWindowPlan.release_validation.map((item) => item.instruction).join("\n"),
  /检查2个插接箱、6个机柜、4个中继和2个温升入口/,
);
assert.equal(
  smallWindowPlan.actions.some((item) => item.scope === "COL-B"),
  false,
  "单屏单列不得生成第二物理列人工窗口任务",
);

const expandedWindowPlan = core.buildWindowGuiPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": { boxCount: 10, cabinetCount: 19, relayCount: 2 },
    "COL-B": { boxCount: 0, cabinetCount: 0, relayCount: 0 },
  },
});
assert.deepEqual(expandedWindowPlan.columns["COL-A"].box_buttons.clone, ["A9", "A10"]);
assert.deepEqual(expandedWindowPlan.columns["COL-A"].cabinet_buttons.clone, ["A17", "A18", "A19"]);
assert.equal(expandedWindowPlan.columns["COL-A"].expected_main_window_objects.value, 269);
assert.deepEqual(
  expandedWindowPlan.actions.map((item) => item.module),
  ["第一物理列新增插接箱按钮", "第一物理列新增机柜按钮"],
  "超过模板容量时只列出真正需要新增的控件",
);

const doubleWindowPlan = core.buildWindowGuiPlan({
  hasSecondColumn: true,
  columns: {
    "COL-A": { boxCount: 2, cabinetCount: 6, relayCount: 2 },
    "COL-B": { boxCount: 10, cabinetCount: 7, relayCount: 2 },
  },
});
assert.equal(doubleWindowPlan.columns["COL-B"].active, true);
assert.deepEqual(doubleWindowPlan.columns["COL-B"].box_buttons.clone, ["B7", "B8", "B9", "B10"]);
assert.equal(doubleWindowPlan.columns["COL-B"].expected_main_window_objects.value, 249);
assert.equal(doubleWindowPlan.has_second_column, true);

function programBoxes(count, cabinets = 20, options = {}) {
  return Array.from({ length: count }, (_, index) => {
    const position = index + 1;
    const start = (position - 1) * 3 + 1;
    const route = [start + 2, start + 1, start].map((value) => (value <= cabinets ? value : 0));
    return {
      position,
      typeId: options.typeId || "3x1P",
      windowName: options.windowName || "插接箱",
      routeA: options.routeA?.[position] || route,
      routeB: options.routeB?.[position] || route,
    };
  });
}

function programBoxesSecondColumn(count, cabinets = 20) {
  return Array.from({ length: count }, (_, index) => {
    const position = index + 1;
    const start = (position - 1) * 3 + 1;
    const route = [start, start + 1, start + 2].map((value) => (value <= cabinets ? value : 0));
    return {
      position,
      typeId: "3x1P",
      windowName: "插接箱",
      routeA: route,
      routeB: route,
    };
  });
}

const templateDiff = core.buildProgramDiffPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": {
      boxCount: 7,
      cabinetCount: 20,
      boxes: programBoxes(7, 20),
    },
  },
});
assert.equal(templateDiff.backend_needs_change, false);
assert.deepEqual(templateDiff.open_strategies, []);
assert.deepEqual(templateDiff.window.box_buttons, []);
assert.deepEqual(
  templateDiff.window.cabinet_buttons.map((item) => item.cabinet),
  [17, 18, 19, 20],
  "模板后台支持20柜，但主系统图只预置16个机柜按钮，超出的4个仍需新增",
);

const reducedDiff = core.buildProgramDiffPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": {
      boxCount: 1,
      cabinetCount: 3,
      boxes: programBoxes(1, 3),
    },
  },
});
assert.equal(reducedDiff.backend_needs_change, true);
assert.deepEqual(reducedDiff.open_strategies, []);
assert.deepEqual(reducedDiff.window.box_buttons, []);
assert.deepEqual(reducedDiff.window.cabinet_buttons, []);

const mixedRouteDiff = core.buildProgramDiffPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": {
      boxCount: 1,
      cabinetCount: 3,
      boxes: programBoxes(1, 3, {
        windowName: "插接箱_AB路不同",
        routeB: { 1: [1, 2, 3] },
      }),
    },
  },
});
assert.equal(mixedRouteDiff.backend_needs_change, true);
assert.deepEqual(mixedRouteDiff.open_strategies, [{ column: "COL-A", position: 1 }]);
assert.deepEqual(mixedRouteDiff.window.box_buttons, [{ column: "COL-A", position: 1 }]);
assert.equal(mixedRouteDiff.window.cabinet_buttons.length, 3);

const newTypeDiff = core.buildProgramDiffPlan({
  hasSecondColumn: false,
  columns: {
    "COL-A": {
      boxCount: 1,
      cabinetCount: 2,
      boxes: programBoxes(1, 2, {
        typeId: "2x6",
        windowName: "插接箱2X6",
        routeA: { 1: [2, 1] },
        routeB: { 1: [2, 1] },
      }),
    },
  },
});
assert.equal(newTypeDiff.backend_needs_change, true);
assert.deepEqual(newTypeDiff.open_strategies, [{ column: "COL-A", position: 1 }]);
assert.deepEqual(newTypeDiff.window.box_buttons, [{ column: "COL-A", position: 1 }]);
assert.equal(newTypeDiff.window.cabinet_buttons.length, 2);

const doubleTemplateDiff = core.buildProgramDiffPlan({
  hasSecondColumn: true,
  columns: {
    "COL-A": {
      boxCount: 7,
      cabinetCount: 20,
      boxes: programBoxes(7, 20),
    },
    "COL-B": {
      boxCount: 7,
      cabinetCount: 20,
      boxes: programBoxesSecondColumn(7, 20),
    },
  },
});
assert.equal(doubleTemplateDiff.backend_needs_change, false);
assert.deepEqual(doubleTemplateDiff.open_strategies, []);
assert.deepEqual(
  doubleTemplateDiff.window.box_buttons,
  [{ column: "COL-B", position: 7 }],
  "B列第7个箱按钮超过主系统图_B列预置的6个按钮，仍需新增",
);

assert.equal(core.secondLoopRuntimeFlag(1, true), 1);
assert.equal(core.secondLoopRuntimeFlag(2, true), 0);
assert.equal(core.secondLoopRuntimeFlag(2, false), 0);
assert.equal(core.secondLoopRuntimeFlag(null, true), null);

const projectedDualLoop = core.protocolSecondLoopProjection(
  core.buildBoardTopology({
    columnKey: "COL-A",
    boxes: [
      {
        boxPosition: 1,
        slotId: "2x6",
        typeCode: "3P*2",
        layoutPattern: "2",
        boardTemplateIds: ["board_1to6_3phase_dual"],
      },
    ],
    temperatureModes: {
      "COL-A|AB_PAIR|P01|B00": {
        mode: "independent_temperature",
        topologyFingerprint: "2x6|3P*2|2|B00|board_1to6_3phase_dual",
      },
    },
  }).rows,
);
assert.deepEqual(projectedDualLoop, [
  {
    configuration_key: "COL-A|AB_PAIR|P01|B00",
    column: "COL-A",
    box_position: 1,
    board_index: 1,
    board_ordinal: 1,
    temperature_mode: "independent_temperature",
    mode_value: 1,
    object_name: "BK_Branch_list01",
    route_a_board: 101,
    route_b_board: 201,
  },
]);

const completeBundle = {
  delivery_status: { status: "deliverable", ok: true },
  delivery_bundle: {
    status: "complete",
    files: {
      excel: { status: "generated", download: "/download/excel" },
      alarm_code: { status: "generated", download: "/download/alarm" },
      program_upload: { status: "generated", download: "/download/upload" },
    },
  },
  validation: { status: "passed" },
  alarm_codegen: { status: "generated" },
  program_upload: { status: "generated" },
};
assert.deepEqual(core.protocolBundleStatus(completeBundle), { ok: true, issues: [] });
for (const mutate of [
  (value) => { value.delivery_status.ok = false; },
  (value) => { value.delivery_bundle.status = "partial"; },
  (value) => { value.validation.status = "failed"; },
  (value) => { value.alarm_codegen.status = "failed"; },
  (value) => { value.program_upload.status = "failed"; },
  (value) => { delete value.delivery_bundle.files.excel.download; },
  (value) => { delete value.delivery_bundle.files.alarm_code.download; },
  (value) => { delete value.delivery_bundle.files.program_upload.download; },
]) {
  const candidate = JSON.parse(JSON.stringify(completeBundle));
  mutate(candidate);
  assert.equal(core.protocolBundleStatus(candidate).ok, false);
}

const protocolConfig = core.buildProtocolConfig({
  projectName: "单屏单列反序测试",
  projectCode: "WORKFLOW-CORE-001",
  uploadProtocol: "modbus_rtu_forwarder",
  baudRate: 9600,
  stationAddress: 1,
  representativeColumn: {
    label: "第一物理列",
    typeIds: ["3x1P", "3x1P"],
    cabinetCount: 5,
    relayCount: 2,
  },
  customProtocolTypes: {},
});
assert.equal(protocolConfig.workflow_version, "unified_protocol_v1");
assert.equal(protocolConfig.project.name, "单屏单列反序测试");
assert.deepEqual(protocolConfig.routes.A.plug_boxes.sequence, [
  { type_code: "1P*3", count: 2, layout_pattern: "1" },
]);
assert.equal(protocolConfig.extensions.single_cabinet.cabinet_count, 5);
assert.equal(protocolConfig.extensions.repeater.A_count, 2);
assert.equal(protocolConfig.extensions.repeater.B_count, 2);

console.log(
  JSON.stringify({
    status: "pass",
    reverseFillSix: orderedValues(core.reverseFill(sixSlots, 6), sixSlots),
    reverseFillFive: orderedValues(core.reverseFill(sixSlots, 5), sixSlots),
    disabledMasks: [1, 2, 3, 4].map((branch) => core.branchDisabledMask(branch)),
    threePhaseSwitch: core.switchReadAnyExpression("A", "StateC101", [0, 1, 2]),
    initializationClass2Changes: realClass2Patch.changedLines,
    secondColumnPointer: core.cabinetDataPointer("B", 7),
    singleColumnJgDlBActive: singleColumn.objectFamilies.JG_DL_B.active,
    alarmSelectorReverse: core.alarmSelectorPermutation([1, 2, 3], [3, 2, 1]),
    alarmChangedLines: alarmPatch.changedLines,
    protocolSequence: protocolConfig.routes.A.plug_boxes.sequence,
    smallWindowTotals: smallWindowPlan.totals,
    expandedMainWindowObjects: expandedWindowPlan.columns["COL-A"].expected_main_window_objects.value,
  }),
);
