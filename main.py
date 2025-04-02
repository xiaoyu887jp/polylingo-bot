from flask import Flask, request
import requests

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
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        res.raise_for_status()
        return res.json().get("translatedText", "翻译失败")
    except Exception as e:
        return f"翻译出错：{e}"

def reply_to_line(reply_token, message):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=body)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return "NO EVENT", 200

    event = events[0]
    if event.get("type") != "message" or event["message"].get("type") != "text":
        return "IGNORED", 200

    user_text = event["message"]["text"]
    reply_token = event["replyToken"]

    if "英文" in user_text:
        lang = "en"
        text = user_text.replace("翻译成英文：", "").strip()
    elif "日文" in user_text or "日語" in user_text:
        lang = "ja"
        text = user_text.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    else:
        reply_to_line(reply_token, "请加上目标语言，例如：翻译成英文：你好")
        return "OK", 200

    translated = translate(text, lang)
    reply_to_line(reply_token, translated)
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
