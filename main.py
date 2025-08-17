
# -*- coding: utf-8 -*-
import sqlite3
import requests, os
import json 
import hmac, hashlib, base64  
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, abort
from linebot import LineBotApi
...

# 复用 HTTP 连接，减少 TLS 握手与排队 ✅
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
HTTP.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20))
HTTP.mount("http://",  HTTPAdapter(pool_connections=10, pool_maxsize=10))


from concurrent.futures import ThreadPoolExecutor

# ===================== 配置 =====================
LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_ACCESS_TOKEN")  # 推荐的变量名
    or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")  # 兼容旧名
    or "<LINE_CHANNEL_ACCESS_TOKEN>"
)
LINE_CHANNEL_SECRET = (
    os.getenv("LINE_CHANNEL_SECRET")
    or os.getenv("LINE_SECRET")  # 兼容旧名
    or "<LINE_CHANNEL_SECRET>"
)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "<STRIPE_WEBHOOK_SECRET>")

BOT_AVATAR_FALLBACK = "https://i.imgur.com/sTqykvy.png"

# 计划与额度
PLANS = {
    'Free':    {'quota': 5000,    'max_groups': 0},
    'Starter': {'quota': 300000,  'max_groups': 1},
    'Basic':   {'quota': 1000000, 'max_groups': 3},
    'Pro':     {'quota': 2000000, 'max_groups': 5},
    'Expert':  {'quota': 4000000, 'max_groups': 10}
}

# 支持的重置指令
RESET_ALIASES = {"/re", "/reset", "/resetlang"}

