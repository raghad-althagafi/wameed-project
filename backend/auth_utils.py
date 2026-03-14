from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth
from Singleton.firebase_connection import FirebaseConnection

# function to get Bearer token from request header
def get_bearer_token():
    # get Authorization header
    auth_header = request.headers.get("Authorization", "")
    # check if header starts with Bearer
    if not auth_header.startswith("Bearer "):
        return None
    # return token only without the word Bearer
    return auth_header.split(" ", 1)[1].strip()

# function to verify Firebase token
def verify_request_token():
    token = get_bearer_token() # get token from request
    # if token does not exist
    if not token:
        return None, ("Missing Authorization Bearer token", 401)

    try:
        FirebaseConnection.get_db()  # ensures firebase app is initialized
        decoded = auth.verify_id_token(token, clock_skew_seconds=60) # verify token using Firebase Admin
        return decoded, None # return decoded token data
    except Exception as e:
        # return error if token is invalid
        return None, (f"Invalid token: {str(e)}", 401)

# decorator to protect routes and require login
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 200
        # verify token from request
        decoded, error = verify_request_token()
        if error:
            message, status = error
            return jsonify({"ok": False, "error": message}), status

        # save Firebase user data in Flask global object
        g.firebase_user = decoded
        g.user_uid = decoded.get("uid")
        g.user_email = decoded.get("email")
        return fn(*args, **kwargs) # run the original function
    return wrapper