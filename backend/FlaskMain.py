from flask import Flask #import Flask calss from flask library
from flask_cors import CORS
from Data.predicted_fire_data import predictions_bp 
from Data.detected_fire_data import detections_bp

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

#register BluePrints
app.register_blueprint(fire_spread_bluePrint)
app.register_blueprint(fire_threat_bp)
app.register_blueprint(test_gee_bp)

app.register_blueprint(predictions_bp)
app.register_blueprint(detections_bp)


if __name__ == "__main__":
    app.run(debug=True)