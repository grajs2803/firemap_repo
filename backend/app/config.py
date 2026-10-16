import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


class Config:
    FRONT_END_URL = os.environ.get("FRONT_END_URL", "dummy frontend url")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://fireheatmap:fireheatmap@localhost:5432/firemap"
    )
    JWT_SECRET_KEY= os.environ.get("JWT_SECRET_KEY")
    TILE_SERVER_URL = os.environ.get("TILE_SERVER_URL", "http://localhost:8000/tiles")
    
class DevelopmentConfig(Config):
    DEBUG = True

config_by_name = {
    "development": DevelopmentConfig,
}
