import os
import firebase_admin
from firebase_admin import credentials, firestore

class FirebaseConnection:
    _db = None

    @staticmethod
    def initialize():
        try:
            # check if Firebase app is not initialized yet
            if not firebase_admin._apps:
                # get the main project folder path
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                # build full path to firebase_key.json
                key_path = os.path.join(base_dir, "firebase_key.json")
                # load Firebase service account key
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred) # initialize Firebase app

        except Exception as e:
            print(f"Firebase initialization failed: {e}")
            raise

    
    @staticmethod
    def get_db():
        try:
            if FirebaseConnection._db is None:
                # Initialize Firebase first
                FirebaseConnection.initialize()
                 # Create Firestore database client
                FirebaseConnection._db = firestore.client()

            return FirebaseConnection._db

        except Exception as e:
            print(f"Firestore connection failed: {e}")
            raise
