from flask import Flask, request
import requests
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_avatar_cache = {}

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

flex_message_json = { 
    "type":"bubble",
    "header":{
        "type":"box","layout":"vertical","contents":[
            {"type":"text","text":"🌍 Please select translation language","weight":"bold","size":"lg","align":"center"}
        ], "backgroundColor":"#FFCC80"
    },
    "body":{
        "type":"box","layout":"vertical","spacing":"sm",
        "contents":[
            {"type":"button","style":"primary","color":"#4CAF50","action":{"type":"message","label":"🇺🇸 English","text":"en"}},
            {"type":"button","style":"primary","color":"#33CC66","action":{"type":"message","label":"🇨🇳 简体中文","text":"zh-cn"}},
            {"type":"button","style":"primary","color":"#3399FF","action":{"type":"message","label":"🇹🇼 繁體中文","text":"zh-tw"}},
            {"type":"button","style":"primary","color":"#FF6666","action":{"type":"message","label":"🇯🇵 日本語","text":"ja"}},
            {"type":"button","style":"secondary","action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}}
        ]
    }
}

def reply_to_line(reply_token, messages):
    requests.post("https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"},
        json={"replyToken": reply_token, "messages": messages})

def translate(text, lang):
    res = requests.post(
        f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}",
        json={"q": text, "target": lang, "format": "text"}
    )
    return res.json()["data"]["translations"][0]["translatedText"]

@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        if 'replyToken' not in event:
            continue

        reply_token = event["replyToken"]
        source = event["source"]
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        if event["type"] == "join":
            user_language_settings[key] = []
            reply_to_line(reply_token, [{"type":"flex", "altText":"Select language", "contents":flex_message_json}])
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].lower().strip()

            if user_text == "/resetlang":
                user_language_settings[key] = []
                reply_to_line(reply_token, [{"type":"flex","altText":"Select language","contents":flex_message_json}])
                continue

            if user_text in LANGUAGES:
                if key not in user_language_settings:
                    user_language_settings[key] = []
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                langs_display = ', '.join(user_language_settings[key])
                reply_to_line(reply_token, [{"type":"text","text":f"✅ Your languages: {langs_display}"}])
                continue

            langs = user_language_settings.get(key, [])
            if not langs:
                continue

            user_avatar = user_avatar_cache.get(user_id)
            if not user_avatar:
                profile_res = requests.get(
                    f"https://api.line.me/v2/bot/profile/{user_id}",
                    headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"})
                user_avatar = profile_res.json().get("pictureUrl", "")
                user_avatar_cache[user_id] = user_avatar

            messages = []
            for lang in langs:
                translated_text = translate(user_text, lang)
                messages.append({
                    "type":"text",
                    "text": translated_text,
                    "sender":{"name":f"Saygo ({lang})","iconUrl":user_avatar}
                })

            reply_to_line(reply_token, messages)

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
