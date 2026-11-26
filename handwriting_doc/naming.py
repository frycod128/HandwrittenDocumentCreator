"""文件名模板：``{Time}``、``{Seed}``、``{LineCount}``、``{FontsCount}``。

模板在生成时展开，因此同一个“文件名”输入框可以反复使用而不覆盖上一次结果。
未知占位符原样保留；展开结果会去掉文件名中不允许的字符。
"""

from __future__ import annotations

import datetime as dt
import re

DEFAULT_BASE_NAME = "手写文档_{Time}"
TIME_FORMAT = "%Y%m%d%H%M%S"
MAX_BASE_NAME_LENGTH = 150
IMAGE_PDF_SUFFIX = "_纯图片"

_ILLEGAL_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_DOTS_OR_SPACES = re.compile(r"[. ]+$")
_DOCUMENT_SUFFIX = re.compile(r"\.(pdf|docx)$", re.IGNORECASE)


def render_base_name(
    template: str,
    *,
    time: dt.datetime,
    seed: int,
    line_count: int,
    fonts_count: int,
) -> str:
    """把模板中的占位符替换成实际值，未知占位符保持不变。"""
    values = {
        "Time": time.strftime(TIME_FORMAT),
        "Seed": str(seed),
        "LineCount": str(line_count),
        "FontsCount": str(fonts_count),
    }
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("{" + name + "}", value)
    return rendered


def sanitize_base_name(value: str) -> str:
    """替换文件名中不允许的字符，并去掉结尾的点和空格。"""
    cleaned = _ILLEGAL_CHARACTERS.sub("_", value).strip()
    return _TRAILING_DOTS_OR_SPACES.sub("", cleaned)


def build_base_name(
    template: str | None,
    *,
    time: dt.datetime,
    seed: int,
    line_count: int,
    fonts_count: int,
) -> str:
    """展开模板并清理成可用的文件名（不含扩展名）。"""
    text = (template or "").strip()
    if not text:
        text = DEFAULT_BASE_NAME
    text = _DOCUMENT_SUFFIX.sub("", text)
    rendered = render_base_name(
        text,
        time=time,
        seed=seed,
        line_count=line_count,
        fonts_count=fonts_count,
    )
    rendered = _DOCUMENT_SUFFIX.sub("", rendered)
    cleaned = sanitize_base_name(rendered)
    if not cleaned:
        cleaned = sanitize_base_name(
            render_base_name(
                DEFAULT_BASE_NAME,
                time=time,
                seed=seed,
                line_count=line_count,
                fonts_count=fonts_count,
            )
        )
    return cleaned[:MAX_BASE_NAME_LENGTH].rstrip(". ")


def build_image_pdf_stem(base_name: str) -> str:
    """纯图片 PDF 的文件名（不含扩展名）：在原文件名后加 ``_纯图片``。"""
    return f"{base_name}{IMAGE_PDF_SUFFIX}"
