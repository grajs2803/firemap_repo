"""Tests run against a throw-away Postgres database. Create one and point TEST_DATABASE_URL at it:

    createdb embergrid_pytest
    export TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/embergrid_pytest
    python -m pytest

The database name must contain "test": every table in it is dropped and rebuilt.
"""
import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import make_url, text

URL = os.environ.get("TEST_DATABASE_URL")
SQL_DIR = Path(__file__).resolve().parent.parent / "db" / "sql"

if not URL:
    pytest.skip("TEST_DATABASE_URL is not set", allow_module_level=True)
if "test" not in (make_url(URL).database or ""):
    pytest.exit("TEST_DATABASE_URL must point to a database whose name contains 'test'", returncode=2)

from app import create_app  # noqa: E402  (after the checks above)
from app.extensions import db  # noqa: E402
from app.jobs.build_fire_grid import build  # noqa: E402
from app.ml import get_model  # noqa: E402
from app.models.cell import Cell  # noqa: E402
from app.models.daily_features import DailyFeature  # noqa: E402
from app.models.fire_event import FireEvent  # noqa: E402
from app.models.ingest_scope import IngestScope  # noqa: E402
from app.models.ingestion_run import IngestionRun  # noqa: E402
from app.models.risk_prediction import RiskPrediction  # noqa: E402

CELLS = [("r2200c8500", 22.005, 85.005), ("r2200c8501", 22.005, 85.015), ("r2201c8500", 22.015, 85.005)]
DAYS = [date(2019, 4, 10), date(2019, 4, 11)]
PROBS = {"r2200c8500": 0.05, "r2200c8501": 0.30, "r2201c8500": 0.80}


def _fire(key, cell, day, conf, lat=22.005, lon=85.005, dtype=0):
    return FireEvent(event_key=key, cell_id=cell, latitude=lat, longitude=lon, detected_at=f"{day}T06:00:00+00:00",
                     local_date=day, confidence=conf, detection_type=dtype, source="test")


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        db.session.execute(text("DROP VIEW IF EXISTS v_fire CASCADE"))
        db.session.execute(text("DROP TABLE IF EXISTS data_window, fire_grid_01 CASCADE"))
        db.session.commit()
        db.drop_all()
        db.create_all()
        for name in ("006_fire_view.sql", "008_feature_window.sql"):
            db.session.connection().exec_driver_sql((SQL_DIR / name).read_text().replace("%", "%%"))
        db.session.commit()

        for cid, lat, lon in CELLS:
            db.session.add(Cell(cell_id=cid, lat=lat, lon=lon, district="D1", elevation=500.0))
        db.session.flush()
        db.session.add(IngestScope(district="D1", from_date=date(2019, 4, 1), to_date=date(2019, 4, 30)))
        for cid, _, _ in CELLS:
            for d in DAYS:
                db.session.add(DailyFeature(cell_id=cid, date=d, ndvi=0.5, fwi=12.0, temp_c=33.0, rainfall_mm=0.0,
                                            wind_speed=3.0, wind_dir=90.0, fire_count=0))
            db.session.add(RiskPrediction(cell_id=cid, date=DAYS[1], model_version=get_model().version,
                                          calibrated_prob=PROBS[cid], raw_score=0.0))
        db.session.add_all([
            _fire("e1", "r2200c8500", date(2019, 3, 5), "h"),
            _fire("e2", "r2200c8500", date(2019, 3, 6), "n"),
            _fire("e3", "r2200c8501", date(2019, 4, 2), "h", lon=85.015),
            _fire("e4", "r2200c8500", date(2019, 4, 3), "l"),                 # low confidence: not a fire
            _fire("e5", None, date(2019, 4, 4), "h", lat=5.0, lon=5.0),        # outside every cell: not counted
            _fire("e6", "r2200c8500", date(2019, 4, 5), "h", dtype=2),         # not a vegetation fire
            _fire("e7", "r2200c8500", date(2024, 4, 1), "h"),                  # after the data window
        ])
        db.session.add(IngestionRun(source="test", job_type="label_layer", status="success",
                                    start_date=DAYS[0], end_date=DAYS[1]))
        db.session.commit()
        build()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
