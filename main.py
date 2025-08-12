# -*- coding: utf-8 -*-
# 可直接覆盖原文件

import os
import html
import json
import logging
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage

logging.basicConfig(level=logging.INFO)

# ---------------------- 基础配置 ----------------------
app = Flask(__name__)
DATABASE = '/var/data/data.db'
STRICT_GROUP_MODE = True  # 严格群模式：群未激活时群聊一律不翻译
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)

LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]

# 内存态：可选；若要持久化语言，可扩展到 DB（你清单里建议持久化）
user_language_settings = {}
user_usage = {}
MONTHLY_FREE_QUOTA = 5000

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

flex_message_json = {
    "type": "bubble",
    "header": {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text",
             "text": "🌍 Please select translation language",
             "weight": "bold", "size": "lg", "align": "center"}
        ],
        "backgroundColor": "#F8FAFC"  # 浅色标题条，视觉更轻
    },
    "body": {
        "type": "box",
        "layout": "vertical",
        "spacing": "md",
        "contents": [
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇺🇸 English","text":"en"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇨🇳 简体中文","text":"zh-cn"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇹🇼 繁體中文","text":"zh-tw"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇯🇵 日本語","text":"ja"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇰🇷 한국어","text":"ko"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇹🇭 ภาษาไทย","text":"th"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇻🇳 Tiếng Việt","text":"vi"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇫🇷 Français","text":"fr"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇪🇸 Español","text":"es"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇩🇪 Deutsch","text":"de"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇮🇩 Bahasa Indonesia","text":"id"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇮🇳 हिन्दी","text":"hi"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇮🇹 Italiano","text":"it"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇵🇹 Português","text":"pt"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇷🇺 Русский","text":"ru"}},
            {"type":"button","style":"primary","color":"#2A6FF0","action":{"type":"message","label":"🇸🇦 العربية","text":"ar"}},
            {"type":"button","style":"secondary","action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}}
        ]
    }
}



# ---------------------- 小工具函数 ----------------------
def reply_to_line(reply_token, messages):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json={"replyToken": reply_token, "messages": messages}
    )

def send_language_selection_card(reply_token):
    flex_message = FlexSendMessage(alt_text="Please select translation language", contents=flex_message_json)
    line_bot_api.reply_message(reply_token, flex_message)

def translate(text, target_language):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    response = requests.post(url, json={"q": text, "target": target_language})
    if response.status_code == 200:
        response.encoding = 'utf-8'
        translation_data = response.json()
        translated_text = translation_data["data"]["translations"][0]["translatedText"]
        translated_text = html.unescape(translated_text)
        return translated_text
    return "Translation error."

