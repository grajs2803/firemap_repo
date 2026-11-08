"""Export the training table: one row per (pilot cell, day), features known on that day, label = fire in the next H days.

  python -m app.jobs.export_training OUT_DIR [--horizon 1] [--neg-rate 1.0] [--start D --end D] [--seed 0]

Output: OUT_DIR/ym=YYYY-MM.parquet (one file per month) and OUT_DIR/_meta.json (label definition, window, sampling).

Label  y(c,d) = 1 if cell c has at least one valid fire (v_fire) on any of days d+1 .. d+H, else 0.
         Rows whose next H days are not all present are dropped (no partial labels).
No leakage: every feature uses data up to day d only. fires_7d / fires_30d / rain_7d cover days d-7..d-1 / d-30..d-1.
Negatives can be down-sampled (--neg-rate q < 1). Column `w` is the weight that undoes it (positives 1, kept negatives 1/q),
so weighted statistics equal the full data.
Splits: fold_space = district, fold_time = calendar year. Never use a random row split (neighbouring cells and days are correlated).
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.utils.window import get_feature_window

FEATURES = ["ndvi", "ndmi", "fwi", "temp_c", "rainfall_mm", "wind_speed", "wind_dir", "elevation",
            "fires_7d", "fires_30d", "rain_7d", "doy_sin", "doy_cos"]
LOOKBACK = 30

SQL = """
WITH w AS (
  SELECT d.cell_id, d.date, d.ndvi, d.ndmi, d.fwi, d.temp_c, d.rainfall_mm, d.wind_speed, d.wind_dir,
         max((d.fire_count > 0)::int)  OVER nxt AS y,
         count(*)                      OVER nxt AS n_next,
         sum(d.fire_count)             OVER p7  AS fires_7d,
         sum(d.fire_count)             OVER p30 AS fires_30d,
         sum(d.rainfall_mm)            OVER p7  AS rain_7d
  FROM daily_features d
  WHERE d.date BETWEEN :lo AND :hi
    AND d.cell_id IN (SELECT c.cell_id FROM cells c JOIN ingest_scope s USING (district))
  WINDOW nxt AS (PARTITION BY d.cell_id ORDER BY d.date ROWS BETWEEN 1 FOLLOWING AND __H__ FOLLOWING),
         p7  AS (PARTITION BY d.cell_id ORDER BY d.date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING),
         p30 AS (PARTITION BY d.cell_id ORDER BY d.date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)
)
SELECT w.cell_id, w.date, c.district, c.elevation, w.ndvi, w.ndmi, w.fwi, w.temp_c, w.rainfall_mm, w.wind_speed, w.wind_dir,
       w.fires_7d, w.fires_30d, w.rain_7d, w.y
FROM w JOIN cells c USING (cell_id)
WHERE w.date BETWEEN :s AND :e AND w.n_next = __H__
"""


def month_ranges(start, end):
    d = start
    while d <= end:
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        yield d, min(end, nxt - timedelta(days=1))
        d = nxt


def run(out_dir, horizon, neg_rate, start, end, seed):
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    sql = text(SQL.replace("__H__", str(int(horizon))))
    tot = {"rows": 0, "pos": 0, "kept": 0}
    nulls = pd.Series(0, index=FEATURES, dtype="int64")
    by_year = {}
    with create_app().app_context():
        if start is None or end is None:
            fs, fe = get_feature_window()
            start, end = start or fs, end or fe
        for s, e in month_ranges(start, end):
            df = pd.read_sql(sql, db.engine, params={"lo": s - timedelta(days=LOOKBACK),
                                                     "hi": e + timedelta(days=horizon), "s": s, "e": e})
            if df.empty:
                print(f"{s:%Y-%m}: no rows")
                continue
            df["date"] = pd.to_datetime(df["date"])
            doy = df["date"].dt.day_of_year.to_numpy()
            df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
            for yr, g in df.groupby(df["date"].dt.year):
                a = by_year.setdefault(int(yr), [0, 0])
                a[0] += len(g)
                a[1] += int(g.y.sum())
            tot["rows"] += len(df)
            tot["pos"] += int(df.y.sum())
            nulls += df[FEATURES].isna().sum()
            keep = (df.y == 1) | (rng.random(len(df)) < neg_rate)
            df = df[keep].copy()
            df["w"] = np.where(df.y == 1, 1.0, 1.0 / neg_rate)
            df["fold_space"] = df["district"]
            df["fold_time"] = df["date"].dt.year
            df["date"] = df["date"].dt.date
            df = df[["cell_id", "date", "fold_space", "fold_time", "w"] + FEATURES + ["y"]]
            df.to_parquet(os.path.join(out_dir, f"ym={s:%Y-%m}.parquet"), index=False)
            tot["kept"] += len(df)
            print(f"{s:%Y-%m}: {len(df):,} rows kept")
    meta = {"label": f"fire (v_fire) in any of the next {horizon} day(s)", "horizon_days": horizon,
            "start": start.isoformat(), "end": end.isoformat(), "neg_rate": neg_rate, "seed": seed,
            "features": FEATURES, "weight_column": "w", "split_columns": ["fold_space", "fold_time"],
            "created_at": datetime.now(timezone.utc).isoformat(), "rows_before_sampling": tot["rows"],
            "positives": tot["pos"], "rows_written": tot["kept"]}
    with open(os.path.join(out_dir, "_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    rate = tot["pos"] / tot["rows"] if tot["rows"] else 0
    print(f"\nrows={tot['rows']:,} positives={tot['pos']:,} base rate={rate:.6f} written={tot['kept']:,}")
    print("per year (rows, positives):", {y: tuple(v) for y, v in sorted(by_year.items())})
    if tot["rows"]:
        print("null % per feature:")
        print((100 * nulls / tot["rows"]).round(1).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--neg-rate", type=float, default=1.0)
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if not 0 < a.neg_rate <= 1 or a.horizon < 1:
        raise SystemExit("--neg-rate must be in (0, 1] and --horizon >= 1")
    run(a.out_dir, a.horizon, a.neg_rate, a.start, a.end, a.seed)
