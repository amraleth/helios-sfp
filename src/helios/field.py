"""Field descriptors that map byte ranges to decoded values.

This module defines the building blocks of a :class:`Spec`. Each field
captures an offset, a size, and a decoding rule. During parsing, every field
receives the full buffer plus a :class:`Ctx` of values decoded so far,
allowing later fields to depend on earlier ones through ``when=`` predicates,
callable ``enum=`` / ``scale=`` parameters, or :class:`Computed` fields
with no byte position at all.

Public field types:
    :class:`Field`         Base descriptor.
    :func:`U8`-:func:`I32` Big-endian integer scalars.
    :class:`Bits`          Bit slice within a single byte.
    :class:`Bit`           Single bit as ``bool``.
    :class:`Ascii`         Fixed-length ASCII string.
    :class:`Hex`           Raw bytes rendered as hex.
    :class:`Raw`           Raw bytes returned unchanged.
    :class:`Computed`      Virtual field driven by a callable.
"""
from __future__ import annotations
import struct
from enum import Enum
from typing import Any, Callable, Optional, Union

from .ctx import Ctx, _resolve

Buffer = Union[bytes, bytearray, memoryview, str]
"""Any input :meth:`Spec.parse` accepts. Bytes-like or a whitespace-tolerant hex string."""


class FieldType(Enum):
    RO_RQD = "RO RQD"
    RO_OPT = "RO OPT"


class Field:
    """Base class for all field descriptors.

    A ``Field`` is attached as a class attribute on a :class:`Spec` subclass.
    During parsing, :meth:`decode` is called with the full buffer and a
    :class:`Ctx` of previously decoded values. The result is stored under
    the field's name and returned via attribute access on the parsed instance.

    Subclasses must override :meth:`decode`.

    Attributes:
        offset: Byte position in the buffer, or ``None`` for a virtual field
            such as :class:`Computed`.
        size: Number of bytes consumed at ``offset``. Zero for virtual fields.
        name: Filled in automatically by :meth:`__set_name__` when the field
            is bound to a class attribute.
        doc: Optional human-readable description.
        when: Optional predicate ``fn(ctx) -> bool``. If provided and falsy,
            decoding is skipped and the field's value becomes ``None``.
        unit: Optional engineering unit shown next to the value in
            :meth:`Spec.__repr__`.
    """

    def __init__(self, offset: Optional[int], size: int, *,
                 when: Optional[Callable[[Ctx], bool]] = None,
                 doc: str = "", ftype: FieldType = FieldType.RO_RQD) -> None:
        """Initializes a field descriptor.

        Args:
            offset: Byte position of the field, or ``None`` for virtual fields.
            size: Number of bytes the field occupies. Zero for virtual fields.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
            ftype: The type of data this field holds.
        """
        self.offset = offset
        self.size = size
        self.name = ""
        self.doc = doc
        self.when = when
        self.unit: Optional[str] = None
        self.ftype = ftype

    def __set_name__(self, owner, name: str) -> None:
        """Captures the attribute name when the field is bound to a :class:`Spec` subclass."""
        self.name = name

    def __get__(self, instance, owner=None):
        """Returns the decoded value when accessed on a parsed instance.

        Returns the descriptor itself when accessed on the class, so that
        :class:`Spec` can introspect its own fields.
        """
        if instance is None:
            return self
        return instance._values[self.name]

    def raw(self, buf: bytes) -> bytes:
        """Returns the raw bytes covered by this field.

        Args:
            buf: The buffer the field was parsed from.

        Returns:
            The slice ``buf[offset:offset+size]``, or ``b""`` for virtual fields.
        """
        if self.offset is None:
            return b""
        return bytes(buf[self.offset:self.offset + self.size])

    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        """Decodes the field from ``buf``, given the current parsing :class:`Ctx`.

        Subclasses must override this.

        Raises:
            NotImplementedError: Always, on the base class.
        """
        raise NotImplementedError


