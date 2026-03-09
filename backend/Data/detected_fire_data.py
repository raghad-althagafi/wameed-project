from flask import Blueprint, jsonify, g
from datetime import datetime # import class datetime
from Singleton.firebase_connection import FirebaseConnection  # import firebase connection class
from auth_utils import login_required

DETECTED_COLLECTION = "detected_fire" # name of collection

# Blue print for detections
detections_bp = Blueprint("detections_bp", __name__, url_prefix="/api/detections")

# ---------- ROUTES ----------

@detections_bp.route("", methods=["GET"]) # route for method GET
@login_required
def api_get_detections(): # the function will be excuted


    user_id = g.user_uid # return User_Id from Firebase token
    
    # call get_user_detections function to return user detections
    detections = get_user_detections(user_id)

    if not detections:
        return jsonify({
            "ok": True,
            "message": "No detections found",
            "data": []
        }), 200

    return jsonify({
        "ok": True,
        "data": detections
    }), 200

# ---------- DATA ----------

# function that return user detections based on User_ID
def get_user_detections(user_id: str):
    db = FirebaseConnection.get_db() # get Firebase Connection

    docs = (
        db.collection(DETECTED_COLLECTION)
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

        det_at = data.get("detected_at") # return the value of detected_at
        if hasattr(det_at, "to_datetime"): # if detected_at has method to_datetime
            data["detected_at"] = det_at.to_datetime().isoformat() # then convert it to datetime then to ISO 
        elif isinstance(det_at, datetime): # if detected_at does not have the method
            data["detected_at"] = det_at.isoformat()

        results.append(data) # append document to results array

    return results # return results which is documents