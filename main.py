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
        "contents": [{"type": "text", "text": "🌍 Choose Languages", "weight": "bold", "size": "lg", "align": "center"}],
        "backgroundColor": "#FFCC80"
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "button", "action": {"type": "message", "label": "🇺🇸 English", "text": "/setlang_add en"}},
            {"type": "button", "action": {"type": "message", "label": "🇨🇳 简体中文", "text": "/setlang_add zh-cn"}},
            {"type": "button", "action": {"type": "message", "label": "🇹🇼 繁體中文", "text": "/setlang_add zh-tw"}},
            {"type": "button", "action": {"type": "message", "label": "🇯🇵 日本語", "text": "/setlang_add ja"}},
            {"type": "button", "action": {"type": "message", "label": "🇹🇭 ภาษาไทย", "text": "/setlang_add th"}},
            {"type": "button", "action": {"type": "message", "label": "🇰🇷 한국어", "text": "/setlang_add ko"}},
            {"type": "button", "action": {"type": "message", "label": "🇫🇷 Français", "text": "/setlang_add fr"}},
            {"type": "button", "action": {"type": "message", "label": "🇩🇪 Deutsch", "text": "/setlang_add de"}},
            {"type": "button", "action": {"type": "message", "label": "🇮🇹 Italiano", "text": "/setlang_add it"}},
            {"type": "button", "action": {"type": "message", "label": "🇪🇸 Español", "text": "/setlang_add es"}},
            {"type": "button", "action": {"type": "message", "label": "🇻🇳 Tiếng Việt", "text": "/setlang_add vi"}},
            {"type": "button", "action": {"type": "message", "label": "🇮🇩 Bahasa Indonesia", "text": "/setlang_add id"}},
            {"type": "button", "action": {"type": "message", "label": "🇷🇺 Русский", "text": "/setlang_add ru"}},
            {"type": "button", "action": {"type": "message", "label": "🇵🇹 Português", "text": "/setlang_add pt"}},
            {"type": "button", "action": {"type": "message", "label": "🇸🇦 العربية", "text": "/setlang_add ar"}},
            {"type": "button", "action": {"type": "message", "label": "🇳🇱 Nederlands", "text": "/setlang_add nl"}}
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

        if user_message.startswith('/setlang_add '):
            lang = user_message.split(' ')[1]
            languages = group_language_settings.get(group_id, [])
            if lang not in languages:
                languages.append(lang)
                group_language_settings[group_id] = languages
                reply_to_line(reply_token, f"✅ 已添加语言: {', '.join(languages)}")
            continue

        languages = group_language_settings.get(group_id, [])
        if not languages:
            send_flex(reply_token, "请选择语言：")
        else:
            for lang in languages:
                translation = translate_text(user_message, lang)
                reply_to_line(reply_token, f"[{lang}] {translation}")

    return 'OK'

def send_flex(reply_token, alt_text):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "flex", "altText": alt_text, "contents": flex_message_json}]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

def reply_to_line(reply_token, text):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

def translate_text(text, target):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    res = requests.post(url, json={'q': text, 'target': target})
    return res.json()['data']['translations'][0]['translatedText']

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