class _Scalar(Field):
    """Generic big-endian integer field driven by a :mod:`struct` format.

    Used internally by the integer factory functions :func:`U8`, :func:`U16`,
    :func:`U32`, :func:`I8`, :func:`I16`, and :func:`I32`. Supports either
    ``scale`` (multiply the raw value) or ``enum`` (map the raw value to a
    name) as the decoded representation. Both may be callables resolved
    against the parsing :class:`Ctx`.
    """

    def __init__(self, offset: int, fmt: str, *,
                 enum=None, scale=None, unit: Optional[str] = None,
                 when=None, doc: str = "") -> None:
        """Initializes a scalar integer field.

        Args:
            offset: Byte position of the value.
            fmt: A :mod:`struct` format string such as ``">H"``. Determines the
                size, signedness, and byte order.
            enum: Optional mapping (or callable returning a mapping) from raw
                value to display name.
            scale: Optional multiplier (or callable returning one). Applied
                to the raw value when set. Takes precedence over ``enum``.
            unit: Optional engineering unit (``"C"``, ``"V"``, ...) shown in
                the rendered output.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
        """
        super().__init__(offset, struct.calcsize(fmt), when=when, doc=doc)
        self.fmt = fmt
        self.enum = enum
        self.scale = scale
        self.unit = unit

    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        """Decodes the integer at ``offset`` and applies ``scale`` or ``enum``.

        Returns:
            ``raw * scale`` when ``scale`` is set. Otherwise, the looked-up
            enum entry, or a ``"Reserved(0x..)"`` placeholder when no mapping
            matches. Otherwise, the raw integer.
        """
        (v,) = struct.unpack_from(self.fmt, buf, self.offset if self.offset is not None else 0)
        scale = _resolve(self.scale, ctx)
        if scale is not None:
            return v * scale
        enum = _resolve(self.enum, ctx)
        if enum is not None:
            return enum.get(v, f"Reserved(0x{v:0{self.size * 2}X})")
        return v


def U8(offset, **kw):
    """Unsigned 8-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">B", **kw)


def U16(offset, **kw):
    """Unsigned 16-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">H", **kw)


def U32(offset, **kw):
    """Unsigned 32-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">I", **kw)


def I8(offset, **kw):
    """Signed 8-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">b", **kw)


