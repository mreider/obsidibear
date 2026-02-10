"""Read-only SQLite access to Bear's database."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Core Data epoch offset (2001-01-01 00:00:00 UTC)
CORE_DATA_EPOCH = 978307200

# Default Bear DB location
BEAR_DB_PATH = Path.home() / (
    "Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear"
    "/Application Data/database.sqlite"
)

# Bear local files (attachments)
BEAR_FILES_PATH = Path.home() / (
    "Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear"
    "/Application Data/Local Files/Note Images"
)


@dataclass
class BearAttachment:
    uuid: str
    filename: str
    source_path: Optional[Path] = None


@dataclass
class BearNote:
    uuid: str
    title: str
    text: str
    created: float  # Unix timestamp
    modified: float  # Unix timestamp
    archived: bool
    pinned: bool
    tags: List[str] = field(default_factory=list)
    attachments: List[BearAttachment] = field(default_factory=list)


def _core_data_to_unix(ts: Optional[float]) -> float:
    """Convert Core Data timestamp to Unix timestamp."""
    if ts is None:
        return 0.0
    return ts + CORE_DATA_EPOCH


def open_bear_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open Bear's database in read-only mode."""
    path = db_path or BEAR_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Bear database not found at: {path}")
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all_notes(conn: sqlite3.Connection) -> List[BearNote]:
    """Fetch all active (non-trashed, non-encrypted) notes from Bear."""
    cursor = conn.execute("""
        SELECT
            Z_PK,
            ZUNIQUEIDENTIFIER,
            ZTITLE,
            ZTEXT,
            ZCREATIONDATE,
            ZMODIFICATIONDATE,
            ZARCHIVED,
            ZPINNED
        FROM ZSFNOTE
        WHERE ZTRASHED = 0
          AND (ZENCRYPTED = 0 OR ZENCRYPTED IS NULL)
    """)

    notes_by_pk = {}
    notes = []

    for row in cursor:
        note = BearNote(
            uuid=row["ZUNIQUEIDENTIFIER"],
            title=row["ZTITLE"] or "Untitled",
            text=row["ZTEXT"] or "",
            created=_core_data_to_unix(row["ZCREATIONDATE"]),
            modified=_core_data_to_unix(row["ZMODIFICATIONDATE"]),
            archived=bool(row["ZARCHIVED"]),
            pinned=bool(row["ZPINNED"]),
        )
        notes_by_pk[row["Z_PK"]] = note
        notes.append(note)

    # Fetch tags via join table
    tag_cursor = conn.execute("""
        SELECT jt.Z_5NOTES AS note_pk, t.ZTITLE AS tag_title
        FROM Z_5TAGS jt
        JOIN ZSFNOTETAG t ON jt.Z_13TAGS = t.Z_PK
    """)
    for row in tag_cursor:
        note = notes_by_pk.get(row["note_pk"])
        if note:
            note.tags.append(row["tag_title"])

    # Deduplicate tags (keep unique, preserve order)
    for note in notes:
        seen = set()
        deduped = []
        for tag in note.tags:
            if tag not in seen:
                seen.add(tag)
                deduped.append(tag)
        note.tags = deduped

    # Fetch attachments
    att_cursor = conn.execute("""
        SELECT ZNOTE, ZUNIQUEIDENTIFIER, ZFILENAME
        FROM ZSFNOTEFILE
        WHERE ZFILENAME IS NOT NULL
    """)
    for row in att_cursor:
        note = notes_by_pk.get(row["ZNOTE"])
        if note:
            att_uuid = row["ZUNIQUEIDENTIFIER"]
            filename = row["ZFILENAME"]
            source = BEAR_FILES_PATH / att_uuid / filename
            note.attachments.append(BearAttachment(
                uuid=att_uuid,
                filename=filename,
                source_path=source if source.exists() else None,
            ))

    return notes


def fetch_note_by_uuid(conn: sqlite3.Connection, uuid: str) -> Optional[BearNote]:
    """Fetch a single note by its UUID."""
    cursor = conn.execute("""
        SELECT
            Z_PK,
            ZUNIQUEIDENTIFIER,
            ZTITLE,
            ZTEXT,
            ZCREATIONDATE,
            ZMODIFICATIONDATE,
            ZARCHIVED,
            ZPINNED
        FROM ZSFNOTE
        WHERE ZUNIQUEIDENTIFIER = ?
          AND ZTRASHED = 0
          AND (ZENCRYPTED = 0 OR ZENCRYPTED IS NULL)
    """, (uuid,))

    row = cursor.fetchone()
    if not row:
        return None

    note = BearNote(
        uuid=row["ZUNIQUEIDENTIFIER"],
        title=row["ZTITLE"] or "Untitled",
        text=row["ZTEXT"] or "",
        created=_core_data_to_unix(row["ZCREATIONDATE"]),
        modified=_core_data_to_unix(row["ZMODIFICATIONDATE"]),
        archived=bool(row["ZARCHIVED"]),
        pinned=bool(row["ZPINNED"]),
    )

    pk = row["Z_PK"]

    # Tags
    tag_cursor = conn.execute("""
        SELECT t.ZTITLE AS tag_title
        FROM Z_5TAGS jt
        JOIN ZSFNOTETAG t ON jt.Z_13TAGS = t.Z_PK
        WHERE jt.Z_5NOTES = ?
    """, (pk,))
    seen = set()
    for trow in tag_cursor:
        tag = trow["tag_title"]
        if tag not in seen:
            seen.add(tag)
            note.tags.append(tag)

    # Attachments
    att_cursor = conn.execute("""
        SELECT ZUNIQUEIDENTIFIER, ZFILENAME
        FROM ZSFNOTEFILE
        WHERE ZNOTE = ? AND ZFILENAME IS NOT NULL
    """, (pk,))
    for arow in att_cursor:
        att_uuid = arow["ZUNIQUEIDENTIFIER"]
        filename = arow["ZFILENAME"]
        source = BEAR_FILES_PATH / att_uuid / filename
        note.attachments.append(BearAttachment(
            uuid=att_uuid,
            filename=filename,
            source_path=source if source.exists() else None,
        ))

    return note
