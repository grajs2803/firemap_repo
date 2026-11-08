import os

from flask import Flask
from flask_compress import Compress
from flask_cors import CORS
from sqlalchemy import text

from app.config import check_config, config_by_name
from app.extensions import db


def create_app(env=None):
    app = Flask(__name__)

    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name[env])
    check_config(app, env)

    db.init_app(app)
    Compress(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
         allow_headers=["Authorization", "Content-Type"], max_age=600)

    from app.errors import register_error_handlers
    register_error_handlers(app)

    from app.routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    from app.routes.cell_routes import cell_bp
    app.register_blueprint(cell_bp, url_prefix="/api/v1/cells")
    from app.routes.heatmap_routes import heatmap_bp
    app.register_blueprint(heatmap_bp, url_prefix="/api/v1/heatmap")
    from app.routes.history_routes import history_bp
    app.register_blueprint(history_bp, url_prefix="/api/v1/history")
    from app.routes.status_routes import status_bp
    app.register_blueprint(status_bp, url_prefix="/api/v1/status")

    app.json.compact = True

    @app.get("/map")
    def history_map():
        return app.send_static_file("history_map.html")

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            app.logger.exception("health check: database unreachable")
            return {"status": "degraded", "database": "down"}, 503
        return {"status": "ok", "database": "up"}, 200

    return app
