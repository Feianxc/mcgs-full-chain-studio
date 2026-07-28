from __future__ import annotations

import csv
import gc
import tempfile
from pathlib import Path

from _test_support import add_repo_to_import_path, configure_process_runtime

add_repo_to_import_path()
configure_process_runtime("mcgs-program-upload")

from openpyxl import Workbook

from protocol_studio.program_upload import UPLOAD_HEADERS, write_program_upload_csv


PROTOCOL_HEADERS = [
    "通道号",
    "变量名",
    "变量类型",
    "通道名称",
    "读写类型",
    "寄存器名称",
    "数据类型",
    "寄存器地址",
]


def build_synthetic_workbook(path: Path) -> None:
    workbook = Workbook()
    first = workbook.active
    first.title = "合成点表A"
    first.append(["合成协议测试数据"])
    first.append(PROTOCOL_HEADERS)
    first.append(
        [
            0,
            "StateS1",
            "SINGLE",
            "只读4WUB1001",
            "只读",
            "[4区]输出寄存器",
            "16位无符号二进制",
            1000,
        ]
    )
    first.append(
        [
            1,
            "IaS1",
            "SINGLE",
            "只读4DF1002",
            "只读",
            "[4区]输出寄存器",
            "32位浮点数",
            1001,
        ]
    )

    second = workbook.create_sheet("合成点表B")
    second.append(PROTOCOL_HEADERS)
    second.append(
        [
            2,
            "Comm_EC101",
            "SINGLE",
            "只读4WUB2001",
            "只读",
            "[4区]输出寄存器",
            "16位无符号二进制",
            2000,
        ]
    )
    workbook.save(path)
    workbook.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mcgs-program-upload-artifacts-") as temp_dir:
        temp_root = Path(temp_dir)
        workbook_path = temp_root / "synthetic-protocol.xlsx"
        output_path = temp_root / "synthetic-program-upload.csv"
        build_synthetic_workbook(workbook_path)

        result = write_program_upload_csv(
            workbook_path,
            output_path,
            device_name="fixture-upload",
            driver_library_path="fixtures/drivers/modbus-upload.ui",
            driver_component_name="合成串口驱动",
            driver_component_version="1.0-test",
        )

        assert result["status"] == "generated"
        assert result["point_count"] == 3
        assert result["encoding"].lower() == "gb18030"
        assert result["sheet_boundaries"] == [
            {"sheet": "合成点表A", "start_index": 0, "end_index": 1, "count": 2},
            {"sheet": "合成点表B", "start_index": 2, "end_index": 2, "count": 1},
        ]

        raw = output_path.read_bytes()
        assert raw and not raw.startswith(b"\xef\xbb\xbf")
        decoded = raw.decode("gb18030")
        assert decoded.encode("gb18030") == raw
        rows = list(csv.reader(decoded.splitlines()))
        assert rows[:5] == [
            ["组态设备名称:fixture-upload"],
            ["驱动库文件路径:fixtures/drivers/modbus-upload.ui"],
            ["驱动构件名称:合成串口驱动"],
            ["驱动构件版本:1.0-test"],
            UPLOAD_HEADERS,
        ]
        assert [row[1] for row in rows[5:]] == ["StateS1", "IaS1", "Comm_EC101"]
        assert [row[7] for row in rows[5:]] == ["1001", "1002", "2001"]
        assert all(len(row) == len(UPLOAD_HEADERS) for row in rows[5:])
        gc.collect()

    print("protocol_studio_program_upload_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
