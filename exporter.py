"""Bear → Obsidian export orchestration."""

from pathlib import Path
from typing import Callable, List, Optional

from obsidibear.attachments import build_attachment_map, copy_attachments
from obsidibear.bear_db import BearNote, fetch_all_notes, open_bear_db
from obsidibear.config import Config
from obsidibear.filenames import FilenameDeduplicator
from obsidibear.markdown import bear_to_obsidian, extract_primary_tag
from obsidibear.sync_state import SyncStateManager, content_hash


def tag_to_folder(tag: str) -> Path:
    """Convert a Bear tag path to a folder path.

    Example: 'areas/dynatrace/otel' → Path('areas/dynatrace/otel')
    """
    # Tags may have leading / or # — strip those
    clean = tag.strip("#/").strip()
    if not clean:
        return Path("_untagged")
    return Path(clean)


def export_all(
    config: Config,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Export all Bear notes to the Obsidian vault.

    Args:
        config: Configuration with vault path.
        progress: Optional callback for progress messages.

    Returns:
        Dict with stats: notes_exported, attachments_copied, errors.
    """
    def log(msg: str):
        if progress:
            progress(msg)

    vault = config.vault_path
    vault.mkdir(parents=True, exist_ok=True)

    db_path = Path(config.bear_db_path) if config.bear_db_path else None
    conn = open_bear_db(db_path)
    state = SyncStateManager(vault)
    dedup = FilenameDeduplicator()

    stats = {"notes_exported": 0, "attachments_copied": 0, "errors": []}

    try:
        notes = fetch_all_notes(conn)
        log(f"Found {len(notes)} notes in Bear")

        exclude = set(config.exclude_tags)

        for note in notes:
            # Skip excluded tags
            if exclude and any(t in exclude for t in note.tags):
                continue

            try:
                _export_note(note, vault, state, dedup)
                stats["notes_exported"] += 1

                # Copy attachments
                if note.attachments:
                    primary_tag = extract_primary_tag(note.text, note.tags)
                    folder = vault / (tag_to_folder(primary_tag) if primary_tag else Path("_untagged"))
                    copied = copy_attachments(note.attachments, folder)
                    stats["attachments_copied"] += copied

                if stats["notes_exported"] % 25 == 0:
                    log(f"  Exported {stats['notes_exported']} notes...")

            except Exception as e:
                stats["errors"].append(f"{note.title}: {e}")

        state.save()
        log(f"Export complete: {stats['notes_exported']} notes, "
            f"{stats['attachments_copied']} attachments")

    finally:
        conn.close()

    return stats


def export_note(
    note: BearNote,
    vault: Path,
    state: SyncStateManager,
    dedup: FilenameDeduplicator,
):
    """Export a single Bear note (public wrapper)."""
    _export_note(note, vault, state, dedup)


def _export_note(
    note: BearNote,
    vault: Path,
    state: SyncStateManager,
    dedup: FilenameDeduplicator,
):
    """Export a single Bear note to the vault."""
    # Determine folder from primary tag
    primary_tag = extract_primary_tag(note.text, note.tags)
    if primary_tag:
        folder = vault / tag_to_folder(primary_tag)
    else:
        folder = vault / "_untagged"

    folder.mkdir(parents=True, exist_ok=True)

    # Build attachment mapping
    att_map = build_attachment_map(note.attachments, folder)

    # Convert content
    obsidian_content = bear_to_obsidian(
        text=note.text,
        bear_id=note.uuid,
        created=note.created,
        modified=note.modified,
        archived=note.archived,
        pinned=note.pinned,
        attachment_map=att_map,
    )

    # Get unique file path
    file_path = dedup.get_unique_path(folder, note.title)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    file_path.write_text(obsidian_content, encoding="utf-8")

    # Update sync state
    bear_hash = content_hash(note.text)
    obs_hash = content_hash(obsidian_content)
    rel_path = str(file_path.relative_to(vault))

    state.set_note(
        bear_id=note.uuid,
        file_path=rel_path,
        bear_hash=bear_hash,
        obsidian_hash=obs_hash,
    )


def pull_changes(
    config: Config,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Pull new and changed notes from Bear into the vault.

    Returns:
        Dict with stats: pulled, new, conflicts, errors.
    """
    def log(msg: str):
        if progress:
            progress(msg)

    vault = config.vault_path
    db_path = Path(config.bear_db_path) if config.bear_db_path else None
    conn = open_bear_db(db_path)
    state = SyncStateManager(vault)
    dedup = FilenameDeduplicator()

    stats = {"pulled": 0, "new": 0, "conflicts": 0, "errors": []}

    try:
        notes = fetch_all_notes(conn)
        notes_by_id = {n.uuid: n for n in notes}
        exclude = set(config.exclude_tags)

        # Register existing files in dedup to avoid collisions
        for ns in state.all_notes().values():
            p = Path(ns.file_path)
            dedup.get_unique_path(vault / p.parent, p.stem)

        # Build current hashes
        bear_hashes = {}
        obs_hashes = {}
        for note in notes:
            if exclude and any(t in exclude for t in note.tags):
                continue
            bear_hashes[note.uuid] = content_hash(note.text)

        for bear_id, ns in state.all_notes().items():
            fp = vault / ns.file_path
            if fp.exists():
                obs_hashes[bear_id] = content_hash(
                    fp.read_text(encoding="utf-8")
                )

        changes = state.detect_changes(bear_hashes, obs_hashes)

        # Handle new notes
        for bid in changes.new_in_bear:
            note = notes_by_id.get(bid)
            if not note:
                continue
            if exclude and any(t in exclude for t in note.tags):
                continue
            try:
                _export_note(note, vault, state, dedup)
                stats["new"] += 1
            except Exception as e:
                stats["errors"].append(f"New {note.title}: {e}")

        # Handle Bear-side changes
        for bid in changes.bear_changed:
            note = notes_by_id.get(bid)
            if not note:
                continue
            ns = state.get_note(bid)
            if not ns:
                continue
            try:
                # Re-export to the same file path
                file_path = vault / ns.file_path
                att_map = build_attachment_map(note.attachments, file_path.parent)
                obsidian_content = bear_to_obsidian(
                    text=note.text,
                    bear_id=note.uuid,
                    created=note.created,
                    modified=note.modified,
                    archived=note.archived,
                    pinned=note.pinned,
                    attachment_map=att_map,
                )
                file_path.write_text(obsidian_content, encoding="utf-8")

                state.set_note(
                    bear_id=note.uuid,
                    file_path=ns.file_path,
                    bear_hash=content_hash(note.text),
                    obsidian_hash=content_hash(obsidian_content),
                )
                stats["pulled"] += 1

                if note.attachments:
                    copy_attachments(note.attachments, file_path.parent)

            except Exception as e:
                stats["errors"].append(f"Pull {note.title}: {e}")

        # Report conflicts
        for bid in changes.conflicts:
            note = notes_by_id.get(bid)
            title = note.title if note else bid
            log(f"  CONFLICT: {title} (changed in both Bear and Obsidian)")
            stats["conflicts"] += 1

        state.save()
        log(f"Pull complete: {stats['pulled']} updated, {stats['new']} new, "
            f"{stats['conflicts']} conflicts")

    finally:
        conn.close()

    return stats
