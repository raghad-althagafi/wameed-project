from flask import Blueprint, request, jsonify
from datetime import datetime # import class datetime
from Singleton.firebase_connection import FirebaseConnection  # import firebase connection class

DETECTED_COLLECTION = "detected_fire" # name of collection

# Blue print for detections
detections_bp = Blueprint("detections_bp", __name__, url_prefix="/api/detections")

# ---------- ROUTES ----------

@detections_bp.route("", methods=["GET"]) # route for method GET
def api_get_detections(): # the function will be excuted

# F5OiRsaaIVCYhbzOyAt3 ONLY FOR TEST
    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3") # return User_Id from the URL
    
    # call get_user_detections function to return user detections
    return jsonify(get_user_detections(user_id))

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