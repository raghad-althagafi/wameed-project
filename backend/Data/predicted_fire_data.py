from flask import Blueprint, request, jsonify # import BluePrint, request, jsonify
from datetime import datetime # import class datetime
from Singleton.firebase_connection import FirebaseConnection # import firebase connection class

PRED_COLLECTION = "PREDICTED_FIRE"  # name of collection

# Blue print for predictions
predictions_bp = Blueprint("predictions_bp", __name__, url_prefix="/api/predictions") # any route in that blueprint start with /api/predictions


# ---------- ROUTES ----------

@predictions_bp.route("", methods=["GET"]) # route for method GET
def api_get_predictions(): # the function will be excuted

    # F5OiRsaaIVCYhbzOyAt3 ONLY FOR TEST
    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3") # return User_Id from the URL
    
    # call get_user_predictions function to return user predictions
    return jsonify(get_user_predictions(user_id)) # convert it to JSON Response


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