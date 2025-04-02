from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

# 你的 LINE Access Token
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
        return response.json().get("translatedText", "翻譯失敗")
    except Exception as e:
        return f"錯誤：{e}"

@app.route("/callback", methods=["POST"])
def webhook():
    body = request.get_json()
    print("接收到的內容：", json.dumps(body, ensure_ascii=False))

    try:
        event = body["events"][0]
        user_text = event["message"]["text"]
        reply_token = event["replyToken"]

        # 判斷目標語言（範例：中翻日、英翻中）
        if all(ord(c) < 128 for c in user_text):  # 英文 ➜ 中文
            target_lang = "zh"
        elif '\u4e00' <= user_text <= '\u9fff':  # 中文 ➜ 日文
            target_lang = "ja"
        else:
            target_lang = "en"  # 其他預設翻英文

        translated = translate(user_text, target_lang)

        reply_message(reply_token, translated)
    except Exception as e:
        print("錯誤：", e)

    return "OK", 200

def reply_message(token, text):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }

    payload = {
        "replyToken": token,
        "messages": [{
            "type": "text",
            "text": text
        }]
    }

    url = "https://api.line.me/v2/bot/message/reply"
    res = requests.post(url, headers=headers, json=payload)
    print("LINE 回傳結果：", res.status_code, res.text)

if __name__ == '__main__':
    print("✅ Flask server is starting...")
    app.run(host='0.0.0.0', port=10000)
