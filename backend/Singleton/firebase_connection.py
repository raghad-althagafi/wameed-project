import firebase_admin
from firebase_admin import credentials, firestore

class FirebaseConnection:
    _db = None

    @staticmethod
    def get_db():
        if FirebaseConnection._db is None:
            cred = credentials.Certificate("firebase_key.json")  # لأنه داخل backend
            firebase_admin.initialize_app(cred)
            FirebaseConnection._db = firestore.client()
        return FirebaseConnection._db
