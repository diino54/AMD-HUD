"""Atomic, conflict-checked persistence for the settings edit buffer."""
import hashlib
import json
import os
import re
from hud import ROOT, validate_config

PALETTE = {"background_color": "#191724", "text_color": "#e0def4",
           "border_color": "#403d52", "muted_color": "#6e6a86",
           "shadow_color": "#000000",
           "frametime_color": "#ebbcba",
           "row_colors": ["#9ccfd8", "#c4a7e7", "#f6c177", "#eb6f92"]}


def digest():
    return hashlib.sha256((ROOT / "config.json").read_bytes()).hexdigest()


def write_config(config, expected_digest=None):
    validate_config(config)
    for key in ("x", "y"):
        if not isinstance(config[key], int) or not -20000 <= config[key] <= 20000:
            raise ValueError("Position must be between -20000 and 20000 px.")
    colors = [config.get(key, default) for key, default in PALETTE.items() if key != "row_colors"]
    rows = config.get("row_colors", PALETTE["row_colors"])
    if len(rows) != 4 or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in colors + rows):
        raise ValueError("Colors must use the #RRGGBB format.")
    temporary = ROOT / (".config-" + str(os.getpid()) + ".tmp")
    try:
        temporary.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if expected_digest is not None and digest() != expected_digest:
            raise RuntimeError("The settings file changed outside this window. Reload the saved settings before saving again.")
        os.replace(temporary, ROOT / "config.json")
    finally:
        temporary.unlink(missing_ok=True)
