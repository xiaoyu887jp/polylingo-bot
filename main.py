from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

group_language_settings = {}
group_greeted = set()

flex_message_json = {
    "type": "bubble",
    "header": {
        "type": "box",
        "layout": "vertical",
        "contents": [{"type": "text", "text": "🌍 Please select translation language", "weight": "bold", "size": "lg", "align": "center"}],
        "backgroundColor": "#FFCC80"
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": [
            {"type":"button","style":"primary","color":"#4CAF50","action":{"type":"message","label":"🇺🇸 English","text":"/setlang en"}},
            {"type":"button","style":"primary","color":"#33CC66","action":{"type":"message","label":"🇨🇳 简体中文","text":"/setlang zh-cn"}},
            {"type":"button","style":"primary","color":"#3399FF","action":{"type":"message","label":"🇹🇼 繁體中文","text":"/setlang zh-tw"}},
            {"type":"button","style":"primary","color":"#FF6666","action":{"type":"message","label":"🇯🇵 日本語","text":"/setlang ja"}},
            {"type":"button","style":"primary","color":"#9966CC","action":{"type":"message","label":"🇰🇷 한국어","text":"/setlang ko"}},
            {"type":"button","style":"primary","color":"#FFCC00","action":{"type":"message","label":"🇹🇭 ภาษาไทย","text":"/setlang th"}},
            {"type":"button","style":"primary","color":"#FF9933","action":{"type":"message","label":"🇻🇳 Tiếng Việt","text":"/setlang vi"}},
            {"type":"button","style":"primary","color":"#33CCCC","action":{"type":"message","label":"🇫🇷 Français","text":"/setlang fr"}},
            {"type":"button","style":"primary","color":"#33CC66","action":{"type":"message","label":"🇪🇸 Español","text":"/setlang es"}},
            {"type":"button","style":"primary","color":"#3399FF","action":{"type":"message","label":"🇩🇪 Deutsch","text":"/setlang de"}},
            {"type":"button","style":"primary","color":"#4CAF50","action":{"type":"message","label":"🇮🇩 Bahasa Indonesia","text":"/setlang id"}},
            {"type":"button","style":"primary","color":"#FF6666","action":{"type":"message","label":"🇮🇳 हिन्दी","text":"/setlang hi"}},
            {"type":"button","style":"primary","color":"#66CC66","action":{"type":"message","label":"🇮🇹 Italiano","text":"/setlang it"}},
            {"type":"button","style":"primary","color":"#FF9933","action":{"type":"message","label":"🇵🇹 Português","text":"/setlang pt"}},
            {"type":"button","style":"primary","color":"#9966CC","action":{"type":"message","label":"🇷🇺 Русский","text":"/setlang ru"}},
            {"type":"button","style":"primary","color":"#CC3300","action":{"type":"message","label":"🇸🇦 العربية","text":"/setlang ar"}},
            {"type":"button","style":"secondary","action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}}
        ]
    }
}

def reply_to_line(reply_token, messages):
    requests.post("https://api.line.me/v2/bot/message/reply",
        headers={"Authorization":f"Bearer {LINE_ACCESS_TOKEN}","Content-Type":"application/json"},
        json={"replyToken":reply_token,"messages":messages})

def translate(text, lang):
    res = requests.post(f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}",
        json={"q":text,"target":lang,"format":"text"})
    return res.json()["data"]["translations"][0]["translatedText"]

@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event["replyToken"]
        source_id = event["source"].get("groupId") or event["source"].get("userId")

        # 仅对join事件进行修改，确保每次加入都发卡片
        if event["type"] == "join":
            reply_to_line(reply_token,[{"type":"flex","altText":"Select language","contents":flex_message_json}])
            continue

        user_text = event["message"]["text"]

        if user_text.startswith("/setlang"):
            lang = user_text.split()[1]
            group_language_settings[source_id] = lang
            reply_to_line(reply_token,[{"type":"text","text":f"✅ Group language set to {lang}"}])
            continue

        if user_text == "/resetlang":
            group_language_settings.pop(source_id, None)
            reply_to_line(reply_token,[{"type":"text","text":"🔄 Language reset."}])
            continue

        lang = group_language_settings.get(source_id)
        if lang:
            translated_text = translate(user_text, lang)
            reply_to_line(reply_token,[{"type":"text","text":f"[{lang.upper()}] {translated_text}"}])

    return "OK",200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
