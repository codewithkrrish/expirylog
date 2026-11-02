# expirylog

A small command-line tool that remembers expiry dates for you — passports,
warranties, subscriptions, pantry stuff — and tells you what's coming up
before it actually lapses.

## Why I made this

I kept finding out about expired things after the fact: a warranty that
ran out a week before something broke, a subscription renewing at a price
I'd forgotten about. Calendar reminders work, but they need setting up one
by one, and they disappear once dismissed. I wanted one plain list I could
glance at, stored in a single JSON file I can read myself.

So this is it. No accounts, no sync, no background service. Add a date,
run `expirylog due` when you feel like it, and it shows you what's overdue
or close.

## Example

```
$ expirylog add Passport --date 2027-03-14 --category travel
Added 'Passport' expiring 2027-03-14.

$ expirylog add "Car insurance" --date 2026-11-20 --category vehicle
Added 'Car insurance' expiring 2026-11-20.

$ expirylog due
2026-11-20  in 18d          Car insurance [vehicle]
2027-03-14  in 132d         Passport [travel]

$ expirylog list --overdue
Nothing here.
```

## Install

Requires Python 3.10 or newer. Install straight from GitHub:

```
pip install git+https://github.com/codewithkrrish/expirylog.git
```

Or clone it and run it from source — there are no dependencies, so
`python -m expirylog` works right out of the checkout (with `src` on
`PYTHONPATH`).

## Usage

```
expirylog add <name> --date YYYY-MM-DD [--category C] [--note N] [--force]
expirylog list [--category C] [--within N] [--overdue] [--sort date|name]
expirylog due [--within N]          # default window: 30 days
expirylog remove <name> [--dry-run]
expirylog purge [--dry-run]         # delete already-expired entries
```

A few behaviours worth knowing:

- `add` refuses to overwrite an existing name unless you pass `--force`.
  Names match case-insensitively, so "Passport" and "passport" are the
  same entry.
- `purge` and `remove` both take `--dry-run`, which prints what would
  happen and changes nothing. I use it before every purge — deleting
  things by accident is exactly the kind of mistake this tool exists
  to prevent.
- Dates must be `YYYY-MM-DD`. Bad input gets a plain error message and
  exit code 1, not a traceback.

## Where the data lives

One file: `~/.expirylog.json`. It's just a JSON list you can open, edit,
or back up by copying it. Point somewhere else with `--data <path>` or
the `EXPIRYLOG_DATA` environment variable — handy for keeping a separate
list for, say, work items.

## Project structure

```
src/expirylog/
  cli.py      argument parsing and output only
  store.py    entries, the JSON file, and all the rules
tests/
  test_expirylog.py
```

The split is deliberate: `cli.py` never touches the file format, and
`store.py` never prints anything, so both are easy to test on their own.

## Limitations

Honest ones, because this is a weekend-scale tool:

- No reminders or notifications. It only answers when you run it — if
  you want a nudge, put `expirylog due` in a weekly cron job.
- No sync between machines. The file lives where you put it; copy it
  yourself if you use two computers.
- One expiry date per entry. Something with two dates (say, a policy
  with a renewal date and a cancellation deadline) needs two entries.

## Tests

```
pip install pytest
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).

## Author

[Krrish](https://github.com/codewithkrrish)
