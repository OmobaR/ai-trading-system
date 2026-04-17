"""
Simple Flask health & emergency stop server.
Runs in a background thread so it doesn't block the async trading loop.
"""

from flask import Flask, jsonify
import threading
import os
import signal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

app = Flask(__name__)
emergency_stop_flag = False
risk_manager_instance = None  # Will be set from main.py

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'emergency_stop': emergency_stop_flag,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/stop', methods=['POST', 'GET'])
def emergency_stop():
    global emergency_stop_flag
    emergency_stop_flag = True
    logger.critical("🚨 EMERGENCY STOP triggered via /stop endpoint")
    # Graceful shutdown signal
    os.kill(os.getpid(), signal.SIGTERM)
    return jsonify({'status': 'stopping'}), 200

@app.route('/risk')
def risk_report():
    if risk_manager_instance is None:
        return jsonify({'error': 'Risk manager not initialized'}), 503
    report = risk_manager_instance.get_risk_report()
    return jsonify(report)

def run_health_server(port: int = 8080):
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def start_health_server(risk_manager=None, port: int = 8080):
    global risk_manager_instance
    risk_manager_instance = risk_manager
    thread = threading.Thread(target=run_health_server, args=(port,), daemon=True)
    thread.start()
    logger.info(f"✅ Health & emergency server started on http://localhost:{port}")