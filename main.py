# 为用户打包完整可运行项目，包括 main.py 和 requirements.txt

from zipfile import ZipFile

project_files = {
    "main.py": """
from flask import Flask, request
import requests
from googletrans import Translator

app = Flask(__name__)
translator = Translator()

# ✅ 替换为你的 LINE Token
LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="

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
    text = event["message"]["text"]
    reply_token = event["replyToken"]

    detected_lang = translator.detect(text).lang

    if detected_lang == "zh-cn":
        th = translator.translate(text, dest="th").text
        en = translator.translate(text, dest="en").text
        reply = f"原文：{text}\\n\\n[TH] {th}\\n\\n[EN] {en}"

    elif detected_lang == "th":
        zh = translator.translate(text, dest="zh-cn").text
        en = translator.translate(text, dest="en").text
        reply = f"原文：{text}\\n\\n[ZH] {zh}\\n\\n[EN] {en}"

    else:
        reply = "目前仅支持中文和泰文自动识别哦。"

    reply_to_line(reply_token, reply)
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
""",
    "requirements.txt": """
Flask
requests
googletrans==4.0.0-rc1
"""
}

zip_path = "/mnt/data/saygo_bot_project.zip"

with ZipFile(zip_path, 'w') as zipf:
    for filename, content in project_files.items():
        file_path = f"/mnt/data/{filename}"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        zipf.write(file_path, arcname=filename)

zip_path
