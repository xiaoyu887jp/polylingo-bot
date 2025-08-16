
# -*- coding: utf-8 -*-
import os
import json
import time
import sqlite3
import hmac
import hashlib
import base64
import requests
from flask import Flask, request, abort

# ===================== 配置 =====================
LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_ACCESS_TOKEN")  # 先读你在 Render 设置的变量
    or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")  # 再读旧代码用的变量名
    or "<LINE_CHANNEL_ACCESS_TOKEN>"
)

LINE_CHANNEL_SECRET = (
    os.getenv("LINE_CHANNEL_SECRET")
    or os.getenv("LINE_SECRET")  # 兼容有人用 LINE_SECRET
    or "<LINE_CHANNEL_SECRET>"
)

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "<STRIPE_WEBHOOK_SECRET>")

BOT_AVATAR_FALLBACK = "https://i.imgur.com/sTqykvy.png"

# 计划与额度
PLANS = {
    'Free':    {'quota': 5000,    'max_groups': 0},
    'Starter': {'quota': 50000,   'max_groups': 1},
    'Basic':   {'quota': 200000,  'max_groups': 3},
    'Pro':     {'quota': 500000,  'max_groups': 5},
    'Expert':  {'quota': 1000000, 'max_groups': 10}
}

# 支持的重置指令（首个 token 命中即可）
RESET_ALIASES = {"/re", "/reset", "/resetlang"}

# 语言名映射
# 语言名映射（修正：补充 zh-cn / zh-tw，并提供大小写兼容）
LANG_NAME_MAP = {
    'en': 'English',
    'zh-cn': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)',
    'zh-CN': 'Chinese (Simplified)', 'zh-TW': 'Chinese (Traditional)',
    'ja': 'Japanese', 'ko': 'Korean', 'th': 'Thai', 'vi': 'Vietnamese',
    'id': 'Indonesian', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'hi': 'Hindi', 'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'ar': 'Arabic'
}
def language_name(code):
    return LANG_NAME_MAP.get(code, LANG_NAME_MAP.get((code or '').lower(), code))

