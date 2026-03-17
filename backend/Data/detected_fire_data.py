from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone # import class datetime
from Singleton.firebase_connection import FirebaseConnection  # import firebase connection class
from auth_utils import login_required

DETECTED_COLLECTION = "DETECTED_FIRE" # name of collection

DETAILS_SUBCOLLECTION = "FIRE_DETAILS" # Subcollection name for fire details

# Blueprint for detections
detections_bp = Blueprint("detections_bp", __name__, url_prefix="/api/detections")


# ---------- HELPER FUNCTIONS ---------- 

# convert input datetime to UTC datetime
def _parse_datetime(value):
    # if available, convert it
    if value:
        # Firestore Timestamp usually have to_datetime()
        if hasattr(value, "to_datetime"):
            dt = value.to_datetime()
        # use it directly if it is python datetime object
        elif isinstance(value, datetime):
            dt = value
        else:
            # parse it
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                # if fails use utc time as fallback
                dt = datetime.now(timezone.utc)
    else:
        # use current utc time 
        dt = datetime.now(timezone.utc)

    # make sure it is in timezone and utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt

# convert Firestore datetime objects to iso
def _to_iso(value):
    if value is None:
        return None

    # convert it to python datetime
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()

    # if the value is a datetime then normalize it to utc and convert it to iso
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc) # assume datetime is UTC
        else:
            value = value.astimezone(timezone.utc) # convert datetime to UTC
        return value.isoformat() # convert datetime to iso

    # if the value is not a datetime return its string
    return str(value)

# convert common formats to bool
def _to_bool(value):
    # if it is already bool return it
    if isinstance(value, bool):
        return value
    # numeric values: 0 = False, else = True
    if isinstance(value, (int, float)):
        return value != 0
    # convert common true-like strings into True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    # anything else is False
    return False

def _to_float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
    
def _serialize_details(doc_snapshot):
    if not doc_snapshot.exists:
        return None

    data = doc_snapshot.to_dict() or {}

    return {
        "id": doc_snapshot.id,
        "Details_ID": data.get("Details_ID"),
        "Temperature": data.get("Temperature"),
        "Humidity": data.get("Humidity"),
        "Severity": data.get("Severity"),
        "Spread_Direction": data.get("Spread_Direction"),
        "Burned_Area": data.get("Burned_Area"),
    }

def _serialize_detection(doc_snapshot):
    data = doc_snapshot.to_dict() or {}

    details_snap = doc_snapshot.reference.collection("FIRE_DETAILS").document("details").get()
    details_obj = _serialize_details(details_snap)

    return {
        "id": doc_snapshot.id,
        "Fire_ID": data.get("Fire_ID", doc_snapshot.id),
        "User_ID": data.get("User_ID"),
        "Area_name": data.get("Area_name"),
        "Latitude": data.get("Latitude"),
        "Longitude": data.get("Longitude"),
        "Is_detected": _to_bool(data.get("Is_detected")),
        "Detected_At": _to_iso(data.get("Detected_At")),
        "FIRE_DETAILS": [details_obj] if details_obj else []
    }

# ---------- ROUTES ----------

@detections_bp.route("", methods=["GET"]) # route for method GET
@login_required # take user token and check it
def api_get_detections(): # the function will be excuted

    user_id = g.user_uid # get user id from the token
    
    # call get_user_detections function to return user detections
    detections = get_user_detections(user_id)

    if not detections: # if there is no detections
        return jsonify({
            "ok": True,
            "message": "No detections found",
            "data": []
        }), 200

    return jsonify({ # return detections
        "ok": True,
        "data": detections
    }), 200

@detections_bp.route("/<fire_id>", methods=["GET"])
@login_required
def api_get_detection_by_id(fire_id):

    user_id = str(g.user_uid)
    db = FirebaseConnection.get_db()

    doc_ref = db.collection(DETECTED_COLLECTION).document(fire_id)
    snap = doc_ref.get()

    # Check if document exists
    if not snap.exists:
        return jsonify({
            "ok": False,
            "error": "Detection not found"
        }), 404

    data = snap.to_dict() or {}

    # Make sure the user owns this document
    if str(data.get("User_ID")) != user_id:
        return jsonify({
            "ok": False,
            "error": "Forbidden"
        }), 403
    
    return jsonify({
        "ok": True,
        "data": _serialize_detection(snap)
    }), 200

# POST DETECTION

