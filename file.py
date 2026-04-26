# -*- coding: utf-8 -*-
"""
Package file discovery, app-name resolution, APK loading, and content parsing.
Supports .apk, .apks, and .xapk formats.
"""

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from utils import SCRIPT_DIR, SUPPORTED_EXT, ICON_THRESHOLD, drawable_density_rank, clean_stem, log

try:
    from androguard.core.apk import APK as AndroAPK
except ImportError:
    try:
        from androguard.core.bytecodes.apk import APK as AndroAPK
    except ImportError:
        AndroAPK = None

try:
    from androguard.core.axml import AXMLPrinter
except ImportError:
    AXMLPrinter = None


# ── File discovery ────────────────────────────────────────────────────────────

def scan_package_files() -> list[Path]:
    """Return sorted list of supported package files in SCRIPT_DIR."""
    return sorted(p for p in SCRIPT_DIR.iterdir() if p.suffix.lower() in SUPPORTED_EXT)


# ── App-name resolution ───────────────────────────────────────────────────────

def _name_from_manifest_json(filepath: Path) -> str | None:
    """Read 'name' field from manifest.json inside an .apks/.xapk bundle."""
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            if "manifest.json" not in zf.namelist():
                return None
            data = json.loads(zf.read("manifest.json"))
            name = str(data.get("name", "")).strip()
            return name or None
    except Exception:
        return None


def _name_from_androguard(apk_bytes: bytes) -> str | None:
    """Use androguard to read the app label from raw APK bytes."""
    if AndroAPK is None:
        return None
    try:
        apk = AndroAPK(apk_bytes, raw=True)
        name = apk.get_app_name().strip()
        return name if (name and not name.startswith("@")) else None
    except Exception as e:
        log.debug(f"androguard get_app_name: {e}")
        return None


def resolve_name(filepath: Path) -> tuple[str, str]:
    """
    Return (app_name, source_label).
    Resolution order:
      1. manifest.json  (bundles only)
      2. AndroidManifest.xml via androguard
      3. filename stem fallback
    """
    ext = filepath.suffix.lower()

    if ext in (".apks", ".xapk"):
        name = _name_from_manifest_json(filepath)
        if name:
            return name, "manifest.json"
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                if "base.apk" in zf.namelist():
                    name = _name_from_androguard(zf.read("base.apk"))
                    if name:
                        return name, "AndroidManifest.xml"
        except Exception:
            pass

    elif ext == ".apk":
        try:
            name = _name_from_androguard(filepath.read_bytes())
            if name:
                return name, "AndroidManifest.xml"
        except Exception:
            pass

    return clean_stem(filepath.name), "filename"


# ── Interactive selection ─────────────────────────────────────────────────────

def select_package() -> tuple[Path, str]:
    """Interactive CLI loop. Returns (chosen_path, app_name)."""
    while True:
        files = scan_package_files()
        if not files:
            print("\nNo .apk / .apks / .xapk found in this directory.")
            input("Place files here and press Enter to retry...")
            continue

        print("\nDetected packages (resolving names…)")
        entries: list[tuple[Path, str, str]] = []
        for fp in files:
            name, source = resolve_name(fp)
            entries.append((fp, name, source))

        print()
        for i, (fp, name, source) in enumerate(entries, 1):
            ext_note = "(base.apk)" if fp.suffix.lower() in (".apks", ".xapk") else ""
            print(f"  [{i}] {fp.name} {ext_note}".rstrip())
            print(f"       └─ \"{name}\"  [{source}]")

        raw = input("\nSelect number and press Enter: ").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(entries)):
            print(f"  Invalid input. Enter a number between 1 and {len(entries)}.")
            continue

        chosen_path, app_name, source = entries[int(raw) - 1]
        log.info(f"Selected: {chosen_path.name} | name=\"{app_name}\" | source={source}")
        return chosen_path, app_name


# ── APK loading ───────────────────────────────────────────────────────────────

