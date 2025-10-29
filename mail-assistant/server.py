from flask import Flask, jsonify, request
from threading import Thread
import logging

# Import worker function defined in app.py
from app import run_agent_background

server = Flask(__name__)
app = server

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200

@app.route("/run", methods=["POST"])
def run_agent():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id")
    if not agent_id:
        return jsonify(error="agent_id required"), 400

    def _run():
        try:
            run_agent_background(agent_id)
        except Exception:
            app.logger.exception("agent run failed")

    Thread(target=_run, daemon=True).start()
    return jsonify(status="started", agent_id=agent_id), 202

@app.route("/", methods=["GET"])
def index():
    return jsonify(message="mail_assistant server running"), 200

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=8002)