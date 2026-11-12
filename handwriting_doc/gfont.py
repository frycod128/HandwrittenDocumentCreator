from __future__ import annotations

import io
import math
import os
import struct
import zipfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from statistics import median
from typing import Iterable, Iterator


_ZIP_MAGIC = b"PK\x03\x04"
_METRIC_SAMPLES = (
    "永中国的一是人在有大十言文我你他这天地上下左右日月水火木金土"
    "目口手心工王主生民中年月日小时东西南北风雨云山石田电前后"
    "春夏秋冬学教书课作业答案问题说明文字内容"
)


class GFontError(ValueError):
    """Raised when a .gfont file cannot be read."""


@dataclass(frozen=True, slots=True)
class Glyph:
    code_point: int
    segments: tuple[tuple[tuple[float, float], ...], ...]

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        return tuple(point for segment in self.segments for point in segment)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        if not self.points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True, slots=True)
class FontInfo:
    path: Path
    name: str
    character_count: int
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.error is None and self.character_count > 0


def _find_zip_offset(path: Path) -> int:
    """Find the appended ZIP without assuming a particular encrypted header size."""
    carry = b""
    consumed = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            searchable = carry + chunk
            found = searchable.find(_ZIP_MAGIC)
            if found >= 0:
                return consumed - len(carry) + found
            carry = searchable[-(len(_ZIP_MAGIC) - 1) :]
            consumed += len(chunk)
    raise GFontError("文件中没有找到 ZIP 字库数据")


class _OffsetReader:
    """Minimal seekable view starting at the embedded ZIP."""

    def __init__(self, stream: io.BufferedReader, offset: int):
        self._stream = stream
        self._offset = offset
        self._stream.seek(offset)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            position = self._stream.seek(self._offset + offset)
        elif whence == os.SEEK_CUR:
            position = self._stream.seek(offset, os.SEEK_CUR)
        elif whence == os.SEEK_END:
            position = self._stream.seek(offset, os.SEEK_END)
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        return position - self._offset

    def tell(self) -> int:
        return self._stream.tell() - self._offset

    def seekable(self) -> bool:
        return True

    def close(self) -> None:
        self._stream.close()


def _split_segments(
    points: tuple[tuple[float, float], ...], flags: bytes
) -> tuple[tuple[tuple[float, float], ...], ...]:
    segments: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        flag = flags[index] if index < len(flags) else 1
        if flag == 0 and current:
            segments.append(tuple(current))
            current = []
        current.append(point)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def decode_glyph(raw: bytes, expected_code_point: int | None = None) -> Glyph:
    if len(raw) < 10:
        raise GFontError("字模数据过短")
    code_point, reserved, float_count = struct.unpack(">HHH", raw[:6])
    if reserved != 0:
        raise GFontError(f"未知字模标志: {reserved}")
    if float_count % 2:
        raise GFontError("字模坐标数量不是偶数")
    float_end = 6 + float_count * 4
    if float_end + 4 > len(raw):
        raise GFontError("字模坐标数据不完整")
    if expected_code_point is not None and code_point != expected_code_point:
        raise GFontError(
            f"字模码点不一致: 期望 {expected_code_point}，实际 {code_point}"
        )
    coordinates = struct.unpack(f">{float_count}f", raw[6:float_end])
    points = tuple(
        (coordinates[index], coordinates[index + 1])
        for index in range(0, float_count, 2)
        if math.isfinite(coordinates[index])
        and math.isfinite(coordinates[index + 1])
    )
    point_count = struct.unpack(">I", raw[float_end : float_end + 4])[0]
    flag_start = float_end + 4
    flags = raw[flag_start : flag_start + point_count]
    if len(flags) != point_count or point_count != len(points):
        raise GFontError(
            f"字模点/标志数量不一致: 坐标 {len(points)}，标志 {len(flags)}"
        )
    return Glyph(code_point=code_point, segments=_split_segments(points, flags))


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


class GFont:
    """Read one KDraw .gfont file while keeping the ZIP directory open."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise GFontError(f"字体不存在: {self.path}")
        self._stream: io.BufferedReader | None = None
        self._reader: _OffsetReader | None = None
        self._zip: zipfile.ZipFile | None = None
        self._glyph_cache: dict[str, Glyph] = {}
        try:
            self.zip_offset = _find_zip_offset(self.path)
            self._stream = self.path.open("rb")
            self._reader = _OffsetReader(self._stream, self.zip_offset)
            self._zip = zipfile.ZipFile(self._reader)
            names = self._zip.namelist()
            self._numeric_entries = tuple(
                name
                for name in names
                if name.isdecimal() and 0 <= int(name) <= 0x10FFFF
            )
            if not self._numeric_entries:
                raise GFontError("ZIP 中没有数字码点字模")
            self.characters = frozenset(chr(int(name)) for name in self._numeric_entries)
        except (OSError, zipfile.BadZipFile, struct.error) as exc:
            self.close()
            raise GFontError(str(exc)) from exc

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def character_count(self) -> int:
        return len(self._numeric_entries)

    @cached_property
    def reference(self) -> tuple[float, float]:
        """Return a font-wide normalization size and vertical center."""
        dimensions: list[float] = []
        vertical_centers: list[float] = []
        sample_chars = [char for char in dict.fromkeys(_METRIC_SAMPLES) if self.supports(char)]
        if len(sample_chars) < 4:
            sample_chars = [
                chr(int(name))
                for name in self._numeric_entries[: min(80, len(self._numeric_entries))]
            ]
        for char in sample_chars:
            try:
                glyph = self.glyph(char)
            except GFontError:
                continue
            x_min, y_min, x_max, y_max = glyph.bounds
            width = x_max - x_min
            height = y_max - y_min
            dimension = max(width, height)
            if dimension > 0:
                dimensions.append(dimension)
                vertical_centers.append((y_min + y_max) / 2)
        if not dimensions:
            raise GFontError(f"{self.name} 没有可用的字模度量")
        return (
            max(_percentile(dimensions, 0.85), 1.0),
            median(vertical_centers),
        )

    def supports(self, char: str) -> bool:
        return len(char) == 1 and char in self.characters

    def glyph(self, char: str) -> Glyph:
        if not self.supports(char):
            raise GFontError(f"{self.name} 缺少字符 {char!r}")
        cached = self._glyph_cache.get(char)
        if cached is not None:
            return cached
        assert self._zip is not None
        raw = self._zip.read(str(ord(char)))
        glyph = decode_glyph(raw, ord(char))
        self._glyph_cache[char] = glyph
        return glyph

    def iter_available(self, chars: Iterable[str]) -> Iterator[str]:
        for char in chars:
            if self.supports(char):
                yield char

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        elif self._stream is not None:
            self._stream.close()
        self._stream = None

    def __enter__(self) -> "GFont":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def discover_fonts(font_dir: str | Path) -> list[FontInfo]:
    root = Path(font_dir)
    if not root.exists():
        return []
    result: list[FontInfo] = []
    for path in sorted(root.rglob("*.gfont"), key=lambda item: item.name.casefold()):
        try:
            with GFont(path) as font:
                result.append(FontInfo(path, path.stem, font.character_count))
        except Exception as exc:
            result.append(FontInfo(path, path.stem, 0, str(exc)))
    return result
