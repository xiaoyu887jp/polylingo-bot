from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_profiles = {}  # 缓存用户头像和昵称
reported_user_ids = set()  # 只提示一次用户ID

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

BLACKLIST = set([])  # 屏蔽用户ID

TARGET_GROUP_ID = "C3eed212cc164a3e0c484bf78c6604e13"


def reply_to_line(reply_token, messages):
    requests.post("https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": messages})

def get_user_profile(user_id):
    if user_id not in user_profiles:
        res = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
        )
        if res.status_code == 200:
            user_profiles[user_id] = res.json()
        else:
            user_profiles[user_id] = {"displayName": "User", "pictureUrl": ""}
    return user_profiles[user_id]

def create_flex_bubble(user_name, picture_url, text):
    return {
        "type": "flex",
        "altText": f"{user_name} 的翻譯訊息",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "md",
                "contents": [
                    {
                        "type": "image",
                        "url": picture_url,
                        "size": "xxs",
                        "aspectRatio": "1:1",
                        "aspectMode": "cover"
                    },
                    {
                        "type": "text",
                        "text": text,
                        "wrap": True,
                        "gravity": "center",
                        "size": "md"
                    }
                ]
            }
        }
    }

@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event["replyToken"]
        source = event["source"]
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        if user_id in BLACKLIST or group_id in BLACKLIST:
            continue

        # 第一次说话显示 ID（只提示一次）
        if user_id not in reported_user_ids and group_id == TARGET_GROUP_ID:
            reported_user_ids.add(user_id)
            reply_to_line(reply_token, [{"type": "text", "text": f"識別碼：{user_id}"}])

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

            if user_text in LANGUAGES:
                user_language_settings.setdefault(key, [])
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                reply_to_line(reply_token, [{"type": "text", "text": f"✅ Your languages: {', '.join(user_language_settings[key])}"}])
                continue

            langs = user_language_settings.get(key, [])
            if langs:
                profile = get_user_profile(user_id)
                display_name = profile.get("displayName", "User")
                picture_url = profile.get("pictureUrl", "")
                for lang in langs:
                    translated_text = translate(user_text, lang)
                    bubble = create_flex_bubble(display_name, picture_url, f"[{lang.upper()}] {translated_text}")
                    reply_to_line(reply_token, [bubble])

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
