@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json()

    # 防止 LINE 发送空数据或非消息事件时出错
    if "events" not in data or len(data["events"]) == 0:
        return "No events", 200

    event = data["events"][0]

    if "message" not in event or "text" not in event["message"]:
        return "No message content", 200

    user_message = event["message"]["text"]
    reply_token = event["replyToken"]

    # 判断翻译目标语言（简单判断）
    if "英文" in user_message:
        target_lang = "en"
        source_text = user_message.replace("翻译成英文：", "").strip()
    elif "日文" in user_message or "日語" in user_message:
        target_lang = "ja"
        source_text = user_message.replace("翻译成日文：", "").replace("翻译成日語：", "").strip()
    else:
        reply_to_line(reply_token, "请注明翻译目标语言，例如：翻译成英文：你好")
        return "OK", 200

    translated = translate(source_text, target_lang)
    reply_to_line(reply_token, translated)
    return "OK", 200
