"""解析操作系统里的默认目录（下载文件夹等）。

Windows 优先使用 Known Folder API，失败时退回注册表（用户可能把“下载”
重定向到其他磁盘），最后退回 ``~/Downloads``；其他系统读取 XDG 配置。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# FOLDERID_Downloads，同时是注册表 User Shell Folders 中的值名。
_DOWNLOADS_FOLDER_ID = "{374DE290-123F-4565-9164-39C4925E467B}"
_USER_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"


def _windows_known_folder() -> Path | None:
    """通过 SHGetKnownFolderPath 读取“下载”文件夹。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    guid = _GUID()
    guid.Data1 = 0x374DE290
    guid.Data2 = 0x123F
    guid.Data3 = 0x4565
    for index, value in enumerate((0x91, 0x64, 0x39, 0xC4, 0x92, 0x5B, 0x5B, 0xE6)):
        guid.Data4[index] = value

    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        pointer = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer)) != 0:
            return None
        try:
            value = pointer.value
        finally:
            ole32 = ctypes.WinDLL("ole32")
            ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ole32.CoTaskMemFree(ctypes.cast(pointer, ctypes.c_void_p))
        return Path(value) if value else None
    except (OSError, AttributeError, ValueError):
        return None


def _windows_registry_folder() -> Path | None:
    """读取资源管理器记录的“下载”路径（支持重定向与 %USERPROFILE%）。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for key_path in (_USER_SHELL_FOLDERS, _SHELL_FOLDERS):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                raw, _kind = winreg.QueryValueEx(key, _DOWNLOADS_FOLDER_ID)
        except OSError:
            continue
        if not raw:
            continue
        return Path(os.path.expandvars(str(raw)))
    return None


def _posix_folder() -> Path | None:
    """读取 XDG user-dirs 中的下载目录。"""
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    try:
        lines = (Path(config_home) / "user-dirs.dirs").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("XDG_DOWNLOAD_DIR="):
            continue
        value = stripped.partition("=")[2].strip().strip('"')
        value = value.replace("$HOME", str(Path.home()))
        return Path(value) if value else None
    return None


def downloads_candidates() -> list[Path]:
    """按优先级返回候选的“下载”目录，去重后保留原始顺序。"""
    result: list[Path] = []
    for resolver in (_windows_known_folder, _windows_registry_folder, _posix_folder):
        try:
            found = resolver()
        except Exception:  # pragma: no cover - 防御系统 API 的意外异常
            found = None
        if found is not None:
            result.append(found)
    result.append(Path.home() / "Downloads")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def default_downloads_dir() -> Path:
    """返回系统默认的“下载”目录；不存在时返回第一个候选路径。"""
    candidates = downloads_candidates()
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def is_writable_directory(path: str | Path) -> bool:
    """通过实际写入一个临时文件判断目录是否可写。

    权限不足、目录不存在、被安全策略拦截时都会返回 False；``os.access``
    在部分重定向目录或受限进程里并不可靠，所以这里直接试写。
    """
    directory = Path(path)
    if not directory.is_dir():
        return False
    probe = directory / f".hdc-write-test-{os.getpid()}-{time.time_ns()}"
    try:
        probe.write_bytes(b"")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass
    return True


def default_output_dir(project_root: str | Path) -> Path:
    """系统默认的“下载”文件夹；不存在且无法创建时退回项目内 output/。

    这里只判断“能否作为默认位置”，不判断是否可写——不可写时由界面询问用户
    是否提升权限，而不是悄悄换到别的目录。
    """
    for path in downloads_candidates():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue
    fallback = Path(project_root) / "output"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def writable_output_dir(project_root: str | Path) -> Path:
    """第一个真正可写的候选目录；都不可写时退回项目内 output/。"""
    for path in downloads_candidates():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if is_writable_directory(path):
            return path
    fallback = Path(project_root) / "output"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
