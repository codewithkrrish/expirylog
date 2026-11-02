"""Tests for expirylog: happy paths plus the ways real data goes wrong."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from expirylog.cli import run
from expirylog.store import (
    CorruptDataError,
    DuplicateEntryError,
    Entry,
    EntryNotFoundError,
    add_entry,
    load_entries,
    parse_date,
    remove_entry,
    save_entries,
)

TODAY = date.today()


def entry(name: str = "Passport", days: int = 60, **kwargs) -> Entry:
    return Entry(name=name, expires=TODAY + timedelta(days=days), **kwargs)


def test_add_and_list_roundtrip(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    assert run(["--data", str(data), "add", "Passport", "--date", "2027-03-14"]) == 0
    assert run(["--data", str(data), "list"]) == 0
    out = capsys.readouterr().out
    assert "Passport" in out and "2027-03-14" in out


def test_list_sorts_soonest_first(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    save_entries(data, [entry("Later", 90), entry("Sooner", 10)])
    assert run(["--data", str(data), "list"]) == 0
    out = capsys.readouterr().out
    assert out.index("Sooner") < out.index("Later")


def test_due_window_and_overdue(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    save_entries(
        data, [entry("Old", -5), entry("Soon", 10), entry("Far", 400)]
    )
    assert run(["--data", str(data), "due", "--within", "30"]) == 0
    out = capsys.readouterr().out
    assert "Old" in out and "Soon" in out and "Far" not in out
    assert "overdue by 5d" in out


def test_list_filters_by_category_and_overdue(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    save_entries(
        data,
        [
            entry("Passport", 10, category="travel"),
            entry("Milk", -1, category="pantry"),
        ],
    )
    assert run(["--data", str(data), "list", "--category", "pantry"]) == 0
    out = capsys.readouterr().out
    assert "Milk" in out and "Passport" not in out
    assert run(["--data", str(data), "list", "--overdue"]) == 0
    out = capsys.readouterr().out
    assert "Milk" in out and "Passport" not in out


def test_duplicate_needs_force(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    save_entries(data, [entry("Passport", 60)])
    with pytest.raises(DuplicateEntryError):
        add_entry([entry("Passport", 60)], entry("passport", 90))
    # ...but --force replaces instead of failing.
    assert (
        run(
            [
                "--data",
                str(data),
                "add",
                "passport",
                "--date",
                "2028-01-01",
                "--force",
            ]
        )
        == 0
    )
    assert load_entries(data)[0].expires == date(2028, 1, 1)


def test_add_bad_date_exits_1_not_traceback(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    assert (
        run(["--data", str(data), "add", "X", "--date", "14-03-2027"]) == 1
    )
    err = capsys.readouterr().err
    assert "not a valid date" in err and "Traceback" not in err


def test_remove_missing_entry_exits_1(tmp_path: Path) -> None:
    assert run(["--data", str(tmp_path / "d.json"), "remove", "Nope"]) == 1


def test_remove_entry_function_raises(tmp_path: Path) -> None:
    with pytest.raises(EntryNotFoundError):
        remove_entry([entry()], "Something else")


def test_purge_dry_run_changes_nothing(tmp_path: Path, capsys) -> None:
    data = tmp_path / "data.json"
    save_entries(data, [entry("Old", -3), entry("New", 30)])
    assert run(["--data", str(data), "purge", "--dry-run"]) == 0
    assert "Old" in capsys.readouterr().out
    assert len(load_entries(data)) == 2
    assert run(["--data", str(data), "purge"]) == 0
    assert [e.name for e in load_entries(data)] == ["New"]


def test_remove_dry_run_changes_nothing(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    save_entries(data, [entry("Passport", 60)])
    assert run(["--data", str(data), "remove", "Passport", "--dry-run"]) == 0
    assert len(load_entries(data)) == 1


def test_missing_file_lists_empty(tmp_path: Path, capsys) -> None:
    assert run(["--data", str(tmp_path / "nope.json"), "list"]) == 0
    assert "Nothing here." in capsys.readouterr().out


def test_corrupt_json_is_reported(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    data.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptDataError):
        load_entries(data)


def test_empty_and_wrong_shape_files(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CorruptDataError):
        load_entries(empty)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"name": "Passport"}), encoding="utf-8")
    with pytest.raises(CorruptDataError):
        load_entries(wrong)


def test_record_missing_fields_is_corrupt(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    data.write_text(json.dumps([{"name": "Passport"}]), encoding="utf-8")
    with pytest.raises(CorruptDataError):
        load_entries(data)


def test_negative_within_rejected(tmp_path: Path) -> None:
    assert run(["--data", str(tmp_path / "d.json"), "due", "--within", "-5"]) == 1


def test_parse_date_rejects_impossible_dates() -> None:
    with pytest.raises(Exception):
        parse_date("2027-02-30")


def test_status_boundaries() -> None:
    assert entry("A", -1).status(TODAY, 30) == "overdue"
    assert entry("B", 0).status(TODAY, 30) == "due-soon"
    assert entry("C", 30).status(TODAY, 30) == "due-soon"
    assert entry("D", 31).status(TODAY, 30) == "ok"


def test_save_is_atomic_no_tmp_left(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    save_entries(data, [entry("Passport", 60)])
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(data.read_text(encoding="utf-8"))[0]["name"] == "Passport"
