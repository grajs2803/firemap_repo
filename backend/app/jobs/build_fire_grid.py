"""Aggregate fire_events into a coarse monthly grid (fire_grid_01) for the history map.

Why: the full 0.01 degree grid has ~2.9 million cells over India, far too many to send to a
browser. At 0.1 degree (about 11 km) India has at most ~93,000 cells, and only cells with at
least one fire are stored. Coarser views (0.5, 1.0 degree) are derived from this table at
query time by integer division, so no other table is needed.

  grid index  = floor(round(coordinate / 0.1, 9))     (same rounding rule as the cell ids)
  month       = month of local_date (IST day)

Idempotent: each month is deleted and rebuilt inside one transaction, so re-running is safe.

Usage (from backend/):
    python -m app.jobs.build_fire_grid                      # every month present in fire_events
    python -m app.jobs.build_fire_grid 2022-01-01 2022-12-31
"""
import sys
from datetime import date

from sqlalchemy import text

from app import create_app
from app.extensions import db

GRID_DEG = "0.1"          # base resolution; the API reads it back from these constants
# A row counts as a fire when confidence is nominal/high and the detection is a vegetation fire
# (type 0). NULL type is treated as 0 because near-real-time feeds may not carry the column.
FIRE_FILTER = "confidence IN ('n', 'h') AND COALESCE(detection_type, 0) = 0"

DDL = """
CREATE TABLE IF NOT EXISTS fire_grid_01 (
    ym    date    NOT NULL,          -- first day of the month (IST)
    grow  integer NOT NULL,          -- floor(lat / 0.1)
    gcol  integer NOT NULL,          -- floor(lon / 0.1)
    n     integer NOT NULL,          -- fires in that cell that month
    PRIMARY KEY (ym, grow, gcol)
)
"""

MONTH_INSERT = f"""
INSERT INTO fire_grid_01 (ym, grow, gcol, n)
SELECT :ym,
       floor(round(latitude::numeric  / CAST(:deg AS numeric), 9))::int,
       floor(round(longitude::numeric / CAST(:deg AS numeric), 9))::int,
       count(*)
FROM fire_events
WHERE local_date >= :ym AND local_date < :next_ym AND {FIRE_FILTER}
GROUP BY 2, 3
"""


def _month_start(d):
    return date(d.year, d.month, 1)


def _next_month(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _months(first, last):
    m, end = _month_start(first), _month_start(last)
    while m <= end:
        yield m
        m = _next_month(m)


def run(start=None, end=None):
    with create_app().app_context():
        db.session.execute(text(DDL))
        db.session.commit()

        lo, hi = db.session.execute(text("SELECT min(local_date), max(local_date) FROM fire_events")).one()
        if lo is None:
            print("fire_events is empty; nothing to aggregate")
            return
        lo, hi = max(lo, start or lo), min(hi, end or hi)

        total_cells = 0
        for ym in _months(lo, hi):
            try:
                db.session.execute(text("DELETE FROM fire_grid_01 WHERE ym = :ym"), {"ym": ym})
                res = db.session.execute(text(MONTH_INSERT),
                                         {"ym": ym, "next_ym": _next_month(ym), "deg": GRID_DEG})
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                print(f"{ym:%Y-%m}  FAILED: {exc}")
                raise
            total_cells += res.rowcount
            print(f"{ym:%Y-%m}  cells={res.rowcount}")

        # Integrity check: every fire in range must land in exactly one cell.
        first, last = _month_start(lo), _next_month(_month_start(hi))
        in_grid = db.session.execute(text("SELECT coalesce(sum(n), 0) FROM fire_grid_01 WHERE ym >= :a AND ym < :b"),
                                     {"a": first, "b": last}).scalar()
        in_events = db.session.execute(text(f"SELECT count(*) FROM fire_events WHERE local_date >= :a AND local_date < :b AND {FIRE_FILTER}"),
                                       {"a": first, "b": last}).scalar()
        status = "OK" if in_grid == in_events else "MISMATCH"
        print(f"check: grid total={in_grid} fire_events total={in_events} -> {status}")
        if status != "OK":
            sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    s = date.fromisoformat(args[0]) if len(args) > 0 else None
    e = date.fromisoformat(args[1]) if len(args) > 1 else None
    run(s, e)
