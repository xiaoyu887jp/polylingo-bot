from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80oY"

def detect_language(text):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}"
    payload = {"q": text}
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        res.raise_for_status()
        return res.json()["data"]["detections"][0][0]["language"]
    except Exception:
        return None

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {"q": text, "target": target_lang, "format": "text"}
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        res.raise_for_status()
        return res.json()["data"]["translations"][0]["translatedText"]
    except Exception as e:
        return f"[Translation Failed]: {e}"

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
    message = event.get("message", {})
    reply_token = event.get("replyToken")
    user_text = message.get("text", "")

    source_lang = detect_language(user_text)
    if not source_lang:
        return "OK", 200

    # 中文 → 泰文 + 英文（中文在上）
    if source_lang == "zh-CN":
        th = translate(user_text, "th")
        en = translate(user_text, "en")
        reply = f"[TH] {th}\n\n[EN] {en}"

    # 泰文 → 中文 + 英文（泰文在上）
    elif source_lang == "th":
        zh = translate(user_text, "zh-CN")
        en = translate(user_text, "en")
        reply = f"[ZH] {zh}\n\n[EN] {en}"

    else:
        return "OK", 200

    reply_to_line(reply_token, reply)
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
