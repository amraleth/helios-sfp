from __future__ import annotations
import struct
from typing import Any, Callable, Optional, Union

from ctx import Ctx, _resolve


Buffer = Union[bytes, bytearray, memoryview, str]


class Field:


    def __init__(self, offset: Optional[int], size: int, *,
                 when: Optional[Callable[[Ctx], bool]] = None,
                 doc: str = "") -> None:
        self.offset = offset
        self.size = size
        self.name = ""
        self.doc = doc
        self.when = when
        self.unit: Optional[str] = None


    def __set_name__(self, owner, name: str) -> None:
        self.name = name


    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance._values[self.name]


    def raw(self, buf: bytes) -> bytes:
        if self.offset is None:
            return b""
        return bytes(buf[self.offset:self.offset + self.size])


    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        raise NotImplementedError


class _Scalar(Field):


    def __init__(self, offset: int, fmt: str, *,
                 enum=None, scale=None, unit: Optional[str] = None,
                 when=None, doc: str = "") -> None:
        super().__init__(offset, struct.calcsize(fmt), when=when, doc=doc)
        self.fmt = fmt
        self.enum = enum
        self.scale = scale
        self.unit = unit


    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        (v,) = struct.unpack_from(self.fmt, buf, self.offset if self.offset != None else 0)
        scale = _resolve(self.scale, ctx)
        if scale is not None:
            return v * scale
        enum = _resolve(self.enum, ctx)
        if enum is not None:
            return enum.get(v, f"Reserved(0x{v:0{self.size*2}X})")
        return v


def U8 (offset, **kw): return _Scalar(offset, ">B", **kw)
def U16(offset, **kw): return _Scalar(offset, ">H", **kw)
def U32(offset, **kw): return _Scalar(offset, ">I", **kw)
def I8 (offset, **kw): return _Scalar(offset, ">b", **kw)
def I16(offset, **kw): return _Scalar(offset, ">h", **kw)
def I32(offset, **kw): return _Scalar(offset, ">i", **kw)


class Bits(Field):


    def __init__(self, offset: int, hi: int, lo: int, *,
                 enum=None, when=None, doc: str = "") -> None:
        super().__init__(offset, 1, when=when, doc=doc)
        if not (0 <= lo <= hi <= 7):
            raise ValueError(f"invalid bit range [{hi}:{lo}] in byte {offset}")
        self.hi, self.lo = hi, lo
        self.enum = enum


    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        byte = buf[self.offset if self.offset != None else 0]
        width = self.hi - self.lo + 1
        v = (byte >> self.lo) & ((1 << width) - 1)
        enum = _resolve(self.enum, ctx)
        if enum is not None:
            return enum.get(v, f"Reserved({v})")
        return v


class Bit(Bits):


    def __init__(self, offset: int, bit: int, *, when=None, doc: str = "") -> None:
        super().__init__(offset, bit, bit, when=when, doc=doc)


    def decode(self, buf: bytes, ctx: Ctx) -> bool:
        return bool(super().decode(buf, ctx))


class Ascii(Field):


    def __init__(self, offset: int, length: int, *,
                 strip: bool = True, when=None, doc: str = "") -> None:
        super().__init__(offset, length, when=when, doc=doc)
        self.strip = strip


    def decode(self, buf: bytes, ctx: Ctx) -> str:
        s = bytes(buf[self.offset:(self.offset if self.offset != None else 0) + self.size]).decode("ascii", "replace")
        return s.strip() if self.strip else s


class Hex(Field):


    def __init__(self, offset: int, length: int, *,
                 sep: str = ":", when=None, doc: str = "") -> None:
        super().__init__(offset, length, when=when, doc=doc)
        self.sep = sep


    def decode(self, buf: bytes, ctx: Ctx) -> str:
        return bytes(buf[self.offset:(self.offset if self.offset != None else 0) + self.size]).hex(self.sep).upper()


class Raw(Field):


    def __init__(self, offset: int, length: int, *,
                 when=None, doc: str = "") -> None:
        super().__init__(offset, length, when=when, doc=doc)

        
    def decode(self, buf: bytes, ctx: Ctx) -> bytes:
        return bytes(buf[self.offset:(self.offset if self.offset != None else 0) + self.size])


class Computed(Field):


    def __init__(self, fn: Callable[[Ctx], Any], *,
                 unit: Optional[str] = None, when=None, doc: str = "") -> None:
        super().__init__(offset=None, size=0, when=when, doc=doc)
        self.fn = fn
        self.unit = unit

    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        return self.fn(ctx)


