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

BASE_URL = f"https://api.telegram.org/bot{GATEWAY_TOKEN}"

# --- UPSTASH REDIS CLIENT ---
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
    redis_command(["SADD", "anime_members_list", str(user_id)])
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

# --- TELEGRAM HELPER ---
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
        res = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=8)
        return res.json()
    except Exception:
        return {}

# --- LIVE ANIME API (JIKAN / MAL) ---
def fetch_latest_anime():
    try:
        url = "https://api.jikan.moe/v4/seasons/now?limit=6"
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json().get("data", [])
            lines = ["🔥 *LATEST AIRING ANIME & EPISODES* 🔥\n"]
            for idx, item in enumerate(data, 1):
                title = item.get("title", "Unknown")
                episodes = item.get("episodes") or "Ongoing"
                score = item.get("score") or "N/A"
                genres = ", ".join([g["name"] for g in item.get("genres", [])[:2]])
                lines.append(f"✨ *{idx}. {title}*")
                lines.append(f"   ▫️ *Episodes:* `{episodes}` | ⭐ *Score:* `{score}`")
                lines.append(f"   ▫️ *Genre:* _{genres}_\n")
            lines.append("⚡ _Real-time Live Anime Index_")
            return "\n".join(lines)
    except Exception as e:
        print(f"Jikan API Error: {e}")
    return "⚠️ Live index refresh ho raha hai, kripya 1 minute baad dobara check karein."

# --- ROUTES ---
@app.route("/", methods=["GET"])
def home():
    total = get_total_members()
    return f"🛡️ Anime Nation Ultimate Gateway Bot is Live! Vault Audience: {total}", 200

