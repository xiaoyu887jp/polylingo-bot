#放在文件最顶部 ✅（确保导入顺序正确）
import sqlite3
import requests, os
import html
from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage
from datetime import datetime
import logging
logging.basicConfig(level=logging.INFO)

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

def get_user_paid_flag(user_id: str) -> bool:
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)
    
def sub_link(user_id: str, group_id: str) -> str:
    # 你的购买页；把用户和群ID带上便于回调识别
    base = "https://saygo-translator.carrd.co"
    return f"{base}?line_id={user_id}&group_id={group_id}"


import os
from linebot import LineBotApi

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
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

    # 群未激活（没有套餐池）→ 返回 -1，让上层提示去绑定/购买
    if not row:
        conn.close()
        return -1

    new_quota = max(row[0] - text_length, 0)
    cursor.execute('UPDATE group_quota SET quota=? WHERE group_id=?', (new_quota, group_id))
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

        # ✅ 修复后的 join 分支（保留）
        if event["type"] == "join":
            group_id = source.get("groupId")
            # 入群时不做订阅/额度校验，也不退群 —— 只发语言选择卡
            send_language_selection_card(reply_token)
            mark_card_sent(group_id)
            continue

        if event["type"] == "leave":
            group_id = source.get("groupId")
            if group_id:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM group_settings WHERE group_id=?', (group_id,))
                conn.commit()
                conn.close()
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip()

            # 1) 重置语言
            if user_text in ["/reset", "/re", "/resetlang"]:
                user_language_settings[key] = []
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM group_settings WHERE group_id=?', (group_id,))
                conn.commit()
                conn.close()
                send_language_selection_card(reply_token)
                continue

            # 2) 语言按钮（允许用户先选语言）
            if user_text in LANGUAGES:
                if key not in user_language_settings:
                    user_language_settings[key] = []
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                langs_text = ', '.join(user_language_settings[key])
                reply_to_line(reply_token, [{"type": "text", "text": f"✅ Your languages: {langs_text}"}])
                continue

            # 3) 还没选语言 → 发卡片并退出（此时不做配额检查）
            selected_langs = user_language_settings.get(key, [])
            if not selected_langs:
                if not has_sent_card(group_id):  # 确认该群组是否已发送过卡片
                    send_language_selection_card(reply_token)
                    mark_card_sent(group_id)
                continue

            # 4) 配额检查（先看群是否已激活）
            text_len = len(user_text)
            messages = []

            grp_quota = get_group_quota_amount(group_id)

            if grp_quota is None:
                # 群未激活
                if get_user_paid_flag(user_id):
                    # 付费用户在未激活群：不允许无限用 → 提示去绑定/购买
                    link = sub_link(user_id, group_id)
                    reply_to_line(
                        reply_token,
                        [{"type": "text", "text": f"⚠️ 本群尚未激活到你的套餐，请先在购买页绑定本群：\n{link}"}]
                    )
                    continue
                else:
                    # 非付费用户 → 走个人 5000 免费额度
                    if not check_user_quota(user_id, text_len):
                        link = sub_link(user_id, group_id)
                        reply_to_line(
                            reply_token,
                            [{"type": "text", "text": f"⚠️ 免费额度已用完，请订阅：\n{link}"}]
                        )
                        continue
            else:
                # 群已激活
                if grp_quota <= 0:
                    # 已激活但额度用尽
                    link = sub_link(user_id, group_id)
                    reply_to_line(
                        reply_token,
                        [{"type": "text", "text": f"⚠️ 本群套餐额度已用完，请升级或续费：\n{link}"}]
                    )
                    continue

                # 额度 > 0 → 扣群池
                new_quota = update_group_quota(group_id, text_len)
                if new_quota <= 0:
                    link = sub_link(user_id, group_id)
                    reply_to_line(
                        reply_token,
                        [{"type": "text", "text": f"⚠️ 本群套餐额度已用完，请升级或续费：\n{link}"}]
                    )
                    continue

            # 5) 通过配额后再翻译并回发
            for lang in selected_langs:
                translated_text = translate(user_text, lang)
                sender_icon = (
                    user_avatar
                    if user_avatar != "https://example.com/default_avatar.png"
                    else "https://i.imgur.com/sTqykvy.png"
                )
                messages.append({
                    "type": "text",
                    "text": translated_text,
                    "sender": {"name": f"Saygo ({lang})", "iconUrl": sender_icon}
                })

            # 记录统计
            update_usage(group_id, user_id, text_len)

            reply_to_line(reply_token, messages)

    return jsonify(success=True), 200


