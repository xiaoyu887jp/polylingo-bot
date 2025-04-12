from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# 你的 LINE 和 Google API 密钥（已经确认过，完全正确）
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

# 用于存储用户语言设定的字典
user_language = {}

# 检测语言函数
def detect_language(text):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}"
    payload = {"q": text}
    try:
        res = requests.post(url, json=payload, timeout=5)
        res.raise_for_status()
        return res.json()["data"]["detections"][0][0]["language"]
    except:
        return None

# 翻译函数
def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {"q": text, "target": target_lang, "format": "text"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        res.raise_for_status()
        return res.json()["data"]["translations"][0]["translatedText"]
    except:
        return None

# LINE 回复函数
def reply_to_line(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
    requests.post(url, json=payload, headers=headers)

# LINE 消息回调接口（必须存在，不能修改）
@app.route("/callback", methods=["POST"])
def callback():
    data = request.json
    reply_token = data["events"][0]["replyToken"]
    user_id = data["events"][0]["source"]["userId"]
    user_text = data["events"][0]["message"]["text"]

    # 获取用户设定语言，默认翻译为繁体中文
    target_lang = user_language.get(user_id, "zh-tw")

    source_lang = detect_language(user_text)
    if not source_lang:
        reply_to_line(reply_token, "无法识别语言，请重试。")
        return "OK", 200

    translated_text = translate(user_text, target_lang)
    if translated_text:
        reply = f"[翻译结果]: {translated_text}"
    else:
        reply = "翻译失败，请稍后再试。"

    reply_to_line(reply_token, reply)
    return "OK", 200

# 用户语言设定接口（新增多语言设定功能）
@app.route("/set_language", methods=["GET"])
def set_language():
    lang = request.args.get("lang")
    user_id = request.args.get("user_id")

    # 支持的语言代码清单
    supported_langs = ["zh-cn", "zh-tw", "en", "th", "vi", "ja", "ko", "fr", "id", "es", "ru", "hi", "pt", "de"]

    if not user_id or lang not in supported_langs:
        return jsonify({"status": "error", "message": "参数错误，请确认语言代码是否正确。"})

    user_language[user_id] = lang
    return jsonify({"status": "success", "language_set": lang})

# 启动服务（Render要求的格式）
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
