# -*- coding: utf-8 -*-
import os
import time
import json
import hmac
import base64
import hashlib
import logging
import sqlite3
import html
import requests
from typing import Optional
from flask import Flask, request, abort
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor
from linebot import LineBotApi  # 仅为兼容保留，不直接使用

# ===================== HTTP 会话池（更稳更快） =====================
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
retry = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST"]),
    raise_on_status=False,
)
HTTP.mount("https://", HTTPAdapter(pool_connections=50, pool_maxsize=100, max_retries=retry))
HTTP.mount("http://",  HTTPAdapter(pool_connections=25, pool_maxsize=50,  max_retries=retry))

# ===================== 环境变量 =====================
LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_ACCESS_TOKEN")
    or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    or "<LINE_CHANNEL_ACCESS_TOKEN>"
)
LINE_CHANNEL_SECRET = (
    os.getenv("LINE_CHANNEL_SECRET")
    or os.getenv("LINE_SECRET")
    or "<LINE_CHANNEL_SECRET>"
)
# ===================== 购买链接 =====================
BUY_URL_BASE = "https://saygo-translator.carrd.co"

from typing import Optional  # 你顶部已导入，无需重复

def build_buy_link(user_id: str, group_id: Optional[str] = None) -> str:
    url = f"{BUY_URL_BASE}?line_id={user_id}"
    if group_id:
        url += f"&group_id={group_id}"
    return url


def build_free_quota_alert(user_id: str, group_id: Optional[str] = None) -> str:
    url = build_buy_link(user_id, group_id)
    return (
        "⚠️ 您的免費翻譯额度已用完，請升級套餐。\n"
        "Your free translation quota is used up. Please upgrade your plan.\n"
        f"{url}"
    )

def build_group_quota_alert(user_id: str, group_id: Optional[str] = None) -> str:
    url = build_buy_link(user_id, group_id)
    return (
        "⚠️ 本群翻譯额度已用盡，請升級套餐或新增群可用额度。\n"
        "Translation quota for this group is exhausted. Please upgrade your plan.\n"
        f"{url}"
    )


STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "<STRIPE_WEBHOOK_SECRET>")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")  # ✅ 官方翻译 API key 仅从环境读取

if not GOOGLE_API_KEY:
    # 不打印 key，只提示缺失
    logging.warning("GOOGLE_API_KEY is not set. Translation will fail.")

# 头像策略：True=总用用户头像；False=统一用机器人头像
ALWAYS_USER_AVATAR = True
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

# ===================== DB 初始化（沿用新程序结构） =====================
import os, shutil, logging

# ===== SQLite 持久化到 Render 磁盘 =====
DEFAULT_DB = "bot.db"                          # 旧位置（容器临时盘）
DB_PATH = os.getenv("DB_PATH", "/var/data/bot.db")  # 新位置（持久磁盘）

# 确保目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 一次性迁移：若新路径不存在、但旧 DB 存在，则拷贝过去（仅首轮有效）
try:
    if DB_PATH != DEFAULT_DB and (not os.path.exists(DB_PATH)) and os.path.exists(DEFAULT_DB):
        shutil.copyfile(DEFAULT_DB, DB_PATH)
except Exception as e:
    logging.warning(f"DB migrate copy failed: {e}")

# 连接持久化 DB
conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
cur = conn.cursor()
logging.info(f"Using DB at {DB_PATH} (exists={os.path.exists(DB_PATH)})")

# （推荐）提高稳定性/并发的 SQLite 参数
try:
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
except Exception as e:
    logging.warning(f"PRAGMA set failed: {e}")

# ===================== 建表 =====================

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
    try:
        cur.execute("PRAGMA table_info(user_prefs)")
        info = cur.fetchall()
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

