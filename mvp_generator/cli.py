from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mvp_generator.excel_renderer import ClassicCombinedRenderer
    from mvp_generator.generator import ProtocolGenerator
    from mvp_generator.split_renderers import AbScreenSplitRenderer, ExtendedSplitRenderer
else:
    from .excel_renderer import ClassicCombinedRenderer
    from .generator import ProtocolGenerator
    from .split_renderers import AbScreenSplitRenderer, ExtendedSplitRenderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MCGS 动环协议板卡级 MVP 生成器")
    parser.add_argument("--config", required=True, help="项目配置 JSON 路径")
    parser.add_argument("--output", help="输出 canonical JSON 路径")
    parser.add_argument("--excel-output", help="输出当前 export family 对应的 Excel 路径")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.output and not args.excel_output:
        raise SystemExit("至少需要提供 --output 或 --excel-output 之一")

    generator = ProtocolGenerator.with_default_assets()
    output = generator.generate_from_path(Path(args.config))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote canonical model -> {output_path}")

    if args.excel_output:
        export_family = output["profiles"]["export_profile"]["family"]
        excel_path = Path(args.excel_output)
        if export_family == "classic_combined":
            renderer = ClassicCombinedRenderer(output)
        elif export_family == "extended_split":
            renderer = ExtendedSplitRenderer(output)
        elif export_family == "ab_screen_split":
            renderer = AbScreenSplitRenderer(output)
        else:
            raise NotImplementedError(f"未支持的 Excel 导出 family: {export_family}")
        renderer.render_to_path(excel_path)
        print(f"Wrote Excel workbook -> {excel_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
