from flask import Blueprint, request, jsonify   # Flask tools: Blueprint + request + jsonify
from datetime import datetime                  # import class datetime
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