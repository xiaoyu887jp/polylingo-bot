from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

def detect_language(text):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}"
    payload = {"q": text}
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        return res.json()["data"]["detections"][0][0]["language"]
    except:
        return None

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {"q": text, "target": target_lang, "format": "text"}
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        return res.json()["data"]["translations"][0]["translatedText"]
    except:
        return "[Translation Error]"

def reply_to_line(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
    requests.post(url, json=payload, headers=headers)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return "OK", 200

    event = events[0]
    message = event.get("message", {})
    reply_token = event.get("replyToken")
    user_text = message.get("text", "")

    source_lang = detect_language(user_text)

    # 如果语言检测失败，直接告诉用户
    if not source_lang:
        reply_to_line(reply_token, "[无法识别语言]")
        return "OK", 200

    # 强化版翻译流程（确保中文一定翻译成泰文）
    if source_lang in ["zh-CN", "zh-TW"]:
        th_translation = translate(user_text, "th")
        reply = f"{th_translation}"

    elif source_lang == "th":
        zh_translation = translate(user_text, "zh-CN")
        reply = f"{zh_translation}"

    else:
        reply = "[暂不支持此语言翻译]"

    reply_to_line(reply_token, reply)
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
