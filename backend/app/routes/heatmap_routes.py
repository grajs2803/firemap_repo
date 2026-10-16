from flask import Blueprint, jsonify, request

from app.services import heatmap_services

heatmap_bp = Blueprint("heatmap", __name__)


@heatmap_bp.get("")
def get_heatmap():
    a = request.args
    result = heatmap_services.get_heatmap(
        a.get("date"), a.get("bbox"), a.get("layer", "risk"), a.get("format", "geojson"))
    return jsonify(result), 200