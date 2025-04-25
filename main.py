from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

group_language_settings = {}

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
        user_text = event.get("message", {}).get("text", "")
        source_id = event["source"].get("groupId") or event["source"].get("userId")

        if user_text.startswith("/setlang_add"):
            lang = user_text.split()[1]
            group_language_settings.setdefault(source_id, set()).add(lang)
            reply_to_line(reply_token, [{"type": "text", "text": f"✅ Added {lang}"}])
            continue

        if user_text == "/resetlang":
            group_language_settings[source_id] = set()
            reply_to_line(reply_token, [{"type": "text", "text": "🔄 Languages reset."}])
            continue

        langs = group_language_settings.get(source_id)
        if not langs:
            reply_to_line(reply_token, [{"type": "flex", "altText": "Select languages", "contents": flex_message_json}])
            continue

        translations = [{"type": "text", "text": f"[{l.upper()}] {translate(user_text, l)}"} for l in langs]
        reply_to_line(reply_token, translations)

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
