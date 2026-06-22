"""
Umumiy data qatlami — bot.py va admin_panel.py ikkalasi ham shu faylni ishlatadi
"""
import json
import os
import threading

DATA_FILE = "users.json"
_lock = threading.Lock()

def load_data():
    with _lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

def save_data(data):
    with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid, username=None, first_name=None):
    data = load_data()
    key = str(uid)
    if key not in data:
        data[key] = {
            "lang": "uz", "balance": 0, "history": [], "tasks": [],
            "mode": None, "username": username, "first_name": first_name,
            "total_spent": 0, "pending_topup": None, "pending_receipt_file_id": None,
            "pending_receipt_info": None, "pending_topup_time": None
        }
        save_data(data)
    else:
        changed = False
        if username and data[key].get("username") != username:
            data[key]["username"] = username
            changed = True
        if first_name and data[key].get("first_name") != first_name:
            data[key]["first_name"] = first_name
            changed = True
        if changed:
            save_data(data)
    return data[key]

def save_user(uid, ud):
    data = load_data()
    data[str(uid)] = ud
    save_data(data)

def get_pending_topups():
    """Barcha kutilayotgan to'lovlar ro'yxati"""
    data = load_data()
    pending = []
    for uid, ud in data.items():
        if ud.get("pending_topup"):
            pending.append({
                "uid": uid,
                "username": ud.get("username"),
                "first_name": ud.get("first_name"),
                "amount": ud.get("pending_topup"),
                "receipt_file_id": ud.get("pending_receipt_file_id"),
                "receipt_info": ud.get("pending_receipt_info"),
                "time": ud.get("pending_topup_time"),
                "balance": ud.get("balance", 0),
            })
    pending.sort(key=lambda x: x.get("time") or "", reverse=True)
    return pending

def approve_topup(uid):
    data = load_data()
    key = str(uid)
    if key not in data:
        return None
    amount = data[key].get("pending_topup")
    if not amount:
        return None
    data[key]["balance"] = data[key].get("balance", 0) + amount
    data[key]["pending_topup"] = None
    data[key]["pending_receipt_file_id"] = None
    data[key]["pending_receipt_info"] = None
    data[key]["pending_topup_time"] = None
    save_data(data)
    return amount

def reject_topup(uid):
    data = load_data()
    key = str(uid)
    if key not in data:
        return False
    data[key]["pending_topup"] = None
    data[key]["pending_receipt_file_id"] = None
    data[key]["pending_receipt_info"] = None
    data[key]["pending_topup_time"] = None
    save_data(data)
    return True

def get_stats():
    data = load_data()
    total_users = len(data)
    total_balance = sum(u.get("balance", 0) for u in data.values())
    total_spent = sum(u.get("total_spent", 0) for u in data.values())
    pending_count = sum(1 for u in data.values() if u.get("pending_topup"))
    return {
        "total_users": total_users,
        "total_balance": total_balance,
        "total_spent": total_spent,
        "pending_count": pending_count,
    }