@app.route("/gateway-webhook", methods=["POST"])
def gateway_webhook():
    update = request.get_json(silent=True)
    if not update:
        return "No payload", 400

    # 1. Channel Join Request (Auto Approve + Silent Capture)
    if "chat_join_request" in update:
        cjr = update["chat_join_request"]
        user = cjr.get("from", {})
        user_id = str(user.get("id"))
        first_name = user.get("first_name", "")
        username = user.get("username", "")
        chat_id = cjr.get("chat", {}).get("id")

        save_member(user_id, first_name, username)

        try:
            requests.post(f"{BASE_URL}/approveChatJoinRequest", json={"chat_id": chat_id, "user_id": int(user_id)}, timeout=8)
        except Exception:
            pass

        welcome_text = (
            f"🎌 *Welcome to Anime Nation, {first_name}!* 🎌\n\n"
            "✅ *Aapki join request accept ho chuki hai.*\n\n"
            "🛡️ *Vault Protection Active:* Agar channel par koi technical/copyright strike aati hai, toh backup direct isi chat par aayega."
        )
        send_telegram(user_id, welcome_text)
        return "OK", 200

    # 2. Text Messages & Swipe-To-Reply Engine
    if "message" in update and "text" in update["message"]:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        first_name = msg["from"].get("first_name", "Anime Fan")
        username = msg["from"].get("username", "")
        text = msg["text"].strip()

        save_member(chat_id, first_name, username)

        # ADMIN SWIPE-TO-REPLY CHECK
        if OWNER_ID and chat_id == str(OWNER_ID) and "reply_to_message" in msg:
            replied_msg_id = str(msg["reply_to_message"]["message_id"])
            target_user_id = redis_command(["GET", f"reply_map:{replied_msg_id}"])

            if target_user_id:
                reply_payload = (
                    "👑 *Admin Response (Anime Nation)*\n\n"
                    f"{text}\n\n"
                    "🍿 _Happy Watching!_"
                )
                send_telegram(target_user_id, reply_payload)
                send_telegram(chat_id, f"✅ Message delivered to member (`{target_user_id}`).")
                return "OK", 200

        # /myid Check
        if text == "/myid":
            send_telegram(chat_id, f"🆔 *Aapka Telegram ID:* `{chat_id}`")
            return "OK", 200

        # /start Menu
        if text.startswith("/start"):
            menu_keyboard = {
                "inline_keyboard": [
                    [{"text": "📢 Official Channel", "url": "https://t.me/Anime_NationX"}],
                    [
                        {"text": "🎬 Request Anime / Movie", "callback_data": "btn_req"},
                        {"text": "🔥 Latest Releases", "callback_data": "btn_latest"}
                    ],
                    [{"text": "🛡️ Backup Vault Status", "callback_data": "btn_status"}]
                ]
            }
            welcome_msg = (
                f"⚡ *Konnichiwa {first_name}! Welcome to Anime Nation Hub* ⚡\n\n"
                "Aap yahan se:\n"
                "• Manpasand Anime, Episodes ya Movies direct demand kar sakte hain.\n"
                "• Latest airing anime aur update schedule dekh sakte hain.\n"
                "• Channel issue ke waqt instant backup prapt kar sakte hain.\n\n"
                "Niche menu se chunav karein 👇"
            )
            send_telegram(chat_id, welcome_msg, menu_keyboard)
            return "OK", 200

        # Owner /count Command
        if text.startswith("/count"):
            if OWNER_ID and chat_id == str(OWNER_ID):
                total = get_total_members()
                send_telegram(chat_id, f"📊 *Total Database Audience:* `{total}` members saved.")
            else:
                send_telegram(chat_id, "❌ Sirf Bot Owner is command ko use kar sakta hai.")
            return "OK", 200

        # Owner /evacuate Command
        if text.startswith("/evacuate"):
            if not OWNER_ID or chat_id != str(OWNER_ID):
                send_telegram(chat_id, "❌ Unauthorized Access.")
                return "OK", 200

            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                send_telegram(chat_id, "⚠️ Link missing!\nFormat: `/evacuate https://t.me/NayaChannel`")
                return "OK", 200

            new_link = parts[1].strip()
            members = get_all_members()

            send_telegram(chat_id, f"🚨 *Evacuation Started!*\n`{len(members)}` members ko messages send ho rahe hain...")

            evacuate_msg = (
                "🚨 *URGENT: ANIME NATION OFFICIAL BACKUP LINK* 🚨\n\n"
                "Main channel copyright strike/issue ki wajah se migrate kar diya gaya hai.\n\n"
                f"👉 [JOIN NEW ANIME CHANNEL]({new_link})\n\n"
                "Apne episodes safe rakhne ke liye abhi jud jayein!"
            )

            sent, failed = 0, 0
            for u_id in members:
                try:
                    res = requests.post(
                        f"{BASE_URL}/sendMessage",
                        json={"chat_id": u_id, "text": evacuate_msg, "parse_mode": "Markdown"},
                        timeout=5
                    )
                    if res.status_code == 200:
                        sent += 1
                    else:
                        failed += 1
                    time.sleep(0.05)
                except Exception:
                    failed += 1

            send_telegram(
                chat_id,
                f"✅ *Evacuation Done!*\n\n👥 Total: `{len(members)}`\n📨 Delivered: `{sent}`\n❌ Failed: `{failed}`"
            )
            return "OK", 200

        # Check if user was waiting to send Anime Request
        user_state = redis_command(["GET", f"state:{chat_id}"])
        if user_state == "waiting_anime_request":
            redis_command(["DEL", f"state:{chat_id}"])
            
            # Confirm to user
            send_telegram(chat_id, "✅ *Request Registered!* Admin ko notify kar diya gaya hai. Jaldi hi upload kiya jayega.")

            # Notify Admin with Reply Map
            if OWNER_ID:
                admin_alert = (
                    "📩 *NEW ANIME REQUEST RECEIVED!*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *From:* {first_name} (`{chat_id}`)\n"
                    f"🔗 *Username:* @{username if username else 'None'}\n"
                    f"🎯 *Demand:* `{text}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "👉 _Reply dene ke liye is message par Swipe/Reply karein._"
                )
                sent_res = send_telegram(OWNER_ID, admin_alert)
                if sent_res.get("ok"):
                    msg_id = str(sent_res["result"]["message_id"])
                    # 7 din tak reply mapping save rahegi
                    redis_command(["SETEX", f"reply_map:{msg_id}", "604800", str(chat_id)])
            return "OK", 200

    # 3. Inline Button Actions
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        chat_id = str(cb["message"]["chat"]["id"])
        data = cb.get("data", "")

        # Request Anime Button
        if data == "btn_req":
            redis_command(["SETEX", f"state:{chat_id}", "600", "waiting_anime_request"])
            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id})
            prompt_text = (
                "📝 *Anime / Movie Request Mode*\n\n"
                "Aapko konsa Anime, Season ya Episode chahiye? Neeche message likh kar bhejein:"
            )
            send_telegram(chat_id, prompt_text)

        # Latest Releases Button
        elif data == "btn_latest":
            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Fetching live data..."})
            anime_feed = fetch_latest_anime()
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Refresh List", "callback_data": "btn_latest"}],
                    [{"text": "🎬 Request Anime", "callback_data": "btn_req"}]
                ]
            }
            send_telegram(chat_id, anime_feed, back_keyboard)

        # Backup Status Button
        elif data == "btn_status":
            requests.post(
                f"{BASE_URL}/answerCallbackQuery",
                json={
                    "callback_query_id": cb_id,
                    "text": "🛡️ Vault Status: Active! Aapka account permanently backed-up hai.",
                    "show_alert": True
                }
            )

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
        
