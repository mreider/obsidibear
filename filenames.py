"""Title sanitization and filename deduplication."""

import re
from pathlib import Path
from typing import Dict


# Characters not allowed in filenames on macOS/Windows
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Max filename length (leaving room for extension and dedup suffix)
_MAX_NAME_LEN = 200


def sanitize_title(title: str) -> str:
    """Convert a Bear note title to a safe filename (without extension)."""
    name = title.strip()
    if not name:
        name = "Untitled"

    # Replace invalid characters with underscore
    name = _INVALID_CHARS.sub("_", name)

    # Collapse multiple underscores/spaces
    name = re.sub(r"[_ ]{2,}", " ", name)

    # Strip leading/trailing dots and spaces
    name = name.strip(". ")

    if not name:
        name = "Untitled"

    # Truncate
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN].rstrip(". ")

    return name


class FilenameDeduplicator:
    """Tracks used filenames and deduplicates collisions."""

    def __init__(self):
        self._used: Dict[str, int] = {}  # lowercase path -> count

    def get_unique_path(self, folder: Path, title: str) -> Path:
        """Return a unique .md file path within the given folder."""
        base = sanitize_title(title)
        candidate = folder / f"{base}.md"
        key = str(candidate).lower()

        if key not in self._used:
            self._used[key] = 1
            return candidate

        # Deduplicate with numeric suffix
        self._used[key] += 1
        n = self._used[key]
        candidate = folder / f"{base} {n}.md"
        # Handle the (unlikely) case of cascading collisions
        new_key = str(candidate).lower()
        while new_key in self._used:
            n += 1
            candidate = folder / f"{base} {n}.md"
            new_key = str(candidate).lower()
        self._used[new_key] = 1
        return candidate
