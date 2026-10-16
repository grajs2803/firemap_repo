from app.errors import APIError, NotFound
from app.ml import build_feature_row, get_model, risk_level
from app.models.cell import Cell
from app.models.daily_features import DailyFeature
from app.utils.params import parse_date
from app.extensions import db

def _get_cell(cell_id):
    cell = db.session.get(Cell, cell_id)

    if cell is None:
        raise NotFound(f"cell '{cell_id}' not found")

    return cell


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