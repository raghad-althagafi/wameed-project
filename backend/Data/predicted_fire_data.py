from flask import Blueprint, request, jsonify   # Flask tools: Blueprint + request + jsonify
from datetime import datetime, timezone                  # import class datetime
from Singleton.firebase_connection import FirebaseConnection # import firebase connection class
from auth_utils import login_required
from flask import g

PRED_COLLECTION = "PREDICTED_FIRE"  # name of collection

# Blue print for predictions
predictions_bp = Blueprint("predictions_bp", __name__, url_prefix="/api/predictions") # any route in that blueprint start with /api/predictions


# ---------- ROUTES ----------

@predictions_bp.route("", methods=["GET"]) # route for method GET
@login_required
def api_get_predictions(): # the function will be excuted

    user_id = g.user_uid # return User_Id from the URL
    
    
    predictions = get_user_predictions(user_id)

    if not predictions:
        return jsonify({
            "ok": True,
            "message": "No predictions found",
            "data": []
        }), 200

    return jsonify({
        "ok": True,
        "data": predictions
    }), 200

@predictions_bp.route("", methods=["POST"])  # POST لحفظ طلب التنبؤ
@login_required
def api_create_prediction_request():

    payload = request.get_json(silent=True) or {}
    user_id = g.user_uid # return User_Id from Firebase token

    lat = payload.get("lat")
    lng = payload.get("lng")


    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Missing lat/lng"}), 400

    area_name = payload.get("area_name")  # اختياري

    db = FirebaseConnection.get_db()

    doc = {
        "User_ID": str(user_id),
        "latitude": float(lat),
        "Longitude": float(lng),
        "Area_name": area_name or "منطقة محددة من المستخدم",

        "is_Predicted": None,

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

    results = [] # array for predictions results after processing

    # loop for documents
    for d in docs:
        data = d.to_dict() # convert document to dict
        data["id"] = d.id # adding id

        
        pred_at = data.get("predicted_at") # return the value of predicted_at

        if hasattr(pred_at, "to_datetime"): # if pred_at has method to_datetime
            data["predicted_at"] = pred_at.to_datetime().isoformat() # then convert it to datetime then to ISO 
        else: # if pred_at does not have the method
            data["predicted_at"] = pred_at # same value 

        results.append(data) # append document to results array

    return results # return results which is documents