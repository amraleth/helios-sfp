"""The :class:`Spec` base class — declarative byte-buffer schemas.

This module ties the field descriptors from :mod:`.field` into a complete
parser. Users subclass :class:`Spec`, attach :class:`Field` descriptors as
class attributes, and call :meth:`Spec.parse` on a buffer. Fields are
collected at class-creation time in declaration order and decoded
sequentially, which is what allows ``when=`` predicates and
:class:`Computed` fields to depend on already-decoded values.
"""
from typing import Any, Dict
from .field import Buffer, Ctx, Field


class Spec:
    """Declarative byte-buffer schema. Subclass and attach :class:`Field` descriptors.

    Subclasses declare fields as class attributes::

        class Page00(Spec):
            identifier  = U8(0, enum=MODULE_TYPE)
            vendor_name = Ascii(129, 16)
            vendor_oui  = Hex(145, 3)

    Each subclass gets a populated :attr:`_fields_` mapping at class-creation
    time. Calling :meth:`parse` on a buffer returns an instance whose decoded
    values are accessible as attributes::

        page = Page00.parse(raw)
        page.vendor_name        # -> "ACME OPTICS"

    Attributes:
        _fields_: Class-level mapping of field name to :class:`Field`
            descriptor, populated by :meth:`__init_subclass__` from every
            :class:`Field` attribute found across the MRO.
    """
    _fields_: Dict[str, Field] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        """Collects :class:`Field` descriptors from the class hierarchy.

        Walks the MRO in reverse so that subclasses may override fields
        declared on a base class. Declaration order is preserved, and that
        order drives both :meth:`parse` evaluation and :meth:`__repr__`
        output.
        """
        super().__init_subclass__(**kwargs)
        fields: Dict[str, Field] = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, Field):
                    fields[name] = value
        cls._fields_ = fields

    def __init__(self, values: Dict[str, Any], raw: bytes) -> None:
        """Initializes a parsed spec instance.

        End users should not call this directly — use :meth:`parse` instead.
        It is invoked internally once decoding has populated the values dict.

        Args:
            values: Mapping of field name to decoded value.
            raw: The full buffer the values were decoded from.
        """
        self._values = values
        self._raw = raw

    @classmethod
    def parse(cls, buf: Buffer) -> "Spec":
        """Parses ``buf`` into an instance of the spec.

        Decodes every field in declaration order. Each decode call receives
        a :class:`Ctx` view of values decoded so far, so later fields may
        depend on earlier ones. Fields with a ``when=`` predicate that
        evaluates to falsy are skipped and their value becomes ``None``.

        Args:
            buf: A bytes-like object, or a whitespace-tolerant hex string
                such as ``"18 52 00 06"``.

        Returns:
            An instance of the spec with all decoded values exposed as
            attributes.

        Raises:
            ValueError: If the buffer is shorter than the highest
                ``offset + size`` declared by any non-virtual field.
        """
        if isinstance(buf, str):
            buf = bytes.fromhex("".join(buf.split()))
        buf = bytes(buf)
        need = max(
            (f.offset + f.size for f in cls._fields_.values() if f.offset is not None),
            default=0,
        )
        if len(buf) < need:
            raise ValueError(f"buffer too short: {len(buf)} bytes, need {need}")
        values: Dict[str, Any] = {}
        ctx = Ctx(cls._fields_, values, buf)
        for name, f in cls._fields_.items():
            if f.when is not None and not f.when(ctx):
                values[name] = None
                continue
            values[name] = f.decode(buf, ctx)
        return cls(values, raw=buf)

    def to_dict(self) -> Dict[str, Any]:
        """Returns a shallow copy of the decoded values as a plain ``dict``.

        Useful for serialization (JSON, YAML) or for passing the result to
        code that expects a plain mapping rather than the :class:`Spec`
        instance.

        Returns:
            A new dictionary mapping field name to decoded value. Skipped
            fields appear with a value of ``None``.
        """
        return dict(self._values)

    def __repr__(self) -> str:
        """Returns a human-readable table of the parsed fields.

        Each row shows the byte position (``[offset+size]``), the field
        name, the decoded value with its unit, and the raw hex bytes.
        Virtual :class:`Computed` fields show ``(computed)`` in place of
        raw bytes. Fields skipped by a ``when=`` predicate show
        ``(skipped)`` as the value.
        """
        cls = type(self)
        name_w = max((len(n) for n in cls._fields_), default=0)
        lines = [f"{cls.__name__}  ({len(self._raw)} bytes)"]
        for name, field in cls._fields_.items():
            v = self._values[name]
            unit = f" {field.unit}" if getattr(field, "unit", None) else ""
            if field.offset is None:
                pos = "  --   "  # Computed: no byte position
                raw_hex = "(computed)"
            else:
                pos = f"[{field.offset:3d}+{field.size}]"
                raw_hex = f"raw={field.raw(self._raw).hex().upper()}"
            v_str = "(skipped)" if v is None and field.when is not None \
                else f"{v}{unit}"
            lines.append(f"  {pos} {name:<{name_w}} = {v_str:<28} {raw_hex}")
        return "\n".join(lines)
