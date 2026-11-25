#!/usr/bin/env python3
"""项目自举：在项目内准备运行环境并启动应用。

本文件只使用标准库，因此在依赖安装之前也能运行。它负责：

1. 检查项目内 ``.venv`` 是否健康（解释器可运行、依赖齐全、GUI 需要 Tcl/Tk）；
2. 只有在环境缺失或解释器损坏时，才用项目外的 Python 新建 ``.venv`` 并安装
   ``requirements.txt``；已有环境只补齐缺失的依赖，不会重建；
3. 用 ``.venv`` 的解释器启动 ``main.py``。

所有写入都落在项目目录内（``.venv``、``.cache``、``.python``）：不写注册表、
不修改 PATH、不安装全局包，也不影响其他用户。找不到任何 Python 时才会把
便携版 Python 下载到 ``.python``（见 ``tools/get_python.ps1``）。

用法::

    python tools/bootstrap.py                     # 准备环境并打开图形界面
    python tools/bootstrap.py --check             # 只检查，不改动任何文件
    python tools/bootstrap.py -- --list-fonts     # 用 .venv 运行命令行
    python tools/bootstrap.py --python D:\\Python311\\python.exe
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VENV_DIR = PROJECT_ROOT / ".venv"
PORTABLE_DIR = PROJECT_ROOT / ".python"
CACHE_DIR = PROJECT_ROOT / ".cache"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
WHEELHOUSE_DIR = PROJECT_ROOT / ".wheelhouse"
FETCH_SCRIPT = PROJECT_ROOT / "tools" / "get_python.ps1"
STATE_FILENAME = ".hdc-env.json"
MIN_PYTHON = (3, 10)
CORE_MODULES = ("reportlab", "docx", "pymupdf", "PIL", "fontTools")
IS_WINDOWS = os.name == "nt"

_PROBE_SCRIPT = """
import importlib.util as util
import json
import sys

print(json.dumps({
    "executable": sys.executable,
    "version": list(sys.version_info[:3]),
    "tkinter": util.find_spec("tkinter") is not None,
    "venv": util.find_spec("venv") is not None,
}))
"""

_CHECK_TEMPLATE = """
import importlib.util as util
import json
import sys

