from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/hello")
def hello():
    return jsonify({"message": "Hello from Teamflow!"})


if __name__ == "__main__":
    # BUG: binds to 127.0.0.1 — unreachable from outside the container
    app.run(host="127.0.0.1", port=5000, debug=True)
