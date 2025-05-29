import requests, os
import html
from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage
from datetime import datetime  # 新增这一行

app = Flask(__name__)


LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)

user_language_settings = {}
user_usage = {}
MONTHLY_FREE_QUOTA = 5000

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

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
    {"type":"button","style":"primary","color":"#FF9933","action":{"type":"message","label":"🇻🇳 Tiếng Việt","text":"vi"}},
    {"type":"button","style":"primary","color":"#33CCCC","action":{"type":"message","label":"🇫🇷 Français","text":"fr"}},
    {"type":"button","style":"primary","color":"#33CC66","action":{"type":"message","label":"🇪🇸 Español","text":"es"}},
    {"type":"button","style":"primary","color":"#3399FF","action":{"type":"message","label":"🇩🇪 Deutsch","text":"de"}},
    {"type":"button","style":"primary","color":"#4CAF50","action":{"type":"message","label":"🇮🇩 Bahasa Indonesia","text":"id"}},
    {"type":"button","style":"primary","color":"#FF6666","action":{"type":"message","label":"🇮🇳 हिन्दी","text":"hi"}},
    {"type":"button","style":"primary","color":"#66CC66","action":{"type":"message","label":"🇮🇹 Italiano","text":"it"}},
    {"type":"button","style":"primary","color":"#FF9933","action":{"type":"message","label":"🇵🇹 Português","text":"pt"}},
    {"type":"button","style":"primary","color":"#9966CC","action":{"type":"message","label":"🇷🇺 Русский","text":"ru"}},
    {"type":"button","style":"primary","color":"#CC3300","action":{"type":"message","label":"🇸🇦 العربية","text":"ar"}},
    {"type":"button","style":"secondary","action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}}
  ]}
}

def reply_to_line(reply_token, messages):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json={"replyToken": reply_token, "messages": messages}
    )

def send_language_selection_card(reply_token):
    flex_message = FlexSendMessage(
        alt_text="Please select translation language",
        contents=flex_message_json
    )
    line_bot_api.reply_message(reply_token, flex_message)

def translate(text, target_language):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    response = requests.post(url, json={"q": text, "target": target_language})
    return response.json()["data"]["translations"][0]["translatedText"]

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

        profile_res = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
        )
        if profile_res.status_code == 200:
            profile_data = profile_res.json()
            user_avatar = profile_data.get("pictureUrl", "https://example.com/default_avatar.png")
        else:
            user_avatar = "https://example.com/default_avatar.png"

        if event["type"] == "join":
            user_language_settings[key] = []
            send_language_selection_card(reply_token)
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip()

            if user_text in ["/reset", "/re", "/resetlang"]:
                user_language_settings[key] = []
                send_language_selection_card(reply_token)
                continue

            if user_text in LANGUAGES:
                if key not in user_language_settings:
                    user_language_settings[key] = []
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                langs = ', '.join(user_language_settings[key])
                reply_to_line(reply_token, [{"type": "text", "text": f"✅ Your languages: {langs}"}])
                continue

            langs = user_language_settings.get(key, [])
            if not langs:
                send_language_selection_card(reply_token)
                continue

            current_month = datetime.now().strftime("%Y-%m")
            usage_key = f"{user_id}_{current_month}"
            usage = user_usage.get(usage_key, 0)

            messages = []
            if usage >= MONTHLY_FREE_QUOTA:
                quota_message = quota_messages.get(langs[0], quota_messages["en"])
                messages.append({"type": "text", "text": quota_message})
            else:
                for lang in langs:
                    translated_text = translate(user_text, lang)
                    if user_avatar != "https://example.com/default_avatar.png":
                        sender_icon = user_avatar
                    else:
                        sender_icon = "https://example.com/default_avatar.png"

                    messages.append({
                        "type": "text",
                        "text": translated_text,
                        "sender": {
                            "name": f"Saygo ({lang})",
                            "iconUrl": sender_icon
                        }
                    })

                    usage += len(user_text)
                    if usage >= MONTHLY_FREE_QUOTA:
                        quota_message = quota_messages.get(lang, quota_messages["en"])
                        messages.append({"type": "text", "text": quota_message})
                        break
                user_usage[usage_key] = usage

            reply_to_line(reply_token, messages)

    return jsonify(success=True), 200

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    data = request.json
    event_type = data['type']

    if event_type == 'checkout.session.completed':
        customer_email = data['data']['object']['customer_details']['email']
        subscription_id = data['data']['object']['subscription']
        print("付款成功:", customer_email, subscription_id)

    return jsonify(success=True), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
