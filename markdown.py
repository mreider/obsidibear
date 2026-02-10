"""Content conversion between Bear and Obsidian markdown formats."""

import re
from datetime import datetime, timezone
from typing import List, Optional


# Bear uses U+2800 (Braille blank) as empty-line spacers
_BRAILLE_BLANK = "\u2800"


def bear_to_obsidian(
    text: str,
    bear_id: str,
    created: float,
    modified: float,
    archived: bool,
    pinned: bool,
    attachment_map: Optional[dict] = None,
) -> str:
    """Convert Bear note content to Obsidian-compatible markdown.

    Args:
        text: Raw Bear note text.
        bear_id: Bear UUID for frontmatter.
        created: Unix timestamp.
        modified: Unix timestamp.
        archived: Whether note is archived.
        pinned: Whether note is pinned.
        attachment_map: Optional dict mapping Bear image paths to Obsidian paths.

    Returns:
        Obsidian markdown with YAML frontmatter prepended.
    """
    content = text

    # Replace braille blank spacers with empty lines
    content = content.replace(_BRAILLE_BLANK, "")

    # Convert Bear image references to relative Obsidian paths
    if attachment_map:
        for bear_path, obsidian_path in attachment_map.items():
            content = content.replace(bear_path, obsidian_path)

    # Build frontmatter
    frontmatter = _build_frontmatter(bear_id, created, modified, archived, pinned)

    return frontmatter + content


def obsidian_to_bear(text: str, attachment_map: Optional[dict] = None) -> str:
    """Convert Obsidian markdown back to Bear format.

    Strips YAML frontmatter and reverses image path conversion.
    """
    content = strip_frontmatter(text)

    # Reverse image path conversion
    if attachment_map:
        for obsidian_path, bear_path in attachment_map.items():
            content = content.replace(obsidian_path, bear_path)

    return content


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown text."""
    if not text.startswith("---\n"):
        return text

    end = text.find("\n---\n", 4)
    if end == -1:
        return text

    # Skip the closing --- and the newline after it
    return text[end + 5:]


def extract_bear_id(text: str) -> Optional[str]:
    """Extract bear_id from YAML frontmatter."""
    if not text.startswith("---\n"):
        return None

    end = text.find("\n---\n", 4)
    if end == -1:
        return None

    frontmatter = text[4:end]
    for line in frontmatter.split("\n"):
        if line.startswith("bear_id:"):
            return line.split(":", 1)[1].strip()

    return None


def extract_primary_tag(text: str, tags: List[str]) -> Optional[str]:
    """Find the first #tag in the note content to determine folder placement.

    Scans the note text for inline tags and returns the first one that
    matches one of the note's known tags.
    """
    if not tags:
        return None

    # Build a set for fast lookup
    tag_set = set(tags)

    # Find all #tag references in content (including nested like #area/sub)
    # Bear tags can contain letters, numbers, /, -, _
    for match in re.finditer(r'(?:^|(?<=\s))#([\w/\-]+)', text):
        candidate = match.group(1)
        if candidate in tag_set:
            return candidate
        # Also check if it's a prefix of a nested tag
        for tag in tags:
            if tag == candidate:
                return tag

    # Fallback: return the first tag from the tags list
    return tags[0] if tags else None


def _build_frontmatter(
    bear_id: str,
    created: float,
    modified: float,
    archived: bool,
    pinned: bool,
) -> str:
    """Build YAML frontmatter string."""
    created_dt = datetime.fromtimestamp(created, tz=timezone.utc)
    modified_dt = datetime.fromtimestamp(modified, tz=timezone.utc)

    lines = [
        "---",
        f"bear_id: {bear_id}",
        f"created: {created_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"modified: {modified_dt.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"archived: {'true' if archived else 'false'}",
        f"pinned: {'true' if pinned else 'false'}",
        "---",
        "",
    ]
    return "\n".join(lines)
