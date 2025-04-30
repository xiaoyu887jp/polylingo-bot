from flask import Flask, request
import requests
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_profiles = {}  # 缓存用户头像和昵称
reported_user_ids = set()  # 只提示一次用户ID

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

BLACKLIST = set([])  # 屏蔽用户ID

TARGET_GROUP_ID = "C3eed212cc164a3e0c484bf78c6604e13"

flex_message_json = {
    "type": "bubble",
    "header": {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": "🌍 Please select translation language", "weight": "bold", "size": "lg", "align": "center"}
        ],
        "backgroundColor": "#FFCC80"
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": [
            {"type": "button", "style": "primary", "color": "#4CAF50", "action": {"type": "message", "label": "\ud83c\uddfa\ud83c\uddf8 English", "text": "en"}},
            {"type": "button", "style": "primary", "color": "#33CC66", "action": {"type": "message", "label": "\ud83c\udde8\ud83c\uddf3 \u7b80\u4f53\u4e2d\u6587", "text": "zh-cn"}},
            {"type": "button", "style": "primary", "color": "#3399FF", "action": {"type": "message", "label": "\ud83c\uddf9\ud83c\uddfc \u7e41\u9ad4\u4e2d\u6587", "text": "zh-tw"}},
            {"type": "button", "style": "primary", "color": "#FF6666", "action": {"type": "message", "label": "\ud83c\uddef\ud83c\uddf5 \u65e5\u672c\u8a9e", "text": "ja"}},
            {"type": "button", "style": "primary", "color": "#9966CC", "action": {"type": "message", "label": "\ud83c\uddf0\ud83c\uddf7 \ud55c\uad6d\uc5b4", "text": "ko"}},
            {"type": "button", "style": "primary", "color": "#FFCC00", "action": {"type": "message", "label": "\ud83c\uddf9\ud83c\udded \u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22", "text": "th"}},
            {"type": "button", "style": "primary", "color": "#FF9933", "action": {"type": "message", "label": "\ud83c\uddfb\ud83c\uddf3 Ti\u1ebfng Vi\u1ec7t", "text": "vi"}},
            {"type": "button", "style": "primary", "color": "#33CCCC", "action": {"type": "message", "label": "\ud83c\uddeb\ud83c\uddf7 Fran\u00e7ais", "text": "fr"}},
            {"type": "button", "style": "primary", "color": "#33CC66", "action": {"type": "message", "label": "\ud83c\uddea\ud83c\uddf8 Espa\u00f1ol", "text": "es"}},
            {"type": "button", "style": "primary", "color": "#3399FF", "action": {"type": "message", "label": "\ud83c\udde9\ud83c\uddea Deutsch", "text": "de"}},
            {"type": "button", "style": "primary", "color": "#4CAF50", "action": {"type": "message", "label": "\ud83c\uddee\ud83c\udde9 Bahasa Indonesia", "text": "id"}},
            {"type": "button", "style": "primary", "color": "#FF6666", "action": {"type": "message", "label": "\ud83c\uddee\ud83c\uddf3 \u0939\u093f\u0902\u0926\u0940", "text": "hi"}},
            {"type": "button", "style": "primary", "color": "#66CC66", "action": {"type": "message", "label": "\ud83c\uddee\ud83c\uddf9 Italiano", "text": "it"}},
            {"type": "button", "style": "primary", "color": "#FF9933", "action": {"type": "message", "label": "\ud83c\uddf5\ud83c\uddf9 Portugu\u00eas", "text": "pt"}},
            {"type": "button", "style": "primary", "color": "#9966CC", "action": {"type": "message", "label": "\ud83c\uddf7\ud83c\uddfa \u0420\u0443\u0441\u0441\u043a\u0438\u0439", "text": "ru"}},
            {"type": "button", "style": "primary", "color": "#CC3300", "action": {"type": "message", "label": "\ud83c\uddf8\ud83c\udde6 \u0627\u0644\u0639\u0631\u0628\u064a\u0629", "text": "ar"}},
            {"type": "button", "style": "secondary", "action": {"type": "message", "label": "\ud83d\udd04 Reset", "text": "/resetlang"}}
        ]
    }
}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
