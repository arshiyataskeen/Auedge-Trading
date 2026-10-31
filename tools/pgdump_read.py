"""Streaming reader for a pg_dump custom-format archive (PGDMP 1.14-1.16, no compression or gzip).

`iter_copy_rows` finds a table's TABLE DATA block and yields its COPY rows one by one,
without writing the decompressed data to disk.
"""
from __future__ import annotations

import zlib
from pathlib import Path
from typing import BinaryIO, Iterator

_END = bytes([92]) + b"."  # the COPY terminator line: backslash + dot


class _Reader:
    """Reads the archive's own int / string / offset encodings."""

    def __init__(self, f: BinaryIO, int_size: int, off_size: int) -> None:
        self.f, self.int_size, self.off_size = f, int_size, off_size

    def rint(self) -> int:
        sign = self.f.read(1)[0]
        v = int.from_bytes(self.f.read(self.int_size), "little")
        return -v if sign else v

    def rstr(self) -> str | None:
        n = self.rint()
        return None if n < 0 else self.f.read(n).decode("utf8", "replace")

    def roff(self) -> int:
        self.f.read(1)  # state flag, not needed
        return int.from_bytes(self.f.read(self.off_size), "little")


def _find_entry(f: BinaryIO, table: str) -> tuple[_Reader, int, int, bool]:
    """Parse header + TOC; return (reader, dump id, data offset, gzip?) for the table's data."""
    if f.read(5) != b"PGDMP":
        raise ValueError("not a pg_dump custom-format archive")
    vmaj, vmin, _vrev, int_size, off_size, _fmt = f.read(6)
    if (vmaj, vmin) < (1, 14) or (vmaj, vmin) > (1, 16):
        raise ValueError(f"unsupported archive version {vmaj}.{vmin}")
    r = _Reader(f, int_size, off_size)
    if (vmaj, vmin) >= (1, 15):
        gz = f.read(1)[0] == 1  # algorithm byte: 0 none, 1 gzip
    else:
        gz = r.rint() != 0  # older archives store a compression level
    for _ in range(7):  # dump creation timestamp fields
        r.rint()
    r.rstr(), r.rstr(), r.rstr()  # database, server version, pg_dump version
    want = table.split(".")[-1]
    for _ in range(r.rint()):
        dump_id, has_data = r.rint(), r.rint()
        r.rstr(), r.rstr()  # tableoid, oid
        tag, desc = r.rstr(), r.rstr()
        r.rint()  # section
        for _ in range(3):  # defn, drop, copy statement
            r.rstr()
        ns = r.rstr()
        r.rstr(), r.rstr()  # tablespace, tableam
        if (vmaj, vmin) >= (1, 16):
            r.rint()  # relkind
        r.rstr(), r.rstr()  # owner, with-oids
        while r.rstr() is not None:  # dependencies
            pass
        off = r.roff()
        if desc == "TABLE DATA" and tag == want and has_data and (
                "." not in table or ns == table.split(".")[0]):
            return r, dump_id, off, gz
    raise KeyError(f"no TABLE DATA entry for {table}")


def iter_copy_rows(path: str | Path, table: str) -> Iterator[list[str]]:
    """Yield the table's COPY rows as tab-split lists of strings (NULL stays the literal text backslash-N)."""
    with open(path, "rb") as f:
        r, dump_id, off, gz = _find_entry(f, table)
        f.seek(off)
        if f.read(1)[0] != 1 or r.rint() != dump_id:
            raise ValueError("data block does not match its TOC entry")
        dz = zlib.decompressobj() if gz else None
        tail = b""
        while (n := r.rint()) > 0:
            chunk = f.read(n)
            data = tail + (dz.decompress(chunk) if dz else chunk)
            *lines, tail = data.split(b"\n")
            for ln in lines:
                if ln == _END:
                    return
                yield ln.decode("utf8").split("\t")
        if dz:
            tail += dz.flush()
        for ln in tail.split(b"\n"):
            if ln == _END:
                return
            if ln:
                yield ln.decode("utf8").split("\t")
