"""Score daily_features with the active model and upsert into risk_predictions.

This is the model-serving seam: swapping in a trained model means changing get_model() only.
Design points for scale:
  * scope-driven: only dates/cells that already have daily_features rows are scored (see ingest_scope)
  * one date at a time, keyset-paginated by cell_id in batches -> bounded memory, bounded transactions
  * each batch commits; a failing date is rolled back, recorded, and the job moves on
  * idempotent: re-running a date overwrites that (cell, date, model_version) row

Usage:  python -m app.jobs.predict_day 2023-02-01 2023-04-30 [STEP_DAYS]   (STEP_DAYS=15 scores every 15th day)
"""
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import create_app
from app.extensions import db
from app.ml import build_feature_row, get_model
from app.models.cell import Cell
from app.models.daily_features import DailyFeature
from app.models.ingestion_run import IngestionRun
from app.models.risk_prediction import RiskPrediction

BATCH = 10_000


def _score_day(d, model):
    """Return (rows_written, rows_inserted) for one date."""
    version = model.version
    before = db.session.scalar(select(func.count()).select_from(RiskPrediction)
                               .where(RiskPrediction.date == d, RiskPrediction.model_version == version))
    written, after_id = 0, ""
    while True:
        rows = db.session.execute(
            select(Cell, DailyFeature).join(DailyFeature, DailyFeature.cell_id == Cell.cell_id)
            .where(DailyFeature.date == d, DailyFeature.cell_id > after_id)
            .order_by(DailyFeature.cell_id).limit(BATCH)).all()
        if not rows:
            break
        payload = []
        for cell, daily in rows:
            row = build_feature_row(cell, daily)
            logit = model.predict_logit(row)
            payload.append({"cell_id": cell.cell_id, "date": d, "model_version": version,
                            "raw_score": logit, "calibrated_prob": model.predict_proba(row)})
        stmt = pg_insert(RiskPrediction).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["cell_id", "date", "model_version"],
            set_={"raw_score": stmt.excluded.raw_score, "calibrated_prob": stmt.excluded.calibrated_prob,
                  "created_at": func.now()})
        db.session.execute(stmt)
        db.session.commit()
        written += len(payload)
        after_id = rows[-1][0].cell_id
    after = db.session.scalar(select(func.count()).select_from(RiskPrediction)
                              .where(RiskPrediction.date == d, RiskPrediction.model_version == version))
    return written, after - before


def run(start: date, end: date, step: int = 1):
    model = get_model()
    job = IngestionRun(source=f"model:{model.version}", job_type="predict_day",
                       start_date=start, end_date=end, status="running")
    db.session.add(job)
    db.session.commit()
    read = ins = 0
    failed = []
    d = start
    while d <= end:
        try:
            w, i = _score_day(d, model)
            read += w
            ins += i
        except Exception as exc:                      # isolate the bad day, keep going
            db.session.rollback()
            failed.append(f"{d}: {str(exc)[:120]}")
        d += timedelta(days=step)
    job.records_read, job.records_inserted, job.records_updated = read, ins, read - ins
    job.finished_at = datetime.now(timezone.utc)
    job.status = "failed" if failed else "success"
    job.error_message = "; ".join(failed)[:500] or None
    db.session.commit()
    return job


if __name__ == "__main__":
    s, e = (date.fromisoformat(a) for a in sys.argv[1:3])
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    with create_app().app_context():
        j = run(s, e, step)
        print(f"run {j.id}: {j.status} read={j.records_read} inserted={j.records_inserted} "
              f"updated={j.records_updated} {j.error_message or ''}")