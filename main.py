from flask import Flask, request
import requests

app = Flask(__name__)

# ✅ 你的 LINE 机器人金钥
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

# ✅ 每位使用者的语言设定（记忆）
user_lang_prefs = {}

# ✅ 语言名称与 Google 代码对照
lang_alias = {
    "英文": "en",
    "中文": "zh-CN",
    "中文（简体）": "zh-CN",
    "日文": "ja",
    "日語": "ja",
    "泰文": "th",
    "泰語": "th",
    "越南文": "vi",
    "越南語": "vi",
    "韩文": "ko",
    "韓文": "ko",
    "印尼文": "id"
}

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
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    requests.post(url, headers=headers, json=payload)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()
    event = data["events"][0]
    reply_token = event["replyToken"]
    user_id = event["source"].get("userId", "unknown")
    msg = event["message"].get("text", "").strip()

    # ✅ 语言设定：设定语言：xxx,xxx
    if msg.startswith("设定语言："):
        langs = msg.replace("设定语言：", "").split(",")
        lang_codes = []
        for lang in langs:
            lang = lang.strip()
            code = lang_alias.get(lang)
            if code:
                lang_codes.append((lang, code))
        if lang_codes:
            user_lang_prefs[user_id] = lang_codes
            result = "✅ 已设定语言为：\n" + "\n".join([f"{name}（{code}）" for name, code in lang_codes])
        else:
            result = "❌ 设定失败，请使用语言名，如：设定语言：泰文,英文"
        reply_to_line(reply_token, result)
        return "OK", 200

    # ✅ 正常翻译流程
    if user_id in user_lang_prefs:
        output_langs = user_lang_prefs[user_id]
        result = ""
        for name, code in output_langs:
            translated = translate(msg, code)
            result += f"{name}：{translated}\n"
        reply_to_line(reply_token, result.strip())
    else:
        reply_to_line(reply_token, "📝 请先输入：设定语言：泰文,英文")
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
