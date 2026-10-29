"""Reproducible outputs: the run timestamp, the zip re-pack of openpyxl workbooks, atomic writes, versions."""

from __future__ import annotations

import io
import os
import platform
import re
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

_ZIP_MIN = datetime(1980, 1, 1, tzinfo=UTC)
_ZIP_MAX = datetime(2107, 12, 31, 23, 59, 58, tzinfo=UTC)
_CORE = "docProps/core.xml"
_CORE_DATES = re.compile(rb"(<(?:\w+:)?(?:created|modified)\b[^>]*>)[^<]*(</(?:\w+:)?(?:created|modified)>)")
MEMBER_ATTR = 0o600 << 16  # -rw-------; zipfile writes this in place of 0, so it is set explicitly


class TimestampError(ValueError):
    """SOURCE_DATE_EPOCH is set but is not a whole, non-negative number of seconds."""


@dataclass(frozen=True)
class RunTimestamp:
    value: datetime
    source: Literal["SOURCE_DATE_EPOCH", "clock"]

    @property
    def iso(self) -> str:
        return self.value.strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def display(self) -> str:
        return self.value.strftime("%Y-%m-%d %H:%M UTC")

    @property
    def naive(self) -> datetime:
        return self.value.astimezone(UTC).replace(tzinfo=None)


def run_timestamp(env: Mapping[str, str] | None = None, now: datetime | None = None) -> RunTimestamp:
    """SOURCE_DATE_EPOCH (seconds, UTC) when set, else the clock, both without microseconds."""
    source = os.environ if env is None else env
    raw = source.get("SOURCE_DATE_EPOCH", "").strip()
    if raw:
        if not (raw.isascii() and raw.isdigit()):
            raise TimestampError(f"SOURCE_DATE_EPOCH must be a whole number of seconds, got {raw!r}")
        try:
            value = datetime.fromtimestamp(int(raw), tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise TimestampError(f"SOURCE_DATE_EPOCH out of range: {raw!r}") from exc
        return RunTimestamp(value, "SOURCE_DATE_EPOCH")
    current = now if now is not None else datetime.now(UTC)
    return RunTimestamp(current.astimezone(UTC).replace(microsecond=0), "clock")


def zip_time(when: datetime) -> tuple[int, int, int, int, int, int]:
    """A zip date_time: clamped to the range the format can hold, seconds rounded down to even."""
    value = min(max(when.astimezone(UTC), _ZIP_MIN), _ZIP_MAX)
    return (value.year, value.month, value.day, value.hour, value.minute, value.second - value.second % 2)


def normalise_zip(data: bytes, when: datetime) -> bytes:
    """Re-pack a zip with fixed member times and attributes and the core properties set to ``when``."""
    stamp = zip_time(when)
    iso = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ").encode("ascii")
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == _CORE:
                content = _CORE_DATES.sub(lambda match: match.group(1) + iso + match.group(2), content)
            member = zipfile.ZipInfo(info.filename, date_time=stamp)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 0
            member.external_attr = MEMBER_ATTR
            target.writestr(member, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    return output.getvalue()


def save_workbook_bytes(workbook: Any, when: datetime) -> bytes:
    """Save an openpyxl workbook to memory with created and modified set to ``when``, then re-pack it."""
    naive = when.astimezone(UTC).replace(tzinfo=None)
    workbook.properties.created = naive
    workbook.properties.modified = naive
    buffer = io.BytesIO()
    workbook.save(buffer)
    return normalise_zip(buffer.getvalue(), when)


def write_atomic(path: Path, data: bytes) -> None:
    """Write under a temporary name in the same folder, then move into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def environment() -> dict[str, str]:
    """Versions that decide whether two runs can give identical bytes."""
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "openpyxl": version("openpyxl"),
        "pydantic": version("pydantic"),
        "PyYAML": version("PyYAML"),
        "click": version("click"),
    }
