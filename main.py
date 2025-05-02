@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        # 確認 replyToken 存在，避免 KeyError 錯誤
        if 'replyToken' not in event:
            continue

        reply_token = event["replyToken"]
        source = event["source"]
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        if event["type"] == "join":
            user_language_settings[key] = []
            reply_to_line(reply_token, [{"type": "flex", "altText": "Select language", "contents": flex_message_json}])
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]

            if user_text == "/resetlang":
                user_language_settings[key] = []
                reply_to_line(reply_token, [{"type": "flex", "altText": "Select language", "contents": flex_message_json}])
                continue

            langs = user_language_settings.get(key, [])
            user_avatar = user_avatar_cache.get(user_id)

            if not user_avatar:
                profile_res = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}, timeout=5)
                user_avatar = profile_res.json().get("pictureUrl", "")
                user_avatar_cache[user_id] = user_avatar

            messages = []
            for lang in langs:
                translated_text = translate(user_text, lang)
                messages.append({
                    "type": "text",
                    "text": translated_text,
                    "sender": {"name": f"Saygo ({lang})", "iconUrl": user_avatar}
                })

            reply_to_line(reply_token, messages)

    return "OK", 200