# save a detection result into Firestore
@detections_bp.route("", methods=["POST"])
@login_required
def api_create_detection():
    # read json body safely
    payload = request.get_json(silent=True) or {}

    # user_id comes from Firebase token, not from frontend
    user_id = str(g.user_uid)

    # Required fields
    area_name = payload.get("area_name")
    is_detected = payload.get("is_detected")
    lat = _to_float_or_none(payload.get("lat"))
    lng = _to_float_or_none(payload.get("lng"))

    # Validate required fields
    if area_name is None or is_detected is None or lat is None or lng is None:
        return jsonify({
            "ok": False,
            "error": "Missing area_name/is_detected/lat/lng"
        }), 400
    
    # parse the detection time
    detected_at_dt = _parse_datetime(payload.get("detected_at"))

    # FIRE_DETAILS values
    temperature = _to_float_or_none(payload.get("temperature"))
    humidity = _to_float_or_none(payload.get("humidity"))
    severity = payload.get("severity")
    spread_direction = payload.get("spread_direction")
    burned_area = _to_float_or_none(payload.get("burned_area"))

    print("SAVE TEMP:", temperature)
    print("SAVE HUM:", humidity)

    # get Firestore database instance
    db = FirebaseConnection.get_db() 

    # create a new document reference
    doc_ref = db.collection(DETECTED_COLLECTION).document()
    fire_id = doc_ref.id

    # main detection document data
    main_doc = {
        "Fire_ID": fire_id,
        "User_ID": user_id,
        "Area_name": str(area_name),
        "Latitude": lat,
        "Longitude": lng,
        "Is_detected": _to_bool(is_detected),
        "Detected_At": detected_at_dt,
    }

    # save the main detection document into Firestore
    doc_ref.set(main_doc)

    # save detailed fire information if a fire was detected
    if _to_bool(is_detected):
        details_ref = doc_ref.collection(DETAILS_SUBCOLLECTION).document("details")

        details_ref.set({
            "Details_ID": f"{fire_id}_details",
            "Temperature": temperature,
            "Humidity": humidity,
            "Severity": severity,
            "Spread_Direction": spread_direction,
            "Burned_Area": burned_area
        })

        saved_details = details_ref.get().to_dict() or {}
        print("SAVED DETAILS DOC:", saved_details)

    # return success response
    return jsonify({
        "ok": True,
        "id": fire_id,
        "message": "Detection saved successfully"
    }), 201

@detections_bp.route("/<fire_id>/details", methods=["PATCH", "OPTIONS"])
@login_required
def api_update_detection_details(fire_id):
    if request.method == "OPTIONS":
        return "", 200
    
    payload = request.get_json(silent=True) or {}
    user_id = str(g.user_uid)
    db = FirebaseConnection.get_db() # get Firebase Connection

    # Get main fire document
    doc_ref = db.collection(DETECTED_COLLECTION).document(fire_id)
    snap = doc_ref.get()

    if not snap.exists:
        return jsonify({
            "ok": False,
            "error": "Detection not found"
        }), 404

    data = snap.to_dict() or {}

    # Check ownership
    if str(data.get("User_ID")) != user_id:
        return jsonify({
            "ok": False,
            "error": "Forbidden"
        }), 403

    # Prepare allowed fields for update
    update_data = {}

    if "temperature" in payload or "Temperature" in payload:
        update_data["Temperature"] = _to_float_or_none(
            payload.get("Temperature", payload.get("temperature"))
        )

    if "humidity" in payload or "Humidity" in payload:
        update_data["Humidity"] = _to_float_or_none(
            payload.get("Humidity", payload.get("humidity"))
        )

    if "severity" in payload or "Severity" in payload:
        update_data["Severity"] = payload.get("Severity", payload.get("severity"))

    if "spread_direction" in payload or "Spread_Direction" in payload:
        update_data["Spread_Direction"] = payload.get(
            "Spread_Direction",
            payload.get("spread_direction")
        )

    if "burned_area" in payload or "Burned_Area" in payload:
        update_data["Burned_Area"] = _to_float_or_none(
            payload.get("Burned_Area", payload.get("burned_area"))
        )

    if not update_data:
        return jsonify({
            "ok": False,
            "error": "No valid fields to update"
        }), 400

    details_ref = doc_ref.collection(DETAILS_SUBCOLLECTION).document("details")

    # Create empty details doc if it does not exist yet
    current_details = details_ref.get()
    if not current_details.exists:
        details_ref.set({
            "Details_ID": f"{fire_id}_details",
            "Temperature": None,
            "Humidity": None,
            "Severity": None,
            "Spread_Direction": None,
            "Burned_Area": None
        })

    details_ref.set(update_data, merge=True)

    updated_snap = details_ref.get()
    updated_data = _serialize_details(updated_snap)

    return jsonify({
        "ok": True,
        "message": "Fire details updated successfully",
        "data": updated_data
    }), 200

# ---------- DATA ----------

# function that return user detections based on User_ID
def get_user_detections(user_id: str):
    db = FirebaseConnection.get_db() # get Firebase Connection

    docs = ( # return user documents for fire detections
        db.collection(DETECTED_COLLECTION)
          .where("User_ID", "==", str(user_id))
          .stream()
    )

    results = [_serialize_detection(d) for d in docs] # convert every doc into object

    # Sort newest first
    results.sort(key=lambda item: item.get("Detected_At") or "", reverse=True)

    return results # return results which is documents