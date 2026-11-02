"""Expiry dates, kept in one small file.

An entry is just a name, a date, and an optional category and note.
Everything else in this package is built around that record.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

DEFAULT_DATA_PATH = Path.home() / ".expirylog.json"
DATE_FORMAT = "%Y-%m-%d"


class ExpirylogError(Exception):
    """A problem the user can fix (bad input, bad data file, missing item)."""


class DuplicateEntryError(ExpirylogError):
    """Raised when ``add`` would overwrite an entry without ``--force``."""


class EntryNotFoundError(ExpirylogError):
    """Raised when an entry name matches nothing in the store."""


class CorruptDataError(ExpirylogError):
    """Raised when the data file is not the JSON list we expect."""


@dataclass
class Entry:
    """One thing with an expiry date."""

    name: str
    expires: date
    category: str = ""
    note: str = ""

    def days_left(self, today: date) -> int:
        """Days until expiry; negative once the date has passed."""
        return (self.expires - today).days

    def status(self, today: date, within_days: int) -> str:
        """One of ``overdue``, ``due-soon`` or ``ok`` for this entry."""
        remaining = self.days_left(today)
        if remaining < 0:
            return "overdue"
        if remaining <= within_days:
            return "due-soon"
        return "ok"

    def to_dict(self) -> dict:
        """Serialise, keeping the date as an ISO string."""
        data = asdict(self)
        data["expires"] = self.expires.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        """Parse one stored record, rejecting anything malformed."""
        if not isinstance(data, dict):
            raise CorruptDataError("each record must be a JSON object")
        try:
            name = data["name"]
            expires = date.fromisoformat(data["expires"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CorruptDataError(
                "a record is missing a valid name or expiry date"
            ) from exc
        if not isinstance(name, str) or not name.strip():
            raise CorruptDataError("a record has an empty name")
        return cls(
            name=name,
            expires=expires,
            category=data.get("category", "") or "",
            note=data.get("note", "") or "",
        )


def default_data_path() -> Path:
    """Honour EXPIRYLOG_DATA first, so tests never touch the real file."""
    override = os.environ.get("EXPIRYLOG_DATA")
    return Path(override).expanduser() if override else DEFAULT_DATA_PATH


def load_entries(path: Path) -> list[Entry]:
    """Read the store. A missing file is just an empty list.

    Raises CorruptDataError if the file exists but is not our format,
    so a half-written or hand-edited file fails loudly instead of
    silently dropping someone's warranties.
    """
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorruptDataError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise CorruptDataError(f"{path} should hold a JSON list of entries")
    return [Entry.from_dict(item) for item in raw]


def save_entries(path: Path, entries: list[Entry]) -> None:
    """Write via a temp file in the same directory, then rename.

    A crash mid-write leaves the old file intact instead of a
    truncated one, which matters when this file is the only copy.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        [entry.to_dict() for entry in entries], indent=2, sort_keys=True
    )
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def add_entry(
    entries: list[Entry], entry: Entry, force: bool = False
) -> list[Entry]:
    """Add an entry, or replace the same-named one when forced.

    Names compare case-insensitively ("Passport" and "passport" are
    the same item), but the stored name keeps the casing you typed.
    """
    for i, existing in enumerate(entries):
        if existing.name.lower() == entry.name.lower():
            if not force:
                raise DuplicateEntryError(
                    f"'{existing.name}' already exists "
                    "(use --force to replace it)"
                )
            entries[i] = entry
            return entries
    entries.append(entry)
    return entries


def remove_entry(entries: list[Entry], name: str) -> list[Entry]:
    """Drop the entry with this name, or raise if there is none."""
    kept = [e for e in entries if e.name.lower() != name.lower()]
    if len(kept) == len(entries):
        raise EntryNotFoundError(f"no entry named '{name}'")
    return kept


def parse_date(text: str) -> date:
    """Parse a YYYY-MM-DD date, with a message a human can act on."""
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ExpirylogError(
            f"'{text}' is not a valid date (use YYYY-MM-DD, e.g. 2027-03-14)"
        ) from exc
