"""
🛒 Mini App Server — Telegram Web App uchun statik fayl va balans API
Bu admin paneldan ALOHIDA — chunki Mini App ommaviy (login talab qilmaydi)
"""
import os
import hashlib
import hmac
from urllib.parse import parse_qsl
from flask import Flask, send_from_directory, request, jsonify

from data_store import get_user

# ══════════════════════════════════════════
#  CONFIG — Environment Variables orqali olinadi
# ══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
# ══════════════════════════════════════════

app = Flask(__name__, static_folder="webapp")


def verify_telegram_init_data(init_data: str) -> dict | None:
    """Telegram WebApp initData imzosini tekshiradi (xavfsizlik uchun majburiy)."""
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if computed_hash != received_hash:
            return None
        import json
        user_json = parsed.get("user")
        if user_json:
            return json.loads(user_json)
        return None
    except Exception:
        return None


@app.route("/webapp/")
@app.route("/webapp/<path:filename>")
def serve_webapp(filename="index.html"):
    return send_from_directory("webapp", filename)


@app.route("/api/balance")
def api_balance():
    init_data = request.args.get("initData", "")
    user = verify_telegram_init_data(init_data)
    if not user:
        return jsonify({"error": "invalid_signature", "balance": 0}), 401
    uid = user.get("id")
    ud = get_user(uid, user.get("username"), user.get("first_name"))
    return jsonify({"balance": ud.get("balance", 0)})


if __name__ == "__main__":
    print(f"🛒 Mini App server ishga tushdi: http://localhost:{PORT}/webapp/")
    app.run(host="0.0.0.0", port=PORT, debug=False)
