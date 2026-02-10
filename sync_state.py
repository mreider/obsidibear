"""Sync state tracking and change detection."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class NoteState:
    bear_id: str
    file_path: str  # Relative to vault root
    bear_hash: str
    obsidian_hash: str


@dataclass
class ChangeReport:
    bear_changed: List[str]       # bear_ids with Bear-side changes
    obsidian_changed: List[str]   # bear_ids with Obsidian-side changes
    conflicts: List[str]          # bear_ids changed on both sides
    new_in_bear: List[str]        # bear_ids not yet in vault
    deleted_in_bear: List[str]    # bear_ids removed from Bear


def content_hash(text: str) -> str:
    """SHA-256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SyncStateManager:
    """Manages .obsidibear_state.json in the vault root."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.state_file = vault_path / ".obsidibear_state.json"
        self._notes: Dict[str, NoteState] = {}
        self._load()

    def _load(self):
        """Load state from disk."""
        if not self.state_file.exists():
            return
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        for entry in data.get("notes", []):
            state = NoteState(
                bear_id=entry["bear_id"],
                file_path=entry["file_path"],
                bear_hash=entry["bear_hash"],
                obsidian_hash=entry["obsidian_hash"],
            )
            self._notes[state.bear_id] = state

    def save(self):
        """Write state to disk."""
        data = {
            "notes": [
                {
                    "bear_id": s.bear_id,
                    "file_path": s.file_path,
                    "bear_hash": s.bear_hash,
                    "obsidian_hash": s.obsidian_hash,
                }
                for s in sorted(self._notes.values(), key=lambda s: s.file_path)
            ]
        }
        self.state_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def set_note(
        self,
        bear_id: str,
        file_path: str,
        bear_hash: str,
        obsidian_hash: str,
    ):
        """Record or update state for a note."""
        self._notes[bear_id] = NoteState(
            bear_id=bear_id,
            file_path=file_path,
            bear_hash=bear_hash,
            obsidian_hash=obsidian_hash,
        )

    def get_note(self, bear_id: str) -> Optional[NoteState]:
        """Get stored state for a note."""
        return self._notes.get(bear_id)

    def all_notes(self) -> Dict[str, NoteState]:
        """Get all tracked notes."""
        return dict(self._notes)

    def remove_note(self, bear_id: str):
        """Remove a note from tracking."""
        self._notes.pop(bear_id, None)

    def detect_changes(
        self,
        bear_notes: Dict[str, str],  # bear_id -> bear content hash
        obsidian_files: Dict[str, str],  # bear_id -> obsidian content hash
    ) -> ChangeReport:
        """Compare current state against Bear DB and vault files.

        Args:
            bear_notes: Current Bear content hashes by bear_id.
            obsidian_files: Current Obsidian file content hashes by bear_id.

        Returns:
            ChangeReport describing all detected changes.
        """
        bear_changed = []
        obsidian_changed = []
        conflicts = []
        new_in_bear = []
        deleted_in_bear = []

        all_bear_ids = set(bear_notes.keys())
        all_tracked_ids = set(self._notes.keys())

        # New notes in Bear (not yet tracked)
        for bid in all_bear_ids - all_tracked_ids:
            new_in_bear.append(bid)

        # Deleted from Bear (tracked but no longer in Bear)
        for bid in all_tracked_ids - all_bear_ids:
            deleted_in_bear.append(bid)

        # Check tracked notes for changes
        for bid in all_tracked_ids & all_bear_ids:
            state = self._notes[bid]
            current_bear_hash = bear_notes[bid]
            current_obs_hash = obsidian_files.get(bid, state.obsidian_hash)

            bear_diff = current_bear_hash != state.bear_hash
            obs_diff = current_obs_hash != state.obsidian_hash

            if bear_diff and obs_diff:
                conflicts.append(bid)
            elif bear_diff:
                bear_changed.append(bid)
            elif obs_diff:
                obsidian_changed.append(bid)

        return ChangeReport(
            bear_changed=sorted(bear_changed),
            obsidian_changed=sorted(obsidian_changed),
            conflicts=sorted(conflicts),
            new_in_bear=sorted(new_in_bear),
            deleted_in_bear=sorted(deleted_in_bear),
        )
