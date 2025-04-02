from flask import Flask, request
import requests
import os

app = Flask(__name__)

# 你的 LINE Channel Access Token（从 LINE Developers 后台复制）
LINE_ACCESS_TOKEN = '你的 Access Token 填在这里'

def translate(text, target_lang):
    url = "https://libretranslate.de/translate"
    payload = {
        "q": text,
        "source": "auto",
        "target": target_lang,
        "format": "text"
    }
    headers = { "Content-Type": "application/json" }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json().get("translatedText", "Translation failed")
    except Exception as e:
        return f"Error: {e}"

@app.route("/callback", methods=["POST"])
def callback():
    body = request.json
    for event in body.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]
            reply_token = event["replyToken"]

            translated_text = translate(user_text, "en")  # 翻译成英文，可改 "ja"、"zh"、"th" 等
            reply_to_line(reply_token, translated_text)
    return "OK", 200

def reply_to_line(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{
            "type": "text",
            "text": text
        }]
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