# ✅ 新增：群绑定表（记录哪个用户占用了哪些群名额）
cur.execute("""
CREATE TABLE IF NOT EXISTS group_bindings (
    group_id TEXT PRIMARY KEY,
    owner_id TEXT,
    bound_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

# 翻译缓存（表存在即可，实际只用内存缓存避免并发锁）
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
    if not s:
        return ""
    t = s.strip().lower().replace('\u3000', ' ')
    parts = t.split()
    return parts[0] if parts else ""

def is_reset_command(s: str) -> bool:
    return first_token(s) in RESET_ALIASES

def send_reply_message(reply_token, messages):
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        HTTP.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json={"replyToken": reply_token, "messages": messages},
            timeout=5,
        )
    except Exception as e:
        logging.warning(f"[reply] failed: {e}")

def send_push_text(to_id: str, text: str):
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"to": to_id, "messages": [{"type": "text", "text": text}]}
    try:
        HTTP.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body, timeout=5)
    except Exception as e:
        logging.warning(f"[push] failed: {e}")

def is_friend(user_id: str):
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

# 头像/昵称缓存，减少外部请求
PROFILE_CACHE = {}
PROFILE_TTL = 300  # 秒

def get_user_profile_cached(user_id, group_id=None):
    key = (user_id or "", group_id or "")
    now = time.time()
    hit = PROFILE_CACHE.get(key)
    if hit and now - hit[0] < PROFILE_TTL:
        return hit[1]
    prof = get_user_profile(user_id, group_id) or {}
    PROFILE_CACHE[key] = (now, prof)
    return prof

def build_language_selection_flex():
    # 双列按钮卡（沿用你喜欢的设计）
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

def translate_text(text: str, target_lang: str, source_lang: Optional[str] = None):
    """
    使用官方 Google Translate v2，严格保留原文的换行格式。
    - 多行：按行数组提交，一次请求拿回逐行结果，再用 '\n' 拼回
    - 单行：走快路径
    返回: (translated_text, sl_hint/auto) 或 None
    """
    if not GOOGLE_API_KEY:
        return None

    sl = source_lang or "auto"

    # 统一换行，便于缓存与切分
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    cache_key = (text_norm, sl, target_lang)
    hit = translation_cache.get(cache_key)
    if hit:
        return hit, sl

    url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"

    try:
        if "\n" in text_norm:
            # 多行：逐行对应
            lines = text_norm.split("\n")  # 保留空行
            payload = {"q": lines, "target": target_lang, "format": "text"}
            if source_lang:
                payload["source"] = source_lang
            resp = HTTP.post(url, json=payload, timeout=4)
            if resp.status_code != 200:
                return None
            data = resp.json()
            trans_list = data["data"]["translations"]
            translated_lines = [html.unescape(item.get("translatedText", "")) for item in trans_list]
            translated = "\n".join(translated_lines)
        else:
            # 单行快路径
            payload = {"q": text_norm, "target": target_lang, "format": "text"}
            if source_lang:
                payload["source"] = source_lang
            resp = HTTP.post(url, json=payload, timeout=4)
            if resp.status_code != 200:
                return None
            data = resp.json()
            translated = html.unescape(data["data"]["translations"][0]["translatedText"])
    except Exception:
        return None

    translation_cache[cache_key] = translated
    return translated, sl

def guess_source_lang(s: str) -> Optional[str]:
    # 够用的小猜测：中文/日文/韩文/泰文；猜不到返回 None
    for ch in s:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF: return "zh-cn"
        if 0x3040 <= cp <= 0x30FF: return "ja"
        if 0xAC00 <= cp <= 0xD7AF: return "ko"
        if 0x0E00 <= cp <= 0x0E7F: return "th"
    return None

# -------- 原子扣减（沿用新程序）--------
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

def atomic_deduct_user_free_quota(user_id: str, amount: int):
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT free_remaining FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            free_total = PLANS['Free']['quota']
            if amount > free_total:
                conn.execute("ROLLBACK"); return (False, 0)
            remaining = free_total - amount
            cur.execute("INSERT INTO users (user_id, free_remaining) VALUES (?, ?)", (user_id, remaining))
            conn.commit()
            return (True, remaining)
        free_remaining = row[0] or 0
        if free_remaining < amount:
            conn.execute("ROLLBACK"); return (False, free_remaining)
        cur.execute("UPDATE users SET free_remaining = free_remaining - ? WHERE user_id=?",
                    (amount, user_id))
        conn.commit()
        return (True, free_remaining - amount)
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK"); return (False, 0)

# ===================== Flask 应用 =====================
app = Flask(__name__)

# ---------------- LINE Webhook ----------------
@app.route("/callback", methods=["POST"])
def line_webhook():
    # 校验签名
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    if LINE_CHANNEL_SECRET:
        digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        valid_signature = base64.b64encode(digest).decode("utf-8")
        if signature != valid_signature:
            abort(400)

    data = json.loads(body) if body else {}
    for event in data.get("events", []):
        etype = event.get("type")
        source = event.get("source", {}) or {}
        user_id = source.get("userId")
        group_id = source.get("groupId") or source.get("roomId")
        reply_token = event.get("replyToken")

        # A) 机器人被拉入群：清理旧设定并发语言卡
        if etype == "join":
            if group_id:
                cur.execute("DELETE FROM user_prefs WHERE group_id=?", (group_id,))
                conn.commit()
            flex = build_language_selection_flex()
            send_reply_message(reply_token, [{
                "type": "flex",
                "altText": "[Translator Bot] Please select a language / 請選擇語言",
                "contents": flex
            }])
            continue

        # 新成员加入：只发卡，不清空全群
        if etype == "memberJoined":
            continue

        # B) 文本消息
        if etype == "message" and (event.get("message", {}) or {}).get("type") == "text":
            text = (event.get("message", {}) or {}).get("text") or ""

            # B1) 重置
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

            # B2) 语言按钮：更新发言者的语言，并尝试绑定群套餐
            LANG_CODES = {"en","zh-cn","zh-tw","ja","ko","th","vi","fr","es","de","id","hi","it","pt","ru","ar"}
            tnorm = text.strip().lower()
            if tnorm in LANG_CODES:
                lang_code = tnorm
                # 保存语言偏好
                cur.execute(
                    "INSERT OR IGNORE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()

                # ===== 新增：綁定群到套餐 =====
                cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=?", (user_id,))
                row = cur.fetchone()
                if row:
                    plan_type, max_groups = row

                    # 已绑定的群数（必须按 owner_id 过滤）
                    cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=?", (user_id,))
                    used = cur.fetchone()[0] or 0

                    # 该群是否已存在
                    cur.execute("SELECT owner_id FROM group_bindings WHERE group_id=?", (group_id,))
                    exists = cur.fetchone()

                    if exists:
                        if exists[0] == user_id:
                            msg = "该群已在你的套餐名下。"
                        else:
                            msg = "⚠️ 该群已绑定在其他账户下，无法重复绑定。"
                        send_reply_message(reply_token, [{"type": "text", "text": msg}])
                        continue

                    if (max_groups is None) or (used < max_groups):
                        try:
                            cur.execute(
                                "INSERT INTO group_bindings (group_id, owner_id) VALUES (?, ?)",
                                (group_id, user_id)
                            )
                            conn.commit()
                            msg = "✅ 群绑定成功。"
                        except sqlite3.IntegrityError:
                            msg = "⚠️ 并发冲突，该群已被绑定。"
                        send_reply_message(reply_token, [{"type": "text", "text": msg}])
                    else:
                        send_reply_message(reply_token, [{
                            "type": "text",
                            "text": f"⚠️ 你的套餐最多可綁定 {max_groups} 個群組。請在舊群輸入 /unbind 解除綁定，或升級套餐。"
                        }])
                    continue

                # 回覆當前語言設置
                cur.execute("SELECT target_lang FROM user_prefs WHERE user_id=? AND group_id=?", (user_id, group_id))
                my_langs = [r[0] for r in cur.fetchall()] or [lang_code]
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Your languages: {', '.join(my_langs)}"}])
                continue

            # B3) 非群聊不翻译
            if not group_id:
                continue

            # B4) 收集发言者在本群配置的目标语言
            cur.execute("SELECT target_lang FROM user_prefs WHERE group_id=? AND user_id=?", (group_id, user_id))
            configured = [row[0].lower() for row in cur.fetchall() if row and row[0]]
            configured = list(dict.fromkeys(configured))
            if not configured:
                tip = ("請先為【你自己】設定翻譯語言，輸入 /re /reset /resetlang 會出現語言卡片。\n"
                       "Set your language with /re.")
                send_reply_message(reply_token, [{"type": "text", "text": tip}])
                continue

            src_hint = guess_source_lang(text)
            targets = [tl for tl in configured if (not src_hint or tl != src_hint)]
            if not targets:
                continue

            profile = get_user_profile_cached(user_id, group_id) or {}
            icon = profile.get("pictureUrl") or BOT_AVATAR_FALLBACK
            display_name = (profile.get("displayName") or "User")[:20]

            # B5) 翻译
            t0 = time.perf_counter()
            translations = []
            if len(targets) == 1:
                tl = targets[0]
                r = translate_text(text, tl, src_hint)
                if r:
                    txt = r[0] if isinstance(r, tuple) else r
                    translations.append((tl, txt))
            else:
                with ThreadPoolExecutor(max_workers=min(6, len(targets))) as pool:
                    futs = {tl: pool.submit(translate_text, text, tl, src_hint) for tl in targets}
                    for tl, fut in futs.items():
                        r = fut.result()
                        if r:
                            txt = r[0] if isinstance(r, tuple) else r
                            translations.append((tl, txt))
            logging.info(f"[translate] langs={len(targets)} elapsed_ms={(time.perf_counter()-t0)*1000:.1f}")

            # B6) 扣费 + 检查过期
            chars_used = len(text) * max(1, len(translations))
            cur.execute("SELECT plan_type, plan_remaining, plan_owner, expires_at FROM groups WHERE group_id=?", (group_id,))
            group_plan = cur.fetchone()
            if group_plan:
                plan_type, plan_remaining, plan_owner, expires_at = group_plan
                if expires_at:
                    import datetime
                    try:
                        if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(expires_at):
                            buy_url = build_buy_link(user_id, group_id)
                            send_reply_message(reply_token, [{
                                "type": "text",
                                "text": f"⚠️ 套餐已到期，請重新購買。\nPlan expired. Please renew:\n{buy_url}"
                            }])
                            continue
                    except Exception as e:
                        logging.warning(f"expires_at parse failed: {e}")

                if not atomic_deduct_group_quota(group_id, chars_used):
                    alert = build_group_quota_alert(user_id, group_id)
                    send_reply_message(reply_token, [
                        {"type": "text", "text": alert},
                        {"type": "text", "text": build_buy_link(user_id, group_id)}
                    ])
                    continue
            else:
                ok, _remain = atomic_deduct_user_free_quota(user_id, chars_used)
                if not ok:
                    alert = build_free_quota_alert(user_id, group_id)
                    send_reply_message(reply_token, [
                        {"type": "text", "text": alert},
                        {"type": "text", "text": build_buy_link(user_id, group_id)}
                    ])
                    continue

            # B7) 发送
            sender_icon = icon if ALWAYS_USER_AVATAR else BOT_AVATAR_FALLBACK
            messages = []
            for lang_code, txt in translations:
                messages.append({
                    "type": "text",
                    "text": txt,
                    "sender": {"name": f"{display_name} ({lang_code})"[:20], "iconUrl": sender_icon}
                })
            if messages:
                send_reply_message(reply_token, messages[:5])

        # C) 旧卡 postback
        if etype == "postback":
            data_pb = (event.get("postback", {}) or {}).get("data", "")
            if data_pb.startswith("lang="):
                lang_code = data_pb.split("=", 1)[1]
                cur.execute(
                    "INSERT OR IGNORE INTO user_prefs (user_id, group_id, target_lang) VALUES (?, ?, ?)",
                    (user_id, group_id, lang_code)
                )
                conn.commit()

                cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=?", (user_id,))
                plan = cur.fetchone()
                if plan:
                    plan_type, max_groups = plan
                    cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=?", (user_id,))
                    used = cur.fetchone()[0]
                    if used < (max_groups or 0):
                        cur.execute("SELECT owner_id FROM group_bindings WHERE group_id=?", (group_id,))
                        exists = cur.fetchone()
                        if not exists:
                            cur.execute(
                                "INSERT INTO group_bindings (group_id, owner_id) VALUES (?, ?)",
                                (group_id, user_id)
                            )
                            conn.commit()
                    else:
                        alert = (f"當前套餐最多可用於{max_groups}個群組，請升級套餐。\n"
                                 f"Current plan allows up to {max_groups} groups. Please upgrade for more.")
                        send_reply_message(reply_token, [{"type": "text", "text": alert}])

                cur.execute("SELECT target_lang FROM user_prefs WHERE user_id=? AND group_id=?", (user_id, group_id))
                my_langs = [r[0] for r in cur.fetchall()] or [lang_code]
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Your languages: {', '.join(my_langs)}"}])

    return "OK"

# ---------------- Stripe Webhook ----------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=False)  # 原始字节
    sig_header = request.headers.get("Stripe-Signature", "")

    # 校验签名
    if STRIPE_WEBHOOK_SECRET:
        try:
            ts, v1 = None, None
            for part in sig_header.split(","):
                k, v = part.split("=", 1)
                if k == "t":
                    ts = v
                elif k == "v1":
                    v1 = v
            if not (ts and v1):
                abort(400)
            signed = f"{ts}.{payload.decode('utf-8')}"
            expected = hmac.new(
                STRIPE_WEBHOOK_SECRET.encode("utf-8"),
                signed.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, v1):
                abort(400)
        except Exception:
            abort(400)

    # 解析事件
    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception:
        abort(400)

    etype = event.get("type")

    if etype == "checkout.session.completed":
        obj = (event.get("data", {}) or {}).get("object", {}) or {}

        user_id  = obj.get("client_reference_id")     # Checkout 里传的 line_id
        sub_id   = obj.get("subscription")
        md       = obj.get("metadata") or {}
        plan_name = (md.get("plan") or "").strip().capitalize()
        group_id  = md.get("group_id")

        # 无效计划或无 user_id → 忽略
        if (not user_id) or (plan_name not in PLANS):
            return "OK"

        max_groups = PLANS[plan_name]["max_groups"]
        quota      = PLANS[plan_name]["quota"]

        # 计算套餐到期时间（UTC + 30天）
        import datetime
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()

        # 1) 写入 / 更新用户套餐
        cur.execute(
            """INSERT OR REPLACE INTO user_plans
               (user_id, plan_type, max_groups, subscription_id)
               VALUES (?, ?, ?, ?)""",
            (user_id, plan_name, max_groups, sub_id),
        )
        conn.commit()

        # 2) 如果有 group_id，绑定群并充值额度 + 到期日
        if group_id:
            # 2.1 检查该群是否已经被别人绑定
            cur.execute("SELECT owner_id FROM group_bindings WHERE group_id=?", (group_id,))
            row = cur.fetchone()
            if row and row[0] and row[0] != user_id:
                send_push_text(
                    user_id,
                    f"⚠️ 群 {group_id} 已绑定到其他账号，无法重复绑定。\n"
                    f"⚠️ Group {group_id} is already bound to another account."
                )
            else:
                # 2.2 校验用户群数是否超限
                cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=?", (user_id,))
                used = cur.fetchone()[0] or 0

                if row or (max_groups is None) or (used < max_groups):
                    # 插入 group_bindings
                    if not row:
                        cur.execute(
                            "INSERT INTO group_bindings (group_id, owner_id) VALUES (?, ?)",
                            (group_id, user_id)
                        )
                        conn.commit()

                    # 插入 groups（额度 + 到期日）
                    cur.execute(
                        """INSERT OR REPLACE INTO groups 
                           (group_id, plan_type, plan_owner, plan_remaining, expires_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (group_id, plan_name, user_id, quota, expires_at),
                    )
                    conn.commit()

                    send_push_text(
                        user_id,
                        f"✅ {plan_name} 套餐已启用，群 {group_id} 获得 {quota} 字额度，有效期至 {expires_at} (UTC)。\n\n"
                        f"✅ {plan_name} plan activated. Group {group_id} has {quota} characters. Valid until {expires_at} (UTC)."
                    )
                else:
                    notify_group_limit(user_id, group_id, max_groups)
        else:
            # 没有群 id，只激活用户套餐
            send_push_text(
                user_id,
                f"✅ {plan_name} 套餐已启用。将机器人加入群后，输入 /re 设置翻译语言。\n\n"
                f"✅ {plan_name} plan activated. After adding the bot to a group, type /re to set languages."
            )

    return "OK"


# ---------------- 启动 ----------------
if __name__ == "__main__":
    # 生产建议 Start Command：
    # gunicorn -w 2 -k gthread --threads 8 -t 60 -b 0.0.0.0:$PORT main:app
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
