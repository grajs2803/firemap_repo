"""Read side of the fire history grid (table fire_grid_01, built by app.jobs.build_fire_grid).

Cells are sent as compact [row, col, count] triples; the client turns them into rectangles:
    south = row * cell_deg,  north = (row + 1) * cell_deg
    west  = col * cell_deg,  east  = (col + 1) * cell_deg
Coarser resolutions are derived from the 0.1 degree table by integer division, so a 0.5 degree
cell is the sum of the 5 x 5 base cells it contains.
"""
import math
from datetime import date

from sqlalchemy import text

from app.errors import APIError, NotFound
from app.extensions import db
from app.utils.params import parse_bbox, parse_date

BASE_DEG = 0.1
# resolution (degrees) -> how many base cells per side
RESOLUTIONS = {0.1: 1, 0.5: 5, 1.0: 10}


def _require_table():
    if db.session.execute(text("SELECT to_regclass('fire_grid_01')")).scalar() is None:
        raise NotFound("fire_grid_01 does not exist. Run: python -m app.jobs.build_fire_grid")


def _month(d):
    return date(d.year, d.month, 1)


def get_months():
    """Every month with data (first, last, and per-month fire totals)."""
    _require_table()
    rows = db.session.execute(text("SELECT ym, sum(n)::bigint FROM fire_grid_01 GROUP BY ym ORDER BY ym")).all()
    if not rows:
        raise NotFound("fire_grid_01 is empty. Run: python -m app.jobs.build_fire_grid")
    return {"first": rows[0][0].isoformat(), "last": rows[-1][0].isoformat(),
            "months": [{"ym": r[0].isoformat(), "fires": r[1]} for r in rows]}


def get_grid(res_str, from_str, to_str, bbox_str):
    try:
        res = float(res_str)
    except (TypeError, ValueError):
        raise APIError(f"'res' must be one of {sorted(RESOLUTIONS)}")
    if res not in RESOLUTIONS:
        raise APIError(f"'res' must be one of {sorted(RESOLUTIONS)}")
    factor = RESOLUTIONS[res]

    start, end = parse_date(from_str, "from"), parse_date(to_str, "to")
    if start and end and start > end:
        raise APIError("'from' must not be after 'to'")
    bbox = parse_bbox(bbox_str)

    _require_table()
    params = {"f": factor, "a": _month(start) if start else date.min, "b": _month(end) if end else date.max}
    where = "ym >= :a AND ym <= :b"
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        params.update(r0=math.floor(round(min_lat / BASE_DEG, 9)), r1=math.floor(round(max_lat / BASE_DEG, 9)),
                      c0=math.floor(round(min_lon / BASE_DEG, 9)), c1=math.floor(round(max_lon / BASE_DEG, 9)))
        where += " AND grow BETWEEN :r0 AND :r1 AND gcol BETWEEN :c0 AND :c1"

    rows = db.session.execute(text(f"""
        SELECT floor(grow / CAST(:f AS numeric))::int AS r, floor(gcol / CAST(:f AS numeric))::int AS c, sum(n)::int
        FROM fire_grid_01 WHERE {where} GROUP BY 1, 2 ORDER BY 1, 2"""), params).all()

    cells = [[r, c, n] for r, c, n in rows]
    return {
        "res": res,
        "cell_deg": round(BASE_DEG * factor, 6),
        "from": params["a"].isoformat() if start else None,
        "to": params["b"].isoformat() if end else None,
        "cell_count": len(cells),
        "total_fires": sum(n for _, _, n in cells),
        "max_count": max((n for _, _, n in cells), default=0),
        "cells": cells,
    }
