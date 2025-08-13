# -*- coding: utf-8 -*-
# 覆盖原文件可用

import os
import json
import html
import logging
import sqlite3
import requests
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage

logging.basicConfig(level=logging.INFO)

# ---------------------- 基础配置 ----------------------
app = Flask(__name__)
DATABASE = '/var/data/data.db'

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
GOOGLE_API_KEY   = os.getenv("GOOGLE_API_KEY")
line_bot_api     = LineBotApi(LINE_ACCESS_TOKEN)

# 支持语言 & 重置指令
LANGUAGES = ["en", "ja", "zh-tw", "zh-cn", "th", "vi", "fr", "es", "de", "id", "hi", "it", "pt", "ru", "ar", "ko"]
LANG_RESET_ALIASES = {"/re", "/reset", "/resetlang"}

# 运行期缓存（可选，重启不保留）
user_language_settings = {}  # key = f"{group_id}_{user_id}" -> ["en", "ja", ...]

# ---------------------- Schema 初始化 ----------------------
def ensure_schema():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # 群设置：是否发过卡、卡片版本号
    c.execute("""
      CREATE TABLE IF NOT EXISTS group_settings(
        group_id     TEXT PRIMARY KEY,
        card_sent    INTEGER DEFAULT 0,
        card_version INTEGER DEFAULT 1
      )
    """)

    # 群配额（套餐）
    c.execute("""
      CREATE TABLE IF NOT EXISTS group_quota(
        group_id      TEXT PRIMARY KEY,
        quota         INTEGER DEFAULT 0,
        owner_user_id TEXT,
        activated_at  TEXT
      )
    """)

    # 用户个人配额（终身免费5000 + 付费标记）
    c.execute("""
      CREATE TABLE IF NOT EXISTS user_quota(
        user_id TEXT PRIMARY KEY,
        quota   INTEGER DEFAULT 0,
        is_paid INTEGER DEFAULT 0
      )
    """)

    # 每人每群每月使用统计
    c.execute("""
      CREATE TABLE IF NOT EXISTS usage_records(
        group_id TEXT,
        user_id  TEXT,
        month    TEXT,
        usage    INTEGER,
        PRIMARY KEY(group_id, user_id, month)
      )
    """)

    # 语言偏好（按版本号存）
    c.execute("""
      CREATE TABLE IF NOT EXISTS language_prefs(
        group_id   TEXT NOT NULL,
        user_id    TEXT NOT NULL,
        version    INTEGER NOT NULL,
        langs      TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(group_id, user_id, version)
      )
    """)

    # 好友关系缓存（24h）
    c.execute("""
      CREATE TABLE IF NOT EXISTS friendship_cache(
        user_id    TEXT PRIMARY KEY,
        is_friend  INTEGER NOT NULL,
        checked_at TEXT NOT NULL
      )
    """)

    # 购买者套餐：允许绑定的群数量 + 已绑定的群列表
    c.execute("""
      CREATE TABLE IF NOT EXISTS user_plan(
        user_id             TEXT PRIMARY KEY,
        allowed_group_count INTEGER NOT NULL,
        current_group_ids   TEXT NOT NULL DEFAULT '[]'  -- JSON 数组
      )
    """)

    conn.commit()
    conn.close()

ensure_schema()

# ---------------------- 工具函数 ----------------------
def reply_to_line(reply_token, messages):
    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json={"replyToken": reply_token, "messages": messages}
    )

def has_sent_card(group_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT card_sent FROM group_settings WHERE group_id=?', (group_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def mark_card_sent(group_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT card_version FROM group_settings WHERE group_id=?', (group_id,))
    row = c.fetchone()
    if row is None:
        c.execute('INSERT INTO group_settings(group_id, card_sent, card_version) VALUES (?, 1, 1)', (group_id,))
    else:
        c.execute('UPDATE group_settings SET card_sent=1 WHERE group_id=?', (group_id,))
    conn.commit()
    conn.close()

def get_card_version(group_id) -> int:
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT card_version FROM group_settings WHERE group_id=?', (group_id,))
    row = c.fetchone()
    if row is None:
        c.execute('INSERT INTO group_settings(group_id, card_sent, card_version) VALUES (?, 0, 1)', (group_id,))
        conn.commit()
        version = 1
    else:
        version = int(row[0] or 1)
    conn.close()
    return version

