# -*- coding: utf-8 -*-
"""
HyperOS MTZ Theme Builder
Entry point — orchestrates file selection, APK parsing, image generation, and packaging.
1
Usage:
    python main.py

Requires:
    pip install androguard Pillow numpy
"""

import sys

from utils import SCRIPT_DIR, log
from file  import select_package, open_apk_zip, parse_appfilter, build_drawable_pool
from pic   import build_previews
from mtz   import build_icons_zip, build_mtz


def main() -> None:
    print("=" * 52)
    print("  HyperOS MTZ Theme Builder")
    print("=" * 52)

    # 1. Select package file interactively
    chosen, app_name = select_package()

    # 2. Open as a ZipFile (handles .apk / .apks / .xapk transparently)
    log.info("Loading package…")
    print(f"\n[INFO] Loading {chosen.name}…")
    apk_zip = open_apk_zip(chosen)

    # 3. Parse component → drawable mappings from appfilter.xml
    log.info("Parsing appfilter.xml…")
    print("[INFO] Parsing appfilter.xml…")
    pkg_map = parse_appfilter(apk_zip)

    # 4. Build drawable pool from all valid density directories
    log.info("Scanning drawable directories…")
    print("[INFO] Scanning drawable directories…")
    pool = build_drawable_pool(apk_zip)

    # 5. Build the inner icons zip
    log.info("Building icons zip…")
    print("[INFO] Building icons zip…")
    icons_bytes = build_icons_zip(pkg_map, pool)

    # 6. Generate preview images
    log.info("Generating preview images…")
    print("[INFO] Generating preview images…")
    previews = build_previews(pool)

    # 7. Assemble the final MTZ (no template)
    log.info("Assembling MTZ…")
    print("[INFO] Assembling MTZ…")
    mtz_bytes = build_mtz(app_name, icons_bytes, previews)

    # 8. Write output
    out_path = SCRIPT_DIR / f"{app_name}.mtz"
    out_path.write_bytes(mtz_bytes)

    size_mb = len(mtz_bytes) / 1_048_576
    log.info(f"Done → {out_path.name} ({size_mb:.1f} MB)")
    print(f"\n  Output: {out_path.name}  ({size_mb:.1f} MB)")
    print("  Log:    process.log")
    input("\nPress Enter to exit…")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)
