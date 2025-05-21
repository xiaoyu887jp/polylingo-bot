from flask import Flask, request
import requests
from datetime import datetime

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_quota = {}
monthly_limit = 5000

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

quota_messages = {
    "en": "⚠️ Your free translation quota (5000 characters) has been exhausted. Subscribe here: https://polylingo-bot.onrender.com",
    "zh-cn": "⚠️ 您的免费翻译额度（5000字）已用完。请点击订阅：https://polylingo-bot.onrender.com",
    "zh-tw": "⚠️ 您的免費翻譯額度（5000字）已使用完畢。請點擊訂閱：https://polylingo-bot.onrender.com",
    "ja": "⚠️ 無料翻訳枠（5000文字）を使い切りました。登録はこちら：https://polylingo-bot.onrender.com",
    "ko": "⚠️ 무료 번역 한도(5000자)를 초과했습니다. 구독하기: https://polylingo-bot.onrender.com",
    "th": "⚠️ คุณใช้โควต้าการแปลฟรี (5000 ตัวอักษร) หมดแล้ว สมัครที่นี่: https://polylingo-bot.onrender.com",
    "vi": "⚠️ Bạn đã dùng hết hạn ngạch miễn phí (5000 ký tự). Đăng ký tại đây: https://polylingo-bot.onrender.com",
    "fr": "⚠️ Vous avez épuisé votre quota gratuit (5000 caractères). Abonnez-vous ici : https://polylingo-bot.onrender.com",
    "es": "⚠️ Has agotado tu cuota gratuita (5000 caracteres). Suscríbete aquí: https://polylingo-bot.onrender.com",
    "de": "⚠️ Ihr kostenloses Limit (5000 Zeichen) ist erschöpft. Hier abonnieren: https://polylingo-bot.onrender.com",
    "id": "⚠️ Kuota gratis Anda (5000 karakter) telah habis. Berlangganan: https://polylingo-bot.onrender.com",
    "hi": "⚠️ आपका मुफ्त अनुवाद कोटा (5000 अक्षर) खत्म। यहां सदस्यता लें: https://polylingo-bot.onrender.com",
    "it": "⚠️ Hai esaurito la quota gratuita (5000 caratteri). Abbonati qui: https://polylingo-bot.onrender.com",
    "pt": "⚠️ Sua cota grátis (5000 caracteres) acabou. Assine aqui: https://polylingo-bot.onrender.com",
    "ru": "⚠️ Ваш бесплатный лимит (5000 символов) исчерпан. Подписаться: https://polylingo-bot.onrender.com",
    "ar": "⚠️ لقد استنفدت حصة الترجمة المجانية (5000 حرف). اشترك هنا: https://polylingo-bot.onrender.com"
}

flex_message_json = {
    "type": "bubble",
    "header": {"type": "box", "layout": "vertical", "contents": [
        {"type": "text", "text": "🌍 Please select translation language", "weight": "bold", "size": "lg", "align": "center"}],
        "backgroundColor": "#FFCC80"},
    "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇺🇸 English", "text": "en"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇨🇳 简体中文", "text": "zh-cn"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇹🇼 繁體中文", "text": "zh-tw"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇯🇵 日本語", "text": "ja"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇰🇷 한국어", "text": "ko"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇹🇭 ภาษาไทย", "text": "th"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇻🇳 Tiếng Việt", "text": "vi"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇫🇷 Français", "text": "fr"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇪🇸 Español", "text": "es"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇩🇪 Deutsch", "text": "de"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇮🇩 Bahasa Indonesia", "text": "id"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇮🇳 हिन्दी", "text": "hi"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇮🇹 Italiano", "text": "it"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇵🇹 Português", "text": "pt"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇷🇺 Русский", "text": "ru"}},
        {"type": "button", "style": "primary", "action": {"type": "message", "label": "🇸🇦 العربية", "text": "ar"}},
        {"type": "button", "style": "secondary", "action": {"type": "message", "label": "🔄 Reset", "text": "/resetlang"}}
]}}

# The rest of your callback and functions remain the same as previous implementation provided

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
