#放在文件最顶部 ✅（确保导入顺序正确）
import sqlite3
import requests, os
import html
from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage
from datetime import datetime

# 初始化 Flask 应用（放在最前面）
app = Flask(__name__)
DATABASE = '/var/data/data.db'

# ✅ 检查群组是否已发送过语言卡片
def has_sent_card(group_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT card_sent FROM group_settings WHERE group_id=?', (group_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row[0] == 1

# ✅ 标记群组为已发送过语言卡片
def mark_card_sent(group_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_settings (group_id, card_sent) VALUES (?, 1)', (group_id,))
    conn.commit()
    conn.close()

# ✅ 更新用户的使用量（每条翻译调用时更新）
def update_usage(group_id, user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")

    cursor.execute('''
        SELECT usage FROM usage_records
        WHERE group_id=? AND user_id=? AND month=?
    ''', (group_id, user_id, current_month))
    row = cursor.fetchone()

    if row:
        new_usage = row[0] + text_length
        cursor.execute('''
            UPDATE usage_records SET usage=? 
            WHERE group_id=? AND user_id=? AND month=?
        ''', (new_usage, group_id, user_id, current_month))
    else:
        new_usage = text_length
        cursor.execute('''
            INSERT INTO usage_records (group_id, user_id, month, usage) 
            VALUES (?, ?, ?, ?)
        ''', (group_id, user_id, current_month, new_usage))

    conn.commit()
    conn.close()

# ✅ 获取当前使用量（用于判断是否超额）
def get_current_usage(group_id, user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")

    cursor.execute('''
        SELECT usage FROM usage_records
        WHERE group_id=? AND user_id=? AND month=?
    ''', (group_id, user_id, current_month))
    row = cursor.fetchone()

    conn.close()
    return row[0] if row else 0




LINE_ACCESS_TOKEN = "B3blv9hwkVhaXvm9FEpijEck8hxdiNIhhlXD9A+OZDGGYhn3mEqs71gF1i88JV/7Uh+ZM9mOBOzQlhZNZhl6vtF9X/1j3gyfiT2NxFGRS8B6I0ZTUR0J673O21pqSdIJVTk3rtvWiNkFov0BTlVpuAdB04t89/1O/w1cDnyilFU="
GOOGLE_API_KEY = "AIzaSyBOMVXr3XCeqrD6WZLRLL-51chqDA9I80o"
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)

user_language_settings = {}
user_usage = {}
MONTHLY_FREE_QUOTA = 5000

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

quota_messages = {
     "en": "⚠️ Your free translation quota (5000 characters) has been exhausted. Subscribe here: https://saygo-translator.carrd.co",
    "zh-tw": "⚠️ 您的免費翻譯額度（5000字）已使用完畢。請點擊訂閱：https://saygo-translator.carrd.co",
    "zh-cn": "⚠️ 您的免费翻译额度（5000字）已用完。请点击订阅：https://saygo-translator.carrd.co",
    "ja": "⚠️ 無料翻訳枠（5000文字）を使い切りました。登録はこちら：https://saygo-translator.carrd.co",
    "ko": "⚠️ 무료 번역 한도(5000자)를 초과했습니다. 구독하기: https://saygo-translator.carrd.co",
    "th": "⚠️ คุณใช้โควต้าการแปลฟรี (5000 ตัวอักษร) หมดแล้ว สมัครที่นี่: https://saygo-translator.carrd.co",
    "vi": "⚠️ Bạn đã dùng hết hạn ngạch miễn phí (5000 ký tự). Đăng ký tại đây: https://saygo-translator.carrd.co",
    "fr": "⚠️ Vous avez épuisé votre quota gratuit (5000 caractères). Abonnez-vous ici : https://saygo-translator.carrd.co",
    "es": "⚠️ Has agotado tu cuota gratuita (5000 caracteres). Suscríbete aquí: https://saygo-translator.carrd.co",
    "de": "⚠️ Ihr kostenloses Limit (5000 Zeichen) ist erschöpft. Hier abonnieren: https://saygo-translator.carrd.co",
    "id": "⚠️ Kuota gratis Anda (5000 karakter) telah habis. Berlangganan: https://saygo-translator.carrd.co",
    "hi": "⚠️ आपका मुफ्त अनुवाद कोटा (5000 अक्षर) खत्म। यहां सदस्यता लें: https://saygo-translator.carrd.co",
    "it": "⚠️ Hai esaurito la quota gratuita (5000 caratteri). Abbonati qui: https://saygo-translator.carrd.co",
    "pt": "⚠️ Sua cota grátis (5000 caracteres) acabou. Assine aqui: https://saygo-translator.carrd.co",
    "ru": "⚠️ Ваш бесплатный лимит (5000 символов) исчерпан. Подписаться: https://saygo-translator.carrd.co",
    "ar": "⚠️ لقد استنفدت حصة الترجمة المجانية (5000 حرف). اشترك هنا: https://saygo-translator.carrd.co"
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
    if response.status_code == 200:
        response.encoding = 'utf-8'
        translation_data = response.json()
        translated_text = translation_data["data"]["translations"][0]["translatedText"]
        translated_text = html.unescape(translated_text)  # 解决特殊字符乱码
        return translated_text
    else:
        return "Translation error."
def update_group_quota(group_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT quota FROM group_quota WHERE group_id=?', (group_id,))
    row = cursor.fetchone()

    if row:
        new_quota = max(row[0] - text_length, 0)
        cursor.execute('UPDATE group_quota SET quota=? WHERE group_id=?', (new_quota, group_id))
    else:
        new_quota = max(5000 - text_length, 0)
        cursor.execute('INSERT INTO group_quota (group_id, quota) VALUES (?, ?)', (group_id, new_quota))

    conn.commit()
    conn.close()

    return new_quota


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
            user_name = profile_data.get("displayName", "User")
            user_avatar = profile_data.get("pictureUrl", "")
        else:
            user_name = "User"
            user_avatar = "https://example.com/default_avatar.png"

        if event["type"] == "join":
            if not has_sent_card(group_id):
                user_language_settings[key] = []
                send_language_selection_card(reply_token)
                mark_card_sent(group_id)
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

            messages = []
            new_quota = update_group_quota(group_id, len(user_text))


            if new_quota <= 0:
                quota_message = (
                    f"⚠️ Your free quota is exhausted. Please subscribe here:\n"
                    f"https://saygo-translator.carrd.co?line_id={user_id}\n\n"
                    f"⚠️ 您的免费额度已用完，请点击这里订阅：\n"
                    f"https://saygo-translator.carrd.co?line_id={user_id}"
                )
                messages.append({"type": "text", "text": quota_message})
            else:
                for lang in langs:
                    translated_text = translate(user_text, lang)

                    if user_avatar != "https://example.com/default_avatar.png":
                        sender_icon = user_avatar
                    else:
                        sender_icon = "https://i.imgur.com/sTqykvy.png"

                    messages.append({
                        "type": "text",
                        "text": translated_text,
                        "sender": {
                            "name": f"Saygo ({lang})",
                            "iconUrl": sender_icon
                        }
                    })
                update_usage(group_id, user_id, len(user_text))

            reply_to_line(reply_token, messages)

    return jsonify(success=True), 200


@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    data = request.json
    event_type = data['type']

    if event_type == 'checkout.session.completed':
        metadata = data['data']['object']['metadata']
        group_id = metadata.get('group_id')
        plan = metadata.get('plan', 'Unknown')

        quota_mapping = {
            'Starter': 300000,
            'Basic': 1000000,
            'Pro': 2000000,
            'Expert': 4000000
        }

        quota_amount = quota_mapping.get(plan, 0)
        update_group_quota_to_amount(group_id, quota_amount)

        message = f"🎉 Subscription successful! Plan: {plan}, quota updated to: {quota_amount} characters. Thanks for subscribing!"

        try:
            line_bot_api.push_message(group_id, TextSendMessage(text=message))
            print(f"✅ Notification sent successfully to group: {group_id}")
        except Exception as e:
            print(f"⚠️ Failed to send notification: {e}")

    return jsonify(success=True), 200

def update_group_quota_to_amount(group_id, quota_amount):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_quota (group_id, quota) VALUES (?, ?)', (group_id, quota_amount))
    conn.commit()
    conn.close()




# 新增的辅助函数（更新额度用）
def update_user_quota_by_email(email, quota_amount):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 查找或创建用户
    cursor.execute("SELECT user_id FROM users WHERE email=?", (email,))
    row = cursor.fetchone()

    if row:
        user_id = row[0]
        # 已存在用户，更新额度
        cursor.execute("UPDATE user_quota SET quota=? WHERE user_id=?", (quota_amount, user_id))
    else:
        # 不存在用户，新建用户并初始化额度
        cursor.execute("INSERT INTO users (email) VALUES (?)", (email,))
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO user_quota (user_id, quota) VALUES (?, ?)", (user_id, quota_amount))

    conn.commit()
    conn.close()
    
    return user_id



if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
