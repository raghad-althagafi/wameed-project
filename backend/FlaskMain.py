from flask import Flask #import Flask calss from flask library
from flask_cors import CORS
from Data.predicted_fire_data import predictions_bp 
from Data.detected_fire_data import detections_bp

# ----------------- PAGES ROUTES ------------------
# from flask import render_template
# from routes.pages import pages_bp
# ----------------- PAGES ROUTES ------------------

from test_gee import test_gee_bp
from Singleton.gee_connection import GEEConnection #import GEEConnection calss from gee_connection file
from FireSpreadEstimator import fire_spread_bluePrint #import fire_spread_bluePrint from FireSpreadEstimator file
from FireThreatEstimator import fire_threat_bp 
from FireAreaEstimator import fire_area_bp # import active fire area Blueprint
from FireDetection import fire_detection_bp
from FirePrediction import fire_prediction_bp
from auth import auth_bp

GEEConnection.get_instance() # initalize google earth engine connection once turning on the server, so whenever connection needed after that it will be returned

# ----------------- PAGES ROUTES ------------------
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
# FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
# PAGES_DIR = os.path.join(FRONTEND_DIR, "pages")
# ----------------- PAGES ROUTES ------------------

app = Flask(__name__) # create the server

# enable CORS for frontend requests
CORS(
    app,
    resources={r"/*": {"origins": [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ]}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    supports_credentials=True
)
# GEEConnection.get_instance() # initalize google earth engine connection once turning on the server, so whenever connection needed after that it will be returned

#register BluePrints
app.register_blueprint(fire_spread_bluePrint)
app.register_blueprint(fire_threat_bp)
app.register_blueprint(fire_area_bp)
app.register_blueprint(test_gee_bp)

app.register_blueprint(predictions_bp)
app.register_blueprint(detections_bp)
app.register_blueprint(fire_detection_bp)
app.register_blueprint(fire_prediction_bp)

app.register_blueprint(auth_bp)

if __name__ == "__main__":
    app.run(debug=True)