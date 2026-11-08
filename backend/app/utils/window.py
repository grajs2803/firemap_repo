from sqlalchemy import text

from app.errors import NotFound
from app.extensions import db


def get_window():
    row = db.session.execute(text("SELECT start_date, end_date FROM data_window")).first()
    if row is None:
        raise NotFound("data_window is empty. Run db/sql/006_fire_view.sql")
    return row.start_date, row.end_date



def get_feature_window():
    row = db.session.execute(text("SELECT feature_start, feature_end FROM data_window")).first()
    if row is None or row.feature_start is None:
        raise NotFound("feature window is not set. Run db/sql/008_feature_window.sql")
    return row.feature_start, row.feature_end
