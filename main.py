from flask import Flask, request
import requests

app = Flask(__name__)

LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"

user_language_settings = {}
user_usage = {}
user_plan = {}

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

plans_quota = {"free": 5000}

quota_messages = {
    "en": "⚠️ Your free translation quota (5000 characters) has been exhausted. Subscribe here: https://polylingo-bot.onrender.com",
    "zh-tw": "⚠️ 您的免費翻譯額度（5000字）已使用完畢。請點擊訂閱：https://polylingo-bot.onrender.com",
    "zh-cn": "⚠️ 您的免费翻译额度（5000字）已用完。请点击订阅：https://polylingo-bot.onrender.com",
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

flex_message_json = {"type":"bubble","header":{"type":"box","layout":"vertical","contents":[{"type":"text","text":"🌍 Please select translation language","weight":"bold","size":"lg","align":"center"}],"backgroundColor":"#FFCC80"},"body":{"type":"box","layout":"vertical","spacing":"sm","contents":[
    {"type":"button","style":"primary","color":"#4CAF50","action":{"type":"message","label":"🇺🇸 English","text":"en"}},
    {"type":"button","style":"primary","color":"#33CC66","action":{"type":"message","label":"🇨🇳 简体中文","text":"zh-cn"}},
    {"type":"button","style":"primary","color":"#3399FF","action":{"type":"message","label":"🇹🇼 繁體中文","text":"zh-tw"}},
    {"type":"button","style":"primary","color":"#FF6666","action":{"type":"message","label":"🇯🇵 日本語","text":"ja"}},
    {"type":"button","style":"primary","color":"#9966CC","action":{"type":"message","label":"🇰🇷 한국어","text":"ko"}},
    {"type":"button","style":"primary","color":"#FFCC00","action":{"type":"message","label":"🇹🇭 ภาษาไทย","text":"th"}},
    {"type":"button","style":"secondary","action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}}
]}}

def reply_to_line(reply_token, messages):
    requests.post("https://api.line.me/v2/bot/message/reply",
                  headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}", "Content-Type": "application/json"},
                  json={"replyToken": reply_token, "messages": messages})

def translate(text, lang):
    res = requests.post(f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}",
                        json={"q": text, "target": lang, "format": "text"})
    return res.json()["data"]["translations"][0]["translatedText"]

@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event.get("replyToken")
        user_id = event["source"].get("userId", "unknown")

        if event["type"] == "join":
            user_language_settings[user_id] = []
            user_usage[user_id] = 0
            reply_to_line(reply_token, [{"type": "flex", "altText": "Select language", "contents": flex_message_json}])
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            text = event["message"]["text"]
            if text == "/resetlang":
                user_language_settings[user_id] = []
                reply_to_line(reply_token, [{"type": "flex", "altText": "Select language", "contents": flex_message_json}])
                continue

            if text in LANGUAGES:
                user_language_settings[user_id] = [text]
                reply_to_line(reply_token, [{"type": "text", "text": f"✅ Your language: {text}"}])
                continue

            lang = user_language_settings.get(user_id, ["en"])[0]
            user_usage[user_id] += len(text)

            if user_usage[user_id] > plans_quota["free"]:
                reply_to_line(reply_token, [{"type": "text", "text": quota_messages[lang]}])
                continue

            profile = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}).json()
            translated = translate(text, lang)
            reply_to_line(reply_token, [{"type": "text", "text": translated, "sender": {"name": profile["displayName"], "iconUrl": profile["pictureUrl"]}}])

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
