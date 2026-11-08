import json

from flask import Blueprint, Response, request

from app.services import history_services

history_bp = Blueprint("history", __name__)


def _compact(payload):
    """Cells are sent as many small arrays; skip Flask's pretty printing in debug mode."""
    return Response(json.dumps(payload, separators=(",", ":")), mimetype="application/json")


@history_bp.get("/months")
def get_months():
    return _compact(history_services.get_months()), 200


@history_bp.get("/grid")
def get_grid():
    a = request.args
    return _compact(history_services.get_grid(a.get("res", "0.5"), a.get("from"), a.get("to"), a.get("bbox"))), 200
