from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from field import Field

class Ctx:
    __slots__ = ("_fields", "_values", "buf")


    def __init__(self, fields: Dict[str, "Field"], values: Dict[str, Any],
                 buf: bytes) -> None:
        self._fields = fields
        self._values = values
        self.buf = buf


    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(
                f"field '{name}' not yet decoded (declare it before its dependents)"
            ) from None


    def __contains__(self, name: str) -> bool:
        return name in self._values


    def raw(self, name: str) -> bytes:
        return self._fields[name].raw(self.buf)


    def raw_int(self, name: str) -> int:
        return int.from_bytes(self.raw(name), "big")


def _resolve(value: Any, ctx: Ctx) -> Any:
    return value(ctx) if callable(value) else value
