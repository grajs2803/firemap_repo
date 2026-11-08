from sqlalchemy import text

from app.extensions import db
from app.ml import get_model


def _one(sql, **params):
    return db.session.execute(text(sql), params).first()


def _table_exists(name):
    return db.session.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None


def get_status():
    model = get_model()
    out = {"model": {"version": model.version, "is_dummy": getattr(model, "is_dummy", False)},
           "data_window": None, "feature_window": None, "features": None, "risk": None, "fire_history": None, "last_runs": []}

    if _table_exists("data_window"):
        r = _one("SELECT start_date, end_date, feature_start, feature_end FROM data_window")
        if r:
            out["data_window"] = {"start": r.start_date.isoformat(), "end": r.end_date.isoformat()}
            if r.feature_start:
                out["feature_window"] = {"start": r.feature_start.isoformat(), "end": r.feature_end.isoformat()}

    r = _one("SELECT min(date) AS a, max(date) AS b FROM daily_features")
    if r and r.b:
        out["features"] = {"first_date": r.a.isoformat(), "latest_date": r.b.isoformat()}

    r = _one("SELECT min(date) AS a, max(date) AS b, count(DISTINCT date) AS n FROM risk_predictions WHERE model_version = :v",
             v=model.version)
    if r and r.b:
        out["risk"] = {"model_version": model.version, "first_date": r.a.isoformat(), "latest_date": r.b.isoformat(),
                       "dates": r.n}

    if _table_exists("fire_grid_01"):
        r = _one("SELECT min(ym) AS a, max(ym) AS b FROM fire_grid_01")
        if r and r.b:
            out["fire_history"] = {"first_month": r.a.isoformat(), "last_month": r.b.isoformat()}

    rows = db.session.execute(text("""
        SELECT DISTINCT ON (job_type, source) job_type, source, status, start_date, end_date, finished_at
        FROM ingestion_runs ORDER BY job_type, source, id DESC""")).all()
    out["last_runs"] = [{"job": r.job_type, "source": r.source, "status": r.status,
                         "start": r.start_date.isoformat() if r.start_date else None,
                         "end": r.end_date.isoformat() if r.end_date else None,
                         "finished_at": r.finished_at.isoformat() if r.finished_at else None} for r in rows]
    return out
