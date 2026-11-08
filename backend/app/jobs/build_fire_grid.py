import sys

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.utils.window import get_window

FIRE_FILTER = "local_date BETWEEN :start AND :end"

CREATE = """
CREATE TABLE IF NOT EXISTS fire_grid_01 (
    ym   date    NOT NULL,
    grow integer NOT NULL,
    gcol integer NOT NULL,
    n    integer NOT NULL,
    PRIMARY KEY (ym, grow, gcol)
)
"""

INDEX = "CREATE INDEX IF NOT EXISTS ix_fire_grid_01_rc ON fire_grid_01 (grow, gcol)"

INSERT = f"""
INSERT INTO fire_grid_01 (ym, grow, gcol, n)
SELECT date_trunc('month', local_date)::date,
       floor(round(latitude::numeric / 0.1, 9))::int,
       floor(round(longitude::numeric / 0.1, 9))::int,
       count(*)
FROM v_fire
WHERE {FIRE_FILTER}
GROUP BY 1, 2, 3
"""


def build():
    """Rebuild fire_grid_01 inside an app context. Returns (rows, grid_total, events_total, start, end)."""
    if db.session.execute(text("SELECT to_regclass('v_fire')")).scalar() is None:
        sys.exit("v_fire is missing. Run db/sql/006_fire_view.sql first")
    start, end = get_window()
    w = {"start": start, "end": end}
    db.session.execute(text(CREATE))
    db.session.execute(text(INDEX))
    db.session.execute(text("DELETE FROM fire_grid_01"))
    cells = db.session.execute(text(INSERT), w).rowcount
    db.session.commit()
    in_grid = db.session.execute(text("SELECT coalesce(sum(n), 0) FROM fire_grid_01")).scalar()
    in_events = db.session.execute(text(f"SELECT count(*) FROM v_fire WHERE {FIRE_FILTER}"), w).scalar()
    return cells, in_grid, in_events, start, end


def run():
    with create_app().app_context():
        cells, in_grid, in_events, start, end = build()
        print(f"window={start}..{end} rows={cells} grid_total={in_grid} fire_events_total={in_events}")
        if in_grid != in_events:
            sys.exit("MISMATCH")
        print("OK")


if __name__ == "__main__":
    run()
