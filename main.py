from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = 'B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU='
GOOGLE_API_KEY = 'AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o'

user_language_settings = {}
group_usage = {}

FREE_LIMIT = 5000  # 免費字數限制

LANGUAGES = [
    "en", "ja", "zh-tw", "zh-cn", "th", "vi",
    "ko", "fr", "es", "de", "id", "hi",
    "it", "pt", "ru", "ar"
]

BLACKLIST = {"此處放被拉黑用戶ID"}

def translate(text, target_language):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    response = requests.post(url, json={"q": text, "target": target_language})
    return response.json()["data"]["translations"][0]["translatedText"]

def reply_to_line(reply_token, messages):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}", "Content-Type": "application/json"}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json={"replyToken": reply_token, "messages": messages})

@app.route("/callback", methods=["POST"])
def callback():
    events = request.json.get("events", [])
    for event in events:
        if 'replyToken' not in event:
            continue

        reply_token = event["replyToken"]
        source = event["source"]
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        if user_id in BLACKLIST:
            continue

        if event["type"] == "join":
            user_language_settings[key] = ["en"]
            reply_to_line(reply_token, [{"type": "text", "text": "已加入，預設語言為英文 (en)。"}])
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip().lower()

            if user_text == '/resetlang':
                user_language_settings[key] = []
                reply_to_line(reply_token, [{"type": "text", "text": "已重置語言設定。"}])
                continue

            if user_text in LANGUAGES:
                langs = user_language_settings.setdefault(key, [])
                if user_text not in langs:
                    langs.append(user_text)
                reply_to_line(reply_token, [{"type": "text", "text": f"已選語言：{', '.join(langs)}"}])
                continue

            langs = user_language_settings.get(key, ["en"])

            current_usage = group_usage.get(group_id, 0)
            if current_usage >= FREE_LIMIT:
                reply_to_line(reply_token, [{"type": "text", "text": "免費翻譯已達上限，請升級使用。"}])
                continue

            total_length = current_usage + len(user_text)
            if total_length > FREE_LIMIT:
                reply_to_line(reply_token, [{"type": "text", "text": "免費翻譯額度不足，請升級。"}])
                continue

            messages = []
            for lang in langs:
                translated = translate(user_text, lang)
                messages.append({"type": "text", "text": f"[{lang.upper()}] {translated}"})

            group_usage[group_id] = total_length
            reply_to_line(reply_token, messages)

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
