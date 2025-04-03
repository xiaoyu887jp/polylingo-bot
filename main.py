from flask import Flask, request
import requests

app = Flask(__name__)

# ✅ 你的 LINE Access Token
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0BTlVpuAdB04t89/1O/w1cDnyilFU="

# ✅ 你的 Google API Key
GOOGLE_API_KEY = "AIzaSyCz75hkAR3okY0sTX6HYOHH9r1a0S9Cy0Q"

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {
        "q": text,
        "target": target_lang,
        "format": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
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
    events = data.get("events", [])
    if not events:
        return "OK", 200

    event = events[0]
    user_message = event["message"]["text"]
    reply_token = event["replyToken"]

    # 🌐 判断语言并提取翻译内容
    if "翻译成英文：" in user_message:
        target_lang = "en"
        source_text = user_message.replace("翻译成英文：", "").strip()
    elif "翻译成日文：" in user_message or "翻译成日語：" in user_message:
        target_lang = "ja"
        source_text = user_message.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    elif "翻译成中文：" in user_message or "翻译成中文（简体）：" in user_message:
        target_lang = "zh-CN"
        source_text = user_message.replace("翻译成中文：", "").replace("翻译成中文（简体）：", "").strip()
    else:
        reply_to_line(reply_token, "请输入类似格式：翻译成英文：你好 / 翻译成日文：谢谢")
        return "OK", 200

    translated = translate(source_text, target_lang)
    reply_to_line(reply_token, translated)
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
