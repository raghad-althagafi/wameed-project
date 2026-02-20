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


@predictions_bp.route("", methods=["POST"])  # POST لإرسال البيانات
def api_save_prediction():

    body = request.get_json(silent=True) or {}  
    # قراءة JSON body (لو فاضي يرجع dict فاضي)

    user_id = body.get("user_id", "F5OiRsaaIVCYhbzOyAt3")  # استخراج user_id
    area_name = body.get("area_name", "")  # اسم المنطقة
    lat = float(body.get("lat"))  # استخراج خط العرض
    lng = float(body.get("lng"))  # استخراج خط الطول
    is_predicted = bool(body.get("is_predicted", False))  # هل هو تنبؤ
    predicted_at = body.get("predicted_at")  # قراءة الوقت بصيغة ISO

    return jsonify(save_prediction(user_id, area_name, lat, lng, is_predicted, predicted_at))  
    # إرسال البيانات لفنكشن الحفظ وإرجاع النتيجة


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


def save_prediction(user_id: str, area_name: str, lat: float, lng: float, is_predicted: bool, predicted_at_iso: str):

    db = FirebaseConnection.get_db() # get Firebase Connection

    doc = {
        "User_ID": user_id,
        "Area_name": area_name,
        "latitude": lat,
        "longitude": lng,
        "is_Predicted": bool(is_predicted),
        "predicted_at": predicted_at_iso,
    }

    ref = db.collection(PRED_COLLECTION).document() # create new document
    ref.set(doc) # save data

    return {"id": ref.id, **doc} # return data with id