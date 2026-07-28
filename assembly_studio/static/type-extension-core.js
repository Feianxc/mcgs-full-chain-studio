(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MCGS_TYPE_EXTENSION_CORE = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SCHEMA_VERSION = "mcgs-type-extension-plan/1.0";

  function normalizedText(value) {
    const content = value && typeof value === "object" ? value.content : value;
    if (typeof content !== "string" || !content.length) return null;
    return content.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  }

  function sourceEvidence(record) {
    return record && typeof record === "object"
      ? {
          path: String(record.path || ""),
          sha256: String(record.sha256 || ""),
          lines: Number(record.lines) || 0,
        }
      : { path: "", sha256: "", lines: 0 };
  }

  function replaceExact(text, regex, replacement, expected, label) {
    const countRegex = new RegExp(
      regex.source,
      regex.flags.includes("g") ? regex.flags : `${regex.flags}g`,
    );
    const count = Array.from(text.matchAll(countRegex)).length;
    if (count !== expected) {
      throw new Error(`${label}预期命中${expected}处，实际${count}处`);
    }
    return { text: text.replace(regex, replacement), count };
  }

  function patchLoadStatus(text) {
    const first = replaceExact(
      text,
      /^([ \t]*)BK_Count\s*=\s*2[^\n]*$/gm,
      "$1BK_Count = 1    '一块一拖六双回路板",
      33,
      "BK_Count",
    );
    const second = replaceExact(
      first.text,
      /^([ \t]*)IsClass2\s*=\s*1[^\n]*$/gm,
      "$1IsClass2 = 1    '仍有第二回路",
      33,
      "IsClass2",
    );
    return { text: second.text, count: first.count + second.count };
  }

  function patchSwitchAlarm(text, classNo) {
    const regex = new RegExp(
      `(!BitTest\\(CJX_Class${classNo},m\\)\\s*AND\\s*\\(\\s*y\\s*=\\s*)5(\\s*\\))`,
      "g",
    );
    return replaceExact(
      text,
      regex,
      (whole, prefix, suffix) => `${prefix}3${suffix}`,
      32,
      `Class${classNo}分合闸边界`,
    );
  }

  function patchAlarmDescription(text, classNo) {
    const boundary = /^([ \t]*)IF\s+n\s*=\s*4\s+THEN\s*$/gm;
    const matches = Array.from(text.matchAll(boundary));
    if (matches.length !== 33) {
      throw new Error(`Class${classNo}报警描述结束条件预期命中33处，实际${matches.length}处`);
    }
    for (const match of matches) {
      const context = text.slice(Math.max(0, match.index - 12000), match.index);
      const markers = Array.from(
        context.matchAll(/IF\s+!BitTest\(CJX_Class(\d+),m\)\s+THEN/g),
      );
      const activeClass = Number(markers.at(-1)?.[1]);
      if (activeClass !== Number(classNo)) {
        throw new Error(
          `报警描述第${match.index}字符处属于Class${activeClass || "未知"}，拒绝按Class${classNo}修改`,
        );
      }
    }
    const result = replaceExact(
      text,
      boundary,
      "$1IF n = 2 THEN",
      33,
      `Class${classNo}报警描述结束条件`,
    );
    return result;
  }

  function patchInlineClassCount(text, classNo) {
    const regex = new RegExp(
      `(IF\\s+!BitTest\\(CJX_Class${classNo},m\\)\\s+THEN\\s*)n\\s*=\\s*6`,
      "g",
    );
    return replaceExact(text, regex, "$1n = 3", 1, `Class${classNo}基础回路数量`);
  }

  function patchNextCount(text, classNo, comparison) {
    const suffix = comparison ? "\\s*>\\s*0" : "";
    const regex = new RegExp(
      `(IF\\s+!BitTest\\(CJX_Class${classNo},m\\)${suffix}\\s+THEN[\\s\\S]*?\\bn\\s*=\\s*)6`,
      "g",
    );
    return replaceExact(
      text,
      regex,
      (whole, prefix) => `${prefix}3`,
      1,
      `Class${classNo}第二回路数量`,
    );
  }

  function patchCurrentLimit(text, useA, useB) {
    let result = text;
    let count = 0;
    if (useA) {
      const patched = patchInlineClassCount(result, 2);
      result = patched.text;
      count += patched.count;
    }
    if (useB) {
      const patched = patchInlineClassCount(result, 6);
      result = patched.text;
      count += patched.count;
    }
    return { text: result, count };
  }

  function patchSecondLoopLimit(text, useA, useB) {
    let result = text;
    let count = 0;
    if (useA) {
      const patched = patchNextCount(result, 2, false);
      result = patched.text;
      count += patched.count;
    }
    if (useB) {
      const patched = patchNextCount(result, 6, false);
      result = patched.text;
      count += patched.count;
    }
    return { text: result, count };
  }

  function patchPowerLimit(text, useA, useB) {
    let result = text;
    let count = 0;
    for (const classNo of [useA ? 2 : null, useB ? 6 : null].filter(Boolean)) {
      const first = patchInlineClassCount(result, classNo);
      const second = patchNextCount(first.text, classNo, true);
      result = second.text;
      count += first.count + second.count;
    }
    return { text: result, count };
  }

  function mapIfBlocks(text, marker, transform) {
    const lines = text.split("\n");
    let matched = 0;
    let changed = 0;
    for (let index = 0; index < lines.length; index += 1) {
      if (!marker.test(lines[index])) continue;
      marker.lastIndex = 0;
      let depth = 1;
      let end = index + 1;
      for (; end < lines.length; end += 1) {
        const trimmed = lines[end].trim();
        if (/^IF\b.*\bTHEN\s*$/i.test(trimmed)) depth += 1;
        if (/^ENDIF\s*$/i.test(trimmed)) {
          depth -= 1;
          if (depth === 0) break;
        }
      }
      if (depth !== 0) throw new Error(`从第${index + 1}行开始的IF块没有找到对应ENDIF`);
      const original = lines.slice(index, end + 1).join("\n");
      const next = transform(original);
      if (next !== null && next !== original) {
        lines.splice(index, end - index + 1, ...next.split("\n"));
        end = index + next.split("\n").length - 1;
        matched += 1;
        changed += 1;
      }
      index = end;
    }
    return { text: lines.join("\n"), matched, changed };
  }

  function patchAlarmLimitBulk(text, useA, useB) {
    let result = text;
    let changeCount = 0;
    if (useA) {
      const blocks = mapIfBlocks(
        result,
        /^\s*IF\s+!BitTest\(CJX_Class2,n\)\s*>\s*0\s+THEN\s*$/i,
        (block) => {
          if (!/pointer(?:_2)?\s*=.*-\s*6/i.test(block)) return null;
          let next = block.replace(/WHILE\s*\(\s*x\s*<\s*6\s*\)/g, "WHILE (x < 3)");
          next = next.replace(/(pointer(?:_2)?\s*=.*-\s*)6/g, (whole, prefix) => `${prefix}3`);
          next = next.replace(/第二回路也是6相/g, "第二回路也是3相");
          return next;
        },
      );
      if (blocks.matched !== 2) throw new Error(`A列报警批量限值预期2个Class2块，实际${blocks.matched}个`);
      result = blocks.text;
      changeCount += 6;
    }
    if (useB) {
      const blocks = mapIfBlocks(
        result,
        /^\s*IF\s+!BitTest\(CJX_Class7,n\)\s*>\s*0\s+THEN\s*$/i,
        (block) => {
          if (!/pointer_B_2\s*=.*-\s*6/i.test(block)) return null;
          let next = block.replace(/CJX_Class7/g, "CJX_Class6");
          next = next.replace(/WHILE\s*\(\s*x\s*<\s*6\s*\)/g, "WHILE (x < 3)");
          next = next.replace(/(pointer_B_2\s*=.*-\s*)6/g, (whole, prefix) => `${prefix}3`);
          next = next.replace(/第二回路也是6相/g, "第二回路也是3相");
          return next;
        },
      );
      if (blocks.matched !== 2) throw new Error(`B列报警批量限值预期2个旧Class7块，实际${blocks.matched}个`);
      result = blocks.text;
      changeCount += 8;
      const gate = replaceExact(
        result,
        /^([ \t]*)IF\s+CJX_Class2\s*>\s*0\s+THEN\s*$/m,
        "$1IF (CJX_Class2 > 0) OR (CJX_Class6 > 0) THEN",
        1,
        "第二回路限值总门",
      );
      result = gate.text;
      changeCount += gate.count;
    }
    return { text: result, count: changeCount };
  }

  function patchLimitSaveButton(text, useA, useB) {
    let result = text;
    let count = 0;
    for (const classNo of [useA ? 2 : null, useB ? 6 : null].filter(Boolean)) {
      const regex = new RegExp(
        `(IF\\s+!BitTest\\(CJX_Class${classNo},Number_str-1\\)\\s+THEN[\\s\\S]*?)(ENDIF)`,
        "g",
      );
      const patched = replaceExact(
        result,
        regex,
        (whole, body, end) => {
          const branchHits = (body.match(/Branch_number\s*=\s*4/g) || []).length;
          const secondHits = (body.match(/Exsist_2\s*=\s*10/g) || []).length;
          if (branchHits !== 1 || secondHits !== 1) {
            throw new Error(`Class${classNo}限值保存块参数数量异常`);
          }
          return (
            body
              .replace(/Branch_number\s*=\s*4[^\n]*/, "Branch_number = 2    '两组三相输出")
              .replace(/Exsist_2\s*=\s*10[^\n]*/, "Exsist_2 = 2         '二进制10，仅分路2来自第二回路") + end
          );
        },
        1,
        `Class${classNo}限值保存按钮`,
      );
      result = patched.text;
      count += 2;
    }
    return { text: result, count };
  }

  function refreshLimitClassBlock(classNo) {
    return `IF !BitTest(CJX_Class${classNo},Number_str-1) THEN

 Branch_number = 2 '表示有两组三相数据
 Exsist_2 = 2 '二进制Bit1为1，表示分路2数据来自第二回路
 '关闭其它分路表格
 限值设置_新.控件143.Visible = 0 '插接箱三相表格---1
 限值设置_新.控件113.Visible = 0 '插接箱三相表格---3
 限值设置_新.控件42.Visible = 0 '插接箱三相表格---4

 限值设置_新.控件211.Visible = 0 '插接箱温度表格---5
 限值设置_新.控件177.Visible = 0 '插接箱温度表格---7
 限值设置_新.控件160.Visible = 0 '插接箱温度表格---8
IF ID_Number4 <= 6 THEN

 ALM_Branch = 2
 限值设置_新.控件126.Visible = 1 '插接箱三相表格---2
 限值设置_新.控件196.Visible = 0 '插接箱温度表格---6
ELSE
 ALM_Branch = 6
 限值设置_新.控件126.Visible = 0 '插接箱三相表格---2
 限值设置_新.控件196.Visible = 1 '插接箱温度表格---6
ENDIF
ENDIF
`;
  }

  function patchRefreshLimit(text, useA, useB) {
    let result = text;
    let count = 0;
    for (const classNo of [useA ? 2 : null, useB ? 6 : null].filter(Boolean)) {
      const nextClassNo = classNo + 1;
      const regex = new RegExp(
        `IF\\s+!BitTest\\(CJX_Class${classNo},Number_str-1\\)\\s+THEN[\\s\\S]*?(?=IF\\s+!BitTest\\(CJX_Class${nextClassNo},Number_str-1\\)\\s+THEN)`,
        "g",
      );
      const patched = replaceExact(
        result,
        regex,
        refreshLimitClassBlock(classNo),
        1,
        `Class${classNo}刷新限值表格`,
      );
      result = patched.text;
      count += patched.count;
    }
    return { text: result, count };
  }

  function patchEnterParameters(text, useB) {
    let result = text;
    if (useB) {
      result = replaceExact(
        result,
        /^([ \t]*)IF\s+CJX_Class2\s*>\s*0\s+THEN\s*$/m,
        "$1IF (CJX_Class2 > 0) OR (CJX_Class6 > 0) THEN",
        1,
        "参数页类型入口",
      ).text;
    }
    const labels = replaceExact(
      result,
      /"4\*3P\(两板卡\)"/g,
      '"3P*2(一块一拖六双回路板)"',
      2,
      "类型显示名称",
    );
    return { text: labels.text, count: labels.count + (useB ? 1 : 0) };
  }

  function patchEnergyReset(text, useA, useB) {
    const readableStart = text.indexOf("IF slaveAddr_E < 100 THEN");
    if (readableStart < 0) {
      throw new Error("电量归零源脚本未找到可读正文起点");
    }
    let result = text.slice(readableStart);
    let count = 0;
    for (const classNo of [useA ? 2 : null, useB ? 6 : null].filter(Boolean)) {
      const regex = new RegExp(
        `(^[ \\t]*IF\\s+!BitTest\\(CJX_Class${classNo},E_pointer-1\\)\\s+THEN\\s*$)[\\s\\S]*?^[ \\t]*ENDIF\\s*$`,
        "m",
      );
      const patched = replaceExact(
        result,
        regex,
        (whole, firstLine) => {
          const indent = (firstLine.match(/^[ \t]*/) || [""])[0];
          return [
            firstLine,
            `${indent}\t电量归零.控件17.Visible = 0`,
            `${indent}\tE_BK_String = "板卡1"`,
            `${indent}\tEXIT`,
            `${indent}ENDIF`,
          ].join("\n");
        },
        1,
        `Class${classNo}电量归零`,
      );
      result = patched.text;
      count += 1;
    }
    return { text: result, count };
  }

  function patchTemperature25(text) {
    const lines = text.split("\n");
    const indexes = [];
    for (let index = 0; index < lines.length; index += 1) {
      if (lines[index].includes("'2*6P插接箱(比较1次)")) indexes.push(index);
    }
    if (indexes.length !== 1) throw new Error(`第25箱2*6P尾段预期1处，实际${indexes.length}处`);
    const index = indexes[0];
    if (!/GroupGetFloat/.test(lines[index + 1] || "") || !/\+\s*1\s*-/.test(lines[index + 1] || "")) {
      throw new Error("第25箱下一板读取行不符合预期");
    }
    if (!/IF\s+TCJX_temp\s*>\s*x\s+THEN\s+x\s*=\s*TCJX_temp/.test(lines[index + 2] || "")) {
      throw new Error("第25箱温度比较行不符合预期");
    }
    const indent = (lines[index].match(/^[ \t]*/) || [""])[0];
    lines.splice(index, 3, `${indent}'3P*2插接箱，一块一拖六双回路板，无需读取下一块板`);
    return { text: lines.join("\n"), count: 2 };
  }

  function buildTypeExtensionActions(input = {}) {
    const sources = input.sources || {};
    const positions = Array.isArray(input.positions) ? input.positions : [];
    const target = input.target || {};
    const useA = positions.some((item) => item.column === "COL-A");
    const useB = Boolean(input.hasSecondColumn) && positions.some((item) => item.column === "COL-B");
    const manualActions = [];
    const blockedActions = [];

    const targetSupported =
      String(input.slotId || "2x6") === "2x6" &&
      String(target.typeCode || "3P*2") === "3P*2" &&
      String(target.layoutPattern || "2") === "2" &&
      Number(target.boardCount ?? 1) === 1 &&
      Number(target.branchCount ?? 2) === 2;

    if (!targetSupported) {
      return {
        schemaVersion: SCHEMA_VERSION,
        status: "blocked",
        manualActions,
        blockedActions: [
          {
            id: "TYPE-UNSUPPORTED",
            title: "当前箱型组合还没有经过模板专项验证",
            location: "箱型调整",
            reason: "系统只会输出经过真实脚本逐项校验的修改稿，不用通用替换冒充完整成果。",
          },
        ],
        sourceEvidence: [],
      };
    }

    if (!useA && !useB) {
      return {
        schemaVersion: SCHEMA_VERSION,
        status: "not_applicable",
        manualActions,
        blockedActions,
        sourceEvidence: [],
      };
    }

    const addPatched = (spec) => {
      const record = sources[spec.sourceKey];
      const text = normalizedText(record);
      if (text === null) {
        blockedActions.push({
          id: spec.id,
          title: spec.title,
          location: spec.location,
          reason: `缺少可验证的源脚本：${spec.sourceKey}`,
          sourceKey: spec.sourceKey,
        });
        return;
      }
      try {
        const patched = spec.patch(text);
        manualActions.push({
          id: spec.id,
          category: spec.category,
          title: spec.title,
          location: spec.location,
          instruction: spec.instruction,
          sourceKey: spec.sourceKey,
          changedCount: patched.count,
          patchedContent: patched.text,
          targetColumns: [...spec.targetColumns],
          sourceEvidence: sourceEvidence(record),
        });
      } catch (error) {
        blockedActions.push({
          id: spec.id,
          title: spec.title,
          location: spec.location,
          reason: String(error.message || error),
          sourceKey: spec.sourceKey,
          sourceEvidence: sourceEvidence(record),
        });
      }
    };

    const activeColumns = [useA ? "COL-A" : null, useB ? "COL-B" : null].filter(Boolean);
    if (useA) {
      addPatched({
        id: "TYPE-LOAD-A",
        category: "运行策略",
        title: "第一物理列判断负载状态",
        location: "运行策略 → 判断负载状态 → 脚本01 第Ⅰ列",
        instruction: "整段替换。板卡数改为1，但IsClass2仍保持1，使第二回路继续参与判断。",
        sourceKey: "loadStatusA",
        targetColumns: ["COL-A"],
        patch: patchLoadStatus,
      });
      addPatched({
        id: "TYPE-SWITCH-A",
        category: "报警",
        title: "第一物理列分合闸报警",
        location: "运行策略 → 修改机柜号及报警 → 脚本03",
        instruction: "使用完整长脚本整段替换，只把Class2的输出边界由5改为3。",
        sourceKey: "switchAlarmA",
        targetColumns: ["COL-A"],
        patch: (text) => patchSwitchAlarm(text, 2),
      });
      addPatched({
        id: "TYPE-DESCRIPTION-A",
        category: "报警",
        title: "第一物理列报警描述",
        location: "运行策略 → 修改机柜号及报警 → 脚本05",
        instruction: "使用完整长脚本整段替换，Class2每箱在2个输出后结束。",
        sourceKey: "alarmDescriptionA",
        targetColumns: ["COL-A"],
        patch: (text) => patchAlarmDescription(text, 2),
      });
    }
    if (useB) {
      addPatched({
        id: "TYPE-LOAD-B",
        category: "运行策略",
        title: "第二物理列判断负载状态",
        location: "运行策略 → 判断负载状态 → 脚本02 第Ⅱ列",
        instruction: "整段替换。板卡数改为1，但IsClass2仍保持1，使第二回路继续参与判断。",
        sourceKey: "loadStatusB",
        targetColumns: ["COL-B"],
        patch: patchLoadStatus,
      });
      addPatched({
        id: "TYPE-SWITCH-B",
        category: "报警",
        title: "第二物理列分合闸报警",
        location: "运行策略 → 修改机柜号及报警 → 脚本04",
        instruction: "使用完整长脚本整段替换，只把Class6的输出边界由5改为3。",
        sourceKey: "switchAlarmB",
        targetColumns: ["COL-B"],
        patch: (text) => patchSwitchAlarm(text, 6),
      });
      addPatched({
        id: "TYPE-DESCRIPTION-B",
        category: "报警",
        title: "第二物理列报警描述",
        location: "运行策略 → 修改机柜号及报警 → 脚本06",
        instruction: "使用完整长脚本整段替换，Class6每箱在2个输出后结束。",
        sourceKey: "alarmDescriptionB",
        targetColumns: ["COL-B"],
        patch: (text) => patchAlarmDescription(text, 6),
      });
    }

    addPatched({
      id: "TYPE-ALARM-LIMIT-BULK",
      category: "报警限值",
      title: "批量报警限值",
      location: "运行策略 → 修改报警限值 → 脚本01",
      instruction: useB
        ? "整段替换。Class2/Class6改为每回路3相，并同时修正B列旧Class7误写和第二回路入口。"
        : "整段替换。Class2改为每回路3相，其他类型保持原样。",
      sourceKey: "alarmLimitBulk",
      targetColumns: activeColumns,
      patch: (text) => patchAlarmLimitBulk(text, useA, useB),
    });
    addPatched({
      id: "TYPE-CURRENT-LIMIT",
      category: "报警限值",
      title: "插接箱电流上限",
      location: "运行策略 → 修改报警限值 → 脚本04",
      instruction: "整段替换。目标Class由6个相变量改为3个相变量。",
      sourceKey: "alarmCurrentLimit",
      targetColumns: activeColumns,
      patch: (text) => patchCurrentLimit(text, useA, useB),
    });
    addPatched({
      id: "TYPE-SECOND-LOOP-LIMIT",
      category: "报警限值",
      title: "第二回路功率因数和电压限值",
      location: "运行策略 → 修改报警限值 → 脚本07",
      instruction: "整段替换。每个双回路板只遍历3个相变量。",
      sourceKey: "alarmSecondLoopLimit",
      targetColumns: activeColumns,
      patch: (text) => patchSecondLoopLimit(text, useA, useB),
    });
    addPatched({
      id: "TYPE-POWER-LIMIT",
      category: "报警限值",
      title: "功率报警上限",
      location: "运行策略 → 修改功率报警限值 → 脚本01",
      instruction: "整段替换。基础回路和第二回路都按3个相变量遍历。",
      sourceKey: "powerLimit",
      targetColumns: activeColumns,
      patch: (text) => patchPowerLimit(text, useA, useB),
    });
    addPatched({
      id: "TYPE-LIMIT-SAVE",
      category: "用户窗口",
      title: "限值设置保存按钮",
      location: "用户窗口 → 限值设置_新 → 控件204 → 保存动作",
      instruction: "整段替换。目标Class只显示2个输出，第二个输出读取第二回路。",
      sourceKey: "limitSaveButton",
      targetColumns: activeColumns,
      patch: (text) => patchLimitSaveButton(text, useA, useB),
    });
    addPatched({
      id: "TYPE-ENTER-PARAMETERS",
      category: "运行策略",
      title: "参数页箱型名称",
      location: "运行策略 → 进入参数设置 → 脚本01",
      instruction: `整段替换。限值设置列表显示3P*2一块一拖六；${useB ? "Class2和Class6都可触发该类型" : "由Class2触发该类型"}。`,
      sourceKey: "enterParameters",
      targetColumns: activeColumns,
      patch: (text) => patchEnterParameters(text, useB),
    });
    addPatched({
      id: "TYPE-ENERGY-RESET",
      category: "运行策略",
      title: "电量归零板卡选择",
      location: "运行策略 → 电量归零显示框 → 脚本01",
      instruction: "整段替换。目标Class只有板卡1，隐藏板卡下拉框。",
      sourceKey: "energyReset",
      targetColumns: activeColumns,
      patch: (text) => patchEnergyReset(text, useA, useB),
    });

    addPatched({
      id: "TYPE-REFRESH-LIMIT-AUTO",
      category: "运行策略",
      title: "自动刷新限值设置表格",
      location: "运行策略 → 刷新限值设置表格 → 脚本01",
      instruction: `整段替换。${useB ? "Class2和Class6" : "Class2"}只显示2个输出，分路2读取第二回路。`,
      sourceKey: "refreshLimit",
      targetColumns: activeColumns,
      patch: (text) => patchRefreshLimit(text, useA, useB),
    });
    addPatched({
      id: "TYPE-REFRESH-LIMIT-MANUAL",
      category: "运行策略",
      title: "手动刷新限值设置表格",
      location: "运行策略 → 刷新限值设置表格_手动调用 → 脚本01",
      instruction: `整段替换。${useB ? "Class2和Class6" : "Class2"}与自动刷新策略保持完全相同的2输出表格逻辑。`,
      sourceKey: "refreshLimitManual",
      targetColumns: activeColumns,
      patch: (text) => patchRefreshLimit(text, useA, useB),
    });

    manualActions.push({
      id: "TYPE-WINDOW-NORMAL",
      category: "用户窗口",
      title: "裁剪普通插接箱窗口",
      location: "用户窗口 → 插接箱2X6",
      instruction: "保留原窗口名，只保留一块板和两个输出。叠在一起的图形、标签、状态层和透明点击层必须成组处理。",
      targetColumns: activeColumns,
      guiOperations: [
        "保留控件96、97：第一块板的回路1、回路2",
        "隐藏控件98、99：原第二块板的两个输出",
        "隐藏控件92、控件23（第二板位图）",
        "控件85、100内只保留CJXchannelFlag=1、2；隐藏3、4对应的连线、标签、状态层和点击层",
      ],
    });
    manualActions.push({
      id: "TYPE-WINDOW-TEMPERATURE",
      category: "用户窗口",
      title: "裁剪测温插接箱窗口",
      location: "用户窗口 → 插接箱测温2X6",
      instruction: "保留原窗口名，只保留第一块板的两个回路。",
      targetColumns: activeColumns,
      guiOperations: [
        "保留控件16、24：第一块板回路1、回路2",
        "隐藏控件30、36：原第二块板两个回路",
        "隐藏控件13、14、15及第二板区域的图形、连接线、标签和透明点击层",
      ],
    });

    const position25A = useA && positions.some((item) => item.column === "COL-A" && Number(item.position) === 25);
    const position25B = useB && positions.some((item) => item.column === "COL-B" && Number(item.position) === 25);
    for (const spec of [
      position25A ? ["temperature25AA", "TYPE-TEMP25-AA", "运行策略 → 温升柱图最大值获取 → 脚本03"] : null,
      position25A ? ["temperature25AB", "TYPE-TEMP25-AB", "运行策略 → 温升柱图最大值获取 → 脚本04"] : null,
      position25B ? ["temperature25BA", "TYPE-TEMP25-BA", "运行策略 → 温升柱图最大值获取 → 脚本05"] : null,
      position25B ? ["temperature25BB", "TYPE-TEMP25-BB", "运行策略 → 温升柱图最大值获取 → 脚本06"] : null,
    ].filter(Boolean)) {
      addPatched({
        id: spec[1],
        category: "运行策略",
        title: "第25箱温升最大值",
        location: spec[2],
        instruction: "整段替换。第25箱只有一块板，删除读取头板卡+1的两行。",
        sourceKey: spec[0],
        targetColumns: spec[0].includes("25B") ? ["COL-B"] : ["COL-A"],
        patch: patchTemperature25,
      });
    }

    const sourceEvidenceList = manualActions
      .flatMap((item) => (Array.isArray(item.sourceEvidence) ? item.sourceEvidence : item.sourceEvidence ? [item.sourceEvidence] : []))
      .filter((item) => item.path);
    return {
      schemaVersion: SCHEMA_VERSION,
      status: blockedActions.length ? "partial" : "ready",
      manualActions,
      blockedActions,
      sourceEvidence: sourceEvidenceList,
    };
  }

  return Object.freeze({
    SCHEMA_VERSION,
    buildTypeExtensionActions,
    patchAlarmDescription,
    patchAlarmLimitBulk,
    patchCurrentLimit,
    patchEnergyReset,
    patchEnterParameters,
    patchLimitSaveButton,
    patchLoadStatus,
    patchPowerLimit,
    patchRefreshLimit,
    patchSecondLoopLimit,
    patchSwitchAlarm,
    patchTemperature25,
  });
});
