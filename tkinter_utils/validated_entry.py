"""A typed ttk entry with non-blocking validation feedback."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk
from typing import Any, Generic, TypeVar

ValueT = TypeVar("ValueT")


class ValidatedEntry(ttk.Entry, Generic[ValueT]):
    """Parse and validate text while allowing normal intermediate edits."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        parser: Callable[[str], ValueT] = str,  # type: ignore[assignment]
        validator: Callable[[ValueT], str | None] | None = None,
        min_value: ValueT | None = None,
        max_value: ValueT | None = None,
        allow_empty: bool = False,
        name: str = "Value",
        formatter: Callable[[ValueT], str] = str,
        variable: tk.StringVar | None = None,
        **entry_options: Any,
    ) -> None:
        if "textvariable" in entry_options:
            raise TypeError("use variable= instead of textvariable=")
        super().__init__(master, **entry_options)
        self.variable = variable or tk.StringVar(master=self)
        self.configure(textvariable=self.variable)
        self.parser = parser
        self.validator = validator
        self.min_value = min_value
        self.max_value = max_value
        self.allow_empty = allow_empty
        self.name = name
        self.formatter = formatter
        self._error_message: str | None = None
        self._valid: bool | None = None

        self.bind("<FocusOut>", lambda _event: self.validate_value(), add="+")
        self.bind("<Return>", lambda _event: self.validate_value(), add="+")

    @property
    def valid(self) -> bool | None:
        """Last validation state, or ``None`` before first validation."""

        return self._valid

    @property
    def error_message(self) -> str | None:
        """The last validation error."""

        return self._error_message

    def get_value(self) -> ValueT | None:
        """Return the parsed value or raise ``ValueError`` when invalid."""

        text = self.variable.get().strip()
        if not text:
            if self.allow_empty:
                self._set_validation(True, None)
                return None
            message = f"{self.name} is required"
            self._set_validation(False, message)
            raise ValueError(message)

        try:
            value = self.parser(text)
        except (TypeError, ValueError) as exc:
            message = f"{self.name} is invalid"
            self._set_validation(False, message)
            raise ValueError(message) from exc

        try:
            if self.min_value is not None and value < self.min_value:
                message = f"{self.name} must be at least {self.min_value}"
                self._set_validation(False, message)
                raise ValueError(message)
            if self.max_value is not None and value > self.max_value:
                message = f"{self.name} must be at most {self.max_value}"
                self._set_validation(False, message)
                raise ValueError(message)
        except TypeError as exc:
            raise TypeError("min_value and max_value must be comparable") from exc

        if self.validator is not None:
            error = self.validator(value)
            if error:
                self._set_validation(False, error)
                raise ValueError(error)

        self._set_validation(True, None)
        return value

    def validate_value(self) -> bool:
        """Validate current text and update ttk's ``invalid`` state."""

        try:
            self.get_value()
        except ValueError:
            return False
        return True

    def set_value(self, value: ValueT | None, *, validate: bool = True) -> None:
        """Replace entry text, optionally validating it immediately."""

        self.variable.set("" if value is None else self.formatter(value))
        if validate:
            self.validate_value()
        else:
            self._valid = None
            self._error_message = None
            self.state(["!invalid"])

    def _set_validation(self, valid: bool, message: str | None) -> None:
        changed = valid != self._valid
        self._valid = valid
        self._error_message = message
        self.state(["!invalid"] if valid else ["invalid"])
        if changed:
            self.event_generate("<<ValidationChanged>>", when="tail")
