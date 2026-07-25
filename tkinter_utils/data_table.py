"""A refresh-stable, declarative ttk Treeview table."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Any, Generic, TypeVar

RowT = TypeVar("RowT")


def _stringify(value: Any) -> str:
    return "" if value is None else str(value)


@dataclass(frozen=True)
class ColumnSpec:
    """Description of one :class:`DataTable` column."""

    key: str
    heading: str | None = None
    width: int = 120
    anchor: str = tk.W
    stretch: bool = True
    formatter: Callable[[Any], str] = _stringify
    accessor: Callable[[Any], Any] | None = None


class DataTable(ttk.Frame, Generic[RowT]):
    """Display records while preserving selection across data refreshes."""

    def __init__(
        self,
        master: tk.Misc,
        columns: Iterable[ColumnSpec],
        *,
        row_key: str | Callable[[RowT], Hashable],
        sortable: bool = True,
        selectmode: str = "extended",
        **frame_options: Any,
    ) -> None:
        super().__init__(master, **frame_options)
        self.columns = tuple(columns)
        if not self.columns:
            raise ValueError("at least one column is required")
        column_keys = [column.key for column in self.columns]
        if len(set(column_keys)) != len(column_keys):
            raise ValueError("column keys must be unique")

        self._row_key = row_key
        self.sortable = sortable
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._rows: dict[Hashable, RowT] = {}
        self._iid_by_key: dict[Hashable, str] = {}
        self._key_by_iid: dict[str, Hashable] = {}
        self._next_iid = 1

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            self,
            columns=column_keys,
            show="headings",
            selectmode=selectmode,
        )
        self.vertical_scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.tree.yview,
        )
        self.horizontal_scrollbar = ttk.Scrollbar(
            self,
            orient=tk.HORIZONTAL,
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=self.vertical_scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set,
        )
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        self.vertical_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.horizontal_scrollbar.grid(row=1, column=0, sticky=tk.EW)

        for column in self.columns:
            command = (
                lambda key=column.key: self.sort_by(key)
                if sortable
                else None
            )
            self.tree.heading(
                column.key,
                text=column.heading or column.key.replace("_", " ").title(),
                command=command,
            )
            self.tree.column(
                column.key,
                width=column.width,
                anchor=column.anchor,
                stretch=column.stretch,
            )
        self.tree.bind("<Control-c>", self._on_copy, add="+")
        self.tree.bind("<Control-C>", self._on_copy, add="+")

    def set_rows(self, rows: Iterable[RowT]) -> None:
        """Insert or update rows, retaining selected and focused row keys."""

        incoming: dict[Hashable, RowT] = {}
        input_order: list[Hashable] = []
        for row in rows:
            key = self._get_row_key(row)
            if key in incoming:
                raise ValueError(f"duplicate row key: {key!r}")
            incoming[key] = row
            input_order.append(key)

        selected = set(self.selected_keys())
        focused = self._key_by_iid.get(self.tree.focus())

        for key in set(self._rows) - set(incoming):
            iid = self._iid_by_key.pop(key)
            self._key_by_iid.pop(iid, None)
            self.tree.delete(iid)

        self._rows = incoming
        for key, row in incoming.items():
            values = self._formatted_values(row)
            iid = self._iid_by_key.get(key)
            if iid is None:
                iid = f"row{self._next_iid}"
                self._next_iid += 1
                self._iid_by_key[key] = iid
                self._key_by_iid[iid] = key
                self.tree.insert("", tk.END, iid=iid, values=values)
            else:
                self.tree.item(iid, values=values)

        order = input_order
        if self._sort_column is not None:
            order = self._sorted_keys(self._sort_column, self._sort_reverse)
        self._apply_order(order)

        selected_iids = [
            self._iid_by_key[key] for key in order if key in selected
        ]
        self.tree.selection_set(selected_iids)
        if focused in self._iid_by_key:
            self.tree.focus(self._iid_by_key[focused])

    def clear(self) -> None:
        """Remove every row."""

        self.set_rows(())

    def sort_by(self, column_key: str, reverse: bool | None = None) -> None:
        """Sort by raw column values and update the displayed order."""

        if column_key not in {column.key for column in self.columns}:
            raise KeyError(column_key)
        if reverse is None:
            reverse = (
                not self._sort_reverse
                if self._sort_column == column_key
                else False
            )
        self._sort_column = column_key
        self._sort_reverse = reverse
        self._apply_order(self._sorted_keys(column_key, reverse))

    def selected_keys(self) -> list[Hashable]:
        return [
            self._key_by_iid[iid]
            for iid in self.tree.selection()
            if iid in self._key_by_iid
        ]

    def selected_rows(self) -> list[RowT]:
        return [self._rows[key] for key in self.selected_keys()]

    def focused_row(self) -> RowT | None:
        key = self._key_by_iid.get(self.tree.focus())
        return self._rows.get(key) if key is not None else None

    def row_for_key(self, key: Hashable) -> RowT | None:
        return self._rows.get(key)

    def copy_selected(self, *, include_headings: bool = False) -> str:
        """Copy selected formatted rows as tab-separated text."""

        lines: list[str] = []
        if include_headings:
            lines.append(
                "\t".join(column.heading or column.key for column in self.columns)
            )
        for row in self.selected_rows():
            lines.append("\t".join(self._formatted_values(row)))
        text = "\n".join(lines)
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
        return text

    def _get_row_key(self, row: RowT) -> Hashable:
        if callable(self._row_key):
            key = self._row_key(row)
        else:
            key = _read_field(row, self._row_key)
        try:
            hash(key)
        except TypeError as exc:
            raise TypeError("row keys must be hashable") from exc
        return key

    def _raw_value(self, row: RowT, column: ColumnSpec) -> Any:
        if column.accessor is not None:
            return column.accessor(row)
        return _read_field(row, column.key)

    def _formatted_values(self, row: RowT) -> tuple[str, ...]:
        return tuple(
            column.formatter(self._raw_value(row, column))
            for column in self.columns
        )

    def _sorted_keys(self, column_key: str, reverse: bool) -> list[Hashable]:
        column = next(
            column for column in self.columns if column.key == column_key
        )
        return sorted(
            self._rows,
            key=lambda key: _sortable_value(self._raw_value(self._rows[key], column)),
            reverse=reverse,
        )

    def _apply_order(self, keys: Iterable[Hashable]) -> None:
        for index, key in enumerate(keys):
            self.tree.move(self._iid_by_key[key], "", index)

    def _on_copy(self, _event: tk.Event) -> str:
        self.copy_selected()
        return "break"


def _read_field(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)


def _sortable_value(value: Any) -> tuple[int, str, Any]:
    if value is None:
        return (1, "", "")
    if isinstance(value, str):
        return (0, "str", value.casefold())
    if isinstance(value, (int, float)):
        return (0, "number", value)
    return (0, type(value).__name__, str(value))
