"""Insert live FIRMS hotspots into fire_events.

Dedupe does NOT rely on event_key (the historical key formula is not reproducible here). A row is skipped when a row with the
same (detected_at, latitude, longitude) already exists; new rows get their own key, prefixed 'nrt|', so they can never
collide with historical keys. Live rows carry source = the FIRMS source name (e.g. VIIRS_NOAA20_NRT) so they can be
replaced when the standard-processing archive for the same period is loaded:

    python -m app.jobs.load_fire purge-nrt 2024-03-31          # deletes NRT rows with local_date <= that day
"""
import hashlib
import io
import sys
from datetime import date

import pandas as pd

from app import create_app
from app.extensions import db
from app.jobs.load_weather import global_cell_id


def ingest_firms_df(df: pd.DataFrame, source: str):
    """Return (rows_in_feed, rows_inserted)."""
    if df.empty:
        return 0, 0
    d = df.copy()
    hh = d.acq_time.astype(str).str.zfill(4)
    d["detected_at"] = pd.to_datetime(d.acq_date.astype(str) + " " + hh.str[:2] + ":" + hh.str[2:], utc=True)
    d["local_date"] = d.detected_at.dt.tz_convert("Asia/Kolkata").dt.date
    d["satellite"] = d.satellite.replace({"N20": "NOAA20"})
    d["cell_guess"] = global_cell_id(d.latitude.values, d.longitude.values)
    d["event_key"] = [hashlib.sha256(f"nrt|{s}|{a}|{t}|{la}|{lo}".encode()).hexdigest()
                      for s, a, t, la, lo in zip(d.satellite, d.acq_date, hh, d.latitude, d.longitude)]
    d["detection_type"] = d["type"] if "type" in d else pd.NA
    d["brightness"] = d["bright_ti4"] if "bright_ti4" in d else pd.NA
    d["source"] = source
    d["detected_at"] = d.detected_at.dt.strftime("%Y-%m-%d %H:%M:%S+00")
    cols = ["event_key", "cell_guess", "latitude", "longitude", "detected_at", "local_date", "satellite", "instrument",
            "confidence", "frp", "brightness", "detection_type", "source"]
    d = d[cols].drop_duplicates(["event_key"])
    lo, hi = d.local_date.min(), d.local_date.max()
    conn = db.engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("""CREATE TEMP TABLE tmp_fire (event_key varchar, cell_guess varchar, latitude float8, longitude float8,
                       detected_at timestamptz, local_date date, satellite varchar, instrument varchar, confidence varchar,
                       frp float8, brightness float8, detection_type int, source varchar) ON COMMIT DROP""")
        buf = io.StringIO()
        d.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert("COPY tmp_fire FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
        cur.execute("ANALYZE tmp_fire")
        cur.execute("""INSERT INTO fire_events (event_key, cell_id, latitude, longitude, detected_at, local_date, satellite,
                                                instrument, confidence, frp, brightness, detection_type, source)
                       SELECT t.event_key, c.cell_id, t.latitude, t.longitude, t.detected_at, t.local_date, t.satellite,
                              t.instrument, t.confidence, t.frp, t.brightness, t.detection_type, t.source
                         FROM tmp_fire t LEFT JOIN cells c ON c.cell_id = t.cell_guess
                        WHERE NOT EXISTS (SELECT 1 FROM fire_events e
                                           WHERE e.local_date BETWEEN %s AND %s AND e.detected_at = t.detected_at
                                             AND e.latitude = t.latitude AND e.longitude = t.longitude)
                       ORDER BY t.event_key
                       ON CONFLICT DO NOTHING""", (lo, hi))
        inserted = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return len(d), inserted


def purge_nrt(through: date, like="%_NRT"):
    n = db.session.execute(db.text("DELETE FROM fire_events WHERE source LIKE :s AND local_date <= :d"),
                           {"s": like, "d": through}).rowcount
    db.session.commit()
    return n


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "purge-nrt":
        with create_app().app_context():
            print("deleted", purge_nrt(date.fromisoformat(sys.argv[2])), "NRT rows")
    else:
        raise SystemExit(__doc__)