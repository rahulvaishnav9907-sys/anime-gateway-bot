import os
import json
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
GATEWAY_TOKEN = os.getenv("GATEWAY_BOT_TOKEN", "8823741107:AAHJ7YTjW09lpVg3OuwzlbT5vduVB2abR-w").strip()
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://secure-coyote-163116.upstash.io").strip()
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "ggAAAAAAAn0sAAIgcDJpchU4PqQmTDdyoxZbHFf2T4GK4bVAO_Mfumr2wKYbnA").strip()
OWNER_ID = os.getenv("OWNER_CHAT_ID", "").strip()
EVACUATE_SECRET = os.getenv("EVACUATE_SECRET", "AnimeEvacuationKey2026").strip()
GATEWAY_WEBHOOK_SECRET = os.getenv("GATEWAY_WEBHOOK_SECRET", "GatewaySecret2026").strip()

BASE_URL = f"https://api.telegram.org/bot{GATEWAY_TOKEN}"

# --- UPSTASH REDIS HELPERS ---
def redis_command(command_list):
    try:
        res = requests.post(
            UPSTASH_URL,
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}", "Content-Type": "application/json"},
            json=command_list,
            timeout=8
        )
        return res.json().get("result")
    except Exception as e:
        print(f"Redis Error: {e}")
        return None

def save_member(user_id, first_name, username):
    # Add to main unique set
    redis_command(["SADD", "anime_members_list", str(user_id)])
    # Save user details
    user_data = json.dumps({
        "first_name": first_name or "",
        "username": f"@{username}" if username else "None",
        "registered_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    redis_command(["HSET", "anime_member_profiles", str(user_id), user_data])

def get_total_members():
    count = redis_command(["SCARD", "anime_members_list"])
    return count if count is not None else 0

def get_all_members():
    members = redis_command(["SMEMBERS", "anime_members_list"])
    return members if members else []

# --- TELEGRAM SENDER ---
def send_telegram(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=8)
    except Exception:
        pass

# --- ROUTES ---

@app.route("/", methods=["GET"])
def home():
    total = get_total_members()
    return f"🛡️ Anime Nation Ghost Gateway Bot is Live! Saved Members: {total}", 200

@app.route("/gateway-webhook", methods=["POST"])
def gateway_webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != GATEWAY_WEBHOOK_SECRET:
        return "Unauthorized", 403

    update = request.get_json(silent=True)
    if not update:
        return "No payload", 400

    # Auto-Approve Join Request + Capture Data
    if "chat_join_request" in update:
        cjr = update["chat_join_request"]
        user = cjr.get("from", {})
        user_id = str(user.get("id"))
        first_name = user.get("first_name", "")
        username = user.get("username", "")
        chat_id = cjr.get("chat", {}).get("id")

        # 1. Silently save to database
        save_member(user_id, first_name, username)

        # 2. Instant Auto-Approve
        try:
            requests.post(f"{BASE_URL}/approveChatJoinRequest", json={"chat_id": chat_id, "user_id": int(user_id)}, timeout=8)
        except Exception:
            pass

        # 3. Welcome DM to establish permanent bot contact
        welcome_text = (
            f"🎌 *Welcome to Anime Nation, {first_name}!* 🎌\n\n"
            "Aapki join request approve ho chuki hai.\n\n"
            "⚠️ *Security Notice:* Channel alerts aur future backup links isi bot par receive honge."
        )
        send_telegram(user_id, welcome_text)
        return "OK", 200

    # Normal User Messages / Start Command
    if "message" in update and "text" in update["message"]:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        first_name = msg["from"].get("first_name", "Anime Fan")
        username = msg["from"].get("username", "")
        text = msg["text"].strip()

        # Silently capture every user who interacts
        save_member(chat_id, first_name, username)

        if text.startswith("/start"):
            menu_keyboard = {
                "inline_keyboard": [
                    [{"text": "📢 Official Channel", "url": "https://t.me/Anime_NationX"}],
                    [{"text": "🎬 Request Anime / Episode", "callback_data": "btn_req"}],
                    [{"text": "🛡️ Backup Status: Active", "callback_data": "btn_status"}]
                ]
            }
            welcome_msg = (
                f"👋 *Konnichiwa {first_name}! Welcome to Anime Nation Hub.*\n\n"
                "⚡ Yeh official utility bot hai jahan aap:\n"
                "• Anime episodes request kar sakte hain.\n"
                "• Kisi bhi channel ban/copyright strike ke waqt naya direct link pa sakte hain.\n\n"
                "Channel se jude rahein aur notifications ON rakhein!"
            )
            send_telegram(chat_id, welcome_msg, menu_keyboard)

        elif text.startswith("/count"):
            if chat_id == str(OWNER_ID):
                total = get_total_members()
                send_telegram(chat_id, f"📊 *Total Database Audience:* `{total}` members saved.")

    # Inline Buttons
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        chat_id = str(cb["message"]["chat"]["id"])
        data = cb.get("data", "")

        if data == "btn_req":
            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Episode Request registered! Hamare admin jald add karenge."})
        elif data == "btn_status":
            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "✅ Aapka account backup list mein securely registered hai."})

    return "OK", 200

# --- DISASTER RECOVERY: 1-CLICK EVACUATION API ---
@app.route("/trigger-evacuate", methods=["POST"])
def trigger_evacuate():
    auth = request.headers.get("X-Evacuate-Secret", "")
    if auth != EVACUATE_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    body = request.get_json(silent=True) or {}
    new_channel_link = body.get("new_link", "https://t.me/Anime_NationX").strip()

    members = get_all_members()
    if not members:
        return jsonify({"status": "no_members", "sent": 0}), 200

    evacuate_message = (
        "🚨 *URGENT NOTICE: ANIME NATION BASE MOVED!* 🚨\n\n"
        "Hamara main channel technical/copyright issue ki wajah se migrate kar diya gaya hai.\n\n"
        "Hamare naye official hub ko join karne ke liye niche link par tap karein:\n"
        f"👉 [JOIN NEW ANIME BASE]({new_channel_link})\n\n"
        "Apne anime safe rakhne ke liye abhi jud jayein!"
    )

    sent_count = 0
    failed_count = 0

    # Safe rate-limited broadcasting (20 msg/sec to prevent bot bans)
    for u_id in members:
        try:
            r = requests.post(
                f"{BASE_URL}/sendMessage",
                json={
                    "chat_id": u_id,
                    "text": evacuate_message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                },
                timeout=5
            )
            if r.status_code == 200:
                sent_count += 1
            else:
                failed_count += 1
            time.sleep(0.05)
        except Exception:
            failed_count += 1

    return jsonify({
        "status": "success",
        "total": len(members),
        "delivered": sent_count,
        "failed": failed_count
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

