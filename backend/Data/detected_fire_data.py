from flask import Blueprint, request, jsonify
from datetime import datetime
from Singleton.firebase_connection import FirebaseConnection

DETECTED_COLLECTION = "detected_fire"

detections_bp = Blueprint("detections_bp", __name__, url_prefix="/api/detections")

# ---------- ROUTES ----------

@detections_bp.route("", methods=["GET"])
def api_get_detections():
    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3")
    return jsonify(get_user_detections(user_id))

# ---------- DATA ----------

def get_user_detections(user_id: str):
    db = FirebaseConnection.get_db()

    docs = (
        db.collection(DETECTED_COLLECTION)
          .where("User_ID", "==", user_id)
          .stream()
    )

    results = []
    for d in docs:
        data = d.to_dict()
        data["id"] = d.id

        det_at = data.get("detected_at")
        if hasattr(det_at, "to_datetime"):
            data["detected_at"] = det_at.to_datetime().isoformat()
        elif isinstance(det_at, datetime):
            data["detected_at"] = det_at.isoformat()

        results.append(data)

    return results