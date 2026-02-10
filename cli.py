"""CLI interface: argparse, command dispatch, progress output."""

import argparse
import sys
from pathlib import Path

from obsidibear import __version__
from obsidibear.config import Config, load_config, save_config
from obsidibear.exporter import export_all, pull_changes
from obsidibear.pusher import push_changes


def main():
    parser = argparse.ArgumentParser(
        prog="obsidibear",
        description="Bear ↔ Obsidian sync tool",
    )
    parser.add_argument(
        "--version", action="version", version=f"obsidibear {__version__}"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_p = sub.add_parser("init", help="Export all Bear notes to Obsidian vault")
    init_p.add_argument("vault_path", type=str, help="Path to Obsidian vault")
    init_p.add_argument(
        "--bear-db", type=str, default=None,
        help="Override Bear database path",
    )

    # status
    status_p = sub.add_parser("status", help="Show changes since last sync")
    status_p.add_argument(
        "--vault", type=str, default=None,
        help="Path to vault (default: current directory)",
    )

    # pull
    pull_p = sub.add_parser("pull", help="Pull new/changed Bear notes into vault")
    pull_p.add_argument(
        "--vault", type=str, default=None,
        help="Path to vault (default: current directory)",
    )

    # push
    push_p = sub.add_parser("push", help="Push Obsidian edits back to Bear")
    push_p.add_argument(
        "--vault", type=str, default=None,
        help="Path to vault (default: current directory)",
    )
    push_p.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be pushed without doing it",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        cmd_init(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "pull":
        cmd_pull(args)
    elif args.command == "push":
        cmd_push(args)


def _log(msg: str):
    print(msg)


def _resolve_vault(vault_arg: str = None) -> Path:
    """Resolve vault path from argument or current directory."""
    if vault_arg:
        return Path(vault_arg).expanduser().resolve()

    # Look for .obsidibear.json in current directory or parents
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / ".obsidibear.json").exists():
            return p

    print("Error: No vault found. Run 'python3 run.py init <path>' first,")
    print("or use --vault to specify the vault path.")
    sys.exit(1)


def cmd_init(args):
    vault = Path(args.vault_path).expanduser().resolve()
    print(f"Initializing Obsidian vault at: {vault}")

    config = Config(vault_path=vault, bear_db_path=args.bear_db)
    vault.mkdir(parents=True, exist_ok=True)
    save_config(config)

    stats = export_all(config, progress=_log)

    if stats["errors"]:
        print(f"\n{len(stats['errors'])} errors:")
        for err in stats["errors"][:10]:
            print(f"  - {err}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")


def cmd_status(args):
    vault = _resolve_vault(args.vault)
    config = load_config(vault)

    db_path = Path(config.bear_db_path) if config.bear_db_path else None

    from obsidibear.bear_db import fetch_all_notes, open_bear_db
    from obsidibear.sync_state import SyncStateManager, content_hash

    conn = open_bear_db(db_path)
    state = SyncStateManager(vault)

    try:
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

        if not any([
            changes.bear_changed, changes.obsidian_changed,
            changes.conflicts, changes.new_in_bear, changes.deleted_in_bear,
        ]):
            print("Everything up to date.")
            return

        if changes.new_in_bear:
            print(f"\nNew in Bear ({len(changes.new_in_bear)}):")
            for bid in changes.new_in_bear[:20]:
                note = notes_by_id.get(bid)
                title = note.title if note else bid
                print(f"  + {title}")
            if len(changes.new_in_bear) > 20:
                print(f"  ... and {len(changes.new_in_bear) - 20} more")

        if changes.bear_changed:
            print(f"\nChanged in Bear ({len(changes.bear_changed)}):")
            for bid in changes.bear_changed[:20]:
                note = notes_by_id.get(bid)
                title = note.title if note else bid
                ns = state.get_note(bid)
                path = ns.file_path if ns else "?"
                print(f"  ↓ {title}  ({path})")

        if changes.obsidian_changed:
            print(f"\nChanged in Obsidian ({len(changes.obsidian_changed)}):")
            for bid in changes.obsidian_changed[:20]:
                ns = state.get_note(bid)
                note = notes_by_id.get(bid)
                title = note.title if note else bid
                path = ns.file_path if ns else "?"
                print(f"  ↑ {title}  ({path})")

        if changes.conflicts:
            print(f"\nConflicts ({len(changes.conflicts)}):")
            for bid in changes.conflicts:
                note = notes_by_id.get(bid)
                title = note.title if note else bid
                print(f"  ⚠ {title}  (changed in both)")

        if changes.deleted_in_bear:
            print(f"\nDeleted from Bear ({len(changes.deleted_in_bear)}):")
            for bid in changes.deleted_in_bear[:20]:
                ns = state.get_note(bid)
                path = ns.file_path if ns else bid
                print(f"  - {path}")

        # Summary
        total = (
            len(changes.bear_changed) + len(changes.obsidian_changed) +
            len(changes.conflicts) + len(changes.new_in_bear) +
            len(changes.deleted_in_bear)
        )
        print(f"\n{total} changes total.")
        if changes.bear_changed or changes.new_in_bear:
            print("Run 'python3 run.py pull' to sync Bear → Obsidian")
        if changes.obsidian_changed:
            print("Run 'python3 run.py push' to sync Obsidian → Bear")

    finally:
        conn.close()


def cmd_pull(args):
    vault = _resolve_vault(args.vault)
    config = load_config(vault)
    stats = pull_changes(config, progress=_log)

    if stats["errors"]:
        print(f"\n{len(stats['errors'])} errors:")
        for err in stats["errors"][:10]:
            print(f"  - {err}")


def cmd_push(args):
    vault = _resolve_vault(args.vault)
    config = load_config(vault)
    stats = push_changes(config, progress=_log, dry_run=args.dry_run)

    if stats["errors"]:
        print(f"\n{len(stats['errors'])} errors:")
        for err in stats["errors"][:10]:
            print(f"  - {err}")
