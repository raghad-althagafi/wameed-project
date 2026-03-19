from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from Singleton.firebase_connection import FirebaseConnection
from auth_utils import login_required

PREDICTED_COLLECTION = "PREDICTED_FIRE"

predictions_bp = Blueprint("predictions_bp", __name__, url_prefix="/api/predictions")


# ---------- HELPER FUNCTIONS ----------

# convert input datetime value into UTC datetime object
def _parse_datetime(value):
    if value:
        if hasattr(value, "to_datetime"):
            dt = value.to_datetime()  # convert Firestore timestamp to datetime
        elif isinstance(value, datetime):
            dt = value  # value is already datetime
        else:
            try:
                # convert ISO string into datetime
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                # if conversion fails, use current UTC time
                dt = datetime.now(timezone.utc)
    else:
        # if no value is given, use current UTC time
        dt = datetime.now(timezone.utc)

    # make sure datetime has UTC timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


# convert Firestore/datetime value into ISO string
def _to_iso(value):
    if value is None:
        return None

    # if value is Firestore timestamp, convert it first
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()

    # if value is datetime, convert it to UTC ISO format
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()

    # fallback return value as string
    return str(value)


# convert different input types into boolean
def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


# convert value into float, or return None if conversion fails
def _to_float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# convert Firestore prediction document into normal dictionary
def _serialize_prediction(doc_snapshot):
    data = doc_snapshot.to_dict() or {}

    return {
        "id": doc_snapshot.id,  # Firestore document ID
        "Area_name": data.get("Area_name"),  
        "Longitude": data.get("Longitude"),  
        "User_ID": data.get("User_ID"),  
        "is_Predicted": _to_bool(data.get("is_Predicted")), 
        "latitude": data.get("latitude"),  
        "predicted_at": _to_iso(data.get("predicted_at")), 
        "risk_level": data.get("risk_level")  
    }


# ---------- ROUTES ----------

# get all predictions for current logged in user
@predictions_bp.route("", methods=["GET"])
@login_required
def api_get_predictions():
    user_id = str(g.user_uid)
    predictions = get_user_predictions(user_id)

    # if user has no predictions then return empty list
    if not predictions:
        return jsonify({
            "ok": True,
            "message": "No predictions found",
            "data": []
        }), 200

    # return all found predictions
    return jsonify({
        "ok": True,
        "data": predictions
    }), 200


# get one prediction by its document ID
@predictions_bp.route("/<prediction_id>", methods=["GET"])
@login_required
def api_get_prediction_by_id(prediction_id):
    user_id = str(g.user_uid)
    db = FirebaseConnection.get_db()

    # get prediction document from Firestore
    doc_ref = db.collection(PREDICTED_COLLECTION).document(prediction_id)
    snap = doc_ref.get()

    # if document does not exist
    if not snap.exists:
        return jsonify({
            "ok": False,
            "error": "Prediction not found"
        }), 404

    data = snap.to_dict() or {}

    # prevent user from reading other users predictions
    if str(data.get("User_ID")) != user_id:
        return jsonify({
            "ok": False,
            "error": "Forbidden"
        }), 403

    # return prediction data
    return jsonify({
        "ok": True,
        "data": _serialize_prediction(snap)
    }), 200


# create and save a new prediction
@predictions_bp.route("", methods=["POST"])
@login_required
def api_create_prediction():
    payload = request.get_json(silent=True) or {}

    user_id = str(g.user_uid)

    # get values sent from frontend
    area_name = payload.get("area_name")
    is_predicted = payload.get("is_predicted")
    lat = _to_float_or_none(payload.get("lat"))
    lng = _to_float_or_none(payload.get("lng"))
    risk_level = str(payload.get("risk_level") or "safe")  # use safe if risk_level is missing

    # validate required fields
    if area_name is None or is_predicted is None or lat is None or lng is None:
        return jsonify({
            "ok": False,
            "error": "Missing area_name/is_predicted/lat/lng"
        }), 400

    # parse prediction datetime
    predicted_at_dt = _parse_datetime(payload.get("predicted_at"))

    db = FirebaseConnection.get_db()
    doc_ref = db.collection(PREDICTED_COLLECTION).document()

    # save prediction document in Firestore
    doc_ref.set({
        "Area_name": str(area_name),  # area name
        "Longitude": lng,  # longitude
        "User_ID": user_id,  # current user ID
        "is_Predicted": _to_bool(is_predicted),  # prediction boolean
        "latitude": lat,  # latitude
        "predicted_at": predicted_at_dt,  # prediction datetime
        "risk_level": risk_level  # risk level: safe / low / medium / high
    })

    return jsonify({
        "ok": True,
        "id": doc_ref.id,
        "message": "Prediction saved successfully"
    }), 201


# ---------- DATA FUNCTIONS ----------

# get all predictions for one specific user
def get_user_predictions(user_id: str):
    db = FirebaseConnection.get_db()

    # query predictions collection by user ID
    docs = (
        db.collection(PREDICTED_COLLECTION)
          .where("User_ID", "==", user_id)
          .stream()
    )

    results = []

    # convert each Firestore document into normal dictionary
    for d in docs:
        results.append(_serialize_prediction(d))

    # sort predictions by datetime, newest first
    results.sort(key=lambda item: item.get("predicted_at") or "", reverse=True)
    return results