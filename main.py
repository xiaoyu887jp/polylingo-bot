from flask import Flask, request, jsonify
from google.cloud import translate_v2 as translate
import os

app = Flask(__name__)

# 设置你的密钥文件路径，或者用环境变量 GOOGLE_APPLICATION_CREDENTIALS
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "my-key.json"

# 初始化翻译客户端
translate_client = translate.Client()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    user_message = data["events"][0]["message"]["text"]

    # 翻译为泰文和英文
    result_th = translate_client.translate(user_message, target_language='th')["translatedText"]
    result_en = translate_client.translate(user_message, target_language='en')["translatedText"]

    # 格式化输出（中间空一行，不重复原文）
    reply = f"[TH] {result_th}\n\n[EN] {result_en}"

    # 构造回应格式（适用于 LINE Bot）
    response_data = {
        "replyToken": data["events"][0]["replyToken"],
        "messages": [{
            "type": "text",
            "text": reply
        }]
    }

    return jsonify(response_data)
