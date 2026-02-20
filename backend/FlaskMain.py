import os
from flask import Flask #import Flask calss from flask library
from flask_cors import CORS
# ------------- for data retrival------------------
from flask import request, jsonify
from Data.predicted_fire_data import get_user_predictions
from Data.predicted_fire_data import save_prediction
from Data.detected_fire_data import get_user_detections
# ------------- for data retrival------------------

# ----------------- PAGES ROUTES ------------------
# from flask import render_template
# from routes.pages import pages_bp
# ----------------- PAGES ROUTES ------------------

from routes.test_gee import test_gee_bp
from Singleton.gee_connection import GEEConnection #import GEEConnection calss from gee_connection file
from FireSpreadEstimator import fire_spread_bluePrint #import fire_spread_bluePrint from FireSpreadEstimator file
from FireThreatEstimator import fire_threat_bp


# ----------------- PAGES ROUTES ------------------
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
# FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
# PAGES_DIR = os.path.join(FRONTEND_DIR, "pages")
# ----------------- PAGES ROUTES ------------------


app = Flask(__name__) # create the server

CORS(app)

GEEConnection.get_instance() # initalize google earth engine connection once turning on the server, so whenever connection needed after that it will be returned

#register the routes in BluePrints
# app.register_blueprint(pages_bp)
app.register_blueprint(fire_spread_bluePrint)
app.register_blueprint(fire_threat_bp)
app.register_blueprint(test_gee_bp)

#-----------------------------------------------

@app.route("/api/predictions", methods=["GET"])
def api_get_predictions():
    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3")
    return jsonify(get_user_predictions(user_id))



@app.route("/api/predictions", methods=["POST"])
def api_save_prediction():
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", "F5OiRsaaIVCYhbzOyAt3")
    area_name = body.get("area_name", "")
    lat = float(body.get("lat"))
    lng = float(body.get("lng"))
    is_predicted = bool(body.get("is_predicted", False))
    predicted_at = body.get("predicted_at")  # ISO string

    return jsonify(save_prediction(user_id, area_name, lat, lng, is_predicted, predicted_at))


@app.route("/api/detections", methods=["GET"])
def api_get_detections():
    user_id = request.args.get("user_id", "F5OiRsaaIVCYhbzOyAt3")
    return jsonify(get_user_detections(user_id))

#-----------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)