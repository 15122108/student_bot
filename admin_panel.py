"""
🌐 Web Admin Panel — Talaba AI Bot uchun
Brauzerda to'lovlarni ko'rish va tasdiqlash/rad etish
"""
import os
import asyncio
from functools import wraps
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

from data_store import get_pending_topups, approve_topup, reject_topup, get_stats, load_data

# ══════════════════════════════════════════
#  CONFIG — Environment Variables orqali olinadi
# ══════════════════════════════════════════
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CHANGE_ME_STRONG_PASSWORD")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-string")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "5000"))
# ══════════════════════════════════════════

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ── Auth ───────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Telegram notify helper (sync wrapper) ──
async def _send_telegram_message(chat_id, text):
    import aiohttp
    async with aiohttp.ClientSession() as s:
        await s.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )

def notify_user(chat_id, text):
    try:
        asyncio.run(_send_telegram_message(chat_id, text))
    except Exception as e:
        print(f"Notify error: {e}")


# ── Templates ──────────────────────────────
BASE_STYLE = """
<style>
  :root {
    --bg: #0F1115;
    --panel: #171A21;
    --panel-2: #1E222B;
    --border: #2A2F3A;
    --text: #E8EAED;
    --text-dim: #8B92A3;
    --accent: #4F8CFF;
    --accent-dim: #2A4A8C;
    --green: #2FBF71;
    --red: #E5484D;
    --amber: #F5A623;
    --radius: 12px;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    min-height: 100vh;
  }
  .topbar {
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 16px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .brand {
    font-weight: 700;
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .brand .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
  .logout-link { color: var(--text-dim); text-decoration: none; font-size: 14px; }
  .logout-link:hover { color: var(--text); }
  .container { max-width: 1100px; margin: 0 auto; padding: 28px; }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
  }
  .stat-label { color: var(--text-dim); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
  .stat-value { font-size: 26px; font-weight: 700; }
  .stat-value.accent { color: var(--accent); }
  .stat-value.amber { color: var(--amber); }
  .section-title { font-size: 15px; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 14px 2px; }
  .payment-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    margin-bottom: 14px;
    display: flex;
    gap: 18px;
    align-items: flex-start;
  }
  .payment-receipt img {
    width: 110px;
    height: 110px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px solid var(--border);
    cursor: pointer;
  }
  .payment-info { flex: 1; min-width: 0; }
  .payment-user { font-weight: 600; font-size: 16px; margin-bottom: 2px; }
  .payment-uid { color: var(--text-dim); font-size: 12px; margin-bottom: 10px; }
  .payment-amount { font-size: 22px; font-weight: 700; color: var(--amber); margin-bottom: 8px; }
  .payment-meta {
    background: var(--panel-2);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 12px;
    color: var(--text-dim);
    font-family: 'SF Mono', Consolas, monospace;
    margin-bottom: 12px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .payment-actions { display: flex; gap: 8px; }
  .btn {
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.85; }
  .btn-approve { background: var(--green); color: #06231A; }
  .btn-reject { background: var(--red); color: #2A0C0E; }
  .empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
  }
  .empty-state .icon { font-size: 40px; margin-bottom: 12px; }
  .login-wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .login-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 36px 32px;
    width: 320px;
  }
  .login-card h1 { font-size: 20px; margin: 0 0 4px; }
  .login-card p { color: var(--text-dim); font-size: 13px; margin: 0 0 24px; }
  .field { margin-bottom: 14px; }
  .field label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
  .field input {
    width: 100%;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    color: var(--text);
    font-size: 14px;
  }
  .field input:focus { outline: none; border-color: var(--accent); }
  .btn-login {
    width: 100%;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 11px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 6px;
  }
  .error-msg { color: var(--red); font-size: 13px; margin-bottom: 14px; }
  .modal-overlay {
    display: none;
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.8);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal-overlay img { max-width: 90vw; max-height: 90vh; border-radius: 8px; }
  .refresh-note { color: var(--text-dim); font-size: 12px; margin-bottom: 18px; }
</style>
"""

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin Panel — Kirish</title>
  {{ style|safe }}
</head>
<body>
  <div class="login-wrap">
    <form class="login-card" method="POST">
      <h1>🎓 Admin Panel</h1>
      <p>Talaba AI Bot boshqaruvi</p>
      {% if error %}<div class="error-msg">❌ {{ error }}</div>{% endif %}
      <div class="field">
        <label>Login</label>
        <input type="text" name="username" autocomplete="username" required autofocus>
      </div>
      <div class="field">
        <label>Parol</label>
        <input type="password" name="password" autocomplete="current-password" required>
      </div>
      <button type="submit" class="btn-login">Kirish</button>
    </form>
  </div>
