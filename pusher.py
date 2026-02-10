"""Push Obsidian edits back to Bear via x-callback-url."""

import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

from obsidibear.bear_db import fetch_note_by_uuid, open_bear_db
from obsidibear.config import Config
from obsidibear.markdown import strip_frontmatter
from obsidibear.sync_state import SyncStateManager, content_hash


def push_changes(
    config: Config,
    progress: Optional[Callable[[str], None]] = None,
    dry_run: bool = False,
) -> dict:
    """Push Obsidian-modified notes back to Bear.

    Returns:
        Dict with stats: pushed, conflicts, errors.
    """
    def log(msg: str):
        if progress:
            progress(msg)

    vault = config.vault_path
    db_path = Path(config.bear_db_path) if config.bear_db_path else None
    conn = open_bear_db(db_path)
    state = SyncStateManager(vault)

    stats = {"pushed": 0, "conflicts": 0, "skipped": 0, "errors": []}

    try:
        # Build current hashes from Bear and Obsidian
        from obsidibear.bear_db import fetch_all_notes

        notes = fetch_all_notes(conn)
        notes_by_id = {n.uuid: n for n in notes}
        bear_hashes = {n.uuid: content_hash(n.text) for n in notes}

        obs_hashes = {}
        for bear_id, ns in state.all_notes().items():
            fp = vault / ns.file_path
            if fp.exists():
                obs_hashes[bear_id] = content_hash(
                    fp.read_text(encoding="utf-8")
                )

        changes = state.detect_changes(bear_hashes, obs_hashes)

        # Report conflicts
        for bid in changes.conflicts:
            note = notes_by_id.get(bid)
            title = note.title if note else bid
            log(f"  CONFLICT: {title} (changed in both Bear and Obsidian — skipping)")
            stats["conflicts"] += 1

        # Push Obsidian changes
        for bid in changes.obsidian_changed:
            ns = state.get_note(bid)
            if not ns:
                continue

            fp = vault / ns.file_path
            if not fp.exists():
                stats["errors"].append(f"File missing: {ns.file_path}")
                continue

            obsidian_content = fp.read_text(encoding="utf-8")
            bear_content = strip_frontmatter(obsidian_content)

            note = notes_by_id.get(bid)
            title = note.title if note else ns.file_path

            if dry_run:
                log(f"  Would push: {title}")
                stats["pushed"] += 1
                continue

            try:
                log(f"  Pushing: {title}")
                _push_to_bear(bid, bear_content)
                time.sleep(config.push_delay)

                # Verify by re-reading from Bear
                conn2 = open_bear_db(db_path)
                try:
                    updated = fetch_note_by_uuid(conn2, bid)
                    if updated:
                        new_bear_hash = content_hash(updated.text)
                        state.set_note(
                            bear_id=bid,
                            file_path=ns.file_path,
                            bear_hash=new_bear_hash,
                            obsidian_hash=content_hash(obsidian_content),
                        )
                        stats["pushed"] += 1
                    else:
                        stats["errors"].append(f"Verify failed for: {title}")
                finally:
                    conn2.close()

            except Exception as e:
                stats["errors"].append(f"Push {title}: {e}")

        state.save()
        log(f"Push complete: {stats['pushed']} pushed, "
            f"{stats['conflicts']} conflicts")

    finally:
        conn.close()

    return stats


def _push_to_bear(bear_id: str, content: str):
    """Push content to Bear via x-callback-url.

    Uses `open -g` to keep Bear in background.
    """
    encoded_text = urllib.parse.quote(content, safe="")
    url = (
        f"bear://x-callback-url/add-text"
        f"?id={bear_id}"
        f"&mode=replace_all"
        f"&text={encoded_text}"
    )
    subprocess.run(
        ["open", "-g", url],
        check=True,
        capture_output=True,
    )
