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

    # 识别语言
    source_lang = detect_language(user_text)
    if not source_lang:
        return "OK", 200

    # 中文 → 英文 + 泰文（顺序改成：原文 → 泰文 → 英文）
    if source_lang == "zh-CN":
        en = translate(user_text, "en")
        th = translate(user_text, "th")
        reply = f"{user_text}\n[TH] {th}\n[EN] {en}"

    # 泰文 → 中文 + 英文（顺序改成：原文 → 中文 → 英文）
    elif source_lang == "th":
        zh = translate(user_text, "zh-CN")
        en = translate(user_text, "en")
        reply = f"{user_text}\n[ZH] {zh}\n[EN] {en}"

    else:
        return "OK", 200

    reply_to_line(reply_token, reply)
    return "OK", 200
