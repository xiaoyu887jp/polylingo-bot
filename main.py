from flask import Flask, request
import requests
import re

app = Flask(__name__)

# ✅ 替换成你的金钥
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU=n"
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

# ✅ 用户类型（你可以之后替换为真实 ID）
user_type_map = {
    "user_boss_id": "boss",
    "user_friend_id": "chinese_friend",
    "user_thai_id": "thai_staff",
    "user_vietnam_id": "vietnam_staff"
}

# 检测语言类型
def is_thai(text):
    return bool(re.search(r'[\u0E00-\u0E7F]', text))

def is_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def is_vietnamese(text):
    return bool(re.search(r'[\u0102\u0110\u1EA0-\u1EF9]', text)) or "ạ" in text.lower()

def translate(text, target_lang):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    payload = {"q": text, "target": target_lang, "format": "text"}
    headers = {"Content-Type": "application/json"}
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
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
    requests.post(url, headers=headers, json=payload)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    event = data["events"][0]
    reply_token = event["replyToken"]
    user_id = event["source"].get("userId", "unknown")
    msg = event["message"].get("text", "").strip()

    user_type = user_type_map.get(user_id, "unknown")
    result = ""

    # 翻译规则
    if user_type == "boss" and is_chinese(msg):
        t1 = translate(msg, "th")
        t2 = translate(msg, "en")
        result = f"泰文：{t1}\n英文：{t2}"

    elif user_type == "chinese_friend" and is_chinese(msg):
        t1 = translate(msg, "vi")
        t2 = translate(msg, "en")
        result = f"越南文：{t1}\n英文：{t2}"

    elif user_type == "thai_staff" and is_thai(msg):
        t1 = translate(msg, "zh-CN")
        t2 = translate(msg, "en")
        result = f"中文：{t1}\n英文：{t2}"

    elif user_type == "vietnam_staff" and is_vietnamese(msg):
        t1 = translate(msg, "zh-CN")
        t2 = translate(msg, "en")
        result = f"中文：{t1}\n英文：{t2}"

    else:
        result = "📝 当前为测试版本，请确认您属于设定的用户组。"

    reply_to_line(reply_token, result)
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
