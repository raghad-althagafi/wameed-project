from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Wameed backend is running"

@app.route("/api/test")
def test():
    return jsonify({"status": "ok", "message": "API is working"})

if __name__ == "__main__":
    app.run(debug=True)