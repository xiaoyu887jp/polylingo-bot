from flask import Flask, request
import requests
import os

app = Flask(__name__)

# 翻译函数
def translate(text, target_lang):
    url = "https://libretranslate.de/translate"
    payload = {
        "q": text,
        "source": "auto",
        "target": target_lang,
        "format": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json().get("translatedText", "Translation failed")
    except Exception as e:
        return f"Error: {e}"

# 回传给 LINE 的函数
def reply_message(reply_token, message):
    line_api_url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('LINE_CHANNEL_ACCESS_TOKEN')}"
    }
    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    requests.post(line_api_url, headers=headers, json=body)

# webhook 路由
@app.route("/callback", methods=['POST'])
def webhook():
    body = request.get_json()

    # 如果没有事件，不回应
    if "events" not in body:
        return "No events", 200

    for event in body["events"]:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]
            reply_token = event["replyToken"]
            translated = translate(user_text, "en")  # 翻成英文
            reply_message(reply_token, translated)

    return "OK", 200

# 测试翻译用（可删）
@app.route("/translate")
def do_translation():
    return translate("こんにちは", "en")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
