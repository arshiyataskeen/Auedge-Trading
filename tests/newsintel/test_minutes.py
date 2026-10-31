"""Tests for the pg_dump reader and the 1-minute candle loader."""
from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

from core.newsintel.minutes import load_backup_minutes
from tools.pgdump_read import iter_copy_rows

TABLE = "public.ohlcv_xauusd"


def _int(v: int) -> bytes:
    return bytes([1 if v < 0 else 0]) + abs(v).to_bytes(4, "little")


def _str(s: str | None) -> bytes:
    if s is None:
        return _int(-1)
    b = s.encode()
    return _int(len(b)) + b


def _write_dump(path: Path, rows: list[list[str]], gzip: bool) -> None:
    """Write a minimal PGDMP 1.16 archive holding one TABLE DATA entry."""
    text = "".join("\t".join(r) + "\n" for r in rows) + "\\.\n\n"
    raw = text.encode()
    payload = zlib.compress(raw) if gzip else raw
    # split into two chunks so chunk boundaries get exercised (mid-line)
    cut = len(payload) // 2
    chunks = [payload[:cut], payload[cut:]]

    head = b"PGDMP" + bytes([1, 16, 0, 4, 8, 1, 1 if gzip else 0])
    head += b"".join(_int(0) for _ in range(7))
    head += _str("db") + _str("16.0") + _str("pg_dump 16.0")
    head += _int(1)  # one TOC entry
    entry = (_int(5) + _int(1) + _str("0") + _str("0") + _str("ohlcv_xauusd")
             + _str("TABLE DATA") + _int(3) + _str("") + _str("")
             + _str("COPY public.ohlcv_xauusd (symbol) FROM stdin;")
             + _str("public") + _str(None) + _str(None) + _int(0)
             + _str("owner") + _str("false") + _str(None))
    toc_tail = bytes([2]) + (0).to_bytes(8, "little")  # placeholder offset
    offset = len(head) + len(entry) + len(toc_tail)
    toc_tail = bytes([2]) + offset.to_bytes(8, "little")
    block = bytes([1]) + _int(5)
    for c in chunks:
        block += _int(len(c)) + c
    block += _int(0)
    path.write_bytes(head + entry + toc_tail + block)


ROWS = [
    ["XAUUSD", "1min", "2024-01-02 00:00:00+00", "2050.1", "2051", "2049.5", "2050.7", "\\N", "3"],
    ["XAUUSD", "1min", "2024-01-02 00:01:00+00", "2050.7", "2052", "2050", "2051.5", "\\N", "5"],
]


def test_iter_copy_rows_plain_and_gzip(tmp_path):
    for gz in (False, True):
        p = tmp_path / f"d{gz}.backup"
        _write_dump(p, ROWS, gz)
        assert list(iter_copy_rows(p, TABLE)) == ROWS


def test_load_minutes_filters_and_sorts(tmp_path):
    rows = [ROWS[1], ROWS[0],
            ["XAUUSD", "1day", "2024-01-02 00:00:00+00", "1", "1", "1", "1", "\\N", "1"]]
    p = tmp_path / "d.backup"
    _write_dump(p, rows, True)
    m = load_backup_minutes(p, cache=tmp_path / "c.npz")
    assert len(m.t) == 2
    assert np.all(np.diff(m.t) > 0)
    assert m.t[0] == 1704153600
    assert m.o[0] == 2050.1 and m.c[1] == 2051.5 and m.h[1] == 2052 and m.l[1] == 2050


def test_load_minutes_uses_cache(tmp_path):
    p = tmp_path / "d.backup"
    _write_dump(p, ROWS, True)
    cache = tmp_path / "c.npz"
    a = load_backup_minutes(p, cache=cache)
    p.unlink()
    # cache is newer than... the deleted file: loader must not need the dump
    b = load_backup_minutes(p, cache=cache)
    assert np.array_equal(a.t, b.t) and np.array_equal(a.c, b.c)


def test_naive_timestamp_rejected(tmp_path):
    import pytest
    rows = [["XAUUSD", "1min", "2024-01-02 00:00:00", "2050.1", "2051", "2049.5", "2050.7", "\\N", "3"]]
    p = tmp_path / "d.backup"
    _write_dump(p, rows, True)
    with pytest.raises(ValueError, match="timezone"):
        load_backup_minutes(p, cache=tmp_path / "c.npz")