modules = %s
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.prefix,
    "version": list(sys.version_info[:3]),
    "missing": [name for name in modules if util.find_spec(name) is None],
    "tkinter": util.find_spec("tkinter") is not None,
}))
"""


class BootstrapError(RuntimeError):
    """环境无法准备时抛出的错误，消息面向最终用户。"""


@dataclass(frozen=True)
class Interpreter:
    command: tuple[str, ...]
    executable: Path
    version: tuple[int, ...]
    tkinter: bool

    @property
    def label(self) -> str:
        return "%d.%d.%d" % (self.version + (0, 0, 0))[:3]


@dataclass(frozen=True)
class Health:
    ok: bool
    kind: str = ""  # missing | interpreter | deps | tk
    reason: str = ""
    version: str = ""
    missing: tuple[str, ...] = ()
    tkinter: bool = False


def say(message: str) -> None:
    print(f"[环境] {message}", flush=True)


def venv_python(venv_dir: Path) -> Path:
    """返回虚拟环境中解释器的路径。"""
    if IS_WINDOWS:
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def requirements_digest() -> str:
    if not REQUIREMENTS_FILE.is_file():
        raise BootstrapError(f"缺少依赖清单：{REQUIREMENTS_FILE}")
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def _clean_env() -> dict[str, str]:
    """去掉跨项目干扰项，避免污染或受外部 Python 配置影响。"""
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _pip_env() -> dict[str, str]:
    env = _clean_env()
    env.update(
        {
            # pip 的缓存与配置都留在项目内，不写用户全局目录。
            "PIP_CACHE_DIR": str(CACHE_DIR / "pip"),
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _run_json(command: Sequence[str], timeout: int = 120) -> dict | None:
    try:
        proc = subprocess.run(
            [str(item) for item in command],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    line = proc.stdout.strip().splitlines()[-1]
    try:
        return json.loads(line)
    except ValueError:
        return None


def probe_interpreter(command: Sequence[str]) -> Interpreter | None:
    """运行一个候选解释器并读取它的版本与能力。"""
    data = _run_json([*command, "-I", "-c", _PROBE_SCRIPT], timeout=60)
    if not data:
        return None
    version = tuple(int(part) for part in data.get("version") or ())
    if len(version) < 2 or version[:2] < MIN_PYTHON or not data.get("venv"):
        return None
    executable = Path(str(data.get("executable") or command[0]))
    if not executable.is_file():
        return None
    return Interpreter(tuple(str(item) for item in command), executable, version, bool(data.get("tkinter")))


def _looks_like_venv(executable: Path) -> bool:
    """判断解释器是否已经属于某个虚拟环境（不能作为基础解释器）。"""
    try:
        return (executable.resolve().parent.parent / "pyvenv.cfg").is_file()
    except OSError:
        return False


def _inside(path: Path, directory: Path) -> bool:
    try:
        resolved = path.resolve()
        return resolved == directory.resolve() or directory.resolve() in resolved.parents
    except OSError:
        return False


def _which_paths(name: str) -> list[str]:
    found = shutil.which(name)
    return [found] if found else []


def _candidate_commands() -> list[tuple[str, ...]]:
    """按优先级列出可以当作基础解释器的命令。"""
    candidates: list[tuple[str, ...]] = []
    seen: set[str] = set()

    def add(*command: str) -> None:
        key = " ".join(command)
        if command and key not in seen:
            seen.add(key)
            candidates.append(tuple(command))

    env_python = os.environ.get("HDC_PYTHON") or os.environ.get("HDC_PYTHON_EXE")
    if env_python:
        add(env_python)

    if IS_WINDOWS:
        add(str(PORTABLE_DIR / "python.exe"))
        for launcher in ("py.exe", "python.exe", "python3.exe"):
            for found in _which_paths(launcher):
                if launcher.lower().startswith("py"):
                    # “py -3”取最新版本，再补一个 3.12 以覆盖老机器的轮子兼容性。
                    add(found, "-3")
                    add(found, "-3.12")
                else:
                    add(found)
        roots = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Python",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Python",
        ]
        for root in roots:
            try:
                for child in sorted(root.glob("Python3*"), reverse=True):
                    add(str(child / "python.exe"))
            except OSError:
                continue
        for pattern, relative in (
            ("uv/python/cpython-*", "python.exe"),
            ("Python/pythoncore-*", "python.exe"),
        ):
            root = Path(os.environ.get("APPDATA", "")) if pattern.startswith("uv") else Path(
                os.environ.get("LOCALAPPDATA", "")
            )
            try:
                for child in sorted(root.glob(pattern), reverse=True):
                    add(str(child / relative))
            except OSError:
                continue
        for found in _which_paths("python.exe"):
            add(found)
    else:
        for name in ("python3", "python"):
            for found in _which_paths(name):
                add(found)

    if not _inside(Path(sys.executable), DEFAULT_VENV_DIR):
        add(sys.executable)
    return candidates


def iter_viable_bases(need_tk: bool) -> Iterator[Interpreter]:
    """按优先级惰性返回可用的基础解释器（自动去重、排除虚拟环境）。"""
    seen: set[str] = set()
    for command in _candidate_commands():
        interpreter = probe_interpreter(command)
        if interpreter is None:
            continue
        key = str(interpreter.executable).casefold()
        if key in seen or _looks_like_venv(interpreter.executable):
            continue
        if need_tk and not interpreter.tkinter:
            continue
        seen.add(key)
        yield interpreter


def viable_bases(need_tk: bool) -> list[Interpreter]:
    return list(iter_viable_bases(need_tk))


def check_environment(venv_dir: Path, need_tk: bool) -> Health:
    """检查项目内虚拟环境是否可以直接使用。"""
    if not (venv_dir / "pyvenv.cfg").is_file():
        return Health(False, "missing", "项目内还没有虚拟环境")
    python = venv_python(venv_dir)
    if not python.is_file():
        return Health(False, "interpreter", "虚拟环境缺少解释器")
    script = _CHECK_TEMPLATE % json.dumps(list(CORE_MODULES))
    data = _run_json([str(python), "-I", "-c", script])
    if not data:
        return Health(False, "interpreter", "虚拟环境中的解释器无法运行")
    missing = tuple(data.get("missing") or ())
    version = ".".join(str(part) for part in data.get("version") or ())
    if missing:
        return Health(False, "deps", "缺少依赖：" + "、".join(missing), version, missing, bool(data.get("tkinter")))
    if need_tk and not data.get("tkinter"):
        return Health(False, "tk", "虚拟环境缺少 Tcl/Tk，无法打开图形界面", version)
    return Health(True, "", "", version, (), bool(data.get("tkinter")))


def _remove_tree(path: Path) -> None:
    """只删除项目根目录下的子目录，避免误删。"""
    if not path.exists():
        return
    if path.parent.resolve() != PROJECT_ROOT.resolve():
        raise BootstrapError(f"拒绝删除项目目录之外的路径：{path}")

    def _on_error(func, target, _exc_info):  # noqa: ANN001 - shutil 回调
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            raise

    # 刚被替换掉的解释器可能还占用着文件，重试几次再放弃。
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            shutil.rmtree(path, onerror=_on_error)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    raise BootstrapError(f"无法删除旧的虚拟环境 {path}：{last_error}")


def create_venv(base: Interpreter, venv_dir: Path) -> None:
    say(f"用 Python {base.label} 创建项目内虚拟环境：{base.executable}")
    _remove_tree(venv_dir)
    try:
        code = subprocess.call(
            [str(base.executable), "-m", "venv", str(venv_dir)],
            cwd=str(PROJECT_ROOT),
            env=_clean_env(),
        )
    except OSError as exc:
        raise BootstrapError(f"无法运行 {base.executable}：{exc}") from exc
    if code != 0 or not venv_python(venv_dir).is_file():
        raise BootstrapError(f"Python {base.label} 未能创建虚拟环境（退出码 {code}）")


def install_dependencies(python: Path, venv_dir: Path) -> None:
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade-strategy",
        "only-if-needed",
        "-r",
        str(REQUIREMENTS_FILE),
    ]
    if WHEELHOUSE_DIR.is_dir() and any(WHEELHOUSE_DIR.iterdir()):
        say(f"使用离线依赖目录：{WHEELHOUSE_DIR}")
        command[4:4] = ["--no-index", "--find-links", str(WHEELHOUSE_DIR)]
    say("安装依赖（只写入项目内 .venv，不安装全局包）…")
    code = subprocess.call(command, cwd=str(PROJECT_ROOT), env=_pip_env())
    if code != 0:
        raise BootstrapError(
            "依赖安装失败。请检查网络后重试；"
            f"也可以手动执行：{python} -m pip install -r {REQUIREMENTS_FILE}"
        )


def _state_path(venv_dir: Path) -> Path:
    return venv_dir / STATE_FILENAME


def read_state(venv_dir: Path) -> dict:
    try:
        return json.loads(_state_path(venv_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(venv_dir: Path, **extra: object) -> None:
    payload = {
        "requirements_sha256": requirements_digest(),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    payload.update(extra)
    path = _state_path(venv_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def fetch_portable_python(need_tk: bool) -> Interpreter:
    """没有可用 Python 时，把便携版下载到项目内 .python。"""
    if not IS_WINDOWS:
        raise BootstrapError(
            "没有找到 Python 3.10 或更高版本。请先安装 Python 后重试，"
            "或用 --python 指定解释器路径。"
        )
    if not FETCH_SCRIPT.is_file():
        raise BootstrapError(f"缺少下载脚本：{FETCH_SCRIPT}")
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(FETCH_SCRIPT)]
    overrides = (("HDC_PYTHON_URL", "-Url"), ("HDC_PYTHON_SHA256", "-Sha256"))
    for variable, flag in overrides:
        value = os.environ.get(variable)
        if value:
            command.extend([flag, value])
    say("没有找到可用的 Python，正在把便携版下载到项目内 .python …")
    code = subprocess.call(command, cwd=str(PROJECT_ROOT))
    if code != 0:
        raise BootstrapError(
            "便携版 Python 下载失败。请检查网络，或安装 Python 3.10+ 后重试；"
            "也可以用 --python 指定解释器路径。"
        )
    interpreter = probe_interpreter((str(PORTABLE_DIR / "python.exe"),))
    if interpreter is None:
        raise BootstrapError("便携版 Python 下载后无法运行，请删除 .python 目录后重试。")
    if need_tk and not interpreter.tkinter:
        raise BootstrapError("便携版 Python 缺少 Tcl/Tk，无法打开图形界面。")
    return interpreter


def ensure_environment(venv_dir: Path, need_tk: bool) -> Path:
    """返回可用的项目内解释器；只有环境缺失或解释器损坏时才新建。"""
    health = check_environment(venv_dir, need_tk)
    if health.ok:
        _sync_requirements(venv_dir, health)
        return venv_python(venv_dir)

    python = venv_python(venv_dir)
    if health.kind == "deps":
        say(f"项目内环境缺少依赖，正在补齐：{health.reason}")
        install_dependencies(python, venv_dir)
        health = check_environment(venv_dir, need_tk)
        if not health.ok:
            raise BootstrapError("依赖安装后自检失败：" + health.reason)
        write_state(venv_dir, python=health.version, rebuilt=False)
        return python
    if health.kind == "tk":
        raise BootstrapError(
            "现有虚拟环境缺少 Tcl/Tk。请删除 .venv 后重新运行以自动重建，"
            "或改用带 Tcl/Tk 的 Python。"
        )

    say("未找到可用的项目内环境，开始初始化：" + health.reason)
    bases = iter_viable_bases(need_tk)
    first = next(bases, None)
    if first is None:
        first = fetch_portable_python(need_tk)

    failure: BootstrapError | None = None
    for base in itertools.chain([first], itertools.islice(bases, 3)):
        try:
            create_venv(base, venv_dir)
        except BootstrapError as exc:
            failure = exc
            say(f"该解释器不可用：{exc}")
            continue
        install_dependencies(venv_python(venv_dir), venv_dir)
        health = check_environment(venv_dir, need_tk)
        if not health.ok:
            raise BootstrapError("环境创建后自检失败：" + health.reason)
        write_state(venv_dir, python=health.version, rebuilt=True, base=str(base.executable))
        say(f"环境就绪：Python {health.version}")
        return venv_python(venv_dir)

    raise BootstrapError(f"无法准备运行环境：{failure or '没有可用的 Python'}")


def _sync_requirements(venv_dir: Path, health: Health) -> None:
    """依赖清单变化时补齐依赖；环境本身不重建。"""
    digest = requirements_digest()
    stored = read_state(venv_dir).get("requirements_sha256")
    if stored and stored != digest:
        say("requirements.txt 已变化，更新项目内依赖 …")
        install_dependencies(venv_python(venv_dir), venv_dir)
        write_state(venv_dir, python=health.version, rebuilt=False)
    elif not stored:
        write_state(venv_dir, python=health.version)


def launch(python: Path, app_args: Sequence[str]) -> int:
    command = [str(python), str(PROJECT_ROOT / "main.py"), *app_args]
    try:
        return subprocess.call(command, cwd=str(PROJECT_ROOT), env=_clean_env())
    except KeyboardInterrupt:
        return 130


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = argparse.ArgumentParser(
        description="准备项目内运行环境并启动应用（不修改系统全局环境）"
    )
    parser.add_argument("--check", action="store_true", help="只检查环境，不做任何改动")
    parser.add_argument("--launch-gui", action="store_true", help="启动图形界面")
    parser.add_argument("--python", help="指定基础解释器路径")
    parser.add_argument("--venv-dir", default=str(DEFAULT_VENV_DIR), help="虚拟环境目录（默认 .venv）")
    args, extra = parser.parse_known_args(argv)

    if args.python:
        os.environ["HDC_PYTHON"] = args.python
    app_args = [item for item in extra if item != "--"]
    if args.launch_gui:
        app_args = ["--gui", *app_args]
    need_tk = "--gui" in app_args
    venv_dir = Path(args.venv_dir).resolve()

    try:
        if args.check:
            health = check_environment(venv_dir, need_tk)
            print(f"项目根目录: {PROJECT_ROOT}")
            print(f"虚拟环境  : {venv_dir}")
            if health.ok:
                print(f"状态      : 可用（Python {health.version}，依赖完整）")
                return 0
            print(f"状态      : 需要初始化（{health.reason}）")
            if health.missing:
                print("缺少依赖  : " + "、".join(health.missing))
            return 1
        python = ensure_environment(venv_dir, need_tk)
        if not app_args:
            app_args = ["--gui"]
        return launch(python, app_args)
    except BootstrapError as exc:
        print(f"\n[环境] 失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
