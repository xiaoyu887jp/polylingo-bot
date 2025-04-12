from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gFIi88JV/7Uh+ZM9m0BOzQlhZNZhL6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

# 紀錄用戶設定語言的資料庫（暫時用簡單方式儲存）
user_language = {}

def detect_language(text):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}"
    payload = {"q": text}
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        res.raise_for_status()
        return res.json()["data"]["detections"][0][0]["language"]
    except Exception as e:
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
        return None

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
    data = request.json
    user_text = data["events"][0]["message"]["text"]
    reply_token = data["events"][0]["replyToken"]
    user_id = data["events"][0]["source"]["userId"]

    # 使用設定的語言或預設繁體中文
    target_lang = user_language.get(user_id, "zh-tw")

    source_lang = detect_language(user_text)
    if not source_lang:
        reply_to_line(reply_token, "無法識別語言")
        return "OK", 200

    translated_text = translate(user_text, target_lang)
    if translated_text:
        reply = f"[翻譯結果]: {translated_text}"
    else:
        reply = "翻譯失敗，請稍後再試。"

    reply_to_line(reply_token, reply)
    return "OK", 200

@app.route("/set_language", methods=["GET"])
def set_language():
    lang = request.args.get("lang")
    user_id = request.args.get("user_id")

    if not user_id or lang not in ["zh-cn", "zh-tw"]:
        return jsonify({"status": "error", "message": "參數錯誤"})

    user_language[user_id] = lang
    return jsonify({"status": "success", "language_set": lang})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
