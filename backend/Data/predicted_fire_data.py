# data/predicted_fire_data.py
from datetime import datetime
from Singleton.firebase_connection import FirebaseConnection

PRED_COLLECTION = "PREDICTED_FIRE"  # عدّلي لو اسم الكولكشن مختلف

def get_user_predictions(user_id: str):
    db = FirebaseConnection.get_db()
    docs = (
        db.collection(PRED_COLLECTION)
          .where("User_ID", "==", user_id)
          .stream()
    )

    results = []
    for d in docs:
        data = d.to_dict()
        data["id"] = d.id

        # توحيد شكل التاريخ للفرونت (ISO)
        pred_at = data.get("predicted_at") or data.get("datetime") or data.get("created_at")
        if hasattr(pred_at, "to_datetime"):           # Firestore Timestamp
            data["predicted_at"] = pred_at.to_datetime().isoformat()
        elif isinstance(pred_at, datetime):           # datetime
            data["predicted_at"] = pred_at.isoformat()
        else:
            # لو عندك تاريخ كنص أصلاً خليه مثل ما هو
            data["predicted_at"] = pred_at

        results.append(data)

    return results


def save_prediction(user_id: str, area_name: str, lat: float, lng: float, is_predicted: bool, predicted_at_iso: str):
    db = FirebaseConnection.get_db()

    doc = {
        "User_ID": user_id,
        "Area_name": area_name,
        "latitude": lat,
        "Longitude": lng,
        "is_Predicted": bool(is_predicted),
        "predicted_at": predicted_at_iso,  # إذا تبين Timestamp صح 100% قولي لي أعطيك نسخة Timestamp
    }

    ref = db.collection(PRED_COLLECTION).document()
    ref.set(doc)
    return {"id": ref.id, **doc}