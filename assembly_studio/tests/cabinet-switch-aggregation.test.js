"use strict";

const assert = require("node:assert/strict");
const core = require("../static/workflow-core.js");

const threePhaseSameCabinet = [
  { cabinetIndex: 1, objectName: "StateC101", bitNos: [0] },
  { cabinetIndex: 1, objectName: "StateC101", bitNos: [1] },
  { cabinetIndex: 1, objectName: "StateC101", bitNos: [2] },
];
assert.deepEqual(core.aggregateCabinetSwitchExpressions("A", threePhaseSameCabinet), {
  1: "!BitTest(StateC101,0) OR !BitTest(StateC101,1) OR !BitTest(StateC101,2)",
});
assert.deepEqual(
  core.aggregateCabinetSwitchExpressions(
    "A",
    threePhaseSameCabinet.map((item) => ({ ...item, objectName: "StateC201" })),
  ),
  {
    1: "!BitTest(StateC201,0) OR !BitTest(StateC201,1) OR !BitTest(StateC201,2)",
  },
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
);

assert.deepEqual(
  core.aggregateCabinetSwitchExpressions("A", [
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [0, 0, 1] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [1, 2] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [2] },
  ]),
  {
    1: "!BitTest(StateC101,0) OR !BitTest(StateC101,1) OR !BitTest(StateC101,2)",
  },
);

assert.deepEqual(
  core.aggregateCabinetSwitchExpressions("A", [
    { cabinetIndex: 0, objectName: "StateC101", bitNos: [0, 1, 2] },
    { cabinetIndex: 1, objectName: "StateC101", bitNos: [0] },
  ]),
  { 1: "!BitTest(StateC101,0)" },
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
assert.equal(core.cabinetCoverageStatus([1, 2, 3], 3, true).valid, true);
assert.deepEqual(core.cabinetCoverageStatus([0, 1, 1], 2, true).missing, [2]);
assert.equal(core.cabinetCoverageStatus([0, 1, 1], 2, true).valid, false);

console.log(
  JSON.stringify({
    status: "pass",
    cases: [
      "three_phase_same_cabinet",
      "three_phase_different_cabinets",
      "duplicate_bits_deduplicated",
      "spare_ignored",
      "unique_cabinet_coverage",
    ],
  }),
);