# ---------------------- DB 读写：群卡/用量 ----------------------
def has_sent_card(group_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT card_sent FROM group_settings WHERE group_id=?', (group_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row[0] == 1

def mark_card_sent(group_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_settings (group_id, card_sent) VALUES (?, 1)', (group_id,))
    conn.commit()
    conn.close()

def update_usage(group_id, user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute('SELECT usage FROM usage_records WHERE group_id=? AND user_id=? AND month=?',
                   (group_id, user_id, current_month))
    row = cursor.fetchone()
    if row:
        new_usage = row[0] + text_length
        cursor.execute('UPDATE usage_records SET usage=? WHERE group_id=? AND user_id=? AND month=?',
                       (new_usage, group_id, user_id, current_month))
    else:
        cursor.execute('INSERT INTO usage_records (group_id, user_id, month, usage) VALUES (?, ?, ?, ?)',
                       (group_id, user_id, current_month, text_length))
    conn.commit()
    conn.close()

def get_current_usage(group_id, user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute('SELECT usage FROM usage_records WHERE group_id=? AND user_id=? AND month=?',
                   (group_id, user_id, current_month))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

# ---------------------- 付费/套餐 ----------------------
def get_user_paid_flag(user_id: str) -> bool:
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def sub_link(user_id: str, group_id: str) -> str:
    base = "https://saygo-translator.carrd.co"
    return f"{base}?line_id={user_id}&group_id={group_id}"

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

# **原子扣减（唯一消费点）** —— 防双扣
def consume_group_quota(group_id: str, text_length: int):
    """
    原子扣减群套餐。成功返回 (True, remaining)，
    失败返回 (False, remaining_or_None)。未激活时 remaining 为 None。
    """
    conn = sqlite3.connect(DATABASE, timeout=30.0, isolation_level=None)
    cursor = conn.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('SELECT quota FROM group_quota WHERE group_id=?', (group_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute('ROLLBACK')
            conn.close()
            return (False, None)  # 未激活
        current = int(row[0] or 0)
        if current < text_length:
            cursor.execute('ROLLBACK')
            conn.close()
            return (False, current)  # 额度不足
        cursor.execute('UPDATE group_quota SET quota = quota - ? WHERE group_id=?', (text_length, group_id))
        conn.commit()
        remaining = current - text_length
        conn.close()
        return (True, remaining)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        logging.exception("consume_group_quota failed")
        return (False, None)

def _plan_quota_by_allowed(allowed_groups: int) -> int:
    mapping = {1: 300000, 3: 1000000, 5: 2000000, 10: 4000000}
    return mapping.get(allowed_groups, 0)

def _get_user_plan_info(user_id: str):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT allowed_group_count, current_group_ids FROM user_plan WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return 0, []
    allowed, ids = (row[0] or 0), (row[1] or '[]')
    try:
        groups = json.loads(ids) if ids else []
    except Exception:
        groups = []
    return allowed, groups

def _bind_group_if_allowed(user_id: str, group_id: str):
    """
    自动绑定：若用户还有名额，则把当前群加入套餐，并为该群初始化群池。
    返回 (bound: bool, allowed: int, used_after: int)
    """
    allowed, groups = _get_user_plan_info(user_id)
    used = len(groups)
    if allowed <= 0 or used >= allowed:
        return (False, allowed, used)

    if group_id in groups:
        per_quota = _plan_quota_by_allowed(allowed)
        if per_quota > 0:
            update_group_quota_to_amount(group_id, per_quota)
        return (True, allowed, used)

    groups.append(group_id)
    per_quota = _plan_quota_by_allowed(allowed)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_plan SET current_group_ids=? WHERE user_id=?', (json.dumps(groups), user_id))
    conn.commit()
    conn.close()

    if per_quota > 0:
        update_group_quota_to_amount(group_id, per_quota)

    return (True, allowed, used + 1)

# ---------------------- 用户额度（个人试用 5000） ----------------------
def check_user_quota(user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT quota, is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = cursor.fetchone()

    if row:
        current_quota, is_paid = row
        if is_paid:
            conn.close()
            return True  # 付费用户在个人通道无限（群扣费仍走群池）
        else:
            if current_quota <= 0:
                conn.close()
                return False
            elif current_quota >= text_length:
                cursor.execute('UPDATE user_quota SET quota = quota - ? WHERE user_id=?', (text_length, user_id))
                conn.commit()
                conn.close()
                return True
            else:
                conn.close()
                return False
    else:
        # 首次使用，初始化终身免费额度 5000 字
        initial_quota = 5000 - text_length
        cursor.execute('INSERT INTO user_quota (user_id, quota, is_paid) VALUES (?, ?, 0)',
                       (user_id, initial_quota))
        conn.commit()
        conn.close()
        return initial_quota >= 0

def update_user_quota(user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_quota SET quota = quota - ? WHERE user_id=? AND is_paid=0',
                   (text_length, user_id))
    conn.commit()
    conn.close()

# 测试/维护小函数
def reset_group_settings():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_settings')
    conn.commit()
    conn.close()

def reset_all_user_quota():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_quota SET quota = 5000 WHERE is_paid=0')
    conn.commit()
    conn.close()

# ---------------------- LINE 回调 ----------------------
@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event.get("replyToken")
        if not reply_token:
            continue

        source = event.get("source", {})
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        key = f"{group_id}_{user_id}"

        # 统一取头像：群用 group/{gid}/member/{uid}；私聊用 /profile/{uid}
        try:
            if group_id != "private":
                profile_url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
            else:
                profile_url = f"https://api.line.me/v2/bot/profile/{user_id}"
            profile_res = requests.get(profile_url, headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"})
            if profile_res.status_code == 200:
                profile_data = profile_res.json()
                user_name = profile_data.get("displayName", "User")
                user_avatar = profile_data.get("pictureUrl", "")
            else:
                user_name = "User"
                user_avatar = "https://example.com/default_avatar.png"
        except Exception:
            user_name = "User"
            user_avatar = "https://example.com/default_avatar.png"

        # 入群：只发语言卡
        if event["type"] == "join":
            gid = source.get("groupId")
            send_language_selection_card(reply_token)
            if gid:
                mark_card_sent(gid)
            continue

        # 退群：清理 UI 状态
        if event["type"] == "leave":
            gid = source.get("groupId")
            if gid:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM group_settings WHERE group_id=?', (gid,))
                conn.commit()
                conn.close()
            continue

        # 文本消息
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

            # 2) 选择语言
            if user_text in LANGUAGES:
                if key not in user_language_settings:
                    user_language_settings[key] = []
                if user_text not in user_language_settings[key]:
                    user_language_settings[key].append(user_text)
                langs_text = ', '.join(user_language_settings[key])
                reply_to_line(reply_token, [{"type": "text", "text": f"✅ Your languages: {langs_text}"}])
                continue

            # 3) 未选语言 → 发卡
            selected_langs = user_language_settings.get(key, [])
            if not selected_langs:
                if not has_sent_card(group_id):
                    send_language_selection_card(reply_token)
                    mark_card_sent(group_id)
                continue

            # 4) 配额检查（绑定/扣费只发生一次）
            text_len = len(user_text)
            messages = []
            charged_group = False  # 本条消息是否已从群池扣过

            grp_quota = get_group_quota_amount(group_id)

            if grp_quota is None:
                # 未激活
                if STRICT_GROUP_MODE and group_id != "private":
                    if get_user_paid_flag(user_id):
                        # 付费用户：尝试自动绑定
                        bound, allowed, used_after = _bind_group_if_allowed(user_id, group_id)
                        link = sub_link(user_id, group_id)
                        if not bound:
                            reply_to_line(reply_token, [{
                                "type": "text",
                                "text": f"⚠️ 你的套餐名额已满（{used_after}/{allowed} 个群）。请升级套餐：\n{link}"
                            }])
                            continue
                        # 绑定成功 → 尝试原子扣减（只在此处扣一次）
                        ok, remaining = consume_group_quota(group_id, text_len)
                        if not ok:
                            reply_to_line(reply_token, [{
                                "type": "text",
                                "text": f"⚠️ 本群套餐额度已用完，请升级或续费：\n{link}"
                            }])
                            continue
                        charged_group = True
                    else:
                        # 非付费用户：直接引导购买/绑定
                        link = sub_link(user_id, group_id)
                        reply_to_line(reply_token, [{
                            "type": "text",
                            "text": f"⚠️ 本群未购买/未绑定套餐，暂不可用。请联系管理员购买/绑定：\n{link}"
                        }])
                        continue
                else:
                    # 非严格模式或私聊 → 允许用个人5000
                    if get_user_paid_flag(user_id):
                        link = sub_link(user_id, group_id)
                        reply_to_line(reply_token, [{
                            "type": "text",
                            "text": f"⚠️ 本群尚未激活到你的套餐，请先绑定/购买：\n{link}"
                        }])
                        continue
                    else:
                        if not check_user_quota(user_id, text_len):
                            link = sub_link(user_id, group_id)
                            reply_to_line(reply_token, [{
                                "type": "text",
                                "text": f"⚠️ 免费额度已用完，请订阅：\n{link}"
                            }])
                            continue
            else:
                # 已激活
                if grp_quota <= 0:
                    link = sub_link(user_id, group_id)
                    reply_to_line(reply_token, [{
                        "type": "text",
                        "text": f"⚠️ 本群套餐额度已用完，请升级或续费：\n{link}"
                    }])
                    continue

                if not charged_group:
                    ok, remaining = consume_group_quota(group_id, text_len)
                    if not ok:
                        link = sub_link(user_id, group_id)
                        reply_to_line(reply_token, [{
                            "type": "text",
                            "text": f"⚠️ 本群套餐额度已用完，请升级或续费：\n{link}"
                        }])
                        continue

            # 5) 翻译并回发（每种语言单独一条）
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

            update_usage(group_id, user_id, text_len)
            reply_to_line(reply_token, messages)

    return jsonify(success=True), 200

# ---------------------- Stripe Webhook ----------------------
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

        # 1) 若带了 group_id，则初始化该群的群池额度
        if group_id:
            update_group_quota_to_amount(group_id, quota_amount)

        # 2) 写入/更新 user_plan（合并旧的 current_group_ids，避免覆盖）
        current_ids = [group_id] if group_id else []

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # 读取旧的 current_group_ids
        cursor.execute('SELECT current_group_ids FROM user_plan WHERE user_id=?', (line_id,))
        row = cursor.fetchone()
        old_ids = []
        if row and row[0]:
            try:
                old_ids = json.loads(row[0])
            except Exception:
                old_ids = []

        # 合并 + 去重（保持顺序）
        merged = list(dict.fromkeys([*old_ids, *current_ids]))
        merged_json = json.dumps(merged)

        # 有则更新，无则插入
        if row:
            cursor.execute(
                'UPDATE user_plan SET allowed_group_count=?, current_group_ids=? WHERE user_id=?',
                (allowed_groups, merged_json, line_id)
            )
        else:
            cursor.execute(
                'INSERT INTO user_plan (user_id, allowed_group_count, current_group_ids) VALUES (?, ?, ?)',
                (line_id, allowed_groups, merged_json)
            )

        conn.commit()
        conn.close()

        # 3) 标记该 LINE 用户为已付费
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_quota (user_id, quota, is_paid)
            VALUES (?, 0, 1)
            ON CONFLICT(user_id) DO UPDATE SET is_paid=1
        ''', (line_id,))
        conn.commit()
        conn.close()

        # 4) 推送通知
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


# ---------------------- 入口 ----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
