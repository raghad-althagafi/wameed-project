from flask import Flask
from routes.test_gee import test_gee_bp

app = Flask(__name__)
app.register_blueprint(test_gee_bp)

if __name__ == "__main__":
    app.run(debug=True)