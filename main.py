
from flask import Flask, request
import requests

app = Flask(__name__)

# 這裡請填入你正確的密鑰
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_greeted = set()

# 完整的Flex Message JSON (16種語言)
flex_message_json = {
    "type": "bubble",
    "header": {
        "type": "box",
        "layout": "vertical",
        "contents": [{
            "type": "text",
            "text": "🌍 Please select your translation language",
            "weight": "bold",
            "size": "lg",
            "align": "center"
        }],
        "backgroundColor": "#FFCC80"
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": [
            {"type": "button", "style": "primary", "color": "#4CAF50",
             "action": {"type": "message", "label": "🇺🇸 English (en)", "text": "/setlang_add en"}},
            {"type": "button", "style": "primary", "color": "#33CC66",
             "action": {"type": "message", "label": "🇨🇳 简体中文 (zh-cn)", "text": "/setlang_add zh-cn"}},
            {"type": "button", "style": "primary", "color": "#3399FF",
             "action": {"type": "message", "label": "🇹🇼 繁體中文 (zh-tw)", "text": "/setlang_add zh-tw"}},
            {"type": "button", "style": "primary", "color": "#FF6666",
             "action": {"type": "message", "label": "🇯🇵 日本語 (ja)", "text": "/setlang_add ja"}},
            {"type": "button", "style": "primary", "color": "#9966CC",
             "action": {"type": "message", "label": "🇰🇷 한국어 (ko)", "text": "/setlang_add ko"}},
            {"type": "button", "style": "primary", "color": "#FFCC00",
             "action": {"type": "message", "label": "🇹🇭 ภาษาไทย (th)", "text": "/setlang_add th"}},
            {"type": "button", "style": "primary", "color": "#FF9933",
             "action": {"type": "message", "label": "🇻🇳 Tiếng Việt (vi)", "text": "/setlang_add vi"}},
            {"type": "button", "style": "primary", "color": "#33CCCC",
             "action": {"type": "message", "label": "🇫🇷 Français (fr)", "text": "/setlang_add fr"}},
            {"type": "button", "style": "primary", "color": "#33CC66",
             "action": {"type": "message", "label": "🇪🇸 Español (es)", "text": "/setlang_add es"}},
            {"type": "button", "style": "primary", "color": "#3399FF",
             "action": {"type": "message", "label": "🇩🇪 Deutsch (de)", "text": "/setlang_add de"}},
            {"type": "button", "style": "primary", "color": "#4CAF50",
             "action": {"type": "message", "label": "🇮🇩 Bahasa Indonesia (id)", "text": "/setlang_add id"}},
            {"type": "button", "style": "primary", "color": "#FF6666",
             "action": {"type": "message", "label": "🇮🇳 हिन्दी (hi)", "text": "/setlang_add hi"}},
            {"type": "button", "style": "primary", "color": "#66CC66",
             "action": {"type": "message", "label": "🇮🇹 Italiano (it)", "text": "/setlang_add it"}},
            {"type": "button", "style": "primary", "color": "#FF9933",
             "action": {"type": "message", "label": "🇵🇹 Português (pt)", "text": "/setlang_add pt"}},
            {"type": "button", "style": "primary", "color": "#9966CC",
             "action": {"type": "message", "label": "🇷🇺 Русский (ru)", "text": "/setlang_add ru"}},
            {"type": "button", "style": "primary", "color": "#CC3300",
             "action": {"type": "message", "label": "🇸🇦 العربية (ar)", "text": "/setlang_add ar"}}
        ]
    },
    "footer": {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "button", "style": "secondary",
             "action": {"type": "message", "label": "🔄 Reset", "text": "/resetlang"}}
        ]
    }
}

def reply_to_line(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": messages}
    requests.post(url, headers=headers, json=payload)

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {"q": text, "target": target_lang, "format": "text"}
    res = requests.post(url, json=payload)
    return res.json()["data"]["translations"][0]["translatedText"]

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    for event in data.get("events", []):
        reply_token = event["replyToken"]
        user_id = event["source"].get("userId")
        text = event.get("message", {}).get("text", "")

        if text.startswith("/setlang_add"):
            lang = text.split()[1]
            user_language_settings.setdefault(user_id, set()).add(lang)
            reply_to_line(reply_token, [{"type": "text", "text": f"✅ Added {lang}"}])
            continue

        if text == "/resetlang":
            user_language_settings[user_id] = set()
            user_greeted.discard(user_id)
            reply_to_line(reply_token, [{"type": "text", "text": "🔄 Languages reset."}])
            continue

        langs = user_language_settings.get(user_id)
        if not langs:
            if user_id not in user_greeted:
                user_greeted.add(user_id)
                reply_to_line(reply_token, [{"type": "flex", "altText": "Select languages", "contents": flex_message_json}])
            continue

        translations = [{"type": "text", "text": f"[{l.upper()}] {translate(text, l)}"} for l in langs]
        reply_to_line(reply_token, translations)

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
