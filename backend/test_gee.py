from flask import Blueprint, jsonify
from Singleton.gee_connection import GEEConnection

test_gee_bp = Blueprint("test_gee", __name__)

@test_gee_bp.route("/api/test/gee")
def test_gee():
    gee = GEEConnection.get_instance()
    ee = gee.get_ee()

    # اختبار بسيط: عدد الصور في مجموعة معروفة
    size = ee.ImageCollection("MODIS/006/MOD13Q1").size().getInfo()

    return jsonify({
        "status": "success",
        "message": "GEE connection is working",
        "collection_size": size
    })