# ===================== DB 初始化 =====================
# autocommit 模式 + 并发友好设置
conn = sqlite3.connect('bot.db', check_same_thread=False, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=5000;")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    free_remaining INTEGER
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS user_prefs (
    user_id TEXT,
    group_id TEXT,
    target_lang TEXT,
    PRIMARY KEY(user_id, group_id)
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    plan_type TEXT,
    plan_owner TEXT,
    plan_remaining INTEGER
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS user_plans (
    user_id TEXT PRIMARY KEY,
    plan_type TEXT,
    max_groups INTEGER,
    subscription_id TEXT
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS translations_cache (
    text TEXT,
    source_lang TEXT,
    target_lang TEXT,
    translated TEXT,
    PRIMARY KEY(text, source_lang, target_lang)
)""")
conn.commit()

# 内存缓存（可选）
translation_cache = {}  # (text, sl, tl) -> translated

# ===================== 工具函数 =====================
def first_token(s: str) -> str:
    if not s: return ""
    t = s.strip().lower().replace('\u3000', ' ')
    parts = t.split()
    return parts[0] if parts else ""

def is_reset_command(s: str) -> bool:
    return first_token(s) in RESET_ALIASES

def send_reply_message(reply_token, messages):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    body = {"replyToken": reply_token, "messages": messages}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(body))

def send_push_text(to_id: str, text: str):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    body = {"to": to_id, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=json.dumps(body))

def is_friend(user_id: str) -> bool:
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    r = requests.get(f"https://api.line.me/v2/bot/friendship/status?userId={user_id}", headers=headers, timeout=5)
    if r.status_code == 200:
        return bool(r.json().get("friendFlag"))
    return False

def get_user_profile(user_id, group_id=None):
    """群内优先用 group member API；非好友时依然可获取，但头像是否展示由 is_friend 决定。"""
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    if group_id:
        url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
    else:
        url = f"https://api.line.me/v2/bot/profile/{user_id}"
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code == 200:
        return r.json()
    return {}

def build_language_selection_flex():
    """语言选择 Flex（message：点击直接发送 en/ja/...）——卡片式双列版"""
    # 快速构造一个“卡片按钮”
    def card(label, code, bg):
        return {
            "type": "box",
            "layout": "vertical",
            "action": {"type": "message", "label": label, "text": code},
            "backgroundColor": bg,
            "cornerRadius": "md",
            "paddingAll": "12px",
            "contents": [
                {"type": "text", "text": label, "align": "center", "weight": "bold", "color": "#FFFFFF"}
            ]
        }

    # 两列一行
    def row(left, right):
        return {
            "type": "box", "layout": "horizontal", "spacing": "12px",
            "contents": [{"type": "box", "layout": "vertical", "flex": 1, "contents": [left]},
                         {"type": "box", "layout": "vertical", "flex": 1, "contents": [right]}]
        }

    # 色板（深色系，统一观感）
    c_green  = "#2E7D32"
    c_blue   = "#1976D2"
    c_red    = "#D32F2F"
    c_purple = "#7B1FA2"
    c_orange = "#F57C00"
    c_teal   = "#0097A7"
    c_lime   = "#43A047"

    rows = [
        row(card("🇺🇸 English", "en", c_green),   card("🇨🇳 简体中文", "zh-cn", "#FF8A00")),
        row(card("🇹🇼 繁體中文", "zh-tw", c_blue), card("🇯🇵 日本語",  "ja",    c_red)),
        row(card("🇰🇷 한국어",  "ko", c_purple),   card("🇹🇭 ภาษาไทย", "th",   c_orange)),
        row(card("🇻🇳 Tiếng Việt", "vi", c_orange), card("🇫🇷 Français", "fr",  c_teal)),
        row(card("🇪🇸 Español", "es", c_green),     card("🇩🇪 Deutsch",  "de",  c_blue)),
        row(card("🇮🇩 Bahasa Indonesia", "id", c_green), card("🇮🇳 हिन्दी", "hi", "#C62828")),
        row(card("🇮🇹 Italiano", "it", c_lime),     card("🇵🇹 Português", "pt", c_orange)),
        row(card("🇷🇺 Русский", "ru", c_purple),    card("🇸🇦 العربية", "ar",  "#D84315")),
    ]

    footer = {
        "type": "box",
        "layout": "vertical",
        "spacing": "8px",
        "contents": [
            {"type": "separator"},
            {
                "type": "button", "style": "secondary", "height": "sm",
                "action": {"type": "message", "label": "🔄 Reset", "text": "/resetlang"}
            },
            {"type": "text", "text": "Language Selection", "wrap": True,
             "color": "#9CA3AF", "size": "xs", "align": "center"}
        ]
    }

    return {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#FFE3B3",
            "contents": [{
                "type": "text", "text": "🌍 Please select translation language",
                "weight": "bold", "size": "lg", "align": "center", "color": "#1F2937"
            }]
        },
        "body": {"type": "box", "layout": "vertical", "spacing": "12px", "contents": rows + [footer]}
    }

def build_translation_flex(user_name, avatar_url, original_text, translations):
    """翻译展示 Flex：头像+原文+多语言结果"""
    contents = []
    header_contents = []
    if avatar_url:
        header_contents.append({"type": "image", "url": avatar_url, "size": "xs",
                                "aspectMode": "cover", "aspectRatio": "1:1", "flex": 0})
    header_contents.append({"type": "text", "text": f"{user_name}:", "weight": "bold", "wrap": True, "margin": "sm"})
    contents.append({"type": "box", "layout": "horizontal", "contents": header_contents})
    contents.append({"type": "text", "text": original_text, "wrap": True, "color": "#555555", "margin": "xs"})
    for lang, txt in translations:
        contents.append({"type": "separator", "margin": "md"})
        contents.append({"type": "text", "text": f"{lang}: {txt}", "wrap": True, "margin": "xs"})
    return {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}}

def translate_text(text, target_lang, source_lang=None):
    """使用 gtx 非官方端点（无 Key）。若要稳定生产，建议换官方 Translate v2/v3。"""
    cache_key = (text, source_lang or 'auto', target_lang)
    if cache_key in translation_cache:
        return translation_cache[cache_key], (source_lang or 'auto')
    sl = source_lang if source_lang else 'auto'
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t"
           f"&sl={sl}&tl={target_lang}&q=" + requests.utils.requote_uri(text))
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None
    segs = [seg[0] for seg in data[0] if seg[0]]
    translated_text = "".join(segs)
    detected_source = source_lang or (data[2] if len(data) > 2 else '')
    translation_cache[cache_key] = translated_text
    try:
        cur.execute("INSERT OR IGNORE INTO translations_cache (text, source_lang, target_lang, translated) VALUES (?, ?, ?, ?)",
                    (text, detected_source, target_lang, translated_text))
        conn.commit()
    except Exception:
        pass
    return translated_text, detected_source

# ---------------- 原子扣减：群池 ----------------
def atomic_deduct_group_quota(group_id: str, amount: int) -> bool:
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT plan_remaining FROM groups WHERE group_id=?", (group_id,))
        row = cur.fetchone()
        if not row or (row[0] is None) or (row[0] < amount):
            conn.execute("ROLLBACK")
            return False
        cur.execute("UPDATE groups SET plan_remaining = plan_remaining - ? WHERE group_id=?", (amount, group_id))
        conn.commit()
        return True
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK")
        return False

# ---------------- 原子扣减：个人 5000 ----------------
def atomic_deduct_user_free_quota(user_id: str, amount: int) -> (bool, int):
    """返回 (成功/失败, 扣减后剩余或当前余额)"""
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT free_remaining FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            free_total = PLANS['Free']['quota']
            if amount > free_total:
                conn.execute("ROLLBACK")
                return (False, 0)
            remaining = free_total - amount
            cur.execute("INSERT INTO users (user_id, free_remaining) VALUES (?, ?)", (user_id, remaining))
            conn.commit()
            return (True, remaining)
        free_remaining = row[0] or 0
        if free_remaining < amount:
            conn.execute("ROLLBACK")
            return (False, free_remaining)
        cur.execute("UPDATE users SET free_remaining = free_remaining - ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        return (True, free_remaining - amount)
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK")
        return (False, 0)

# === 新增：构造“对话气泡的 sender”（控制名字与头像） ===
def build_sender(user_id: str, group_id: str | None, lang_code: str | None):
    """
    - 若用户已加好友：使用用户头像；否则使用机器人头像
    - 名称：显示名 + (lang_code)，与截图一致（例如：'Saygo (en)'）
    """
    profile = get_user_profile(user_id, group_id) if user_id else {}
    name = (profile.get("displayName") or "User")
    if lang_code:
        name = f"{name} ({lang_code})"
    name = name[:20]  # 控制长度避免被 LINE 截断

    icon = BOT_AVATAR_FALLBACK
    try:
        if user_id and is_friend(user_id):
            icon = profile.get("pictureUrl") or BOT_AVATAR_FALLBACK
    except Exception:
        pass

    return {"name": name, "iconUrl": icon}


# ===================== Flask 应用 =====================
app = Flask(__name__)

# ---------------- LINE Webhook ----------------

     # ---------------- LINE Webhook ----------------
@app.route("/callback", methods=["POST"])
def line_webhook():
    # 校验 LINE 签名
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    if LINE_CHANNEL_SECRET:
        digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"),
                          body.encode("utf-8"),
                          hashlib.sha256).digest()
        valid_signature = base64.b64encode(digest).decode("utf-8")
        if signature != valid_signature:
            abort(400)

    data = json.loads(body) if body else {}
    for event in data.get("events", []):
        etype = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        group_id = source.get("groupId") or source.get("roomId")
        reply_token = event.get("replyToken")

        # 进群：立即发语言选择卡
        if etype == "join":
            flex = build_language_selection_flex()
            alt_text = "[Translator Bot] Please select a language / 請選擇語言"
            send_reply_message(reply_token, [{
                "type": "flex", "altText": alt_text, "contents": flex
            }])
            continue

        # 处理文本消息
        if etype == "message" and (event.get("message", {}).get("type") == "text"):
            text = event["message"]["text"] or ""

            # A) 重置指令：清空本群语言偏好并再次发卡
            if is_reset_command(text):
                cur.execute("DELETE FROM user_prefs WHERE group_id=?", (group_id,))
                conn.commit()
                flex = build_language_selection_flex()
                alt_text = "[Translator Bot] Please select a language / 請選擇語言"
                send_reply_message(reply_token, [{
                    "type": "flex", "altText": alt_text, "contents": flex
                }])
                continue

            # B) 识别“语言按钮”（message 型）并保存 → 仅回英文单行确认
            LANG_CODES = {"en","zh-cn","zh-tw","ja","ko","th","vi","fr","es","de","id","hi","it","pt","ru","ar"}
            tnorm = text.strip().lower()
            if tnorm in LANG_CODES:
                lang_code = tnorm
                cur.execute(
                    "INSERT OR REPLACE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()
                send_reply_message(reply_token, [{
                    "type": "text", "text": f"✅ Your languages: {lang_code}"
                }])
                continue

            # C) 非群聊直接忽略（sender 在 1:1 聊天不显示）
            if not group_id:
                continue

            # D) 统计本群目标语言（**包含发送者本人**，修复“已设语言仍被提示未设置”）
            cur.execute("SELECT user_id, target_lang FROM user_prefs WHERE group_id=?", (group_id,))
            prefs = cur.fetchall()
            targets = [lang for (_uid, lang) in prefs if lang]
            # 去重并统一小写，顺序保留
            targets = list(dict.fromkeys([t.lower() for t in targets]))
            if not targets:
                tip = "請先設定翻譯語言，輸入 /re /reset /resetlang 會出現語言卡片。\nSet your language with /re."
                send_reply_message(reply_token, [{"type": "text", "text": tip}])
                continue

            # E) 翻译（先用第一个语言翻译以获得 detected_src，再按同源批量翻）
            translations = []  # [(lang_code, translated_text)]
            first_lang = targets[0]
            result = translate_text(text, first_lang)
            if not result:
                send_reply_message(reply_token, [{
                    "type": "text",
                    "text": "翻譯服務繁忙，請稍後再試 / Translation is busy, please retry."
                }])
                continue
            first_txt, detected_src = result
            translations.append((first_lang, first_txt))
            for tl in targets[1:]:
                r = translate_text(text, tl, source_lang=detected_src)
                if r:
                    translations.append((tl, r[0]))

            # F) 扣费：群池优先，否则走个人 5000
            chars_used = len(text) * len(translations)
            cur.execute("SELECT plan_type, plan_remaining, plan_owner FROM groups WHERE group_id=?", (group_id,))
            group_plan = cur.fetchone()
            if group_plan:
                ok = atomic_deduct_group_quota(group_id, chars_used)
                if not ok:
                    alert = ("翻譯额度已用盡，請升級套餐。\n"
                             "Translation quota exhausted, please upgrade your plan.")
                    send_reply_message(reply_token, [{"type": "text", "text": alert}])
                    continue
            else:
                ok, _remain = atomic_deduct_user_free_quota(user_id, chars_used)
                if not ok:
                    alert = ("您的免費翻譯额度已用完，請升級套餐。\n"
                             "Your free translation quota is used up. Please upgrade your plan.")
                    send_reply_message(reply_token, [{"type": "text", "text": alert}])
                    continue

            # G) 使用“普通对话气泡”，每种语言单独一条；sender 控制名字与头像
            messages = []
            for lang_code, txt in translations:
                sender = build_sender(user_id, group_id, lang_code)  # 好友=用户头像；未加好友=机器人头像
                messages.append({
                    "type": "text",
                    "text": txt,     # 文本只放译文本身；语言代码体现在名字里：昵称 (en)
                    "sender": sender
                })

            # 一次 reply 最多 5 条
            if messages:
                send_reply_message(reply_token, messages[:5])

        # 兼容旧卡：postback 选择语言，也统一回英文单行
        elif etype == "postback":
            data_pb = event.get("postback", {}).get("data", "")
            if data_pb.startswith("lang="):
                lang_code = data_pb.split("=", 1)[1]
                cur.execute(
                    "INSERT OR REPLACE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()

                # 若该用户有套餐，尝试把本群绑定到他的套餐（受上限约束）
                cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=?", (user_id,))
                plan = cur.fetchone()
                if plan:
                    plan_type, max_groups = plan
                    cur.execute("SELECT COUNT(*) FROM groups WHERE plan_owner=?", (user_id,))
                    used = cur.fetchone()[0]
                    if used < (max_groups or 0):
                        cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
                        exists = cur.fetchone()
                        if not exists:
                            quota = PLANS.get(plan_type, {}).get('quota', 0)
                            cur.execute(
                                "INSERT INTO groups (group_id, plan_type, plan_owner, plan_remaining) VALUES (?, ?, ?, ?)",
                                (group_id, plan_type, user_id, quota)
                            )
                            conn.commit()
                    else:
                        alert = (f"當前套餐最多可用於{max_groups}個群組，請升級套餐。\n"
                                 f"Current plan allows up to {max_groups} groups. Please upgrade for more.")
                        send_reply_message(reply_token, [{"type": "text", "text": alert}])

                # 统一英文确认
                send_reply_message(reply_token, [{
                    "type": "text", "text": f"✅ Your languages: {lang_code}"
                }])

    return "OK"


        # 兼容旧卡：postback 选择语言，也统一回英文单行
        elif etype == "postback":
            data_pb = event.get("postback", {}).get("data", "")
            if data_pb.startswith("lang="):
                lang_code = data_pb.split("=", 1)[1]
                cur.execute(
                    "INSERT OR REPLACE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()

                # 若该用户有套餐，尝试把本群绑定到他的套餐（受上限约束）
                cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=?", (user_id,))
                plan = cur.fetchone()
                if plan:
                    plan_type, max_groups = plan
                    cur.execute("SELECT COUNT(*) FROM groups WHERE plan_owner=?", (user_id,))
                    used = cur.fetchone()[0]
                    if used < (max_groups or 0):
                        cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
                        exists = cur.fetchone()
                        if not exists:
                            quota = PLANS.get(plan_type, {}).get('quota', 0)
                            cur.execute(
                                "INSERT INTO groups (group_id, plan_type, plan_owner, plan_remaining) VALUES (?, ?, ?, ?)",
                                (group_id, plan_type, user_id, quota)
                            )
                            conn.commit()
                    else:
                        alert = (f"當前套餐最多可用於{max_groups}個群組，請升級套餐。\n"
                                 f"Current plan allows up to {max_groups} groups. Please upgrade for more.")
                        send_reply_message(reply_token, [{"type": "text", "text": alert}])

                # 统一英文确认
                send_reply_message(reply_token, [{
                    "type": "text", "text": f"✅ Your languages: {lang_code}"
                }])

    return "OK"

# ---------------- Stripe Webhook ----------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get("Stripe-Signature", "")
    # 签名校验（简化版本）
    if STRIPE_WEBHOOK_SECRET:
        try:
            timestamp, signature = None, None
            for part in sig_header.split(","):
                k, v = part.split("=", 1)
                if k == "t":  timestamp = v
                elif k == "v1": signature = v
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode('utf-8'),
                                signed_payload.encode('utf-8'), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature or ""):
                abort(400)
        except Exception:
            abort(400)

    try:
        event = json.loads(payload.decode('utf-8'))
    except:
        abort(400)

    etype = event.get("type")
    obj   = event.get("data", {}).get("object", {})
    if etype == "checkout.session.completed":
        # 新购/首购
        user_id   = obj.get("client_reference_id")  # 作为购买者的 LINE userId
        sub_id    = obj.get("subscription")
        metadata  = obj.get("metadata") or {}
        plan_name = (metadata.get("plan") or "").capitalize() or None
        group_id  = metadata.get("group_id")  # 若传了 group_id，则立即为该群激活

        if not plan_name and obj.get("display_items"):
            plan_name = obj["display_items"][0].get("plan", {}).get("nickname")
        if plan_name and plan_name not in PLANS:
            plan_name = None

        if user_id and plan_name:
            max_groups = PLANS[plan_name]['max_groups']
            cur.execute("INSERT OR REPLACE INTO user_plans (user_id, plan_type, max_groups, subscription_id) VALUES (?, ?, ?, ?)",
                        (user_id, plan_name, max_groups, sub_id))
            conn.commit()

            # 如果 metadata 带了 group_id → 当场尝试绑定并初始化额度（受群数上限）
            if group_id:
                cur.execute("SELECT COUNT(*) FROM groups WHERE plan_owner=?", (user_id,))
                used = cur.fetchone()[0]
                if used < max_groups:
                    cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
                    exists = cur.fetchone()
                    if not exists:
                        quota = PLANS[plan_name]['quota']
                        cur.execute("INSERT INTO groups (group_id, plan_type, plan_owner, plan_remaining) VALUES (?, ?, ?, ?)",
                                    (group_id, plan_name, user_id, quota))
                        conn.commit()
                else:
                    send_push_text(user_id, f"當前套餐最多可用於 {max_groups} 個群組，已達上限，無法激活新群（{group_id}）。請升級套餐。")

            # 友好通知
            send_push_text(user_id, f"Thank you for purchasing the {plan_name} plan! Your plan is now active.")

    elif etype == "invoice.payment_succeeded":
        # 续费成功 → 静默补额（按“补额”语义：在现有余额上 + 本期配额）
        sub_id = obj.get("subscription")
        if obj.get("billing_reason") == "subscription_cycle" and sub_id:
            cur.execute("SELECT user_id, plan_type FROM user_plans WHERE subscription_id=?", (sub_id,))
            row = cur.fetchone()
            if row:
                user_id, plan_type = row
                add_quota = PLANS.get(plan_type, {}).get('quota', 0)
                cur.execute("UPDATE groups SET plan_remaining = COALESCE(plan_remaining,0) + ? WHERE plan_owner=?",
                            (add_quota, user_id))
                conn.commit()

    return "OK"

# ---------------- 启动 ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
