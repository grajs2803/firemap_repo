import sys

from sqlalchemy import text

from app import create_app
from app.extensions import db

FIRE_FILTER = "cell_id IS NOT NULL AND confidence IN ('n', 'h') AND COALESCE(detection_type, 0) = 0"

CREATE = """
CREATE TABLE IF NOT EXISTS fire_grid_01 (
    ym   date    NOT NULL,
    grow integer NOT NULL,
    gcol integer NOT NULL,
    n    integer NOT NULL,
    PRIMARY KEY (ym, grow, gcol)
)
"""

INSERT = f"""
INSERT INTO fire_grid_01 (ym, grow, gcol, n)
SELECT date_trunc('month', local_date)::date,
       floor(round(latitude::numeric / 0.1, 9))::int,
       floor(round(longitude::numeric / 0.1, 9))::int,
       count(*)
FROM fire_events
WHERE {FIRE_FILTER}
GROUP BY 1, 2, 3
"""


def run():
    with create_app().app_context():
        db.session.execute(text(CREATE))
        db.session.execute(text("DELETE FROM fire_grid_01"))
        cells = db.session.execute(text(INSERT)).rowcount
        db.session.commit()

        in_grid = db.session.execute(text("SELECT coalesce(sum(n), 0) FROM fire_grid_01")).scalar()
        in_events = db.session.execute(text(f"SELECT count(*) FROM fire_events WHERE {FIRE_FILTER}")).scalar()
        print(f"rows={cells} grid_total={in_grid} fire_events_total={in_events}")
        if in_grid != in_events:
            sys.exit("MISMATCH")
        print("OK")


if __name__ == "__main__":
    run()
