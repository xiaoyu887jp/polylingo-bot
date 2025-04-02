from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="

def translate(text, target_lang="en"):
    try:
        url = "https://libretranslate.de/translate"
        payload = {
            "q": text,
            "source": "auto",
            "target": target_lang,
            "format": "text"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        result = response.json()
        return result.get("translatedText", "翻译失败")
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
        "messages": [{
            "type": "text",
            "text": message
        }]
    }
    requests.post(url, headers=headers, json=payload)

@app.route("/callback", methods=["POST"])
def callback():
    try:
        data = request.get_json()
        print("📥 收到事件：", data)

        if not data.get("events"):
            return "No event", 200

        event = data["events"][0]
        if "message" not in event or "text" not in event["message"]:
            reply_token = event["replyToken"]
            reply_to_line(reply_token, "暂不支持此类型消息")
            return "Unsupported", 200

        user_message = event["message"]["text"]
        reply_token = event["replyToken"]

        translated = translate(user_message, "en")
        reply_to_line(reply_token, translated)
        return "OK", 200

    except Exception as e:
        print("❌ 处理失败：", e)
        return "Error", 500

if __name__ == '__main__':
    print("✅ Flask 服务已启动")
    app.run(host="0.0.0.0", port=10000)
