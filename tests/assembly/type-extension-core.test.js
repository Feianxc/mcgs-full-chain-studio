"use strict";

const assert = require("node:assert/strict");
global.window = global;
require("../../assembly_studio/static/type-extension-data.js");
require("../../assembly_studio/static/type-extension-refresh-data.js");
const core = require("../../assembly_studio/static/type-extension-core.js");

const sources = {
  ...global.MCGS_TYPE_EXTENSION_SOURCES.sources,
  ...global.MCGS_TYPE_EXTENSION_REFRESH_SOURCES.sources,
};
const target = {
  typeCode: "3P*2",
  layoutPattern: "2",
  boardCount: 1,
  branchCount: 2,
};

const single = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target,
  positions: [
    { column: "COL-A", position: 1 },
    { column: "COL-A", position: 2 },
  ],
  sources,
});

assert.equal(single.status, "ready", JSON.stringify(single.blockedActions));
assert.equal(single.blockedActions.length, 0);
assert.equal(single.manualActions.length, 14);
assert.equal(new Set(single.manualActions.map((item) => item.id)).size, single.manualActions.length);
assert.equal(single.manualActions.some((item) => item.targetColumns?.includes("COL-B")), false);
for (const action of single.manualActions) {
  if (action.patchedContent) {
    assert.doesNotMatch(action.patchedContent, /\$[1-9]/, `${action.id}含未展开的替换捕获组`);
  }
  const visibleMetadata = [action.title, action.location, action.instruction, action.content]
    .filter(Boolean)
    .join("\n");
  assert.doesNotMatch(
    visibleMetadata,
    /Class6|COL-B|第二物理列/,
    `${action.id}向单屏单列用户泄露了第二物理列内部信息`,
  );
}

const loadA = single.manualActions.find((item) => item.id === "TYPE-LOAD-A");
assert.ok(loadA?.patchedContent);
assert.equal((loadA.patchedContent.match(/BK_Count\s*=\s*2/g) || []).length, 0);
assert.equal((loadA.patchedContent.match(/一块一拖六双回路板/g) || []).length, 33);
assert.equal((loadA.patchedContent.match(/仍有第二回路/g) || []).length, 33);

const switchA = single.manualActions.find((item) => item.id === "TYPE-SWITCH-A");
assert.equal((switchA.patchedContent.match(/CJX_Class2,m\)\s*AND\s*\(\s*y\s*=\s*3/g) || []).length, 32);
assert.equal((switchA.patchedContent.match(/CJX_Class4,m\)\s*AND\s*\(\s*y\s*=\s*5/g) || []).length, 32);
assert.equal((switchA.patchedContent.match(/CJX_Class4,m\)\s*AND\s*\(\s*y\s*=\s*3/g) || []).length, 0);

const descriptionA = single.manualActions.find((item) => item.id === "TYPE-DESCRIPTION-A");
assert.equal((descriptionA.patchedContent.match(/IF\s+n\s*=\s*2\s+THEN/g) || []).length, 33);
assert.equal((descriptionA.patchedContent.match(/IF\s+n\s*=\s*4\s+THEN/g) || []).length, 0);

const normalWindowAction = single.manualActions.find((item) => item.id === "TYPE-WINDOW-NORMAL");
assert.ok(normalWindowAction?.guiOperations?.includes("隐藏控件92、控件23（第二板位图）"));

const refreshAutoSingle = single.manualActions.find((item) => item.id === "TYPE-REFRESH-LIMIT-AUTO");
const refreshManualSingle = single.manualActions.find((item) => item.id === "TYPE-REFRESH-LIMIT-MANUAL");
assert.ok(refreshAutoSingle?.patchedContent);
assert.ok(refreshManualSingle?.patchedContent);
assert.equal(refreshAutoSingle.patchedContent, refreshManualSingle.patchedContent);
assert.match(
  refreshAutoSingle.patchedContent,
  /IF !BitTest\(CJX_Class2,Number_str-1\) THEN[\s\S]*?Branch_number = 2[\s\S]*?Exsist_2 = 2[\s\S]*?ALM_Branch = 2[\s\S]*?控件126\.Visible = 1[\s\S]*?ALM_Branch = 6[\s\S]*?控件196\.Visible = 1/,
);
assert.match(
  refreshAutoSingle.patchedContent,
  /IF !BitTest\(CJX_Class6,Number_str-1\) THEN[\s\S]*?Branch_number = 4[\s\S]*?Exsist_2 = 10/,
);
assert.deepEqual(refreshAutoSingle.targetColumns, ["COL-A"]);

const double = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: true,
  target,
  positions: [
    { column: "COL-A", position: 25 },
    { column: "COL-B", position: 25 },
  ],
  sources,
});

assert.equal(double.status, "ready", JSON.stringify(double.blockedActions));
assert.equal(double.blockedActions.length, 0);
assert.equal(double.manualActions.length, 21);
assert.equal(new Set(double.manualActions.map((item) => item.id)).size, double.manualActions.length);
assert.ok(double.manualActions.some((item) => item.id === "TYPE-SWITCH-B"));
assert.ok(double.manualActions.some((item) => item.id === "TYPE-TEMP25-AA"));
assert.ok(double.manualActions.some((item) => item.id === "TYPE-TEMP25-BB"));

const bulk = double.manualActions.find((item) => item.id === "TYPE-ALARM-LIMIT-BULK");
assert.match(bulk.patchedContent, /CJX_Class6,n\)\s*>\s*0/);
assert.match(bulk.patchedContent, /\(CJX_Class2 > 0\) OR \(CJX_Class6 > 0\)/);
assert.equal((bulk.patchedContent.match(/第二回路也是3相/g) || []).length, 4);

