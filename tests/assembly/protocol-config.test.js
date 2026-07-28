"use strict";

const assert = require("node:assert/strict");
const core = require("../../assembly_studio/static/workflow-core.js");

const legacyRtu = core.buildProtocolConfig({
  projectName: "旧调用兼容测试",
  uploadProtocol: "modbus_rtu_forwarder",
  baudRate: 9600,
  stationAddress: 1,
  representativeColumn: {
    typeIds: ["3x1P", "3x1P"],
    cabinetCount: 5,
    relayCount: 2,
  },
});

assert.deepEqual(legacyRtu.program_upload, {
  device_name: "upload",
  driver_component_name: "ModbusRTU上传",
  driver_library_path: "modbuscommslave_str.ui",
  driver_component_version: "7.105",
  encoding: "gb18030",
});
assert.deepEqual(legacyRtu.routes.A.plug_boxes.sequence, [
  { type_code: "1P*3", count: 2, layout_pattern: "1" },
]);
assert.equal(legacyRtu.extensions.single_cabinet.cabinet_count, 5);
assert.deepEqual(
  [legacyRtu.extensions.repeater.A_count, legacyRtu.extensions.repeater.B_count],
  [2, 2],
);
assert.deepEqual(legacyRtu.extensions.second_loop_temperature, []);

const temperatureProjection = [
  {
    column: 2,
    box_position: 3,
    board_index: 1,
    second_loop: true,
    temperature_index: null,
    source_indexes: [7, 8],
  },
];
const tcp = core.buildProtocolConfig({
  projectName: "TCP容量解耦测试",
  uploadProtocol: "modbus_tcpip_forwarder",
  stationAddress: 1,
  protocolColumn: {
    typeIds: ["2x6"],
    cabinetCount: 4,
    relayCount: 1,
  },
  representativeColumn: {
    typeIds: ["3x1P"],
    cabinetCount: 2,
    relayCount: 0,
  },
  maxCabinetCount: 19,
  relayCounts: { A: 1, B: 3 },
  tcpipUpload: {
    listen_port: 1502,
    bind_ip: "192.0.2.10",
    station_address: 7,
  },
  secondLoopTemperature: temperatureProjection,
});

assert.equal(tcp.communication.protocol, "Modbus TCP/IP");
assert.deepEqual(tcp.communication.tcpip_upload, {
  listen_port: 1502,
  bind_ip: "192.0.2.10",
  station_address: 7,
});
assert.equal(tcp.communication.default_screen_address, 7);
assert.deepEqual(tcp.program_upload, {
  device_name: "数据上传_以太网",
  driver_component_name: "modbus_tcpip_forwarder",
  driver_library_path: "modbustcpipslave_str.ui",
  driver_component_version: "7.1.0.12",
  encoding: "gb18030",
});
assert.deepEqual(tcp.routes.A.plug_boxes.sequence, [
  { type_code: "3P*4", count: 1, layout_pattern: "2+2" },
]);
assert.equal(tcp.extensions.single_cabinet.cabinet_count, 19);
assert.deepEqual([tcp.extensions.repeater.A_count, tcp.extensions.repeater.B_count], [1, 3]);
const rereadTcp = JSON.parse(JSON.stringify(tcp));
assert.deepEqual(rereadTcp.extensions.second_loop_temperature, temperatureProjection);
assert.equal(typeof rereadTcp.extensions.second_loop_temperature[0].board_index, "number");
assert.equal(typeof rereadTcp.extensions.second_loop_temperature[0].second_loop, "boolean");
assert.equal(rereadTcp.extensions.second_loop_temperature[0].temperature_index, null);
assert.ok(Array.isArray(rereadTcp.extensions.second_loop_temperature[0].source_indexes));

console.log(JSON.stringify({ status: "pass", cases: ["legacy_rtu", "tcp_decoupled"] }));