def bump_card_version(group_id) -> int:
    """版本+1并清空该群语言设定；允许再次发卡。"""
    current = get_card_version(group_id)
    new_v = current + 1
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('UPDATE group_settings SET card_version=?, card_sent=0 WHERE group_id=?', (new_v, group_id))
    c.execute('DELETE FROM language_prefs WHERE group_id=?', (group_id,))
    conn.commit()
    conn.close()
    # 清理内存态
    for k in [k for k in user_language_settings.keys() if k.startswith(f"{group_id}_")]:
        user_language_settings.pop(k, None)
    return new_v

def set_user_langs_db(group_id, user_id, version, langs):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO language_prefs (group_id, user_id, version, langs, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
    ''', (group_id, user_id, version, json.dumps(langs)))
    conn.commit()
    conn.close()

def get_user_langs_db(group_id, user_id, version):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('SELECT langs FROM language_prefs WHERE group_id=? AND user_id=? AND version=?',
                  (group_id, user_id, version))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return None

def parse_lang_payload(text):
    """解析按钮文本：/lang en v7  -> 返回 (code, 7)；不匹配返回 None"""
    t = (text or "").strip()
    if not t.lower().startswith("/lang "):
        return None
    parts = t.split()
    if len(parts) < 3:
        return None
    code = parts[1].lower()
    ver  = parts[2].lower()
    if not ver.startswith('v'):
        return None
    try:
        vnum = int(ver[1:])
    except Exception:
        return None
    return (code, vnum)

def update_usage(group_id, user_id, text_length):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    c.execute('SELECT usage FROM usage_records WHERE group_id=? AND user_id=? AND month=?',
              (group_id, user_id, current_month))
    row = c.fetchone()
    if row:
        new_usage = (row[0] or 0) + text_length
        c.execute('UPDATE usage_records SET usage=? WHERE group_id=? AND user_id=? AND month=?',
                  (new_usage, group_id, user_id, current_month))
    else:
        c.execute('INSERT INTO usage_records (group_id, user_id, month, usage) VALUES (?, ?, ?, ?)',
                  (group_id, user_id, current_month, text_length))
    conn.commit()
    conn.close()

def check_user_quota(user_id, text_length) -> bool:
    """个人终身免费 5000；付费用户 is_paid=1 则个人通道不限量（群扣费仍走群池）。"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT quota, is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = c.fetchone()
    if row:
        current_quota, is_paid = row
        if is_paid:
            conn.close()
            return True
        if current_quota is None or current_quota <= 0:
            conn.close()
            return False
        if current_quota >= text_length:
            c.execute('UPDATE user_quota SET quota = quota - ? WHERE user_id=?', (text_length, user_id))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False
    else:
        initial_quota = 5000 - text_length
        c.execute('INSERT INTO user_quota (user_id, quota, is_paid) VALUES (?, ?, 0)', (user_id, initial_quota))
        conn.commit()
        conn.close()
        return initial_quota >= 0

def is_group_activated(group_id: str) -> bool:
    """是否已激活：只看是否存在 group_quota 记录，与剩余额度无关。"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT 1 FROM group_quota WHERE group_id=?', (group_id,))
    ok = c.fetchone() is not None
    conn.close()
    return ok

def consume_group_quota(group_id: str, amount: int):
    """原子扣减群套餐。成功返回 (True, remaining)，失败返回 (False, remaining_or_None)。"""
    conn = sqlite3.connect(DATABASE, timeout=30.0, isolation_level=None)
    c = conn.cursor()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('SELECT quota FROM group_quota WHERE group_id=?', (group_id,))
        row = c.fetchone()
        if not row:
            conn.rollback(); conn.close()
            return (False, None)  # 未激活
        current = int(row[0] or 0)
        if current < amount:
            conn.rollback(); conn.close()
            return (False, current)  # 额度不足
        c.execute('UPDATE group_quota SET quota = quota - ? WHERE group_id=?', (amount, group_id))
        conn.commit()
        remaining = current - amount
        conn.close()
        return (True, remaining)
    except Exception:
        try: conn.rollback()
        except: pass
        conn.close()
        logging.exception("consume_group_quota failed")
        return (False, None)

def activate_group_quota(group_id: str, owner_user_id: str, quota_amount: int):
    """Webhook 激活/重置群池额度（覆盖式）。"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO group_quota (group_id, quota, owner_user_id, activated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(group_id) DO UPDATE SET
          quota=excluded.quota,
          owner_user_id=excluded.owner_user_id,
          activated_at=excluded.activated_at
    ''', (group_id, quota_amount, owner_user_id))
    conn.commit()
    conn.close()

