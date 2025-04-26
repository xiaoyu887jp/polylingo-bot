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
        "contents": [
            {"type": "text", "text": "🌍 Choose Languages", "weight": "bold", "size": "lg", "align": "center"}
        ],
        "backgroundColor": "#FFCC80"
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "button", "action": {"type": "message", "label": "🇺🇸 English", "text": "/setlang en"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇨🇳 简体中文", "text": "/setlang zh-cn"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇹🇼 繁體中文", "text": "/setlang zh-tw"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇯🇵 日本語", "text": "/setlang ja"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇹🇭 ภาษาไทย", "text": "/setlang th"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇰🇷 한국어", "text": "/setlang ko"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇫🇷 Français", "text": "/setlang fr"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇩🇪 Deutsch", "text": "/setlang de"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇮🇹 Italiano", "text": "/setlang it"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇪🇸 Español", "text": "/setlang es"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇻🇳 Tiếng Việt", "text": "/setlang vi"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇮🇩 Bahasa Indonesia", "text": "/setlang id"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇷🇺 Русский", "text": "/setlang ru"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇵🇹 Português", "text": "/setlang pt"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇸🇦 العربية", "text": "/setlang ar"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🇳🇱 Nederlands", "text": "/setlang nl"}, "color": "#4CAF50"},
            {"type": "button", "action": {"type": "message", "label": "🔄 Reset Languages", "text": "/reset"}, "color": "#E57373"}
        ]
    }
}

@app.route("/callback", methods=['POST'])
def callback():
    body = request.json
    events = body['events']
    for event in events:
        reply_token = event['replyToken']
        group_id = event['source'].get('groupId', event['source'].get('userId'))
        user_message = event['message']['text'].lower()

        if user_message == '/reset':
            group_language_settings.pop(group_id, None)
            send_flex_message(reply_token)
            continue

        if user_message.startswith('/setlang '):
            lang = user_message.split(' ')[1]
            languages = group_language_settings.get(group_id, [])
            if lang not in languages:
                languages.append(lang)
                group_language_settings[group_id] = languages
                reply_to_line(reply_token, f"✅ Language added: {', '.join(languages)}")
            continue

        if group_id not in group_language_settings:
            send_flex_message(reply_token)
        else:
            languages = group_language_settings[group_id]
            for lang in languages:
                translated = translate_text(user_message, lang)
                reply_to_line(reply_token, f"[{lang}] {translated}")

    return 'OK'

def send_flex_message(reply_token):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": [{"type": "flex", "altText": "Choose languages", "contents": flex_message_json}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

def reply_to_line(reply_token, message):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

def translate_text(text, target_language):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    data = {'q': text, 'target': target_language}
    response = requests.post(url, data=data)
    return response.json()['data']['translations'][0]['translatedText']

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
