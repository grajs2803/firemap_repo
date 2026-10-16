from app.errors import APIError, NotFound
from app.ml import build_feature_row, get_model, risk_level
from app.models.cell import Cell
from app.models.daily_features import DailyFeature
from app.utils.params import parse_date
from app.extensions import db
from datetime import date

def _get_cell(cell_id):
    cell = db.session.get(Cell, cell_id)

    if cell is None:
        raise NotFound(f"cell '{cell_id}' not found")

    return cell


TIMESERIES_FEATURES = {
    "ndvi": {"label": "Vegetation Index (NDVI)", "unit": ""},
    "ndmi": {"label": "Moisture Index (NDMI)", "unit": ""},
    "fwi": {"label": "Fire Weather Index", "unit": ""},
    "rainfall_mm": {"label": "Rainfall", "unit": "mm"},
    "temp_c": {"label": "Temperature", "unit": "°C"},
    "wind_speed": {"label": "Wind Speed", "unit": ""},
    "risk": {"label": "Predicted Fire Risk", "unit": "probability"},
}




def get_cell(cell_id, date_str):
    cell = _get_cell(cell_id)
    d = parse_date(date_str)

    q = DailyFeature.query.filter_by(cell_id=cell_id)

    daily = (
        q.filter_by(date=d).first()
        if d
        else q.order_by(DailyFeature.date.desc()).first()
    )

    if daily is None:
        raise NotFound(
            f"no features for cell '{cell_id}' on the requested date"
        )

    model = get_model()
    result = model.explain(build_feature_row(cell, daily))

    return {
        "cell_id": cell.cell_id,
        "date": daily.date.isoformat(),
        "location": {
            "lat": cell.lat,
            "lon": cell.lon,
            "district": cell.district,
        },
        "static": {
            "elevation": cell.elevation,
            "slope": cell.slope,
            "dist_to_road_m": cell.dist_to_road_m,
        },
        "weather": {
            "temp_c": daily.temp_c,
            "rainfall_mm": daily.rainfall_mm,
            "wind_speed": daily.wind_speed,
            "wind_dir": daily.wind_dir,
        },
        "prediction": {
            **result,
            "level": risk_level(result["probability"]),
            "model_version": model.version,
        },
    }
    
    
    
def get_cell_timeseries(cell_id, feature, start_str, end_str):
    if feature not in TIMESERIES_FEATURES:
        raise APIError(
            "Invalid feature. Supported features: "
            + ", ".join(TIMESERIES_FEATURES.keys())
        )

    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except (TypeError, ValueError):
        raise APIError("start and end must be valid dates in YYYY-MM-DD format")

    if start_date > end_date:
        raise APIError("start must be earlier than or equal to end")

    if (end_date - start_date).days > 365:
        raise APIError("Date range cannot exceed 366 calendar days")

    cell = db.session.get(Cell, cell_id)
    if cell is None:
        raise NotFound(f"Cell '{cell_id}' was not found")

    records = (
        DailyFeature.query
        .filter(
            DailyFeature.cell_id == cell_id,
            DailyFeature.date >= start_date,
            DailyFeature.date <= end_date,
        )
        .order_by(DailyFeature.date.asc())
        .all()
    )

    model = get_model()
    points = []

    for record in records:
        value = getattr(record, feature, None) if feature != "risk" else None

        point = {
            "date": record.date.isoformat(),
            "value": None,
        }

        if feature == "risk":
            row = build_feature_row(cell, record)
            probability = model.predict_proba(row)

            point["value"] = round(float(probability), 4)
            point["level"] = risk_level(probability)
        elif value is not None:
            point["value"] = float(value)

        points.append(point)

    metadata = TIMESERIES_FEATURES[feature]

    return {
        "cell_id": cell_id,
        "feature": feature,
        "label": metadata["label"],
        "unit": metadata["unit"],
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "count": len(points),
        "points": points,
    } 
    