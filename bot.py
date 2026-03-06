import time
import json
import requests
from pathlib import Path
import re
import html
import hashlib

# =======================
# Configuration
# =======================
TELEGRAM_BOT_TOKEN = "8487835280:AAEtYBZeTOT9vKQWhhTIvbzO9tk5lzhaCxc"
TELEGRAM_CHAT_ID = "-1003221166532"
HADI_API_URL = "http://147.135.212.197/crapi/had/viewstats"
HADI_API_KEY = "RldTRDRSQkdngpFzh4lveGNXdl9SYIpYZmyCYXFq"
POLL_INTERVAL = 1  # seconds

SEEN_FILE = Path("seen_ids.json")

# =======================
# Utilities
# =======================
def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        with SEEN_FILE.open("r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen(seen_set):
    with SEEN_FILE.open("w") as f:
        json.dump(list(seen_set), f, indent=2)

def fetch_hadi():
    try:
        resp = requests.get(HADI_API_URL, params={"token": HADI_API_KEY, "records": 50}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print("⚠️ Hadi API error:", e)
        return None

# =======================
# OTP extraction (4–8 digits)
# =======================
OTP_RE = re.compile(r"\b(\d{4,8})\b")

def extract_otp(text):
    if not text:
        return None
    m = OTP_RE.search(text)
    return m.group(1) if m else None

# =======================
# Country & Service inference
# =======================

COUNTRY_CODE_NAME = {
    "93": "🇦🇫 Afghanistan",
    "355": "🇦🇱 Albania",
    "213": "🇩🇿 Algeria",
    "880": "🇧🇩 Bangladesh",
    "91": "🇮🇳 India",
    "1": "🇺🇸🇨🇦 United States/Canada",
    "44": "🇬🇧 United Kingdom",
    "82": "🇰🇷 South Korea",
    "66": "🇹🇭 Thailand",
    "62": "🇮🇩 Indonesia",
    "49": "🇩🇪 Germany",
    "971": "🇦🇪 United Arab Emirates",
    "61": "🇦🇺 Australia",
    "25": "🇹🇿 Tanzania",
    "7": "🇷🇺 Russia",
    "20": "🇪🇬 Egypt",
    "27": "🇿🇦 South Africa",
    "30": "🇬🇷 Greece",
    "31": "🇳🇱 Netherlands",
    "32": "🇧🇪 Belgium",
    "33": "🇫🇷 France",
    "34": "🇪🇸 Spain",
    "36": "🇭🇺 Hungary",
    "39": "🇮🇹 Italy",
    "41": "🇨🇭 Switzerland",
    "43": "🇦🇹 Austria",
    "45": "🇩🇰 Denmark",
    "46": "🇸🇪 Sweden",
    "47": "🇳🇴 Norway",
    "48": "🇵🇱 Poland",
    "52": "🇲🇽 Mexico",
    "53": "🇨🇺 Cuba",
    "54": "🇦🇷 Argentina",
    "55": "🇧🇷 Brazil",
    "56": "🇨🇱 Chile",
    "57": "🇨🇴 Colombia",
    "58": "🇻🇪 Venezuela",
    "60": "🇲🇾 Malaysia",
    "64": "🇳🇿 New Zealand",
    "65": "🇸🇬 Singapore",
    "81": "🇯🇵 Japan",
    "84": "🇻🇳 Vietnam",
    "86": "🇨🇳 China",
    "90": "🇹🇷 Turkey",
    "98": "🇮🇷 Iran",
    "212": "🇲🇦 Morocco",
    "218": "🇱🇾 Libya",
    "233": "🇬🇭 Ghana",
    "229": "🇧🇯 Benin",
    "95": "🇲🇲 Myanmar",
    "51": "🇵🇪 Peru"
}
def infer_country_from_phone(phone, country_field=None):
    if country_field:
        return country_field
    if not phone:
        return ""
    p = str(phone).strip()
    if not p.startswith("+"):
        p = "+" + p
    digits = re.sub(r"\D", "", p[1:])
    for length in (3,2,1):
        if len(digits) >= length:
            code = digits[:length]
            if code in COUNTRY_CODE_NAME:
                return COUNTRY_CODE_NAME[code]
    return "Unknown Country"

def detect_service_from_text(message, service_field=None):
    if service_field and str(service_field).strip():
        return str(service_field)
    if not message:
        return ""
    txt = message.lower()
    KEYWORDS = {
        "facebook": ["facebook", "fb"],
        "imo": ["imo"],
        "whatsapp": ["whatsapp", "wa"],
        "gmail": ["gmail", "google"],
        "google": ["google", "gmail", "accounts.google"],
        "twitter": ["twitter", "x.com", "x "],
        "instagram": ["instagram", "insta"],
        "telegram": ["telegram"],
        "bank": ["bank", "transaction", "debit", "credit"],
        "paypal": ["paypal"],
        "amazon": ["amazon"],
        "apple": ["apple", "icloud"],
        "microsoft": ["microsoft", "outlook", "live.com"],
        "sms": ["one time password", "otp", "verification code"],
    }
    for svc, keys in KEYWORDS.items():
        for k in keys:
            if k in txt:
                return svc.capitalize() if svc not in ("sms","bank") else (svc.upper() if svc=="sms" else svc.capitalize())
    return "Unknown"

def mask_phone(phone):
    if not phone:
        return "unknown"
    p = str(phone).strip()
    if not p.startswith("+"):
        p = "+" + p
    digits = re.sub(r"\D", "", p[1:])
    country_code = ""
    for code in sorted(COUNTRY_CODE_NAME.keys(), key=len, reverse=True):
        if p.startswith("+" + code):
            country_code = "+" + code
            break
    if not country_code:
        country_code = "+" + digits[:2]
    local = digits[len(country_code.lstrip("+")):]
    if len(local) <= 4:
        return country_code + local
    first_keep = 2
    last_keep = 4
    if len(local) < (first_keep + last_keep):
        first_keep = max(0, len(local) - last_keep)
    masked_local = local[:first_keep] + ("*" * max(1, len(local)-(first_keep+last_keep))) + local[-last_keep:]
    return country_code + masked_local

# =======================
# Telegram
# =======================
def build_reply_markup():
    keyboard = [
        [
            {"text": "📢 Main Channel", "url": "https://t.me/fb_work_hub"},
            {"text": "🤖 NUMBER BOT", "url": "https://t.me/onlynumbarbot"}
        ]
    ]
    return {"inline_keyboard": keyboard}

def send_telegram(text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("Telegram error:", e)
        return None

# =======================
# Generate unique ID for each OTP
# =======================
def get_item_id(item):
    otp = extract_otp(item.get("message") or "")
    phone = item.get("num") or item.get("phone") or ""
    dt = item.get("dt") or item.get("time") or ""
    unique_str = f"{phone}-{otp}-{dt}"
    return hashlib.md5(unique_str.encode()).hexdigest()

# =======================
# Format Message
# =======================
def format_message(item):
    raw_phone = item.get("num") or item.get("phone") or ""
    message = item.get("message") or item.get("msg") or ""
    dt = item.get("dt") or item.get("time") or ""
    country_field = item.get("country") or item.get("ctry") or ""
    service_field = item.get("service") or item.get("srv") or ""

    detected_service = detect_service_from_text(message, service_field)
    country_display = infer_country_from_phone(raw_phone, country_field)
    phone_masked = mask_phone(raw_phone)
    otp = extract_otp(message)

    msg_esc = html.escape(message).replace("\x00", "")
    clean_sms = msg_esc.replace("\n", " ").strip()
    if len(clean_sms) > 400:
        clean_sms = clean_sms[:400] + "..."

    text = (
        "✨ <b>OTP Received</b> ✨\n\n"
        f"⏰ <b>Time:</b> {dt}\n"
        f"📱 <b>Number:</b> {phone_masked}\n"
        f"🌍 <b>Country:</b> {country_display}\n"
        f"🔧 <b>Service:</b> {detected_service}\n\n"  # Gap added here
        f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n\n"
        f"💬 <b>Full Message:</b>\n<pre>{clean_sms}</pre>"
    )

    id_ = get_item_id(item)
    return id_, text, otp

# =======================
# Init Seen
# =======================
def init_seen():
    seen = load_seen()
    data = fetch_hadi()
    if data and data.get("status") != "error":
        for item in data.get("data", []):
            seen.add(get_item_id(item))
        save_seen(seen)
    return seen

# =======================
# Main Loop
# =======================
def main():
    print("🚀 Starting OTP bot (text-only, formatted clean output)...")
    seen = init_seen()
    try:
        while True:
            data = fetch_hadi()
            if not data or data.get("status") == "error":
                time.sleep(POLL_INTERVAL)
                continue

            for item in data.get("data", []):
                id_, msg_text, otp = format_message(item)
                if id_ in seen:
                    continue
                reply_markup = build_reply_markup()
                res = send_telegram(msg_text, reply_markup=reply_markup)
                if res and res.get("ok"):
                    print(f"✅ Sent new OTP: {otp}")
                    seen.add(id_)
                    save_seen(seen)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("🛑 Bot stopped.")
    except Exception as e:
        print("⚠️ Fatal error:", e)

if __name__ == "__main__":
    main()

