from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from .gfont import discover_fonts
from .paths import default_output_dir, is_writable_directory
from .renderer import generate_document


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FONT_DIR = PROJECT_ROOT / "字体素材"


def _resolve_font_paths(values: list[str], font_dir: Path) -> list[Path]:
    resolved: list[Path] = []
    missing: list[str] = []
    for value in values:
        candidate = Path(value)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = font_dir / value
        if not candidate.exists() and not value.lower().endswith(".gfont"):
            candidate = font_dir / f"{value}.gfont"
        if candidate.is_file():
            resolved.append(candidate.resolve())
        else:
            missing.append(value)
    if missing:
        raise FileNotFoundError("找不到字体: " + ", ".join(missing))
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将长文本排成 A3 横向双栏、逐字随机字体/旋转/位移的手写文档"
    )
    parser.add_argument("--input", help="UTF-8 文本文件；使用 - 从标准输入读取")
    parser.add_argument(
        "--fonts",
        nargs="+",
        help="字体文件名或路径；可一次提供多个",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=52,
        help="每栏行数，常用 46-58，默认 52",
    )
    parser.add_argument(
        "--output",
        help="输出 PDF 路径；省略时保存在 output/ 下",
    )
    parser.add_argument(
        "--docx",
        nargs="?",
        const="AUTO",
        help="同时生成 Word；只写 --docx 时自动使用 PDF 同名文件",
    )
    parser.add_argument("--seed", type=int, help="随机种子；相同输入可复现版式")
    parser.add_argument("--font-dir", default=str(DEFAULT_FONT_DIR), help="字体目录")
    parser.add_argument("--list-fonts", action="store_true", help="仅列出可用字体")
    parser.add_argument("--gui", action="store_true", help="启动图形界面")
    parser.add_argument("--restore-text", help=argparse.SUPPRESS)
    return parser


def run_cli(args: argparse.Namespace) -> int:
    font_dir = Path(args.font_dir).resolve()
    if args.list_fonts:
        fonts = discover_fonts(font_dir)
        for info in fonts:
            state = f"{info.character_count} 字" if info.available else f"不可用: {info.error}"
            print(f"{info.name}\t{state}")
        return 0

    if not args.input:
        raise ValueError("命令行模式需要 --input，或使用 --gui 启动界面")
    if not args.fonts:
        raise ValueError("命令行模式需要 --fonts")
    if args.input == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding="utf-8-sig")
    font_paths = _resolve_font_paths(args.fonts, font_dir)

    if args.output:
        pdf_path = Path(args.output)
        if pdf_path.suffix.lower() != ".pdf":
            pdf_path = pdf_path.with_suffix(".pdf")
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = default_output_dir(PROJECT_ROOT) / f"手写文档_{timestamp}.pdf"

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if not is_writable_directory(pdf_path.parent):
        fallback = default_output_dir(PROJECT_ROOT)
        if is_writable_directory(fallback) and fallback.resolve() != pdf_path.parent.resolve():
            print(f"输出目录不可写：{pdf_path.parent}，改用 {fallback}")
            pdf_path = fallback / pdf_path.name
        else:
            raise ValueError(f"输出目录不可写：{pdf_path.parent}")

    docx_path = None
    if args.docx:
        docx_path = (
            pdf_path.with_suffix(".docx")
            if args.docx == "AUTO"
            else Path(args.docx).with_suffix(".docx")
        )
        docx_path.parent.mkdir(parents=True, exist_ok=True)
        if not is_writable_directory(docx_path.parent):
            raise ValueError(f"输出目录不可写：{docx_path.parent}")

    def progress(fraction: float, message: str) -> None:
        print(f"[{fraction:>6.1%}] {message}", flush=True)

    result = generate_document(
        text=text,
        font_paths=font_paths,
        lines_per_column=args.lines,
        output_pdf=pdf_path,
        output_docx=docx_path,
        seed=args.seed,
        progress=progress,
    )
    print()
    print(f"PDF : {result.pdf_path}")
    if result.docx_path:
        print(f"DOCX: {result.docx_path}")
    print(
        f"页数: {result.page_count}  字符: {result.character_count}  "
        f"随机种子: {result.seed}"
    )
    if result.fallback_count:
        missing = "".join(result.missing_characters[:30])
        print(f"缺字回退: {result.fallback_count} 个；字符: {missing}")
    return 0


def cli_main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not argv or "--gui" in argv:
        args, _unknown = parser.parse_known_args(argv)
        from .gui import launch_gui

        try:
            launch_gui(PROJECT_ROOT, DEFAULT_FONT_DIR, restore_text=args.restore_text)
        except Exception as exc:
            print(f"无法启动图形界面: {exc}")
            print("请双击 run_gui.bat，或使用带 Tcl/Tk 的解释器启动。")
            return 3
        return 0
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except Exception as exc:
        parser.exit(2, f"错误: {exc}\n")
