# Obsidibear

Bear <-> Obsidian two-way sync. Exports your Bear notes to an Obsidian vault as markdown files, tracks changes on both sides, and pushes edits back to Bear.

Zero external dependencies — Python 3.10+ stdlib only.

## Quick Start

```bash
# From the obsidibear directory:
python3 run.py init ~/obsidian-vault

# Open the vault in Obsidian, then check for changes anytime
python3 run.py status --vault ~/obsidian-vault

# Pull new/changed Bear notes into the vault
python3 run.py pull --vault ~/obsidian-vault

# Push Obsidian edits back to Bear
python3 run.py push --vault ~/obsidian-vault
```

## Commands

### `init <vault_path>`

First-time export. Creates the vault directory, exports all non-trashed/non-encrypted Bear notes, copies attachments, and writes sync state.

```bash
python3 run.py init ~/obsidian-vault
python3 run.py init ~/obsidian-vault --bear-db /path/to/database.sqlite  # custom DB path
```

### `status`

Shows what changed since last sync — Bear-side changes, Obsidian-side edits, conflicts, new notes, and deletions.

```bash
python3 run.py status                       # auto-finds vault from cwd
python3 run.py status --vault ~/obsidian-vault
```

### `pull`

Pulls new and modified Bear notes into the vault. Skips conflicts (changed on both sides) and warns you.

```bash
python3 run.py pull --vault ~/obsidian-vault
```

### `push`

Pushes Obsidian edits back to Bear via `bear://x-callback-url`. Bear must be installed. Runs in background (`open -g`) with a 0.5s delay between notes.

```bash
python3 run.py push --vault ~/obsidian-vault
python3 run.py push --vault ~/obsidian-vault --dry-run  # preview only
```

## How It Works

### Folder Structure

Bear tags map to folders. A note tagged `#areas/dynatrace/otel` goes in `areas/dynatrace/otel/`. Multi-tagged notes use the first `#tag` found in content. Untagged notes go in `_untagged/`.

### Notes Look the Same

Tags stay inline — both Bear and Obsidian support `#tag/subtag`. Wiki-links `[[note]]` work in both. The only addition is YAML frontmatter with `bear_id` (stripped before pushing back to Bear):

```yaml
---
bear_id: UUID-HERE
created: 2024-07-09T14:27:11
modified: 2024-12-30T10:21:32
archived: false
pinned: false
---
```

### Change Detection

Sync state (`.obsidibear_state.json`) stores SHA-256 hashes of both Bear and Obsidian content for each note:

- Bear hash differs -> Bear changed (pull)
- Obsidian hash differs -> Obsidian changed (push)
- Both differ -> conflict (skipped with warning)

### Attachments

Images and files are copied from Bear's storage to `_attachments/` folders alongside notes. Image references in markdown are rewritten to relative paths.

## Config

`.obsidibear.json` in the vault root:

```json
{
  "vault_path": "/Users/you/obsidian-vault",
  "exclude_tags": ["private"],
  "push_delay": 0.5
}
```

## Project Structure

```
obsidibear/
    __init__.py          # Package, version
    __main__.py          # python -m obsidibear
    cli.py               # argparse, command dispatch
    config.py            # .obsidibear.json management
    bear_db.py           # Read-only SQLite access to Bear DB
    exporter.py          # Bear -> Obsidian export + pull
    pusher.py            # Obsidian -> Bear via x-callback-url
    sync_state.py        # .obsidibear_state.json, change detection
    markdown.py          # Content conversion, frontmatter
    filenames.py         # Title sanitization, dedup
    attachments.py       # Image/file copying
```