const power = double.manualActions.find((item) => item.id === "TYPE-POWER-LIMIT");
assert.equal(power.changedCount, 4);
assert.match(power.patchedContent, /CJX_Class2/);
assert.match(power.patchedContent, /CJX_Class6/);
assert.equal((power.patchedContent.match(/\bn\s*=\s*6\b/g) || []).length, 0);

const energy = double.manualActions.find((item) => item.id === "TYPE-ENERGY-RESET");
assert.equal(
  energy.patchedContent.startsWith("IF slaveAddr_E < 100 THEN"),
  true,
  "电量归零完整代码必须从可读MCGS正文开始，不能携带二进制前缀",
);
assert.doesNotMatch(energy.patchedContent, /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/);
assert.match(energy.patchedContent, /CJX_Class2[\s\S]*?控件17\.Visible = 0[\s\S]*?E_BK_String = "板卡1"/);
assert.match(energy.patchedContent, /CJX_Class6[\s\S]*?控件17\.Visible = 0[\s\S]*?E_BK_String = "板卡1"/);

const switchB = double.manualActions.find((item) => item.id === "TYPE-SWITCH-B");
assert.equal((switchB.patchedContent.match(/CJX_Class8,m\)\s*AND\s*\(\s*y\s*=\s*5/g) || []).length, 32);
assert.equal((switchB.patchedContent.match(/CJX_Class8,m\)\s*AND\s*\(\s*y\s*=\s*3/g) || []).length, 0);

const refreshAutoDouble = double.manualActions.find((item) => item.id === "TYPE-REFRESH-LIMIT-AUTO");
const refreshManualDouble = double.manualActions.find((item) => item.id === "TYPE-REFRESH-LIMIT-MANUAL");
for (const action of [refreshAutoDouble, refreshManualDouble]) {
  assert.ok(action?.patchedContent);
  assert.equal((action.patchedContent.match(/Branch_number = 2/g) || []).length, 2);
  assert.equal((action.patchedContent.match(/Exsist_2 = 2/g) || []).length, 2);
  assert.match(
    action.patchedContent,
    /IF !BitTest\(CJX_Class6,Number_str-1\) THEN[\s\S]*?ALM_Branch = 2[\s\S]*?控件126\.Visible = 1[\s\S]*?ALM_Branch = 6[\s\S]*?控件196\.Visible = 1/,
  );
  assert.doesNotMatch(action.patchedContent, /\bClass2\/Class6\b/);
}

for (const id of ["TYPE-TEMP25-AA", "TYPE-TEMP25-AB", "TYPE-TEMP25-BA", "TYPE-TEMP25-BB"]) {
  const action = double.manualActions.find((item) => item.id === id);
  assert.ok(action?.patchedContent, id);
  assert.doesNotMatch(action.patchedContent.slice(action.patchedContent.indexOf("'以下代码与布局类型有关")), /2\*6P插接箱\(比较1次\)/);
}

const unsupported = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target: { typeCode: "3P*4", layoutPattern: "2+2", boardCount: 2, branchCount: 4 },
  positions: [{ column: "COL-A", position: 1 }],
  sources,
});
assert.equal(unsupported.status, "blocked");
assert.equal(unsupported.manualActions.length, 0);
assert.equal(unsupported.blockedActions.length, 1);

const missingSource = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target,
  positions: [{ column: "COL-A", position: 1 }],
  sources: {},
});
assert.equal(missingSource.status, "partial");
assert.ok(missingSource.blockedActions.length >= 8);

const emptySources = structuredClone(sources);
emptySources.switchAlarmA.content = "";
const emptySource = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target,
  positions: [{ column: "COL-A", position: 1 }],
  sources: emptySources,
});
assert.equal(emptySource.status, "partial");
assert.ok(emptySource.blockedActions.some((item) => item.id === "TYPE-SWITCH-A"));

const wrongCountSources = structuredClone(sources);
wrongCountSources.alarmDescriptionA.content = wrongCountSources.alarmDescriptionA.content.replace(
  /^([ \t]*)IF\s+n\s*=\s*4\s+THEN\s*$/m,
  "$1IF n = 5 THEN",
);
const wrongCount = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target,
  positions: [{ column: "COL-A", position: 1 }],
  sources: wrongCountSources,
});
assert.equal(wrongCount.status, "partial");
assert.ok(
  wrongCount.blockedActions.some(
    (item) => item.id === "TYPE-DESCRIPTION-A" && /预期命中33处，实际32处/.test(item.reason),
  ),
);

const wrongClassSources = structuredClone(sources);
wrongClassSources.alarmDescriptionA.content = wrongClassSources.alarmDescriptionA.content.replace(
  /IF\s+!BitTest\(CJX_Class2,m\)\s+THEN/g,
  "IF !BitTest(CJX_Class3,m) THEN",
);
const wrongClass = core.buildTypeExtensionActions({
  slotId: "2x6",
  hasSecondColumn: false,
  target,
  positions: [{ column: "COL-A", position: 1 }],
  sources: wrongClassSources,
});
assert.equal(wrongClass.status, "partial");
assert.ok(
  wrongClass.blockedActions.some(
    (item) => item.id === "TYPE-DESCRIPTION-A" && /拒绝按Class2修改/.test(item.reason),
  ),
);

console.log(
  JSON.stringify({
    status: "pass",
    singleActions: single.manualActions.length,
    doubleActions: double.manualActions.length,
    doubleBlocked: double.blockedActions.length,
    switchAChanges: switchA.changedCount,
  }),
);
