from flask import Flask #import Flask calss from flask library
from routes.test_gee import test_gee_bp
from Singleton.gee_connection import GEEConnection #import GEEConnection calss from gee_connection file
from FireSpreadEstimator import fire_spread_bluePrint #import fire_spread_bluePrint from FireSpreadEstimator file


app = Flask(__name__) # create the server

GEEConnection.get_instance() # initalize google earth engine connection once turning on the server, so whenever connection needed after that it will be returned

#register the routes in BluePrints
app.register_blueprint(fire_spread_bluePrint)
app.register_blueprint(test_gee_bp)

if __name__ == "__main__":
    app.run(debug=True)