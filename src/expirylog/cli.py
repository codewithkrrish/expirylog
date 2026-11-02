"""Command-line front end for expirylog.

This module only parses arguments and prints output. All real work
lives in :mod:`expirylog.store`, so the logic stays testable without
spawning a subprocess.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .store import (
    CorruptDataError,
    DuplicateEntryError,
    Entry,
    EntryNotFoundError,
    ExpirylogError,
    add_entry,
    default_data_path,
    load_entries,
    parse_date,
    remove_entry,
    save_entries,
)

DEFAULT_WITHIN_DAYS = 30


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (one subcommand per verb)."""
    parser = argparse.ArgumentParser(
        prog="expirylog",
        description="Track expiry dates: warranties, subscriptions, "
        "IDs, pantry items.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="data file to use (default: ~/.expirylog.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="record something with an expiry date")
    add.add_argument("name", help="what expires, e.g. Passport")
    add.add_argument("--date", required=True, help="expiry date, YYYY-MM-DD")
    add.add_argument("--category", default="", help="e.g. travel, home")
    add.add_argument("--note", default="", help="free-form note")
    add.add_argument(
        "--force", action="store_true", help="replace an existing entry"
    )

    lst = sub.add_parser("list", help="show everything, soonest first")
    lst.add_argument("--category", default=None, help="only this category")
    lst.add_argument(
        "--within",
        type=int,
        default=None,
        help="only items expiring within N days",
    )
    lst.add_argument(
        "--overdue", action="store_true", help="only already-expired items"
    )
    lst.add_argument(
        "--sort",
        choices=["date", "name"],
        default="date",
        help="sort order (default: date)",
    )

    due = sub.add_parser(
        "due", help="show what expires soon or is already overdue"
    )
    due.add_argument(
        "--within",
        type=int,
        default=DEFAULT_WITHIN_DAYS,
        help=f"window in days (default: {DEFAULT_WITHIN_DAYS})",
    )

    rm = sub.add_parser("remove", help="forget an entry")
    rm.add_argument("name", help="entry name")
    rm.add_argument(
        "--dry-run",
        action="store_true",
        help="say what would be removed, change nothing",
    )

    purge = sub.add_parser("purge", help="delete all already-expired entries")
    purge.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be deleted, change nothing",
    )
    return parser


def _data_path(args: argparse.Namespace) -> Path:
    return args.data if args.data is not None else default_data_path()


def _format(entries: list[Entry], today: date, within: int) -> str:
    """Render entries as a plain aligned table, soonest first."""
    if not entries:
        return "Nothing here."
    rows = []
    for entry in entries:
        left = entry.days_left(today)
        if left < 0:
            when = f"overdue by {-left}d"
        elif left == 0:
            when = "today"
        else:
            when = f"in {left}d"
        cat = f" [{entry.category}]" if entry.category else ""
        rows.append(f"{entry.expires.isoformat()}  {when:<14} {entry.name}{cat}")
    return "\n".join(rows)


def _filtered(
    entries: list[Entry],
    today: date,
    category: str | None,
    within: int | None,
    overdue_only: bool,
) -> list[Entry]:
    out = entries
    if category is not None:
        out = [e for e in out if e.category.lower() == category.lower()]
    if overdue_only:
        out = [e for e in out if e.days_left(today) < 0]
    elif within is not None:
        out = [e for e in out if 0 <= e.days_left(today) <= within]
    return out


def run(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code, never raises."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except ExpirylogError as exc:
        print(f"expirylog: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    today = date.today()
    path = _data_path(args)

    if args.command == "add":
        entries = load_entries(path)
        entry = Entry(
            name=args.name,
            expires=parse_date(args.date),
            category=args.category,
            note=args.note,
        )
        save_entries(path, add_entry(entries, entry, force=args.force))
        print(f"Added '{args.name}' expiring {args.date}.")
        return 0

    if args.command == "list":
        entries = load_entries(path)
        shown = _filtered(
            entries, today, args.category, args.within, args.overdue
        )
        shown.sort(
            key=lambda e: e.expires if args.sort == "date" else e.name.lower()
        )
        print(_format(shown, today, DEFAULT_WITHIN_DAYS))
        return 0

    if args.command == "due":
        if args.within < 0:
            raise ExpirylogError("--within must be 0 or more")
        entries = load_entries(path)
        shown = [
            e
            for e in entries
            if e.days_left(today) < 0 or e.days_left(today) <= args.within
        ]
        shown.sort(key=lambda e: e.expires)
        print(_format(shown, today, args.within))
        return 0

    if args.command == "remove":
        entries = load_entries(path)
        kept = remove_entry(entries, args.name)
        if args.dry_run:
            print(f"Would remove '{args.name}'.")
            return 0
        save_entries(path, kept)
        print(f"Removed '{args.name}'.")
        return 0

    if args.command == "purge":
        entries = load_entries(path)
        expired = [e for e in entries if e.days_left(today) < 0]
        if args.dry_run:
            if expired:
                print("Would delete:")
                print(_format(expired, today, DEFAULT_WITHIN_DAYS))
            else:
                print("Nothing expired.")
            return 0
        kept = [e for e in entries if e.days_left(today) >= 0]
        save_entries(path, kept)
        print(f"Deleted {len(expired)} expired entr{'y' if len(expired) == 1 else 'ies'}.")
        return 0

    raise AssertionError(f"unhandled command {args.command!r}")


def main() -> None:
    """Entry point for the ``expirylog`` console script."""
    sys.exit(run())


if __name__ == "__main__":
    main()