# ===================== DB 初始化 =====================
conn = sqlite3.connect('bot.db', check_same_thread=False, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=5000;")
cur = conn.cursor()

# users：个人免费额度（默认5000）
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    free_remaining INTEGER
)""")

# user_prefs：同一个人可以在同一个群组选多语言（主键三列）
def ensure_user_prefs():
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_prefs'")
    exists = cur.fetchone()
    if not exists:
        cur.execute("""
        CREATE TABLE user_prefs (
            user_id TEXT,
            group_id TEXT,
            target_lang TEXT,
            PRIMARY KEY(user_id, group_id, target_lang)
        )""")
        conn.commit()
        return
    # 已存在则检查主键是否三列，不是则迁移
    try:
        cur.execute("PRAGMA table_info(user_prefs)")
        info = cur.fetchall()  # cid, name, type, notnull, dflt_value, pk
        pk_cols = [row[1] for row in info if int(row[5] or 0) > 0]
        if set(pk_cols) != {"user_id", "group_id", "target_lang"}:
            cur.execute("ALTER TABLE user_prefs RENAME TO user_prefs_old")
            cur.execute("""
            CREATE TABLE user_prefs (
                user_id TEXT,
                group_id TEXT,
                target_lang TEXT,
                PRIMARY KEY(user_id, group_id, target_lang)
            )""")
            cur.execute("""
            INSERT OR IGNORE INTO user_prefs (user_id, group_id, target_lang)
            SELECT user_id, group_id, target_lang FROM user_prefs_old
            WHERE target_lang IS NOT NULL AND target_lang <> ''
            """)
            cur.execute("DROP TABLE user_prefs_old")
            conn.commit()
    except Exception:
        pass

ensure_user_prefs()

# groups：把某个用户的套餐绑定到若干群里并记余额
cur.execute("""
CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    plan_type TEXT,
    plan_owner TEXT,
    plan_remaining INTEGER
)""")

# user_plans：记录用户购买的套餐
cur.execute("""
CREATE TABLE IF NOT EXISTS user_plans (
    user_id TEXT PRIMARY KEY,
    plan_type TEXT,
    max_groups INTEGER,
    subscription_id TEXT
)""")

# 简单的翻译缓存（可选）
cur.execute("""
CREATE TABLE IF NOT EXISTS translations_cache (
    text TEXT,
    source_lang TEXT,
    target_lang TEXT,
    translated TEXT,
    PRIMARY KEY(text, source_lang, target_lang)
)""")
conn.commit()

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
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    body = {"replyToken": reply_token, "messages": messages}
    HTTP.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(body), timeout=10)

def send_push_text(to_id: str, text: str):
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    body = {"to": to_id, "messages": [{"type": "text", "text": text}]}
    HTTP.post("https://api.line.me/v2/bot/message/push", headers=headers, data=json.dumps(body), timeout=10)

def is_friend(user_id: str):
    """返回 True/False；接口不可用（403等）时返回 None"""
    try:
        r = HTTP.get(
            f"https://api.line.me/v2/bot/friendship/status?userId={user_id}",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=5
        )
        if r.status_code == 200:
            return bool(r.json().get("friendFlag"))
        return None
    except Exception:
        return None

def get_user_profile(user_id, group_id=None):
    """群内优先用 group member API；单聊用 profile API。"""
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        if group_id:
            url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
        else:
            url = f"https://api.line.me/v2/bot/profile/{user_id}"
        r = HTTP.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def build_language_selection_flex():
    # 简洁双列按钮卡
    def card(label, code, bg):
        return {
            "type": "box",
            "layout": "vertical",
            "action": {"type": "message", "label": label, "text": code},
            "backgroundColor": bg,
            "cornerRadius": "md",
            "paddingAll": "12px",
            "contents": [{"type": "text", "text": label, "align": "center", "weight": "bold", "color": "#FFFFFF"}]
        }
    def row(l, r):
        return {"type": "box", "layout": "horizontal", "spacing": "12px",
                "contents": [{"type": "box", "layout": "vertical", "flex": 1, "contents": [l]},
                             {"type": "box", "layout": "vertical", "flex": 1, "contents": [r]}]}
    rows = [
        row(card("🇺🇸 English","en","#2E7D32"), card("🇨🇳 简体中文","zh-cn","#FF8A00")),
        row(card("🇹🇼 繁體中文","zh-tw","#1976D2"), card("🇯🇵 日本語","ja","#D32F2F")),
        row(card("🇰🇷 한국어","ko","#7B1FA2"), card("🇹🇭 ภาษาไทย","th","#F57C00")),
        row(card("🇻🇳 Tiếng Việt","vi","#FF9933"), card("🇫🇷 Français","fr","#0097A7")),
        row(card("🇪🇸 Español","es","#2E7D32"), card("🇩🇪 Deutsch","de","#1976D2")),
        row(card("🇮🇩 Bahasa Indonesia","id","#2E7D32"), card("🇮🇳 हिन्दी","hi","#C62828")),
        row(card("🇮🇹 Italiano","it","#43A047"), card("🇵🇹 Português","pt","#F57C00")),
        row(card("🇷🇺 Русский","ru","#7B1FA2"), card("🇸🇦 العربية","ar","#D84315")),
    ]
    footer = {
        "type": "box", "layout": "vertical", "spacing": "8px",
        "contents": [
            {"type": "separator"},
            {"type": "button","style":"secondary","height":"sm",
             "action":{"type":"message","label":"🔄 Reset","text":"/resetlang"}},
            {"type":"text","text":"Language Selection","wrap":True,"color":"#9CA3AF","size":"xs","align":"center"}
        ]
    }
    return {"type":"bubble",
            "header":{"type":"box","layout":"vertical","backgroundColor":"#FFE3B3",
                      "contents":[{"type":"text","text":"🌍 Please select translation language",
                                   "weight":"bold","size":"lg","align":"center","color":"#1F2937"}]},
            "body":{"type":"box","layout":"vertical","spacing":"12px","contents":rows+[footer]}}

def translate_text(text, target_lang, source_lang=None):
    """使用 gtx 非官方端点；返回 (translated_text, detected_source) 或 None"""
    cache_key = (text, source_lang or 'auto', target_lang)
    if cache_key in translation_cache:
        return translation_cache[cache_key], (source_lang or 'auto')
    sl = source_lang if source_lang else 'auto'
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t"
           f"&sl={sl}&tl={target_lang}&q=" + requests.utils.requote_uri(text))
    try:
        resp = HTTP.get(url, timeout=6)
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
        cur.execute("""INSERT OR IGNORE INTO translations_cache
                       (text, source_lang, target_lang, translated)
                       VALUES (?, ?, ?, ?)""",
                    (text, detected_source, target_lang, translated_text))
        conn.commit()
    except Exception:
        pass
    return translated_text, detected_source

# -------- 原子扣减：群池 --------
def atomic_deduct_group_quota(group_id: str, amount: int) -> bool:
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT plan_remaining FROM groups WHERE group_id=?", (group_id,))
        row = cur.fetchone()
        if not row or (row[0] is None) or (row[0] < amount):
            conn.execute("ROLLBACK")
            return False
        cur.execute("UPDATE groups SET plan_remaining = plan_remaining - ? WHERE group_id=?",
                    (amount, group_id))
        conn.commit()
        return True
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK")
        return False

# -------- 原子扣减：个人 5000 --------
def atomic_deduct_user_free_quota(user_id: str, amount: int):
    """返回 (成功/失败, 剩余)"""
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
            cur.execute("INSERT INTO users (user_id, free_remaining) VALUES (?, ?)",
                        (user_id, remaining))
            conn.commit()
            return (True, remaining)
        free_remaining = row[0] or 0
        if free_remaining < amount:
            conn.execute("ROLLBACK")
            return (False, free_remaining)
        cur.execute("UPDATE users SET free_remaining = free_remaining - ? WHERE user_id=?",
                    (amount, user_id))
        conn.commit()
        return (True, free_remaining - amount)
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK")
        return (False, 0)

# -------- sender 构造（名字 + 头像）--------
def build_sender(user_id: str, group_id: str | None, lang_code: str | None):
    profile = get_user_profile(user_id, group_id) if user_id else {}
    name = (profile.get("displayName") or "User")
    if lang_code:
        name = f"{name} ({lang_code})"
    name = name[:20]

    # 总是优先用用户头像（拿不到再用备用图）
    icon = profile.get("pictureUrl") or BOT_AVATAR_FALLBACK
    return {"name": name, "iconUrl": icon}


# ===================== Flask 应用 =====================
app = Flask(__name__)

# ---------------- LINE Webhook ----------------
@app.route("/callback", methods=["POST"])
def line_webhook():
    # 1) 校验 LINE 签名
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    if LINE_CHANNEL_SECRET:
        digest = hmac.new(
            LINE_CHANNEL_SECRET.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256
        ).digest()
        valid_signature = base64.b64encode(digest).decode("utf-8")
        if signature != valid_signature:
            abort(400)

    # 2) 解析事件并逐个处理（整段替换）
    data = json.loads(body) if body else {}
    for event in data.get("events", []):
        etype = event.get("type")
        source = event.get("source", {}) or {}
        user_id = source.get("userId")
        group_id = source.get("groupId") or source.get("roomId")
        reply_token = event.get("replyToken")

        # --- A) 进群：发送语言选择卡 ---
        if etype == "join":
            flex = build_language_selection_flex()
            send_reply_message(reply_token, [{
                "type": "flex",
                "altText": "[Translator Bot] Please select a language / 請選擇語言",
                "contents": flex
            }])
            continue

        # --- B) 文本消息 ---
        elif etype == "message" and (event.get("message", {}) or {}).get("type") == "text":
            text = (event.get("message", {}) or {}).get("text") or ""

            # B1) 重置指令
            if is_reset_command(text):
                cur.execute("DELETE FROM user_prefs WHERE group_id=?", (group_id,))
                conn.commit()
                flex = build_language_selection_flex()
                send_reply_message(reply_token, [{
                    "type": "flex",
                    "altText": "[Translator Bot] Please select a language / 請選擇語言",
                    "contents": flex
                }])
                continue

            # B2) 识别“语言按钮”（message 型）
            LANG_CODES = {"en","zh-cn","zh-tw","ja","ko","th","vi","fr","es","de","id","hi","it","pt","ru","ar"}
            tnorm = text.strip().lower()
            if tnorm in LANG_CODES:
                lang_code = tnorm
                cur.execute(
                    "INSERT OR IGNORE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Your languages: {lang_code}"}])
                continue

            # B3) 非群聊忽略（单聊不翻译）
            if not group_id:
                continue

            # B4) 收集本群目标语言
            cur.execute("SELECT target_lang FROM user_prefs WHERE group_id=?", (group_id,))
            targets = [row[0] for row in cur.fetchall() if row and row[0]]
            targets = list(dict.fromkeys([t.lower() for t in targets]))  # 去重保序
            if not targets:
                tip = "請先設定翻譯語言，輸入 /re /reset /resetlang 會出現語言卡片。\nSet your language with /re."
                send_reply_message(reply_token, [{"type": "text", "text": tip}])
                continue

            # —— 一次性获取头像/昵称（后面复用，不要在循环里重复查）——
            profile = get_user_profile(user_id, group_id) or {}
            icon = profile.get("pictureUrl") or BOT_AVATAR_FALLBACK
            display_name = (profile.get("displayName") or "User")[:20]

            # B5) 翻译（先译第一个确定 detected_src，再并发其余）
            translations = []
            first_lang = targets[0]
            result = translate_text(text, first_lang)
            if not result:
                send_reply_message(reply_token, [{
                    "type": "text",
                    "text": "翻譯服務繁忙，請稍後再試 / Translation is busy, please retry."
                }])
                continue

            # 兼容 translate_text 返回 (txt, detected_src) 或仅返回 txt 的两种实现
            if isinstance(result, tuple):
                first_txt, detected_src = result
            else:
                first_txt, detected_src = result, 'auto'
            translations.append((first_lang, first_txt))

            others = targets[1:]
            if others:
                # 如未全局 import，可解开下一行的局部导入
                # from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(6, len(others))) as pool:
                    futs = {tl: pool.submit(translate_text, text, tl, detected_src) for tl in others}
                    for tl in others:
                        r = futs[tl].result()
                        if r:
                            if isinstance(r, tuple):
                                translations.append((tl, r[0]))
                            else:
                                translations.append((tl, r))

            # B6) 扣费：群池优先，否则个人5000（按语种数计费）
            chars_used = len(text) * max(1, len(translations))
            cur.execute("SELECT plan_type, plan_remaining, plan_owner FROM groups WHERE group_id=?", (group_id,))
            group_plan = cur.fetchone()
            if group_plan:
                if not atomic_deduct_group_quota(group_id, chars_used):
                    alert = "翻譯额度已用盡，請升級套餐。\nTranslation quota exhausted, please upgrade your plan."
                    send_reply_message(reply_token, [{"type": "text", "text": alert}])
                    continue
            else:
                ok, _remain = atomic_deduct_user_free_quota(user_id, chars_used)
                if not ok:
                    alert = "您的免費翻譯额度已用完，請升級套餐。\nYour free translation quota is used up. Please upgrade your plan."
                    send_reply_message(reply_token, [{"type": "text", "text": alert}])
                    continue

            # B7) 发送：每个目标语言一个消息气泡（一次性回复）
            messages = []
            for lang_code, txt in translations:
                # 复用一次性获取到的头像/名字，避免重复请求
                messages.append({
                    "type": "text",
                    "text": txt,
                    "sender": {"name": f"{display_name} ({lang_code})", "iconUrl": icon}
                })
            if messages:
                send_reply_message(reply_token, messages[:5])  # 防超限（LINE 每次最多 5 条）

        # --- C) 旧卡 postback：data=lang=xx ---
        elif etype == "postback":
            data_pb = (event.get("postback", {}) or {}).get("data", "")
            if data_pb.startswith("lang="):
                lang_code = data_pb.split("=", 1)[1]
                cur.execute(
                    "INSERT OR IGNORE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
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

                # 确认
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Your languages: {lang_code}"}])

    return "OK"

# ---------------- Stripe Webhook ----------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get("Stripe-Signature", "")

    # 签名校验（简化）
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
        user_id   = obj.get("client_reference_id")
        sub_id    = obj.get("subscription")
        metadata  = obj.get("metadata") or {}
        plan_name = (metadata.get("plan") or "").capitalize() or None
        group_id  = metadata.get("group_id")

        if not plan_name and obj.get("display_items"):
            plan_name = obj["display_items"][0].get("plan", {}).get("nickname")
        if plan_name and plan_name not in PLANS:
            plan_name = None

        if user_id and plan_name:
            max_groups = PLANS[plan_name]['max_groups']
            cur.execute("""INSERT OR REPLACE INTO user_plans
                           (user_id, plan_type, max_groups, subscription_id)
                           VALUES (?, ?, ?, ?)""",
                        (user_id, plan_name, max_groups, sub_id))
            conn.commit()

            # metadata 带了 group_id → 当场尝试绑定并初始化额度
            if group_id:
                cur.execute("SELECT COUNT(*) FROM groups WHERE plan_owner=?", (user_id,))
                used = cur.fetchone()[0]
                if used < max_groups:
                    cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
                    exists = cur.fetchone()
                    if not exists:
                        quota = PLANS[plan_name]['quota']
                        cur.execute("""INSERT INTO groups
                                       (group_id, plan_type, plan_owner, plan_remaining)
                                       VALUES (?, ?, ?, ?)""",
                                    (group_id, plan_name, user_id, quota))
                        conn.commit()
                else:
                    send_push_text(user_id, f"當前套餐最多可用於 {max_groups} 個群組，已達上限，無法激活新群（{group_id}）。請升級套餐。")

            send_push_text(user_id, f"Thank you for purchasing the {plan_name} plan! Your plan is now active.")

    elif etype == "invoice.payment_succeeded":
        sub_id = obj.get("subscription")
        if obj.get("billing_reason") == "subscription_cycle" and sub_id:
            cur.execute("SELECT user_id, plan_type FROM user_plans WHERE subscription_id=?", (sub_id,))
            row = cur.fetchone()
            if row:
                user_id, plan_type = row
                add_quota = PLANS.get(plan_type, {}).get('quota', 0)
                cur.execute("""UPDATE groups
                               SET plan_remaining = COALESCE(plan_remaining,0) + ?
                               WHERE plan_owner=?""",
                            (add_quota, user_id))
                conn.commit()

    return "OK"

# ---------------- 启动 ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
