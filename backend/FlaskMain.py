import os
from flask import Flask #import Flask calss from flask library
from flask_cors import CORS
from flask import render_template
from routes.test_gee import test_gee_bp
from Singleton.gee_connection import GEEConnection #import GEEConnection calss from gee_connection file
from routes.pages import pages_bp
from FireSpreadEstimator import fire_spread_bluePrint #import fire_spread_bluePrint from FireSpreadEstimator file
from FireThreatEstimator import fire_threat_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
PAGES_DIR = os.path.join(FRONTEND_DIR, "pages")


# Create Flask app
app = Flask(
    __name__,
    template_folder=PAGES_DIR,     # frontend/pages
    static_folder=FRONTEND_DIR,    # frontend
    static_url_path=""             
)

CORS(app)

GEEConnection.get_instance() # initalize google earth engine connection once turning on the server, so whenever connection needed after that it will be returned

#register the routes in BluePrints
app.register_blueprint(pages_bp)
app.register_blueprint(fire_spread_bluePrint)
app.register_blueprint(fire_threat_bp)
app.register_blueprint(test_gee_bp)

if __name__ == "__main__":
    app.run(debug=True)