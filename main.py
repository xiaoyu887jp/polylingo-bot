from flask import Flask, request
import requests
import json

app = Flask(__name__)

LINE_ACCESS_TOKEN = 'B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU='
LINE_REPLY_ENDPOINT = 'https://api.line.me/v2/bot/message/reply'

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

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    print("Received body:", body)

    for event in body.get("events", []):
        if event.get("type") == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]
            reply_token = event["replyToken"]
            translated_text = translate(user_text, "en")  # 翻译成英文

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
            }
            payload = {
                "replyToken": reply_token,
                "messages": [
                    {"type": "text", "text": translated_text}
                ]
            }
            requests.post(LINE_REPLY_ENDPOINT, headers=headers, data=json.dumps(payload))

    return "OK", 200

if __name__ == "__main__":
    print("✅ Server is running...")
    app.run(host='0.0.0.0', port=10000)
