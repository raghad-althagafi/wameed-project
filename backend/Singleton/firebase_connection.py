import os
import firebase_admin
from firebase_admin import credentials, firestore

class FirebaseConnection:
    _db = None

    @staticmethod
    def initialize():
        # check if Firebase app is not initialized yet
        if not firebase_admin._apps:
            # get the main project folder path
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # build full path to firebase_key.json
            key_path = os.path.join(base_dir, "firebase_key.json")
            # load Firebase service account key
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred) # initialize Firebase app

    
    @staticmethod
    def get_db():
        if FirebaseConnection._db is None:
            cred = credentials.Certificate("firebase_key.json")

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)

            FirebaseConnection._db = firestore.client()

        return FirebaseConnection._db