def I16(offset, **kw):
    """Signed 16-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">h", **kw)


def I32(offset, **kw):
    """Signed 32-bit big-endian scalar. See :class:`_Scalar` for keyword arguments."""
    return _Scalar(offset, ">i", **kw)


class Bits(Field):
    """Extracts a contiguous bit slice ``[hi:lo]`` from a single byte.

    Bit numbering follows the SFF/CMIS convention. Bit 7 is the MSB and bit 0
    is the LSB. The slice is inclusive on both ends.

    Example:
        The two CMIS revision nibbles in byte 1::

            rev_major = Bits(1, 7, 4)
            rev_minor = Bits(1, 3, 0)
    """

    def __init__(self, offset: int, hi: int, lo: int, *,
                 enum=None, when=None, doc: str = "") -> None:
        """Initializes a bit-slice field.

        Args:
            offset: Byte position to read.
            hi: Highest bit index in the slice (0..7).
            lo: Lowest bit index in the slice (0..7). Must satisfy ``lo <= hi``.
            enum: Optional mapping (or callable returning a mapping) from raw
                value to display name.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.

        Raises:
            ValueError: If the bit range falls outside ``[0, 7]`` or ``lo > hi``.
        """
        super().__init__(offset, 1, when=when, doc=doc)
        if not (0 <= lo <= hi <= 7):
            raise ValueError(f"invalid bit range [{hi}:{lo}] in byte {offset}")
        self.hi, self.lo = hi, lo
        self.enum = enum

    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        """Returns the bit slice as an integer, optionally mapped through ``enum``."""
        byte = buf[self.offset if self.offset is not None else 0]
        width = self.hi - self.lo + 1
        v = (byte >> self.lo) & ((1 << width) - 1)
        enum = _resolve(self.enum, ctx)
        if enum is not None:
            return enum.get(v, f"Reserved({v})")
        return v


class Bit(Bits):
    """Single bit returned as a ``bool``. Convenience wrapper around :class:`Bits`."""

    def __init__(self, offset: int, bit: int, *, when=None, doc: str = "") -> None:
        """Initializes a single-bit field.

        Args:
            offset: Byte position to read.
            bit: Bit index within the byte (0..7).
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
        """
        super().__init__(offset, bit, bit, when=when, doc=doc)

    def decode(self, buf: bytes, ctx: Ctx) -> bool:
        """Returns ``True`` if the bit is set, ``False`` otherwise."""
        return bool(super().decode(buf, ctx))


class Ascii(Field):
    """Fixed-length ASCII string field.

    CMIS pads strings with ``0x20`` (space). When ``strip`` is ``True`` the
    surrounding whitespace is removed. Pass ``strip=False`` to preserve the
    full padded value (useful when the exact byte content matters).
    """

    def __init__(self, offset: int, length: int, *,
                 strip: bool = True, when=None, doc: str = "") -> None:
        """Initializes an ASCII string field.

        Args:
            offset: Byte position of the first character.
            length: Number of bytes in the field.
            strip: Whether to strip surrounding whitespace from the decoded value.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
        """
        super().__init__(offset, length, when=when, doc=doc)
        self.strip = strip

    def decode(self, buf: bytes, ctx: Ctx) -> str:
        """Returns the bytes decoded as ASCII, with non-ASCII bytes replaced.

        Returns:
            The decoded string, optionally stripped of surrounding whitespace.
        """
        s = bytes(buf[self.offset:(self.offset if self.offset is not None else 0) + self.size]).decode("ascii",
                                                                                                       "replace")
        return s.strip() if self.strip else s


class Hex(Field):
    """Raw bytes rendered as a separator-joined uppercase hex string.

    Useful for fields like the IEEE OUI where the canonical printed form is
    ``AA:BB:CC`` rather than the raw integer value.
    """

    def __init__(self, offset: int, length: int, *,
                 sep: str = ":", when=None, doc: str = "") -> None:
        """Initializes a hex string field.

        Args:
            offset: Byte position of the first byte.
            length: Number of bytes in the field.
            sep: Separator inserted between byte hex pairs. Default is ``":"``.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
        """
        super().__init__(offset, length, when=when, doc=doc)
        self.sep = sep

    def decode(self, buf: bytes, ctx: Ctx) -> str:
        """Returns the bytes as an uppercase hex string joined by ``sep``."""
        return bytes(buf[self.offset:(self.offset if self.offset is not None else 0) + self.size]).hex(self.sep).upper()


class Raw(Field):
    """Raw bytes returned unchanged.

    Use this when downstream code needs the original byte sequence. Examples
    include feeding the bytes into an external CRC routine or copying them
    verbatim into another buffer.
    """

    def __init__(self, offset: int, length: int, *,
                 when=None, doc: str = "") -> None:
        """Initializes a raw byte field.

        Args:
            offset: Byte position of the first byte.
            length: Number of bytes in the field.
            when: Optional predicate that gates decoding.
            doc: Optional human-readable description.
        """
        super().__init__(offset, length, when=when, doc=doc)

    def decode(self, buf: bytes, ctx: Ctx) -> bytes:
        """Returns the raw bytes covered by the field."""
        return bytes(buf[self.offset:(self.offset if self.offset is not None else 0) + self.size])


class Computed(Field):
    """Virtual field whose value is derived from already-decoded values.

    A ``Computed`` field consumes no bytes. Its ``offset`` is ``None`` and
    its ``size`` is ``0``. The supplied callable receives the parsing
    :class:`Ctx` and may reference any field declared above it.

    Example:
        Joining two bit slices into a version string::

            rev_major = Bits(1, 7, 4)
            rev_minor = Bits(1, 3, 0)
            revision  = Computed(lambda c: f"{c.rev_major}.{c.rev_minor}")
    """

    def __init__(self, fn: Callable[[Ctx], Any], *,
                 unit: Optional[str] = None, when=None, doc: str = "") -> None:
        """Initializes a computed field.

        Args:
            fn: Callable receiving a :class:`Ctx` and returning the decoded value.
            unit: Optional engineering unit shown in the rendered output.
            when: Optional predicate that gates evaluation.
            doc: Optional human-readable description.
        """
        super().__init__(offset=None, size=0, when=when, doc=doc)
        self.fn = fn
        self.unit = unit

    def decode(self, buf: bytes, ctx: Ctx) -> Any:
        """Returns ``fn(ctx)``."""
        return self.fn(ctx)
