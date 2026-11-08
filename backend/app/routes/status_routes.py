from flask import Blueprint, jsonify

from app.services import status_services

status_bp = Blueprint("status", __name__)


@status_bp.get("")
def get_status():
    return jsonify(status_services.get_status()), 200
