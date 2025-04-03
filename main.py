from flask import Flask, request
import requests

app = Flask(__name__)

# 你的 LINE Messaging API 的 Token
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="

# 你的 Google Translate API 密钥
GOOGLE_API_KEY = "AIzaSyCz75hkAR3okY0sTX6HYOHH9r1a0S9Cy0Q"

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {
        "q": text,
        "target": target_lang,
        "format": "text"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json()["data"]["translations"][0]["translatedText"]
    except Exception as e:
        return f"翻译失败：{e}"

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

    # 安全检查：无 events
    if not data.get("events"):
        return "OK", 200

    event = data["events"][0]

    # 忽略非文本消息
    if event["type"] != "message" or event["message"]["type"] != "text":
        return "OK", 200

    user_message = event["message"]["text"].strip()
    reply_token = event["replyToken"]

    # 简单语言判断
    if user_message.startswith("翻译成英文："):
        target_lang = "en"
        text = user_message.replace("翻译成英文：", "").strip()
    elif user_message.startswith("翻译成日文：") or user_message.startswith("翻译成日語："):
        target_lang = "ja"
        text = user_message.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    else:
        reply_to_line(reply_token, "请使用格式：翻译成英文：你好")
        return "OK", 200

    result = translate(text, target_lang)
    reply_to_line(reply_token, result)
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
