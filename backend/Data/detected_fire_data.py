# Data/detected_fire_data.py
from datetime import datetime
from Singleton.firebase_connection import FirebaseConnection

DETECTED_COLLECTION = "detected_fire"  # عدّلي لو اسم الكولكشن مختلف عندك

def get_user_detections(user_id: str):
    db = FirebaseConnection.get_db()

    docs = (
        db.collection(DETECTED_COLLECTION)
          .where("User_ID", "==", user_id)
          .stream()
    )

    results = []
    for d in docs:
        data = d.to_dict()
        data["id"] = d.id

        # توحيد التاريخ للفرونت
        det_at = data.get("detected_at")
        if hasattr(det_at, "to_datetime"):          # Firestore Timestamp
            data["detected_at"] = det_at.to_datetime().isoformat()
        elif isinstance(det_at, datetime):
            data["detected_at"] = det_at.isoformat()
        else:
            data["detected_at"] = det_at  # string أو None

        results.append(data)

    return results