"""Helpers for loading the vendored Azure ttk theme."""

from __future__ import annotations

import base64
from importlib import resources
from importlib.resources.abc import Traversable
import tkinter as tk
from tkinter import ttk
from typing import Literal

ThemeMode = Literal["light", "dark"]


def load_theme(
    root: tk.Misc,
    mode: ThemeMode = "light",
    *,
    fallback: str | None = "clam",
) -> bool:
    """Load and activate the vendored Azure theme.

    Returns ``True`` when Azure was activated. If loading fails and ``fallback``
    is set, that built-in ttk theme is activated and ``False`` is returned.
    Pass ``fallback=None`` to let a ``tk.TclError`` propagate.
    """

    _validate_mode(mode)
    try:
        style = ttk.Style(root)
        if not {"azure-light", "azure-dark"}.issubset(style.theme_names()):
            _source_vendored_theme(root)
        root.tk.call("set_theme", mode)
        # Some Windows ttk builds keep reporting the previous native theme
        # after the Tcl helper runs; selecting it through ttk makes activation
        # deterministic.
        style.theme_use(f"azure-{mode}")
        return True
    except (FileNotFoundError, ModuleNotFoundError, OSError, ValueError, tk.TclError):
        if fallback is None:
            raise
        ttk.Style(root).theme_use(fallback)
        return False


def set_theme(root: tk.Misc, mode: ThemeMode) -> None:
    """Switch an already loaded Azure theme between light and dark."""

    _validate_mode(mode)
    if not load_theme(root, mode, fallback=None):
        raise tk.TclError("unable to activate the Azure ttk theme")


def _validate_mode(mode: str) -> None:
    if mode not in {"light", "dark"}:
        raise ValueError("mode must be 'light' or 'dark'")


def _source_vendored_theme(root: tk.Misc) -> None:
    """Evaluate theme assets without relying on Tcl filesystem access.

    Reading through ``importlib.resources`` also makes the loader work from
    wheels, frozen applications, and Windows paths that Tcl cannot resolve.
    """

    theme_root = resources.files("azure_ttk_theme")
    for mode in ("light", "dark"):
        _eval_mode_script(root, theme_root, mode)

    azure_script = theme_root.joinpath("azure.tcl").read_text(encoding="utf-8")
    azure_script = "\n".join(
        line
        for line in azure_script.splitlines()
        if not line.strip().startswith("source ")
    )
    root.tk.eval(azure_script)


def _eval_mode_script(
    root: tk.Misc,
    theme_root: Traversable,
    mode: str,
) -> None:
    mode_directory = theme_root.joinpath("theme", mode)
    image_items: list[str] = []
    for image_resource in sorted(
        mode_directory.iterdir(),
        key=lambda item: item.name,
    ):
        if image_resource.name.endswith(".png"):
            image_items.extend(
                (
                    image_resource.name.removesuffix(".png"),
                    base64.b64encode(image_resource.read_bytes()).decode("ascii"),
                )
            )

    images_variable = f"::tkinter_utils_azure_{mode}_images"
    root.tk.call("set", images_variable, tuple(image_items))
    script = theme_root.joinpath(
        "theme",
        f"{mode}.tcl",
    ).read_text(encoding="utf-8")
    replacement = (
        "        proc load_images {imgdir} {\n"
        "            variable I\n"
        f"            foreach {{img data}} ${images_variable} {{\n"
        "                set I($img) [image create photo -data $data -format png]\n"
        "            }\n"
        "        }"
    )
    root.tk.eval(
        _replace_tcl_procedure(
            script,
            "        proc load_images {imgdir} {",
            replacement,
        )
    )


def _replace_tcl_procedure(script: str, marker: str, replacement: str) -> str:
    start = script.index(marker)
    opening_brace = start + len(marker) - 1
    depth = 0
    for index in range(opening_brace, len(script)):
        character = script[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return script[:start] + replacement + script[index + 1 :]
    raise ValueError(f"unterminated Tcl procedure: {marker.strip()}")
