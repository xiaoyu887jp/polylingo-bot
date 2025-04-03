from flask import Flask, request
import requests
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = "你的LINE機器人Token"
GOOGLE_API_KEY = "AIzaSyCz75hkAR3okY0sTX6HYOHH9r1a0S9Cy0Q"

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2"
    params = {
        "q": text,
        "target": target_lang,
        "format": "text",
        "key": GOOGLE_API_KEY
    }
    try:
        response = requests.post(url, data=params, timeout=5)
        response.raise_for_status()
        return response.json()["data"]["translations"][0]["translatedText"]
    except Exception as e:
        return f"翻译失败: {e}"

def reply_to_line(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    requests.post(url, headers=headers, json=payload)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return "No event", 200

    event = events[0]
    if event["type"] != "message" or event["message"]["type"] != "text":
        return "Ignored", 200

    user_message = event["message"]["text"]
    reply_token = event["replyToken"]

    if "翻译成英文：" in user_message:
        target_lang = "en"
        source_text = user_message.replace("翻译成英文：", "").strip()
    elif "翻译成日文：" in user_message or "翻译成日語：" in user_message:
        target_lang = "ja"
        source_text = user_message.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    else:
        reply_to_line(reply_token, "请注明翻译目标语言，例如：翻译成英文：你好")
        return "OK", 200

    translated = translate(source_text, target_lang)
    reply_to_line(reply_token, translated)
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