</body>
</html>
"""

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin Panel — To'lovlar</title>
  {{ style|safe }}
</head>
<body>
  <div class="topbar">
    <div class="brand"><span class="dot"></span> Talaba AI Bot — Admin Panel</div>
    <a class="logout-link" href="{{ url_for('logout') }}">Chiqish →</a>
  </div>
  <div class="container">
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Foydalanuvchilar</div>
        <div class="stat-value">{{ stats.total_users }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Jami balans</div>
        <div class="stat-value accent">{{ "{:,}".format(stats.total_balance).replace(",", " ") }} so'm</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Jami sarflangan</div>
        <div class="stat-value">{{ "{:,}".format(stats.total_spent).replace(",", " ") }} so'm</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Kutilmoqda</div>
        <div class="stat-value amber">{{ stats.pending_count }} ta</div>
      </div>
    </div>

    <div class="section-title">⏳ Tasdiqlash kutilayotgan to'lovlar</div>
    <div class="refresh-note">Sahifa har 15 soniyada avtomatik yangilanadi</div>

    {% if pending %}
      {% for p in pending %}
      <div class="payment-card">
        {% if p.receipt_file_url %}
        <div class="payment-receipt">
          <img src="{{ p.receipt_file_url }}" onclick="openModal('{{ p.receipt_file_url }}')" alt="chek">
        </div>
        {% endif %}
        <div class="payment-info">
          <div class="payment-user">{{ p.first_name or "Noma'lum" }} {% if p.username %}(@{{ p.username }}){% endif %}</div>
          <div class="payment-uid">ID: {{ p.uid }} · Joriy balans: {{ "{:,}".format(p.balance).replace(",", " ") }} so'm</div>
          <div class="payment-amount">💰 {{ "{:,}".format(p.amount).replace(",", " ") }} so'm</div>
          {% if p.receipt_info %}
          <div class="payment-meta">🤖 AI o'qigan ma'lumot:
{{ p.receipt_info }}</div>
          {% endif %}
          <div class="payment-actions">
            <form method="POST" action="{{ url_for('approve', uid=p.uid) }}" style="display:inline;">
              <button class="btn btn-approve" type="submit">✅ Tasdiqlash</button>
            </form>
            <form method="POST" action="{{ url_for('reject', uid=p.uid) }}" style="display:inline;">
              <button class="btn btn-reject" type="submit">❌ Rad etish</button>
            </form>
          </div>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty-state">
        <div class="icon">✅</div>
        Hozircha kutilayotgan to'lovlar yo'q
      </div>
    {% endif %}
  </div>

  <div class="modal-overlay" id="modal" onclick="closeModal()">
    <img id="modal-img" src="">
  </div>

  <script>
    function openModal(src) {
      document.getElementById('modal-img').src = src;
      document.getElementById('modal').classList.add('open');
    }
    function closeModal() {
      document.getElementById('modal').classList.remove('open');
    }
    setTimeout(() => location.reload(), 15000);
  </script>
</body>
</html>
"""


# ── Routes ──────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Login yoki parol noto'g'ri"
    return render_template_string(LOGIN_PAGE, style=BASE_STYLE, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    pending = get_pending_topups()
    for p in pending:
        if p.get("receipt_file_id"):
            p["receipt_file_url"] = url_for("receipt_image", file_id=p["receipt_file_id"])
        else:
            p["receipt_file_url"] = None
    stats = get_stats()
    return render_template_string(DASHBOARD_PAGE, style=BASE_STYLE, pending=pending, stats=stats)

@app.route("/receipt/<file_id>")
@login_required
def receipt_image(file_id):
    """Telegram fayl serveridan chek rasmini olib, brauzerga uzatish"""
    import requests
    try:
        file_info = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}").json()
        file_path = file_info["result"]["file_path"]
        img_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        img_resp = requests.get(img_url)
        return img_resp.content, 200, {"Content-Type": "image/jpeg"}
    except Exception as e:
        return "", 404

@app.route("/approve/<uid>", methods=["POST"])
@login_required
def approve(uid):
    data = load_data()
    ud = data.get(str(uid), {})
    lang = ud.get("lang", "uz")
    amount = approve_topup(uid)
    if amount:
        new_bal = load_data().get(str(uid), {}).get("balance", 0)
        text = (
            f"✅ *To'lovingiz tasdiqlandi!*\n\n💰 +{amount:,} so'm\n💵 Yangi balans: {new_bal:,} so'm".replace(",", " ")
            if lang == "uz" else
            f"✅ *Ваш платёж подтверждён!*\n\n💰 +{amount:,} сум\n💵 Новый баланс: {new_bal:,} сум".replace(",", " ")
        )
        notify_user(int(uid), text)
    return redirect(url_for("dashboard"))

@app.route("/reject/<uid>", methods=["POST"])
@login_required
def reject(uid):
    data = load_data()
    ud = data.get(str(uid), {})
    lang = ud.get("lang", "uz")
    ok = reject_topup(uid)
    if ok:
        text = (
            "❌ To'lovingiz tasdiqlanmadi. Qaytadan urinib ko'ring yoki admin bilan bog'laning."
            if lang == "uz" else
            "❌ Ваш платёж не подтверждён. Попробуйте снова или свяжитесь с админом."
        )
        notify_user(int(uid), text)
    return redirect(url_for("dashboard"))

@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(get_stats())


if __name__ == "__main__":
    print(f"🌐 Admin panel ishga tushdi: http://localhost:{PORT}")
    print(f"   Login: {ADMIN_USERNAME}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