def load_base_apk_bytes(filepath: Path) -> bytes:
    """
    Return raw APK bytes ready for zipfile parsing.
    For bundles (.apks/.xapk) the inner base.apk is extracted automatically.
    """
    if filepath.suffix.lower() == ".apk":
        return filepath.read_bytes()
    with zipfile.ZipFile(filepath, "r") as zf:
        if "base.apk" not in zf.namelist():
            raise FileNotFoundError(f"No base.apk inside {filepath.name}")
        return zf.read("base.apk")


def open_apk_zip(filepath: Path) -> zipfile.ZipFile:
    """Load and return an open ZipFile for the base APK."""
    return zipfile.ZipFile(io.BytesIO(load_base_apk_bytes(filepath)))


# ── appfilter.xml ─────────────────────────────────────────────────────────────

def parse_appfilter(apk_zip: zipfile.ZipFile) -> dict[str, str]:
    """
    Parse the icon pack's component→drawable mapping.
    Returns {package_name: drawable_stem}.

    Lookup order:
      1. assets/appfilter.xml  (plain UTF-8 text)
      2. res/xml/appfilter.xml (binary AXML, decoded via androguard)

    Duplicate package entries are skipped (first wins).
    """
    names = apk_zip.namelist()

    if "assets/appfilter.xml" in names:
        xml_text = apk_zip.read("assets/appfilter.xml").decode("utf-8")
        log.info("appfilter.xml source: assets/ (plain text)")

    elif "res/xml/appfilter.xml" in names:
        if AXMLPrinter is None:
            raise RuntimeError(
                "androguard is required to decode binary AXML. "
                "Run: pip install androguard"
            )
        raw    = apk_zip.read("res/xml/appfilter.xml")
        result = AXMLPrinter(raw).get_xml()
        xml_text = result if isinstance(result, str) else result.decode("utf-8")
        log.info("appfilter.xml source: res/xml/ (binary AXML)")

    else:
        raise FileNotFoundError(
            "appfilter.xml not found in assets/appfilter.xml or res/xml/appfilter.xml"
        )

    root    = ET.fromstring(xml_text)
    mapping: dict[str, str] = {}
    seen:    set[str]        = set()

    for item in root.iter("item"):
        component = item.get("component", "")
        drawable  = item.get("drawable", "")
        if not component or not drawable:
            continue
        m = re.search(r"ComponentInfo\{(.*?)/", component)
        if not m:
            continue
        pkg = m.group(1)
        if pkg in seen:
            log.debug(f"Duplicate package skipped: {pkg}")
            continue
        seen.add(pkg)
        mapping[pkg] = drawable

    log.info(f"appfilter.xml: {len(mapping)} unique package→drawable mappings")
    return mapping


# ── Drawable pool ─────────────────────────────────────────────────────────────

def build_drawable_pool(apk_zip: zipfile.ZipFile) -> dict[str, bytes]:
    """
    Scan all res/drawable* directories inside the APK.
    Only directories with more than ICON_THRESHOLD PNGs are kept.
    Higher-density directories override lower-density ones for the same stem.

    Returns {drawable_stem: png_bytes}.
    """
    dir_contents: dict[str, list[str]] = {}
    for path in apk_zip.namelist():
        if not path.startswith("res/drawable"):
            continue
        parts = path.split("/")
        if len(parts) < 3:
            continue
        dir_contents.setdefault(parts[1], []).append(path)

    valid = {
        d: files for d, files in dir_contents.items()
        if sum(1 for f in files if f.endswith(".png")) > ICON_THRESHOLD
    }

    if not valid:
        raise RuntimeError(
            f"No drawable directory with >{ICON_THRESHOLD} PNGs found. "
            "Is this an icon pack APK?"
        )

    log.info(f"Valid drawable dirs ({len(valid)}): {sorted(valid)}")

    pool: dict[str, bytes] = {}
    for d in sorted(valid, key=drawable_density_rank):
        loaded = 0
        for fpath in valid[d]:
            if not fpath.endswith(".png"):
                continue
            try:
                pool[Path(fpath).stem] = apk_zip.read(fpath)
                loaded += 1
            except Exception as e:
                log.debug(f"Read error {fpath}: {e}")
        log.info(f"  {d}: {loaded} PNGs loaded")

    log.info(f"Drawable pool: {len(pool)} unique stems total")
    return pool
