from flask import Flask, request
import requests
import re

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

# 用户设定的语言偏好（记住每个人设定的语言）
user_lang_prefs = {}

# 支援语言别名 → Google 翻译代码
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

    # 尝试识别语言设定（如 to 英文,泰文 今天很热）
    lang_set_match = re.match(r"^(to|翻译为)?\s*([^\d\w\s：]+[,，][^\d\w\s：]+)(.*)$", msg)
    if not lang_set_match:
        # 简单判断：是否纯语言设定（如 英文,泰文）
        if msg.count(",") and all(lang.strip() in lang_alias for lang in msg.split(",")):
            langs = msg.split(",")
            lang_codes = [(lang.strip(), lang_alias[lang.strip()]) for lang in langs if lang.strip() in lang_alias]
            user_lang_prefs[user_id] = lang_codes
            reply_to_line(reply_token, f"✅ 已设定语言为：{', '.join([name for name, _ in lang_codes])}")
            return "OK", 200

    # 标准匹配设定语言 + 翻译内容
    if lang_set_match:
        raw_langs = lang_set_match.group(2).replace("，", ",")
        content = lang_set_match.group(3).strip()
        langs = [l.strip() for l in raw_langs.split(",") if l.strip() in lang_alias]
        lang_codes = [(l, lang_alias[l]) for l in langs]
        if lang_codes:
            user_lang_prefs[user_id] = lang_codes
            if not content:
                reply_to_line(reply_token, f"✅ 已设定语言为：{', '.join([l for l, _ in lang_codes])}")
                return "OK", 200
            else:
                result = ""
                for name, code in lang_codes:
                    translated = translate(content, code)
                    result += f"{name}：{translated}\n"
                reply_to_line(reply_token, result.strip())
                return "OK", 200

    # 如果之前已经设定过语言，翻译内容
    if user_id in user_lang_prefs:
        lang_codes = user_lang_prefs[user_id]
        result = ""
        for name, code in lang_codes:
            translated = translate(msg, code)
            result += f"{name}：{translated}\n"
        reply_to_line(reply_token, result.strip())
        return "OK", 200
    else:
        reply_to_line(reply_token, "📝 请输入指令，例如：to 英文,泰文 今天很热")
        return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
