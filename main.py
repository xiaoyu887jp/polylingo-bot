import os
import requests
from flask import Flask, request

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyCz75hkAR3okY0sTX6HYOHH9r1a0S9Cy0Q"

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {
        "q": text,
        "target": target_lang,
        "format": "text"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()["data"]["translations"][0]["translatedText"]
    else:
        return f"翻译失败：{response.text}"

def reply_to_line(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    requests.post(url, headers=headers, json=payload)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return "OK", 200

    event = events[0]
    user_message = event["message"]["text"]
    reply_token = event["replyToken"]

    if "翻译成英文：" in user_message:
        text = user_message.split("翻译成英文：", 1)[1].strip()
        translated = translate(text, "en")
        reply_to_line(reply_token, translated)
    elif "翻译成日文：" in user_message:
        text = user_message.split("翻译成日文：", 1)[1].strip()
        translated = translate(text, "ja")
        reply_to_line(reply_token, translated)
    else:
        reply_to_line(reply_token, "请使用格式：翻译成英文：你好")

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
