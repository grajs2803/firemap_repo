from flask import current_app
from sqlalchemy import func
from app.constants import CELL_SIZE_DEG, COORD_DECIMALS, MAX_CELLS_PER_REQUEST
from app.errors import APIError, NotFound
from app.extensions import db
from app.ml import LEVEL_BREAKS, get_model, risk_level
from app.models.cell import Cell
from app.models.daily_features import DailyFeature
from app.models.risk_prediction import RiskPrediction
from app.utils.params import parse_bbox, parse_date

LAYERS = {"risk", "ndvi", "ndmi", "fwi"}
FORMATS = {"geojson", "tiles"}

def _legend():
    lo, out = 0.0, []
    for name, hi in LEVEL_BREAKS:
        out.append({"level": name, "min": lo, "max": hi})
        lo = hi
    return out

def _ring(lat, lon):
    h, r = CELL_SIZE_DEG / 2, COORD_DECIMALS
    w, e, s, n = round(lon - h, r), round(lon + h, r), round(lat - h, r), round(lat + h, r)
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def _tile_response(d, layer, bbox, meta):
    # DUMMY DATA for tile response
    base = current_app.config.get("TILE_SERVER_URL", "http://localhost:8000/tiles")
    return {
        "format": "tiles",
        "tile_url_template": f"{base}/{{z}}/{{x}}/{{y}}.png?date={d.isoformat()}&layer={layer}",
        "minzoom": 8, "maxzoom": 14,
        "bounds": list(bbox) if bbox else None,
        "metadata": {**meta, "stub": True},
    }



def get_heatmap(date_str, bbox_str, layer, fmt="geojson"):
    if layer not in LAYERS:
        raise APIError(f"layer must be one of {sorted(LAYERS)}")
    if fmt not in FORMATS:
        raise APIError(f"format must be one of {sorted(FORMATS)}")
    bbox = parse_bbox(bbox_str)
    model = get_model()
    
    #picking the source table and value column for this layer
    if layer == "risk":
        src, value_col = RiskPrediction, RiskPrediction.calibrated_prob
        filters = [RiskPrediction.model_version == model.version]
    else:
        src, value_col = DailyFeature, getattr(DailyFeature, layer)
        filters = []
        
    # resolving the date string to a date object
    d = parse_date(date_str)
    if d is None:
        d = db.session.query(func.max(src.date)).filter(*filters).scalar()
        if d is None:
            raise NotFound("no data loaded for this layer; run scripts/seed_dummy_data.py")
    filters.append(src.date == d)
        
      # "no data for that date"(404) should be different from  "empty bbox" (200, zero features)
    if db.session.query(src.cell_id).filter(*filters).first() is None:
        raise NotFound(f"no '{layer}' data for {d.isoformat()}")
        
    meta = {"date": d.isoformat(), "layer": layer,
            "model_version": model.version if layer == "risk" else None,
            "cell_size_deg": CELL_SIZE_DEG, "legend": _legend() if layer == "risk" else None}

    
    # future handelling of the tile as of now using a dummy data response 
    if fmt == "tiles":
        return _tile_response(d, layer, bbox, meta)


    # including A cell if  Center is inside the bbox.
    q = (db.session.query(Cell, value_col)
         .join(src, src.cell_id == Cell.cell_id).filter(*filters))
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        q = q.filter(Cell.lon >= min_lon, Cell.lon <= max_lon,
                     Cell.lat >= min_lat, Cell.lat <= max_lat)
    total = q.count()
    rows = q.order_by(Cell.cell_id).limit(MAX_CELLS_PER_REQUEST).all()

    features, west, south, east, north = [], 180.0, 90.0, -180.0, -90.0
    h = CELL_SIZE_DEG / 2
    for cell, value in rows:
        west, east = min(west, cell.lon - h), max(east, cell.lon + h)
        south, north = min(south, cell.lat - h), max(north, cell.lat + h)
        features.append({
            "type": "Feature",
            "id": cell.cell_id,
            "geometry": {"type": "Polygon", "coordinates": [_ring(cell.lat, cell.lon)]},
            "properties": {
                "cell_id": cell.cell_id,
                "value": None if value is None else round(value, 4),
                "level": risk_level(value) if layer == "risk" and value is not None else None,
            },
        })

    out = {"type": "FeatureCollection", "features": features,
           "metadata": {**meta, "cell_count": len(features), "total_matching": total,
                        "truncated": total > len(features)}}
    if features:   # RFC 7946 optional `bbox` member: [west, south, east, north]
        out["bbox"] = [round(west, COORD_DECIMALS), round(south, COORD_DECIMALS),
                       round(east, COORD_DECIMALS), round(north, COORD_DECIMALS)]
    return out
    
    
    
