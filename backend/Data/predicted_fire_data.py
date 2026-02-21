from flask import Blueprint, request, jsonify   # Flask tools: Blueprint + request + jsonify
from datetime import datetime, timezone                  # import class datetime
from Singleton.firebase_connection import FirebaseConnection # import firebase connection class

PRED_COLLECTION = "PREDICTED_FIRE"  # name of collection

# Blue print for predictions
predictions_bp = Blueprint("predictions_bp", __name__, url_prefix="/api/predictions")


# ---------- ROUTES ----------

@predictions_bp.route("", methods=["GET"])  # GET للاختبار وجلب البيانات
def api_get_predictions():

    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3")
    # قراءة user_id من الرابط (GET)

    return jsonify(get_user_predictions(user_id))
    # استدعاء الفنكشن وإرجاع النتيجة كـ JSON

@predictions_bp.route("", methods=["POST"])  # POST لحفظ طلب التنبؤ
def api_create_prediction_request():

    payload = request.get_json(silent=True) or {}

    user_id = payload.get("user_id")
    lat = payload.get("lat")
    lng = payload.get("lng")

    if not user_id or lat is None or lng is None:
        return jsonify({"ok": False, "error": "Missing user_id/lat/lng"}), 400

    area_name = payload.get("area_name")  # اختياري

    db = FirebaseConnection.get_db()

    doc = {
        "User_ID": str(user_id),
        "latitude": float(lat),
        "Longitude": float(lng),
        "Area_name": area_name or "منطقة محددة من المستخدم",

        "is_Predicted": None,
        "confidence": None,

        "predicted_at": datetime.now(timezone.utc),
    }

    ref = db.collection(PRED_COLLECTION).add(doc)
    doc_id = ref[1].id if isinstance(ref, (list, tuple)) and len(ref) > 1 else None

    return jsonify({"ok": True, "id": doc_id}), 201


# ---------- DATA FUNCTIONS ----------


# function that return user predictions based on User_ID
def get_user_predictions(user_id: str):

    db = FirebaseConnection.get_db() # get Firebase Connection

    docs = (
        db.collection(PRED_COLLECTION)
          .where("User_ID", "==", user_id)
          .stream()
    )
    # from collection return all documents that "User_ID", "==", user_id
    # stream is an iterator over returned documents

    results = [] # array for results

    # loop for documents
    for d in docs:
        data = d.to_dict() # convert document to dict
        data["id"] = d.id # adding id

        # convert date into ISO
        pred_at = data.get("predicted_at")

        if hasattr(pred_at, "to_datetime"):   # Firestore Timestamp
            data["predicted_at"] = pred_at.to_datetime().isoformat()

        elif isinstance(pred_at, datetime):   # datetime
            data["predicted_at"] = pred_at.isoformat()

        else:
            data["predicted_at"] = pred_at  # لو string أو None

        results.append(data)

    return results