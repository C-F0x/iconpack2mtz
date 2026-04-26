# -*- coding: utf-8 -*-
"""
Shared constants, logging setup, and small utility functions.
"""

import logging
import re
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_EXT   = (".apk", ".apks", ".xapk")
ICON_THRESHOLD  = 10          # minimum PNGs in a drawable dir to be considered valid

DENSITY_RANK = {
    "xxxhdpi": 7, "xxhdpi": 6, "xhdpi": 5,
    "hdpi": 4,    "mdpi": 3,   "ldpi": 2,
    "nodpi": 1,   "": 0,
}

# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """Configure and return the root application logger."""
    log = logging.getLogger("mtz_builder")
    if log.handlers:          # already configured (e.g. re-import in tests)
        return log

    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler("process.log", encoding="utf-8", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    log.addHandler(fh)
    log.addHandler(ch)

    # Suppress androguard noise
    logging.getLogger("androguard").setLevel(logging.ERROR)

    return log


log = setup_logging()


# ── Small helpers ─────────────────────────────────────────────────────────────

def drawable_density_rank(dir_name: str) -> int:
    """Return sort key for a drawable directory name (higher = better quality)."""
    m = re.search(r"drawable-([a-z]+)", dir_name)
    key = m.group(1) if m else ""
    return DENSITY_RANK.get(key, 0)


def clean_stem(filename: str) -> str:
    """
    Derive a human-readable name from a raw filename.
    Strips extension and common version-noise suffixes.
    """
    stem = Path(filename).stem
    stem = re.sub(r"[_\s]v\d[\d.]*.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s*\(.*?\)\s*$", "", stem)
    return stem.strip() or Path(filename).stem
