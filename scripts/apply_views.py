#!/usr/bin/env python3
"""Apply every sql/views/<schema>/*.sql file to a Postgres database.

Nothing in this repo ever applied these files; this is that step. The database is the
system of record for the views and sql/views is a hand-applied mirror, so this makes the
mirror authoritative again.

Each file is applied with CREATE OR REPLACE, in a transaction, retrying until no new
failures appear so a view may safely reference another view whose file is applied later in
the same run. Nothing is dropped by default: DROP ... CASCADE would silently take views
that live in the database but have no file here (util.active_player_vw and
util.unmatched_player_source_vw both hang off util.player_directory_vw). When a view's
column list has genuinely changed, CREATE OR REPLACE cannot express it -- use --force-drop,
which drops that one view without CASCADE so a real dependency fails loudly instead of
being destroyed.

    PGCONN=postgresql://... python scripts/apply_views.py --dry-run
    PGCONN=postgresql://... python scripts/apply_views.py
    PGCONN=postgresql://... python scripts/apply_views.py --schema fty

The closing count check compares live view counts against the file count per schema, so a
view that exists in the database without a file is visible rather than assumed harmless.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

VIEWS_DIR = Path(__file__).resolve().parent.parent / 'sql' / 'views'
NAME_RE = re.compile(r'create\s+(?:or\s+replace\s+)?view\s+([a-z_]\w*\.[a-z_]\w*)', re.I)
MAX_PASSES = 5


def view_files(schema: str | None) -> list[Path]:
    pattern = f'{schema}/*.sql' if schema else '*/*.sql'
    return sorted(VIEWS_DIR.glob(pattern))


def view_name(sql: str) -> str:
    match = NAME_RE.search(sql)
    if match is None:
        raise ValueError('no CREATE VIEW statement found')
    return match.group(1)


def psql(dsn: str, sql: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ['psql', dsn, '--single-transaction', '-v', 'ON_ERROR_STOP=1', '-c', sql],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def live_counts(dsn: str, schemas: list[str]) -> Counter[str]:
    quoted = ','.join(f"'{s}'" for s in schemas)
    ok, out = psql(
        dsn,
        f'SELECT schemaname, count(*) FROM pg_views WHERE schemaname IN ({quoted}) GROUP BY 1',
    )
    counts: Counter[str] = Counter()
    if not ok:
        return counts
    for line in out.splitlines():
        parts = line.split('|')
        if len(parts) == 2 and parts[1].strip().isdigit():
            counts[parts[0].strip()] = int(parts[1])
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dsn', default=os.environ.get('PGCONN'))
    parser.add_argument('--schema', default=None, help='only this sql/views/<schema>/ folder')
    parser.add_argument(
        '--force-drop',
        action='store_true',
        help='drop each view (no CASCADE) before creating it; needed only when a column '
        'list changed, and it fails loudly rather than taking dependent views with it',
    )
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if not args.dsn:
        print('PGCONN is not set and --dsn was not given', file=sys.stderr)
        return 2

    jobs: list[tuple[Path, str, str]] = []
    for path in view_files(args.schema):
        sql = path.read_text()
        try:
            jobs.append((path, view_name(sql), sql))
        except ValueError as exc:
            print(f'{path}: {exc}', file=sys.stderr)
            return 2

    if not jobs:
        print(f'no view files under {VIEWS_DIR}', file=sys.stderr)
        return 2

    print(f'{len(jobs)} view files under {VIEWS_DIR}')
    if args.dry_run:
        for path, name, _ in jobs:
            print(f'  {name:40s} {path.relative_to(VIEWS_DIR.parent.parent)}')
        return 0

    expected = Counter(name.split('.')[0] for _, name, _ in jobs)
    pending: list[tuple[Path, str, str]] = list(jobs)
    last_errors: dict[Path, str] = {}
    done = False
    for attempt in range(1, MAX_PASSES + 1):
        failed: list[tuple[Path, str, str]] = []
        last_errors = {}
        for path, name, sql in pending:
            prefix = f'DROP VIEW IF EXISTS {name};\n' if args.force_drop else ''
            ok, out = psql(args.dsn, f'{prefix}{sql}\n')
            if not ok:
                failed.append((path, name, sql))
                last_errors[path] = out
        print(f'pass {attempt}: {len(pending) - len(failed)} ok, {len(failed)} failed')
        if not failed:
            done = True
            break
        if len(failed) == len(pending):
            break  # no progress: the same files would fail forever
        pending = failed

    if not done:
        for path, _, _ in pending:
            print(f'FAILED {path}: {last_errors.get(path, "")}', file=sys.stderr)
        return 1

    counts = live_counts(args.dsn, sorted(expected))
    bad = False
    for schema in sorted(expected):
        got, want = counts.get(schema, 0), expected[schema]
        if got < want:
            note, bad = 'MISMATCH', True  # a file did not apply
        elif got > want:
            note = f'EXTRA {got - want} in the db with no file here'
        else:
            note = 'ok'
        print(f'{schema}: {got} views live, {want} files [{note}]')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
