from typing import Any, Dict

from .field import Buffer, Ctx, Field


class Spec:
    _fields_: Dict[str, Field] = {}


    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        fields: Dict[str, Field] = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, Field):
                    fields[name] = value
        cls._fields_ = fields


    def __init__(self, values: Dict[str, Any], raw: bytes) -> None:
        self._values = values
        self._raw = raw


    @classmethod
    def parse(cls, buf: Buffer) -> "Spec":
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
        return dict(self._values)


    def __repr__(self) -> str:
        cls = type(self)
        name_w = max((len(n) for n in cls._fields_), default=0)
        lines = [f"{cls.__name__}  ({len(self._raw)} bytes)"]
        for name, field in cls._fields_.items():
            v = self._values[name]
            unit = f" {field.unit}" if getattr(field, "unit", None) else ""
            if field.offset is None:
                pos = "  --   "       # Computed: no byte position
                raw_hex = "(computed)"
            else:
                pos = f"[{field.offset:3d}+{field.size}]"
                raw_hex = f"raw={field.raw(self._raw).hex().upper()}"
            v_str = "(skipped)" if v is None and field.when is not None \
                    else f"{v}{unit}"
            lines.append(f"  {pos} {name:<{name_w}} = {v_str:<28} {raw_hex}")
        return "\n".join(lines)
