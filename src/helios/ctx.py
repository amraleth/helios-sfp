"""Decode time context that shared between fields during the parsing stage.

This module defines :class:`Ctx` as a read-only view that every callable
parameter (``when=``, callable ``enum=``/``scale=``, and ``Computed``)
receives during a ``Spec.parse()`` call.
"""

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from field import Field


class Ctx:
    """Read-only view of partially decoded values, passed to callables.

    Fields are decoded in declared order. When a callable parameter is invoked, it receives the ``Ctx`` exposing
    everything decoded up to that point plus the underlying buffer.

    Attributes access returns *decoded* values. For raw bytes use :meth:`raw`. or :meth:`raw_int`.

    Attributes:
        buf: The full underlying buffer being parsed

    Example:
        Inside a ``when=`` callable:
                temperature = I16(14, scale=1/256, unit="C",
                              when=lambda c: c.module_state == "ModuleReady")
    """

    __slots__ = ("_fields", "_values", "buf")

    def __init__(self, fields: Dict[str, "Field"], values: Dict[str, Any],
                 buf: bytes) -> None:
        """Initializes the parsing context.

        Args:
            fields: Mapping of field name to ``Field`` descriptor for the spec.
            values: Mutable dict of decoded values, populated in declaration order.
            buf: The raw underlying buffer.
        """
        self._fields = fields
        self._values = values
        self.buf = buf

    def __getattr__(self, name: str) -> Any:
        """Returns the decoded value of a previously parsed field.

        Raises:
            AttributeError: If the ``name`` has not been decoded yet. Happens typically
            because it is declared *after* the field referencing it.
        """
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(
                f"field '{name}' not yet decoded (declare it before its dependents)"
            ) from None

    def __contains__(self, name: str) -> bool:
        """Returns ``True`` if the ``name`` has already been decoded yet."""
        return name in self._values

    def raw(self, name: str) -> bytes:
        """Returns the raw bytes for a field, ignoring any decoding rules.

        Args:
            name: The name of the field to decode.

            Returns:
                The slice of the underlying buffer covered by the field.
        """
        return self._fields[name].raw(self.buf)

    def raw_int(self, name: str) -> int:
        """Returns a field's raw bytes as a big-endian unsigned integer.

        Args:
            name: Field name from the parent spec.

        Returns:
            The integer value of the field's raw bytes as a big-endian integer.
        """

        return int.from_bytes(self.raw(name), "big")


def _resolve(value: Any, ctx: Ctx) -> Any:
    """Resolves a possible callable parameter against the current context.

    If ``value`` is callable, invoke it with ``ctx`` and return the result.
    Otherwise, return ``value`` unchanged. This is how callable ``enum=`` and
    ``scale=`` parameters are handled at decode time.
    """
    return value(ctx) if callable(value) else value
