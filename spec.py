# -*- coding: utf-8 -*-
"""
Icon alias mappings for shortcut / activity components that don't appear
in appfilter.xml but need dedicated icon files inside the icons zip.

Format:
    "target_filename_stem": "source_drawable_stem",

Effect:
    The PNG for `source` is copied and written as `target.png` into
    res/drawable-xxhdpi/ inside the icons zip.

Contributing:
    Add one line per alias. Use comments to explain non-obvious entries.
    PRs welcome — keep entries sorted alphabetically by target name.
"""

ALIASES: dict[str, str] = {
    # Dialer shortcut lives as an activity under the Contacts package.
    # Source is the already-converted package-name icon for the dialer.
    "com.android.contacts.activities.TwelveKeyDialer": "com.android.dialer",

    # Add further aliases below, e.g.:
    # "com.example.app.SomeActivity": "some_icon",
}