@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    data = request.get_json(silent=True) or {}
    event_type = data.get('type')
    logging.info(f"🔔 收到 webhook 请求: {data}")

    if event_type == 'checkout.session.completed':
        obj = (data.get('data') or {}).get('object') or {}
        metadata = obj.get('metadata') or {}
        group_id = metadata.get('group_id')
        line_id = metadata.get('line_id')
        plan = metadata.get('plan', 'Unknown')

        # 1) 计算套餐额度与可绑定群数
        quota_mapping = {
            'Starter': 300000,
            'Basic':   1000000,
            'Pro':     2000000,
            'Expert':  4000000
        }
        group_count_mapping = {
            'Starter': 1,
            'Basic':   3,
            'Pro':     5,
            'Expert': 10
        }
        quota_amount   = quota_mapping.get(plan, 0)
        allowed_groups = group_count_mapping.get(plan, 1)

        # 2) 若带了 group_id，则初始化该群的群池额度
        if group_id:
            update_group_quota_to_amount(group_id, quota_amount)

        # 3) 写入/更新 user_plan （把当前群先记录进去，JSON 存储）
        import json
        current_ids = [group_id] if group_id else []
        current_group_ids = json.dumps(current_ids)

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_plan (user_id, allowed_group_count, current_group_ids)
            VALUES (?, ?, ?)
        ''', (line_id, allowed_groups, current_group_ids))
        conn.commit()
        conn.close()

        # 4) 标记该 LINE 用户为已付费（若不存在则插入，存在则更新）
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_quota (user_id, quota, is_paid)
            VALUES (?, 0, 1)
            ON CONFLICT(user_id) DO UPDATE SET is_paid=1
        ''', (line_id,))
        conn.commit()
        conn.close()

        # 5) 推送通知（沿用你现有的 SDK）
        message = f"🎉 Subscription successful! Plan: {plan}, quota set: {quota_amount} characters. Thanks for subscribing!"
        try:
            to_id = line_id or group_id
            if to_id:
                line_bot_api.push_message(to_id, TextSendMessage(text=message))
                logging.info(f"✅ Notification pushed to {to_id}")
            else:
                logging.warning("⚠️ Missing both line_id and group_id in metadata. No message sent.")
        except Exception as e:
            logging.error(f"⚠️ Failed to send notification: {e}")

    return jsonify(success=True), 200


def update_group_quota_to_amount(group_id, quota_amount):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_quota (group_id, quota) VALUES (?, ?)', (group_id, quota_amount))
    conn.commit()
    conn.close()

def get_group_quota_amount(group_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT quota FROM group_quota WHERE group_id=?', (group_id,))
    row = cursor.fetchone()
    conn.close()
    return (row[0] if row else None)


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

def check_user_quota(user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT quota, is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = cursor.fetchone()

    if row:
        current_quota, is_paid = row

        if is_paid:
            conn.close()
            return True  # 付费用户无限使用
        else:
            if current_quota <= 0:
                conn.close()
                return False  # 额度为0，永久禁止免费使用
            elif current_quota >= text_length:
                cursor.execute('UPDATE user_quota SET quota = quota - ? WHERE user_id=?', (text_length, user_id))
                conn.commit()
                conn.close()
                return True
            else:
                conn.close()
                return False  # 额度不足，无法使用
    else:
        # 首次使用，初始化终身免费额度5000字
        initial_quota = 5000 - text_length
        cursor.execute('INSERT INTO user_quota (user_id, quota, is_paid) VALUES (?, ?, 0)',
                       (user_id, initial_quota))
        conn.commit()
        conn.close()
        return initial_quota >= 0




def update_user_quota(user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE user_quota SET quota = quota - ? 
        WHERE user_id=? AND is_paid=0
    ''', (text_length, user_id))

    conn.commit()
    conn.close()

def reset_group_settings():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_settings')
    conn.commit()
    conn.close()

# 新加入的函数（临时测试额度重置）✅
def reset_all_user_quota():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_quota SET quota = 5000 WHERE is_paid=0')  # 临时把所有非付费用户额度改为100
    conn.commit()
    conn.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
