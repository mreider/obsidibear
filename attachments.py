"""Copy images and files from Bear storage to Obsidian vault."""

import re
import shutil
from pathlib import Path
from typing import Dict, List

from obsidibear.bear_db import BearAttachment


def build_attachment_map(
    attachments: List[BearAttachment],
    note_folder: Path,
) -> Dict[str, str]:
    """Build a mapping of Bear image references to Obsidian relative paths.

    Returns:
        Dict mapping Bear-style references to Obsidian-relative paths.
    """
    mapping = {}
    for att in attachments:
        if att.source_path and att.source_path.exists():
            obsidian_rel = f"_attachments/{att.filename}"
            # Bear uses [image:UUID/filename] syntax in some cases,
            # and also standard markdown ![](path) references
            bear_ref = f"{att.uuid}/{att.filename}"
            mapping[bear_ref] = obsidian_rel
    return mapping


def copy_attachments(
    attachments: List[BearAttachment],
    note_folder: Path,
) -> int:
    """Copy attachment files from Bear storage to the note's _attachments folder.

    Returns:
        Number of files copied.
    """
    copied = 0
    for att in attachments:
        if not att.source_path or not att.source_path.exists():
            continue

        dest_dir = note_folder / "_attachments"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / att.filename

        if not dest.exists() or dest.stat().st_size != att.source_path.stat().st_size:
            shutil.copy2(att.source_path, dest)
            copied += 1

    return copied


def reverse_attachment_map(mapping: Dict[str, str]) -> Dict[str, str]:
    """Reverse the attachment mapping for Obsidian→Bear conversion."""
    return {v: k for k, v in mapping.items()}
