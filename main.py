import os
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def hello():
    return jsonify({
        "status": "success",
        "message": "Hello Suresh! Python Cloud Run is working."
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)