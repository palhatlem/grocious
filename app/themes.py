"""Themes: one JSON file per theme in app/themes/ -> CSS custom properties.

A theme file:
    {"id": "gruvbox", "label": "Gruvbox", "scheme": "dark", "colors": {"bg": "#282828", ...}}

`id` = filename stem, `scheme` = light|dark (drives color-scheme + the default under
prefers-color-scheme), `colors` = the variables in COLOR_KEYS (missing keys fall back to the
base scheme). Drop a file in, restart, and it appears in the picker — nothing else to edit.
"""

import json
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent / "themes"

# every variable a theme may set; the CSS only ever uses these
COLOR_KEYS = (
    "bg",
    "bg2",
    "card",
    "card2",
    "line",
    "fg",
    "mut",
    "accent",
    "accent-fg",
    "pos",
    "neg",
    "warn",
    "trumf",
    "rema",
    "coop",
    "shadow",
)
DEFAULT_ORDER = (
    "light",
    "dark",
    "ink",
    "gruvbox",
    "zenburn",
    "catppuccin-latte",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "catppuccin-mocha",
)


def load_themes():
    themes = []
    for p in sorted(THEMES_DIR.glob("*.json")):
        d = json.loads(p.read_text("utf-8"))
        d.setdefault("id", p.stem)
        d.setdefault("label", p.stem)
        d.setdefault("scheme", "dark")
        d["colors"] = {k: v for k, v in d.get("colors", {}).items() if k in COLOR_KEYS}
        themes.append(d)
    order = {k: i for i, k in enumerate(DEFAULT_ORDER)}
    themes.sort(key=lambda t: (order.get(t["id"], 99), t["label"]))
    return themes


def _block(selector, theme, base):
    colors = {**base.get("colors", {}), **theme["colors"]}
    body = "".join(f"--{k}:{v};" for k, v in colors.items())
    return f"{selector}{{color-scheme:{theme['scheme']};{body}}}\n"


def render_css(themes=None):
    """Light is :root; dark is the prefers-color-scheme default; every theme is [data-theme=id]."""
    themes = themes or load_themes()
    by_id = {t["id"]: t for t in themes}
    light = by_id.get("light") or next((t for t in themes if t["scheme"] == "light"), themes[0])
    dark = by_id.get("dark") or next((t for t in themes if t["scheme"] == "dark"), themes[0])
    out = ["/* generated from app/themes/*.json */\n"]
    out.append(_block(":root", light, light))
    out.append("@media (prefers-color-scheme: dark){" + _block(":root:not([data-theme])", dark, dark) + "}\n")
    for t in themes:
        base = light if t["scheme"] == "light" else dark
        out.append(_block(f'html[data-theme="{t["id"]}"]', t, base))
    return "".join(out)
