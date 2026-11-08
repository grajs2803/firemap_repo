import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def _origins():
    raw = os.environ.get("CORS_ORIGINS") or os.environ.get("FRONT_END_URL") or "*"
    return "*" if raw.strip() == "*" else [o.strip() for o in raw.split(",") if o.strip()]


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg2://fireheatmap:fireheatmap@localhost:5432/firemap_real"
    )
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    TILE_SERVER_URL = os.environ.get("TILE_SERVER_URL", "http://localhost:8000/tiles")
    CORS_ORIGINS = _origins()
    COMPRESS_MIN_SIZE = 1024
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True
    JWT_SECRET_KEY = "test-secret-not-for-production-use-0123456789"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", Config.SQLALCHEMY_DATABASE_URI)


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def check_config(app, env):
    """Fail early with a clear message. In development a missing JWT secret is replaced by a random one."""
    if not app.config.get("JWT_SECRET_KEY"):
        if env == "production":
            raise RuntimeError("JWT_SECRET_KEY must be set in production (see .env.example)")
        app.config["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
        app.logger.warning("JWT_SECRET_KEY not set: using a random one, logins are lost on restart")
    if env == "production" and app.config["CORS_ORIGINS"] == "*":
        raise RuntimeError("Set CORS_ORIGINS (or FRONT_END_URL) to your frontend's address in production")
