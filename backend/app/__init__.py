import os

from flask import Flask

from app.config import config_by_name
from app.extensions import db
def create_app(env=None):
    app = Flask(__name__)

    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name[env])
    
    db.init_app(app)

    from app.errors import register_error_handlers
    register_error_handlers(app)         



    from app.routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    from app.routes.cell_routes import cell_bp
    app.register_blueprint(cell_bp,url_prefix="/api/v1/cells")
    from app.routes.heatmap_routes import heatmap_bp
    app.register_blueprint(heatmap_bp,url_prefix="/api/v1/heatmap")
    from app.routes.history_routes import history_bp
    app.register_blueprint(history_bp, url_prefix="/api/v1/history")

    @app.get("/map")
    def history_map():
        # minimal demo page: grid of past fires over India (see static/history_map.html)
        return app.send_static_file("history_map.html")

    
    
    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    return app