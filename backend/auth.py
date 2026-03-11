from flask import Blueprint, request, jsonify, g
from Singleton.firebase_connection import FirebaseConnection
from auth_utils import login_required

# create Blueprint for authentication routes
auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/auth")

# Firestore collection name
USER_COLLECTION = "USER"

# route for register endpoint
@auth_bp.route("/register", methods=["POST", "OPTIONS"])
def register_options():
    # handle preflight request
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return register_user() # call register function for POST request

# require logged-in user
@login_required
def register_user():
    # get JSON data from request
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip() # get and clean name value

# check if name is empty
    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400

    db = FirebaseConnection.get_db() # get Firestore database

    # get user id and email from verified token
    uid = g.user_uid
    email = g.user_email

    # create user document data
    user_doc = {
        "User_ID": uid,
        "User_name": name,
        "User_email": email
    }

    # save user document in Firestore
    db.collection(USER_COLLECTION).document(uid).set(user_doc, merge=True)

    # return success response
    return jsonify({
        "ok": True,
        "message": "User registered successfully",
        "user": user_doc
    }), 200

@auth_bp.route("/me", methods=["GET", "OPTIONS"])
def me_options():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return get_me()

@login_required
def get_me():
    db = FirebaseConnection.get_db()

    uid = g.user_uid
    doc_ref = db.collection(USER_COLLECTION).document(uid).get()

    if not doc_ref.exists:
        return jsonify({
            "ok": False,
            "error": "User profile not found"
        }), 404

    return jsonify({
        "ok": True,
        "user": doc_ref.to_dict()
    }), 200

# route for updating user profile
@auth_bp.route("/profile", methods=["PUT", "OPTIONS"])
def update_profile_options():
    # handle browser preflight request
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return update_profile()

# require logged-in user
@login_required
def update_profile():
    # get JSON data from request
    payload = request.get_json(silent=True) or {}

    # get updated values from frontend
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()

    # validate name
    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400

    # validate email
    if not email:
        return jsonify({"ok": False, "error": "Email is required"}), 400

    db = FirebaseConnection.get_db()

    # get current logged-in user id from verified token
    uid = g.user_uid

    # update Firestore profile document
    db.collection(USER_COLLECTION).document(uid).set({
        "User_ID": uid,
        "User_name": name,
        "User_email": email
    }, merge=True)

    # get the updated document
    updated_doc = db.collection(USER_COLLECTION).document(uid).get()

    # return updated user data
    return jsonify({
        "ok": True,
        "message": "User profile updated successfully",
        "user": updated_doc.to_dict()
    }), 200