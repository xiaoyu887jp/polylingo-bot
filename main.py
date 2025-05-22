@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event.get("replyToken")
        if not reply_token:
            continue

        source = event["source"]
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        # 🟢 第一步：确保用户数据一定被初始化
        if key not in user_language_settings:
            user_language_settings[key] = []
        if user_id not in user_usage:
            user_usage[user_id] = 0
        # 🟢 第二步：处理用户加入机器人时发送语言选择卡片
        if event["type"] == "join":
            reply_to_line(reply_token, [
                {"type": "flex", "altText": "Select language", "contents": flex_message_json}
            ])
            continue
        # 🟢 第三步：处理用户文字消息
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]

            if user_text == "/resetlang":
                user_language_settings[key] = []
                reply_to_line(reply_token, [
                    {"type": "flex", "altText": "Select language", "contents": flex_message_json}
                ])
                continue

            if user_text in LANGUAGES:
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                reply_to_line(reply_token, [
                    {"type": "text", "text": f"✅ Your languages: {', '.join(user_language_settings[key])}"}
                ])
                continue
            # 🟢 第四步：检查用户免费额度是否已用完
            if user_usage[user_id] + len(user_text) > MONTHLY_FREE_QUOTA:
                lang = user_language_settings[key][0] if user_language_settings[key] else "en"
                quota_message = quota_messages.get(lang, quota_messages["en"])
                reply_to_line(reply_token, [
                    {"type": "text", "text": quota_message}
                ])
                continue

            user_usage[user_id] += len(user_text)
            # 🟢 第五步：执行翻译并发送消息
            langs = user_language_settings.get(key, [])
            profile_res = requests.get(
                f"https://api.line.me/v2/bot/profile/{user_id}",
                headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
            )
            profile_data = profile_res.json()
            user_avatar = profile_data.get("pictureUrl", "")

            messages = [
                {
                    "type": "text",
                    "text": translate(user_text, lang),
                    "sender": {
                        "name": f"Saygo ({lang})",
                        "iconUrl": user_avatar
                    }
                } for lang in langs
            ]

            reply_to_line(reply_token, messages)
    return "OK", 200
