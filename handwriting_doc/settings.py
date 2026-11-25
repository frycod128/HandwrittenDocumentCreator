"""项目根 ``settings.json`` 的读取、校验与保存。

配置只记录界面设置（复选框、输入框），不记录“待排文字”正文。
文件缺失或内容不合法时会立即写入一份新的默认配置。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SETTINGS_FILENAME = "settings.json"
CURRENT_VERSION = 1
MAX_LINE_COUNT = 100
MIN_LINE_COUNT = 1
_MAX_FONTS = 500


@dataclass(frozen=True, slots=True)
class SettingsLoad:
    """一次读取的结果：配置内容与文件状态。"""

    config: dict[str, Any]
    status: str  # "created" | "loaded" | "repaired"


def settings_path(project_root: str | Path) -> Path:
    return Path(project_root) / SETTINGS_FILENAME


def default_config(default_output_dir: str | Path) -> dict[str, Any]:
    return {
        "version": CURRENT_VERSION,
        "line_count": "52",
        "seed": "",
        "output_dir": str(default_output_dir),
        "base_name": "",
        "pdf": True,
        "docx": True,
        "search": "",
        "preview_char": "中",
        "selected_fonts": [],
    }


def _as_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _as_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def normalize(raw: Any, order: dict[str, Any]) -> dict[str, Any] | None:
    """把任意内容规范成完整配置；不合法时返回 None。"""
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != CURRENT_VERSION:
        return None

    line_count = _as_text(raw.get("line_count"))
    if line_count is None:
        return None
    try:
        line_value = int(line_count.strip())
    except ValueError:
        return None
    if not MIN_LINE_COUNT <= line_value <= MAX_LINE_COUNT:
        return None

    seed = _as_text(raw.get("seed"))
    if seed is None:
        return None
    seed = seed.strip()
    if seed:
        try:
            int(seed)
        except ValueError:
            return None

    output_dir = _as_text(raw.get("output_dir"))
    if output_dir is None or not output_dir.strip():
        return None

    base_name = _as_text(raw.get("base_name"))
    if base_name is None:
        return None

    pdf = _as_flag(raw.get("pdf"))
    docx = _as_flag(raw.get("docx"))
    if pdf is None or docx is None:
        return None

    search = _as_text(raw.get("search"))
    preview_char = _as_text(raw.get("preview_char"))
    if search is None or preview_char is None:
        return None

    fonts = raw.get("selected_fonts")
    if not isinstance(fonts, list):
        return None
    selected: list[str] = []
    seen: set[str] = set()
    for item in fonts[:_MAX_FONTS]:
        text = _as_text(item)
        if text is None:
            return None
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            selected.append(text)

    values: dict[str, Any] = {
        "version": CURRENT_VERSION,
        "line_count": str(line_value),
        "seed": seed,
        "output_dir": output_dir.strip(),
        "base_name": base_name,
        "pdf": pdf,
        "docx": docx,
        "search": search,
        "preview_char": preview_char[:1],
        "selected_fonts": selected,
    }
    return {key: values[key] for key in order if key in values}


def write_settings(path: str | Path, config: dict[str, Any]) -> Path:
    """原子写入配置：先写临时文件，再替换目标。"""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    return destination


def save_settings(path: str | Path, config: dict[str, Any]) -> Path:
    """校验后保存；内容不合法时抛出 ValueError，不覆盖已有的好配置。"""
    normalized = normalize(config, config)
    if normalized is None:
        raise ValueError("设置内容不合法，已跳过保存")
    return write_settings(path, normalized)


def load_or_create(path: str | Path, defaults: dict[str, Any]) -> SettingsLoad:
    """读取配置；文件不存在或不合法时写入默认配置。"""
    destination = Path(path)
    if not destination.is_file():
        write_settings(destination, defaults)
        return SettingsLoad(dict(defaults), "created")

    try:
        raw = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        write_settings(destination, defaults)
        return SettingsLoad(dict(defaults), "repaired")

    config = normalize(raw, defaults)
    if config is None:
        write_settings(destination, defaults)
        return SettingsLoad(dict(defaults), "repaired")
    if config != raw:
        write_settings(destination, config)
        return SettingsLoad(config, "repaired")
    return SettingsLoad(config, "loaded")