def translate(text, target_language):
    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"
    resp = requests.post(url, json={"q": text, "target": target_language})
    if resp.status_code == 200:
        resp.encoding = 'utf-8'
        data = resp.json()
        translated_text = data["data"]["translations"][0]["translatedText"]
        return html.unescape(translated_text)
    return "Translation error."

def is_friend(user_id: str) -> bool:
    """查询好友关系（缓存 24h）；失败时按非好友处理。"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('SELECT is_friend, checked_at FROM friendship_cache WHERE user_id=?', (user_id,))
        row = c.fetchone()
        now = datetime.utcnow()
        if row:
            isf, checked = row
            try:
                last = datetime.fromisoformat(checked)
            except Exception:
                last = now - timedelta(days=2)
            if now - last < timedelta(hours=24):
                conn.close()
                return bool(isf)

        r = requests.get(
            f"https://api.line.me/v2/bot/friendship/status?userId={user_id}",
            headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}, timeout=5
        )
        ok = False
        if r.status_code == 200:
            ok = bool(r.json().get("friendFlag"))
        c.execute('REPLACE INTO friendship_cache(user_id, is_friend, checked_at) VALUES (?, ?, ?)',
                  (user_id, 1 if ok else 0, now.isoformat()))
        conn.commit(); conn.close()
        return ok
    except Exception:
        try: conn.close()
        except: pass
        return False

def sub_link(user_id: str, group_id: str) -> str:
    return f"https://saygo-translator.carrd.co?line_id={user_id}&group_id={group_id}"

def quota_message_personal(user_id: str, group_id: str) -> str:
    """个人免费用尽——中英双语提示"""
    link = sub_link(user_id, group_id)
    return f"⚠️ 您的免费翻译额度（5,000字）已用完。\nSubscribe here: {link}"

def quota_message_group(user_id: str, group_id: str) -> str:
    """群池用尽——中英双语提示"""
    link = sub_link(user_id, group_id)
    return f"⚠️ 本群翻译额度已用尽，请续费。\nSubscribe here: {link}"

def send_language_selection_card(reply_token, group_id):
    version = get_card_version(group_id)

    def btn(label, code, color):
        return {
            "type": "button",
            "style": "primary",
            "color": color,
            "action": {
                "type": "message",
                "label": label,
                "text": f"/lang {code} v{version}"  # 带版本号，旧卡自动失效
            }
        }

    contents = [
        btn("🇺🇸 English", "en",   "#166534"),
        btn("🇨🇳 简体中文", "zh-cn", "#2563EB"),
        btn("🇹🇼 繁體中文", "zh-tw", "#1D4ED8"),
        btn("🇯🇵 日本語",   "ja",    "#B91C1C"),
        btn("🇰🇷 한국어",   "ko",    "#7E22CE"),
        btn("🇹🇭 ภาษาไทย",  "th",    "#D97706"),
        btn("🇻🇳 Tiếng Việt", "vi",  "#F97316"),
        btn("🇫🇷 Français", "fr",    "#0E7490"),
        btn("🇪🇸 Español",  "es",    "#16A34A"),
        btn("🇩🇪 Deutsch",  "de",    "#2563EB"),
        btn("🇮🇩 Bahasa Indonesia", "id", "#166534"),
        btn("🇮🇳 हिन्दी",   "hi",    "#B91C1C"),
        btn("🇮🇹 Italiano", "it",    "#16A34A"),
        btn("🇵🇹 Português","pt",    "#F97316"),
        btn("🇷🇺 Русский",  "ru",    "#7E22CE"),
        btn("🇸🇦 العربية",  "ar",    "#B91C1C"),
        {
            "type":"button", "style":"secondary",
            "action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}
        }
    ]

    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text",
                 "text": f"🌍 Select translation languages (v{version})",
                 "weight": "bold", "size": "lg", "align": "center"}
            ],
            "backgroundColor": "#FFCC80"
        },
        "body": {
            "type":"box",
            "layout":"vertical",
            "spacing":"sm",
            "contents": contents
        }
    }

    flex_message = FlexSendMessage(
        alt_text="Please select translation language",
        contents=bubble
    )
    line_bot_api.reply_message(reply_token, flex_message)

# ---------------------- 回调主流程 ----------------------
@app.route("/callback", methods=["POST"])
def callback():
    events = request.get_json().get("events", [])
    for event in events:
        reply_token = event.get("replyToken")
        if not reply_token:
            continue

        source   = event.get("source", {})
        group_id = source.get("groupId") or source.get("roomId") or "private"
        user_id  = source.get("userId", "unknown")
        key      = f"{group_id}_{user_id}"

        # 统一取昵称与头像；头像是否展示取决于好友关系
        try:
            if "groupId" in source:
                profile_url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
            elif "roomId" in source:
                profile_url = f"https://api.line.me/v2/bot/room/{group_id}/member/{user_id}"
            else:
                profile_url = f"https://api.line.me/v2/bot/profile/{user_id}"
            r = requests.get(profile_url, headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}, timeout=5)
            if r.status_code == 200:
                pd = r.json()
                user_name   = pd.get("displayName", "User")
                picture_url = pd.get("pictureUrl", "")
            else:
                user_name   = "User"
                picture_url = ""
        except Exception:
            user_name   = "User"
            picture_url = ""

        friend_ok = is_friend(user_id)
        user_avatar = picture_url if (friend_ok and picture_url) else "https://i.imgur.com/sTqykvy.png"

        # 入群：发语言卡
        if event["type"] == "join":
            if group_id and not has_sent_card(group_id):
                send_language_selection_card(reply_token, group_id)
                mark_card_sent(group_id)
            continue

        # 退群：清理该群设置
        if event["type"] == "leave":
            if group_id:
                conn = sqlite3.connect(DATABASE)
                c = conn.cursor()
                c.execute('DELETE FROM group_settings WHERE group_id=?', (group_id,))
                c.execute('DELETE FROM language_prefs WHERE group_id=?', (group_id,))
                conn.commit(); conn.close()
            continue

        # 文本消息
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = (event["message"]["text"] or "").strip()

            # A) 全群重置（/re /reset /resetlang）
            if user_text.lower() in LANG_RESET_ALIASES:
                bump_card_version(group_id)  # 版本+1并清空
                send_language_selection_card(reply_token, group_id)
                mark_card_sent(group_id)     # 重置后立刻标记为已发卡，避免重复刷卡
                continue  # 注意：不要 return

            # B) 解析“新卡按钮”点击（只认当前版本）
            parsed = parse_lang_payload(user_text)
            if parsed:
                code, v = parsed
                current_v = get_card_version(group_id)
                if v != current_v:
                    reply_to_line(reply_token, [{
                        "type": "text",
                        "text": "这张语言卡已过期，请点击最新的一张（标题里显示 v 号）。"
                    }])
                    continue
                if code not in LANGUAGES:
                    reply_to_line(reply_token, [{"type":"text","text":"不支持的语言代码"}])
                    continue

                langs_now = get_user_langs_db(group_id, user_id, current_v) or []
                if code not in langs_now:
                    langs_now.append(code)

                set_user_langs_db(group_id, user_id, current_v, langs_now)
                user_language_settings[key] = langs_now  # 可选缓存
                reply_to_line(reply_token, [{"type":"text","text":"✅ Your languages: " + ", ".join(langs_now)}])
                continue

            # C) 正常文本 → 检查是否已选语言（只看当前版本）
            current_v = get_card_version(group_id)
            langs = get_user_langs_db(group_id, user_id, current_v) or user_language_settings.get(key, [])
            if not langs:
                # 建议：新成员也直接发卡（即便之前发过）
                send_language_selection_card(reply_token, group_id)
                if not has_sent_card(group_id):
                    mark_card_sent(group_id)
                continue  # 已发卡则本条消息不翻译

            # D) 配额判定与扣减（核心规则）
            text_len = len(user_text)
            messages = []

            if is_group_activated(group_id):
                # 付费群：只扣群池（原子扣减）
                ok, remaining = consume_group_quota(group_id, text_len)
                if not ok:
                    reply_to_line(reply_token, [{"type":"text","text": quota_message_group(user_id, group_id)}])
                    continue
                update_usage(group_id, user_id, text_len)
            else:
                # 未激活群：只走个人5000
                if not check_user_quota(user_id, text_len):
                    reply_to_line(reply_token, [{"type":"text","text": quota_message_personal(user_id, group_id)}])
                    continue
                update_usage(group_id, user_id, text_len)

            # E) 翻译并回发（每种语言单独一条）
            for lang in langs:
                translated_text = translate(user_text, lang)
                messages.append({
                    "type": "text",
                    "text": translated_text,
                    "sender": {"name": f"Saygo ({lang})", "iconUrl": user_avatar}
                })

            # 同一事件只调用一次 reply
            reply_to_line(reply_token, messages)

    return jsonify(success=True), 200

# ---------------------- Stripe Webhook ----------------------
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    data = request.get_json(silent=True) or {}
    event_type = data.get('type')
    logging.info(f"🔔 webhook: {event_type}")

    # 档位 → 群池额度
    quota_mapping = {
        'Starter': 300000,
        'Basic':   1000000,
        'Pro':     2000000,
        'Expert':  4000000
    }
    # 档位 → 允许激活的群数量
    allowed_mapping = {
        'Starter': 1,
        'Basic':   3,
        'Pro':     5,
        'Expert': 10
    }

    if event_type == 'checkout.session.completed':
        obj = (data.get('data') or {}).get('object') or {}
        metadata = obj.get('metadata') or {}
        group_id = metadata.get('group_id')
        line_id  = metadata.get('line_id')   # ← 不再给默认值
        plan     = metadata.get('plan', 'Starter')

        if not line_id:
            logging.warning("checkout.session.completed 缺 line_id，忽略写库")
            return jsonify(success=True), 200

        quota_amount   = quota_mapping.get(plan, 0)
        allowed_groups = allowed_mapping.get(plan, 1)

        conn = sqlite3.connect(DATABASE); c = conn.cursor()
        # 读/初始化购买者的套餐上限与当前已绑定群
        c.execute('SELECT allowed_group_count, current_group_ids FROM user_plan WHERE user_id=?', (line_id,))
        row = c.fetchone()
        if row:
            try:
                bound_ids = json.loads(row[1] or '[]')
            except Exception:
                bound_ids = []
        else:
            bound_ids = []
        # 覆盖 allowed_group_count（也可按你的商业规则只升级时覆盖）
        c.execute('INSERT OR REPLACE INTO user_plan (user_id, allowed_group_count, current_group_ids) VALUES (?, ?, ?)',
                  (line_id, allowed_groups, json.dumps(bound_ids)))
        conn.commit()

        def push_text(to_id, text):
            try:
                line_bot_api.push_message(to_id, TextSendMessage(text=text))
            except Exception:
                logging.exception("push failed")

        if group_id:
            # 上限检查：未绑定且已达上限 -> 不激活，提示升级
            if group_id not in bound_ids and len(bound_ids) >= allowed_groups:
                push_text(line_id, f"当前套餐最多支持 {allowed_groups} 个群。已达上限，无法激活新群（{group_id}）。请升级套餐。")
                conn.close()
                return jsonify(success=True), 200

            # 写入绑定列表（若未绑定）
            if group_id not in bound_ids:
                bound_ids.append(group_id)
                c.execute('UPDATE user_plan SET current_group_ids=? WHERE user_id=?',
                          (json.dumps(bound_ids), line_id))
                conn.commit()

            # 激活/重置群池额度
            activate_group_quota(group_id, line_id, quota_amount)

            # 标记该 LINE 用户为已付费（个人通道不限量）
            try:
                c.execute('''
                    INSERT INTO user_quota (user_id, quota, is_paid)
                    VALUES (?, 0, 1)
                    ON CONFLICT(user_id) DO UPDATE SET is_paid=1
                ''', (line_id,))
                conn.commit()
            except Exception:
                logging.exception("mark paid user failed")

            # 发送一次成功提示（可保留）
            push_text(line_id, f"🎉 套餐已生效：{plan}\n群 {group_id} 已激活，额度：{quota_amount} 字。")

        conn.close()

    elif event_type == 'invoice.payment_succeeded':
        # 月度续费成功：静默为已绑定的群重置当期额度（不额外推送）
        obj = (data.get('data') or {}).get('object') or {}
        metadata = obj.get('metadata') or {}
        line_id = metadata.get('line_id')   # ← 不再给默认值
        plan    = metadata.get('plan', 'Starter')

        if not line_id:
            logging.warning("invoice.payment_succeeded 缺 line_id，忽略写库")
            return jsonify(success=True), 200

        quota_amount = quota_mapping.get(plan, 0)

        conn = sqlite3.connect(DATABASE); c = conn.cursor()
        c.execute('SELECT current_group_ids FROM user_plan WHERE user_id=?', (line_id,))
        row = c.fetchone()
        try:
            bound_ids = json.loads(row[0]) if row and row[0] else []
        except Exception:
            bound_ids = []
        for gid in bound_ids:
            activate_group_quota(gid, line_id, quota_amount)  # 覆盖为新的周期额度
        conn.commit(); conn.close()

    return jsonify(success=True), 200

# ---------------------- 入口 ----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
