# main.py
import os
import signal
import subprocess
import time
import threading
from flask import Flask, request, jsonify

# Env vars (Render sets PORT). Default 8443 for local testing.
PORT = int(os.getenv("PORT", "8443"))
BOT_PROCESS_CMD = ["python", "bot.py"]  # अगर तुम्हारा bot चलाने का कमांड कुछ और है तो बदल देना

app = Flask(__name__)
bot_proc = None
bot_lock = threading.Lock()

def start_bot_process():
    global bot_proc
    with bot_lock:
        if bot_proc and bot_proc.poll() is None:
            # already running
            return
        # Start bot.py as subprocess, inherit env so BOT_TOKEN, DATABASE_URL etc are visible
        bot_proc = subprocess.Popen(BOT_PROCESS_CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=os.environ)
        threading.Thread(target=stream_bot_logs, args=(bot_proc,), daemon=True).start()

def stop_bot_process():
    global bot_proc
    with bot_lock:
        if not bot_proc:
            return
        try:
            bot_proc.terminate()
            # give it a moment, then kill if not stopped
            try:
                bot_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bot_proc.kill()
        except Exception:
            pass
        bot_proc = None

def stream_bot_logs(proc):
    # optional: stream bot stdout to main process stdout (visible in Render logs)
    try:
        for line in proc.stdout:
            print(line.decode(errors="ignore").rstrip())
    except Exception:
        pass

@app.route("/", methods=["GET"])
def index():
    return "OK - Web service running", 200

@app.route("/health", methods=["GET"])
def health():
    # Simple health check: is bot subprocess alive?
    alive = False
    with bot_lock:
        alive = bot_proc is not None and bot_proc.poll() is None
    return jsonify({"status": "ok", "bot_running": alive}), 200

@app.route("/restart-bot", methods=["POST"])
def restart_bot():
    # Optional protected restart endpoint (set ADMIN_TOKEN env var)
    admin_token = os.getenv("ADMIN_TOKEN")
    req_token = request.headers.get("Authorization") or request.args.get("token")
    if admin_token:
        if not req_token or req_token != admin_token:
            return "Unauthorized", 401
    # restart
    stop_bot_process()
    time.sleep(1)
    start_bot_process()
    return "restarted", 200

# Placeholder webhook route (if you later switch to webhook mode,
# you can forward the incoming JSON to bot or handle here).
@app.route("/webhook", methods=["POST"])
def webhook_receiver():
    # For now, just acknowledge. If later you enable webhook handling
    # in bot.py, you can forward this JSON or let bot set webhook itself.
    return "Received", 200

def _graceful_shutdown(signum, frame):
    print("Shutting down gracefully...")
    stop_bot_process()
    # allow Flask to exit after this handler returns

if __name__ == "__main__":
    # ensure we catch TERM/INT so subprocesses are stopped cleanly
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    # Start bot subprocess
    start_bot_process()

    # Start Flask (use 0.0.0.0 for Render)
    app.run(host="0.0.0.0", port=PORT)
