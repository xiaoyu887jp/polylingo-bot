from flask import Flask, request
import requests
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="


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
        return response.json().get("translatedText", "翻译失败")
    except Exception as e:
        return f"Error: {e}"

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
    event = data["events"][0]
    user_message = event["message"]["text"]
    reply_token = event["replyToken"]

    # 判断翻译目标语言（简单判断）
    if "英文" in user_message:
        target_lang = "en"
        source_text = user_message.replace("翻译成英文：", "").strip()
    elif "日文" in user_message or "日語" in user_message:
        target_lang = "ja"
        source_text = user_message.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    else:
        reply_to_line(reply_token, "请注明翻译目标语言，例如：翻译成英文：你好")
        return "OK", 200

    translated = translate(source_text, target_lang)
    reply_to_line(reply_token, translated)
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
