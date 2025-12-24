# -*- coding: utf-8 -*-
import os
import re
import hmac
import hashlib
import binascii
import logging
import json
import time
import base64
import psycopg2
import html
import requests
import stripe
from typing import Optional
from flask import Flask, request, abort, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor
from linebot import LineBotApi  # 仅为兼容保留，不直接使用

# ===== Stripe Plan Definitions =====
PRICE_TO_PLAN = {
    "price_1QxABCstarter": "Starter",
    "price_1QxABCbasic": "Basic",
    "price_1QxABCpro": "Pro",
    "price_1QxABCexpert": "Expert"
}

PLANS = {
    "Starter": {"max_groups": 1, "quota": 300000},
    "Basic":   {"max_groups": 3, "quota": 1000000},
    "Pro":     {"max_groups": 5, "quota": 2000000},
    "Expert":  {"max_groups": 10, "quota": 4000000},
}


# ✅ 日志配置（一定要在 Flask 实例创建前执行）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logging.getLogger().addHandler(logging.StreamHandler())  # 确保日志输出到 Render 控制台

# ✅ Stripe 全局密钥（从环境变量读取）
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# ✅ Flask 实例（必须在日志配置之后）
app = Flask(__name__)

# ✅ 全局 LINE Session（指数退避 + keep-alive）
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging, threading

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

def get_line_session():
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=0.8,
        status_forcelist=[408, 429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=20, pool_block=True)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": "polylingo-bot/1.0 (+python-requests)",
        "Connection": "keep-alive",
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    })
    return s

# ---------------- Stripe ----------------
# 从环境变量读取各 price_id，并建立 price_id -> 套餐名 的映射
_PRICE_TO_PLAN_RAW = {
    os.getenv("STRIPE_PRICE_STARTER"): "Starter",
    os.getenv("STRIPE_PRICE_BASIC"):   "Basic",
    os.getenv("STRIPE_PRICE_PRO"):     "Pro",
    os.getenv("STRIPE_PRICE_EXPERT"):  "Expert",
}

# 过滤掉可能为空的键，避免 None 或 "" 干扰匹配
PRICE_TO_PLAN = {k: v for k, v in _PRICE_TO_PLAN_RAW.items() if k}
# ===================== DB 连接 =====================
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = False   # ❗ 必须 False，才能手动 BEGIN/COMMIT
cur = conn.cursor()

# ===================== HTTP 会话池 =====================
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
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "<LINE_CHANNEL_ACCESS_TOKEN>"
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET") or "<LINE_CHANNEL_SECRET>"
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "<STRIPE_WEBHOOK_SECRET>")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# 你的 Carrd 站点（用于生成购买链接）
BUY_URL_BASE = "https://saygo-translator.carrd.co"

if not GOOGLE_API_KEY:
    logging.warning("GOOGLE_API_KEY is not set. Translation will fail.")

# ===================== 购买链接 & 提示文案 =====================
from typing import Optional  # 如果前面已导入，这行保留或删除都不影响

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

# ===================== 头像策略 =====================
ALWAYS_USER_AVATAR = True
BOT_AVATAR_FALLBACK = "https://i.imgur.com/sTqykvy.png"

# ===================== 计划与额度（含 Stripe price_id） =====================
PLANS = {
    'Free': {
        'quota': 5000,
        'max_groups': 0
    },
    'Starter': {
        'quota': 300000,
        'max_groups': 1,
        'price_id': 'price_1SMP7iLhMUG5xYCs8HGxpDMY'  # 入門方案
    },
    'Basic': {
        'quota': 1000000,
        'max_groups': 3,
        'price_id': 'price_1SMP9oLhMUG5xYCstJo6DBZA'  # 基礎方案
    },
    'Pro': {
        'quota': 2000000,
        'max_groups': 5,
        'price_id': 'price_1SMPATLhMUG5xYCs3HPYy0ur'  # 進階方案
    },
    'Expert': {
        'quota': 4000000,
        'max_groups': 10,
        'price_id': 'price_1SMPBILhMUG5xYCstKviBHIE'  # 專業方案
    }
}

# ===================== 支持的重置指令 =====================
RESET_ALIASES = {"/re", "/reset", "/resetlang"}

# ===================== DB 初始化（沿用新程序结构） =====================
import os, shutil, logging

# ===================== 初始化数据库结构 =====================
def init_db():
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            free_remaining INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id TEXT,
            group_id TEXT,
            target_lang TEXT,
            PRIMARY KEY(user_id, group_id, target_lang)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            plan_type TEXT,
            plan_owner TEXT,
            plan_remaining INTEGER,
            expires_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_plans (
            user_id TEXT PRIMARY KEY,
            plan_type TEXT,
            max_groups INTEGER,
            subscription_id TEXT,
            expires_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_bindings (
            group_id TEXT PRIMARY KEY,
            owner_id TEXT,
            bound_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS translations_cache (
            text TEXT,
            source_lang TEXT,
            target_lang TEXT,
            translated TEXT,
            PRIMARY KEY(text, source_lang, target_lang)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_settings (
            group_id TEXT PRIMARY KEY,
            card_sent BOOLEAN DEFAULT FALSE
        )
        """
    ]
    for sql in tables:
        cur.execute(sql)
    conn.commit()
    logging.info("[init_db] all tables ensured.")

# ===================== 工具函数 =====================
RESET_ALIASES = {"/re", "/reset", "/resetlang"}

def first_token(s: str) -> str:
    if not s:
        return ""
    t = s.strip().lower().replace('\u3000', ' ')
    parts = t.split()
    return parts[0] if parts else ""

def is_reset_command(s: str) -> bool:
    return first_token(s) in RESET_ALIASES

# ✅ 检查群组是否已发送语言卡
def has_sent_card(group_id):
    try:
        cur.execute("SELECT card_sent FROM group_settings WHERE group_id=%s", (group_id,))
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False

# ✅ 标记群组为已发送语言卡
def mark_card_sent(group_id):
    try:
        cur.execute("""
            INSERT INTO group_settings (group_id, card_sent)
            VALUES (%s, TRUE)
            ON CONFLICT (group_id) DO UPDATE SET card_sent=TRUE
        """, (group_id,))
        conn.commit()
    except Exception:
        conn.rollback()

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

def send_push_text(to_id: str, text: str) -> int:
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    # 文本长度保护，避免 400
    body = {"to": to_id, "messages": [{"type": "text", "text": text[:4900]}]}
    try:
        r = HTTP.post(
            "https://api.line.me/v2/bot/message/push",
            headers=headers,
            json=body,
            timeout=5,
        )
        # 关键日志：看到发给谁、状态码是多少
        logging.info(f"[push] to={to_id} status={r.status_code} resp={r.text[:120]}")
        return r.status_code
    except Exception as e:
        logging.error(f"[push] exception: {e}")
        return 0

def notify_group_limit(user_id, group_id, max_groups):
    try:
        send_push_text(
            user_id,
            f"⚠️ 已達可綁定群組上限（{max_groups}）。\n"
            f"⚠️ You've reached the max groups ({max_groups})."
        )
    except Exception as e:
        logging.error(f"[notify_group_limit] {e}")


def is_friend(user_id: str):
    try:
        r = HTTP.get(
            f"https://api.line.me/v2/bot/friendship/status?userId={user_id}",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=5,
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

# 翻译结果缓存（避免重复请求 Google API）
translation_cache = {}


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
            "contents": [
                {
                    "type": "text",
                    "text": label,
                    "align": "center",
                    "weight": "bold",
                    "color": "#FFFFFF",
                }
            ],
        }

    def row(l, r):
        return {
            "type": "box",
            "layout": "horizontal",
            "spacing": "12px",
            "contents": [
                {"type": "box", "layout": "vertical", "flex": 1, "contents": [l]},
                {"type": "box", "layout": "vertical", "flex": 1, "contents": [r]},
            ],
        }

    rows = [
        row(card("🇺🇸 English", "en", "#2E7D32"), card("🇨🇳 简体中文", "zh-cn", "#FF8A00")),
        row(card("🇹🇼 繁體中文", "zh-tw", "#1976D2"), card("🇯🇵 日本語", "ja", "#D32F2F")),
        row(card("🇰🇷 한국어", "ko", "#7B1FA2"), card("🇹🇭 ภาษาไทย", "th", "#F57C00")),
        row(card("🇻🇳 Tiếng Việt", "vi", "#FF9933"), card("🇫🇷 Français", "fr", "#0097A7")),
        row(card("🇪🇸 Español", "es", "#2E7D32"), card("🇩🇪 Deutsch", "de", "#1976D2")),
        row(card("🇮🇩 Bahasa Indonesia", "id", "#2E7D32"), card("🇮🇳 हिन्दी", "hi", "#C62828")),
        row(card("🇮🇹 Italiano", "it", "#43A047"), card("🇵🇹 Português", "pt", "#F57C00")),
        row(card("🇷🇺 Русский", "ru", "#7B1FA2"), card("🇸🇦 العربية", "ar", "#D84315")),
    ]

    footer = {
        "type": "box",
        "layout": "vertical",
        "spacing": "8px",
        "contents": [
            {"type": "separator"},
            {
                "type": "button",
                "style": "secondary",
                "height": "sm",
                "action": {"type": "message", "label": "🔄 Reset", "text": "/resetlang"},
            },
            {
                "type": "text",
                "text": "Language Selection",
                "wrap": True,
                "color": "#9CA3AF",
                "size": "xs",
                "align": "center",
            },
        ],
    }

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FFE3B3",
            "contents": [
                {
                    "type": "text",
                    "text": "🌍 Please select translation language",
                    "weight": "bold",
                    "size": "lg",
                    "align": "center",
                    "color": "#1F2937",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "12px",
            "contents": rows + [footer],
        },
    }


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
            translated_lines = [
                html.unescape(item.get("translatedText", "")) for item in trans_list
            ]
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
            translated = html.unescape(
                data["data"]["translations"][0]["translatedText"]
            )
    except Exception:
        return None

    translation_cache[cache_key] = translated
    return translated, sl


def guess_source_lang(s: str) -> Optional[str]:
    # 够用的小猜测：中文/日文/韩文/泰文；猜不到返回 None
    for ch in s:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF:
            return "zh-cn"
        if 0x3040 <= cp <= 0x30FF:
            return "ja"
        if 0xAC00 <= cp <= 0xD7AF:
            return "ko"
        if 0x0E00 <= cp <= 0x0E7F:
            return "th"
    return None

# -------- 原子扣减（PostgreSQL 版本，去掉 BEGIN）--------
def atomic_deduct_group_quota(group_id: str, amount: int) -> bool:
    try:
        # 直接 FOR UPDATE 锁行，防止并发过扣
        cur.execute("SELECT plan_remaining FROM groups WHERE group_id=%s FOR UPDATE", (group_id,))
        row = cur.fetchone()
        if not row or (row[0] is None) or (row[0] < amount):
            conn.rollback()
            return False

        cur.execute(
            "UPDATE groups SET plan_remaining = plan_remaining - %s WHERE group_id=%s",
            (amount, group_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"[atomic_deduct_group_quota] {e}")
        conn.rollback()
        return False


def atomic_deduct_user_free_quota(user_id: str, amount: int):
    """
    原子扣减个人免费额度：
    - 若用户不存在：先插入起始值（5000），再原子扣减 amount。
    - 若用户存在：FOR UPDATE 锁行后直接扣减。
    - 额度不足返回 (False, 剩余额度)；成功返回 (True, 扣减后的剩余额度)。
    """
    try:
        # 先尝试锁定已存在的用户记录
        cur.execute("SELECT free_remaining FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
        row = cur.fetchone()

        # 情况一：用户已存在
        if row is not None:
            free_remaining = row[0] or 0
            if free_remaining < amount:
                conn.rollback()
                return (False, free_remaining)

            # 扣减并返回最新余额
            cur.execute("""
                UPDATE users
                SET free_remaining = free_remaining - %s
                WHERE user_id = %s
                RETURNING free_remaining
            """, (amount, user_id))
            new_rem = cur.fetchone()[0]
            conn.commit()
            return (True, new_rem)

        # 情况二：用户不存在（第一次使用）
        free_total = PLANS['Free']['quota']
        if amount > free_total:
            conn.rollback()
            return (False, 0)

        # 首次插入起始额度；并发下若别人已插入则无操作
        cur.execute("""
            INSERT INTO users (user_id, free_remaining)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, free_total))

        # 条件 UPDATE 原子扣减（只有余额足够才成功），并返回最新余额
        cur.execute("""
            UPDATE users
            SET free_remaining = free_remaining - %s
            WHERE user_id = %s AND free_remaining >= %s
            RETURNING free_remaining
        """, (amount, user_id, amount))
        r = cur.fetchone()
        if not r:
            # 可能是并发或余额不足：回滚并读取当前余额返回
            conn.rollback()
            cur.execute("SELECT free_remaining FROM users WHERE user_id=%s", (user_id,))
            row2 = cur.fetchone()
            remain = (row2[0] if row2 else 0)
            return (False, remain)

        conn.commit()
        return (True, r[0])

    except Exception as e:
        logging.error(f"[atomic_deduct_user_free_quota] {e}")
        conn.rollback()
        return (False, 0)

# ===================== Flask 应用 =====================
app = Flask(__name__)   # ← 这一行要放最前面

# ===== CORS：Carrd 页面跨域需要 =====
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "https://saygo-translator.carrd.co"
    resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp

# ===== Carrd 调用：返回 Stripe Checkout 链接 (POST) =====
@app.route("/create-checkout-session", methods=["POST", "OPTIONS"])
def create_checkout_session():
    if request.method == "OPTIONS":
        return ("", 204)  # 预检

    if not stripe.api_key:
        return jsonify({"error": "server missing STRIPE_SECRET_KEY"}), 500

    # 获取请求数据
    data = request.get_json(force=True) or {}
    plan = (data.get("plan") or request.args.get("plan") or "").strip().lower()
    user_id = data.get("line_id") or data.get("user_id")
    group_id = data.get("group_id")

    # ✅ 建立 plan → 环境变量名 映射
    PLAN_TO_PRICE_ENV = {
        "starter": "STRIPE_PRICE_STARTER",
        "basic":   "STRIPE_PRICE_BASIC",
        "pro":     "STRIPE_PRICE_PRO",
        "expert":  "STRIPE_PRICE_EXPERT",
    }

    # ✅ 根据 plan 找对应的 price_id
    price_env = PLAN_TO_PRICE_ENV.get(plan, "")
    price_id = os.getenv(price_env, "")

    if not price_id:
        return jsonify({"error": "Plan not available"}), 400

    if not user_id:
        return jsonify({"error": "missing user_id"}), 400

    try:
        # ✅ 创建 Stripe Checkout Session
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url="https://saygo-translator.carrd.co#success",
            cancel_url="https://saygo-translator.carrd.co#cancel",
            client_reference_id=user_id,
            metadata={
                "line_user_id": user_id,         # ✅ 购买者 LINE user ID
                "origin_group_id": group_id or "",  # ✅ 触发购买的群
                "plan": plan                     # ✅ 购买的套餐名称
            },
            expand=["line_items"],  # ✅ webhook 可以直接取 line_items
        )
        return jsonify({"url": session.url})
    except Exception as e:
        logging.error(f"[Stripe checkout create error] {e}")
        return jsonify({"error": "Stripe error"}), 500

# ===== Carrd 按钮 GET 路由 =====
from flask import redirect
@app.route("/buy", methods=["GET"])
def buy_redirect():
    if not stripe.api_key:
        return "server missing STRIPE_SECRET_KEY", 500

    plan_name = (request.args.get("plan") or "").strip().capitalize()
    user_id   = request.args.get("user_id") or request.args.get("line_id")
    group_id  = request.args.get("group_id")

    if (not plan_name) or (plan_name not in PLANS) or (not user_id):
        return "Missing or invalid params", 400

    price_id = PLANS[plan_name].get("price_id")
    if not price_id:
        return f"Plan {plan_name} missing price_id", 500

    try:
        session = stripe.checkout.Session.create(
            mode="payment", 
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url="https://saygo-translator.carrd.co/#success",
            cancel_url="https://saygo-translator.carrd.co/#cancel",
            client_reference_id=user_id,
            metadata={"plan": plan_name, "group_id": group_id or ""},
        )
        return redirect(session.url, code=302)
    except Exception as e:
        logging.error(f"[Stripe checkout create error] {e}")
        return "Stripe error", 500


# ===== 支付成功 / 取消 回显 =====
@app.route("/success")
def success():
    return "✅ Payment success. You can close this page."

@app.route("/cancel")
def cancel():
    return "❌ Payment canceled. You can close this page."

# ---------------- LINE Webhook ----------------
from psycopg2 import extensions

def _ensure_tx_clean(force_reconnect=False):
    global conn, cur
    try:
        if force_reconnect:
            try:
                DATABASE_URL = os.getenv("DATABASE_URL")
                conn = psycopg2.connect(DATABASE_URL, sslmode="require")
                conn.autocommit = False
                cur = conn.cursor()
                logging.info("[db] force reconnected (per request)")
            except Exception as e:
                logging.error(f"[db-force-reconnect] {e}")

        # 检查数据库连接是否关闭，若关闭则重连
        if conn.closed != 0:
            logging.warning("[db] connection closed, reconnecting...")
            DATABASE_URL = os.getenv("DATABASE_URL")
            conn = psycopg2.connect(DATABASE_URL, sslmode="require")
            conn.autocommit = False
            cur = conn.cursor()
            logging.info("[db] reconnected successfully")

        # 检查是否有事务错误
        if conn.get_transaction_status() == extensions.TRANSACTION_STATUS_INERROR:
            logging.warning("[tx] in error state, auto-rollback.")
            conn.rollback()

    except Exception as e:
        logging.error(f"[tx-check] {e}")
        try:
            DATABASE_URL = os.getenv("DATABASE_URL")
            conn = psycopg2.connect(DATABASE_URL, sslmode="require")
            conn.autocommit = False
            cur = conn.cursor()
            logging.info("[db] reconnected after exception")
        except Exception as e2:
            logging.error(f"[db-reconnect-failed] {e2}")


@app.route("/callback", methods=["POST"])
def line_webhook():
    _ensure_tx_clean(force_reconnect=True)   # ✅ 必须这样

    # 校验签名（验证来自 LINE 官方）
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(cache=False, as_text=True)
    if LINE_CHANNEL_SECRET:
        digest = hmac.new(
            LINE_CHANNEL_SECRET.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256
        ).digest()
        valid_signature = base64.b64encode(digest).decode("utf-8")
        if signature != valid_signature:
            abort(400)

    # 解析 LINE Webhook 数据
    data = json.loads(body) if body else {}
    for event in data.get("events", []):
        etype = event.get("type")
        source = event.get("source", {}) or {}
        user_id = source.get("userId")
        group_id = source.get("groupId") or source.get("roomId")
        reply_token = event.get("replyToken")

        # A0) 初始化免费额度（首次或额度为 0 时自动重置）
        if user_id:
            try:
                cur.execute("""
                    INSERT INTO users (user_id, free_remaining)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET free_remaining = EXCLUDED.free_remaining
                    WHERE users.free_remaining IS NULL OR users.free_remaining = 0
                """, (user_id, PLANS['Free']['quota']))
                conn.commit()
            except Exception as e:
                logging.error(f"[init free quota] failed: {e}")
                conn.rollback()

        # A) 机器人被拉入群时，若未发过语言卡则自动发送
        if etype == "join":
            try:
                if group_id and not has_sent_card(group_id):
                    flex = build_language_selection_flex()
                    send_reply_message(reply_token, [{
                        "type": "flex",
                        "altText": "[Translator Bot] Please select a language / 請選擇語言",
                        "contents": flex
                    }])
                    mark_card_sent(group_id)
                    logging.info(f"[join] card sent to new group {group_id}")

                    # === AUTO-BIND-ON-JOIN ===
                    # ✅ 若用户已购买套餐，则在加入群时自动绑定该群（不自动分配旧群）
                    try:
                        cur.execute(
                            "SELECT plan_type, max_groups, expires_at FROM user_plans WHERE user_id=%s",
                            (user_id,)
                        )
                        up = cur.fetchone()
                        if up:
                            plan_type, max_groups, expires_at = up
                            quota = PLANS[plan_type]["quota"]
                            bind_group_tx(user_id, group_id, plan_type, quota, expires_at)
                            logging.info(f"[auto-bind-on-join] group={group_id} auto-bound for user={user_id}")
                    except Exception as e:
                        logging.error(f"[auto-bind-on-join] failed: {e}")
                        conn.rollback()

                else:
                    logging.info(f"[join] group {group_id} already has card, skip sending")

            except Exception as e:
                logging.error(f"[join] failed for group={group_id}: {e}")
                conn.rollback()
            continue  # join 事件处理完毕后跳过后续逻辑

        # ==================== 成员变化时：只在群未发过卡时发送一次 ====================
        if etype in ("memberJoined", "memberLeft"):
            try:
                if group_id and not has_sent_card(group_id):
                    flex = build_language_selection_flex()
                    send_reply_message(reply_token, [{
                        "type": "flex",
                        "altText": "[Translator Bot] Please select a language / 請選擇語言",
                        "contents": flex
                    }])
                    mark_card_sent(group_id)
                    logging.info(f"[auto-card] sent once to group {group_id} on member event {etype}")
                else:
                    logging.info(f"[auto-card] group {group_id} already has card, skip sending on {etype}")
            except Exception as e:
                logging.error(f"[auto-card] failed for group={group_id}: {e}")
                conn.rollback()
            continue


        # ✅ 修正版：默认只设定英文，不再插入16种语言，彻底防止多语言翻译爆发
        try:
            cur.execute("""
                INSERT INTO user_prefs (user_id, group_id, target_lang)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, group_id, target_lang) DO NOTHING
            """, (user_id, group_id, "en"))
            conn.commit()
            logging.info(f"[default-lang] group={group_id} user={user_id} -> en")
        except Exception as e:
            logging.error(f"[default-lang] failed for group={group_id}: {e}")
            conn.rollback()

       # B) 文本消息
        if etype == "message" and (event.get("message", {}) or {}).get("type") == "text":
            text = (event.get("message", {}) or {}).get("text") or ""

            # B1) 重置
            if is_reset_command(text):
                try:
                    cur.execute("DELETE FROM user_prefs WHERE group_id=%s", (group_id,))
                    conn.commit()
                except Exception as e:
                    logging.error(f"[reset command] {e}")
                    conn.rollback()
                flex = build_language_selection_flex()
                send_reply_message(reply_token, [{
                    "type": "flex",
                    "altText": "[Translator Bot] Please select a language / 請選擇語言",
                    "contents": flex
                }])
                continue

            # B1.5) /unbind 解除群绑定
            if text.strip().lower() == "/unbind" and group_id:
                try:
                    cur.execute("DELETE FROM group_bindings WHERE group_id=%s AND owner_id=%s", (group_id, user_id))
                    cur.execute("DELETE FROM groups WHERE group_id=%s", (group_id,))
                    conn.commit()
                    send_reply_message(reply_token, [{"type":"text","text":"✅ 已解除綁定，本群將使用個人免費額度。"}])
                except Exception as e:
                    conn.rollback()
                    logging.error(f"[unbind] {e}")
                    send_reply_message(reply_token, [{"type":"text","text":"❌ 解除綁定失敗，請稍後再試。"}])
                continue

            # B1.6) /bind 绑定新群
            if text.strip().lower() == "/bind" and group_id:
                try:
                    # 读取用户当前的套餐信息
                    cur.execute("SELECT plan_type, expires_at FROM user_plans WHERE user_id=%s", (user_id,))
                    row = cur.fetchone()
                    if not row:
                        send_reply_message(reply_token, [{"type": "text", "text": "⚠️ 你尚未购买套餐。"}])
                        return "OK"
                        
                    plan_name, expires_at = row
                    quota = PLANS[plan_name]["quota"]

                    # 调用通用绑定函数
                    status = bind_group_tx(user_id, group_id, plan_name, quota, expires_at)

                    if status == "ok":
                        send_reply_message(reply_token, [{"type": "text", "text": f"✅ 已绑定本群 {group_id}（{plan_name}）"}])
                    elif status == "limit":
                        send_reply_message(reply_token, [{"type": "text", "text": f"⚠️ 已达群组上限（{PLANS[plan_name]['max_groups']}）。请在旧群 /unbind 后再试。"}])
                    elif status == "bound_elsewhere":
                        send_reply_message(reply_token, [{"type": "text", "text": f"⚠️ 群 {group_id} 已被其他账号绑定。"}])
                    else:
                        send_reply_message(reply_token, [{"type": "text", "text": "⚠️ 绑定失败，请稍后再试。"}])
                except Exception as e: 
                    logging.error(f"[bind command] {e}")
                    conn.rollback()
                    send_reply_message(reply_token, [{"type": "text", "text": "⚠️ 系统异常，请稍后重试。"}])
                return "OK"
                     
            # B2) 语言按钮逻辑（点按卡片后的绑定）
            LANG_CODES = {"en","zh-cn","zh-tw","ja","ko","th","vi","fr","es","de","id","hi","it","pt","ru","ar"}
            tnorm = text.strip().lower()
            if tnorm in LANG_CODES:
                lang_code = tnorm
                try:
                    # 清除旧的语言设置，只保留当前语言
                    cur.execute("DELETE FROM user_prefs WHERE user_id=%s AND group_id=%s", (user_id, group_id))
                    cur.execute("""
                        INSERT INTO user_prefs (user_id, group_id, target_lang)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, group_id, target_lang) DO NOTHING
                    """, (user_id, group_id, lang_code))
                    conn.commit()
                    logging.info(f"[lang set] user={user_id} group={group_id} -> {lang_code}")
                except Exception as e:
                    logging.error(f"[insert user_prefs] {e}")
                    conn.rollback()
                    
                # 回复确认信息 
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Language set to: {lang_code}"}])
                continue

                logging.info(f"[lang set] user={user_id} group={group_id} lang={lang_code}")

                # 【静默绑定版】
                try:
                    cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=%s", (user_id,))
                    row = cur.fetchone()
                    if row:
                        plan_type, max_groups = row
                        cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=%s", (user_id,))
                        used = cur.fetchone()[0] or 0
                        cur.execute("SELECT owner_id FROM group_bindings WHERE group_id=%s", (group_id,))
                        exists = cur.fetchone()

                        if exists and exists[0] != user_id:
                            send_reply_message(reply_token, [{
                                "type": "text",
                                "text": "⚠️ 该群已绑定在其他账户下，无法重复绑定。"
                            }])
                        elif (not exists) and ((max_groups is None) or (used < max_groups)):
                            cur.execute("INSERT INTO group_bindings (group_id, owner_id) VALUES (%s, %s)", (group_id, user_id))
                            conn.commit()
                        # 其他情况（已绑定在自己名下 / 达上限）静默不提示
                except Exception as e:
                    logging.error(f"[group binding] {e}")
                    conn.rollback()
                except Exception as e:
                    pass
                    
                # 简单确认，只回本次选择的语言代码
                send_reply_message(reply_token, [{"type": "text", "text": f"✅ Your language: {lang_code}"}])
                continue
               

            # B3) 非群聊不翻译
            if not group_id:
                continue

            # ===== B3.5) 授权/名额门禁（修复点）=====
            # 规则：优先看“群是否已有套餐”。有套餐就放行；没有套餐才看“发送者是否名额已满”，满则提示并拦截。
            try:
                # 1) 群级套餐检查
                cur.execute("""
                    SELECT plan_type, plan_owner, plan_remaining, expires_at
                    FROM groups
                    WHERE group_id=%s
                """, (group_id,))
                g = cur.fetchone()
                if not g:
                    # 2) 群没有套餐：检查发送者的可绑定名额
                    cur.execute("SELECT plan_type, max_groups FROM user_plans WHERE user_id=%s", (user_id,))
                    up = cur.fetchone()
                    if up:
                        plan_type, max_groups = up
                        cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=%s", (user_id,))
                        used = (cur.fetchone() or [0])[0] or 0
                        if (max_groups is not None) and (used >= max_groups):
                            buy_url = build_buy_link(user_id, group_id)
                            msg = (
                                f"⚠️ 你的 {plan_type} 套餐最多可綁定 {max_groups} 個群組。\n"
                                f"本群尚未授權，已暫停翻譯。\n\n"
                                f"👉 在已綁定的舊群輸入 /unbind 可釋放名額；\n"
                                f"👉 或升級套餐以增加可綁定群數：\n{buy_url}\n\n"
                                f"⚠️ Your {plan_type} plan allows up to {max_groups} groups.\n"
                                f"This group is not authorized; translation paused.\n"
                                f"Use /unbind in an old group, or upgrade here:\n{buy_url}"
                            )
                            send_reply_message(reply_token, [{"type": "text", "text": msg[:4900]}])
                            continue  # 不翻译，直接提示
            except Exception as e:
                logging.error(f"[bind gate] {e}")
                # 出错时放行，避免意外挡住翻译

            # B4) 收集语言
            cur.execute("SELECT target_lang FROM user_prefs WHERE group_id=%s AND user_id=%s", (group_id, user_id))
            configured = [row[0].lower() for row in cur.fetchall() if row and row[0]]
            configured = list(dict.fromkeys(configured))
            if not configured:
                tip = "請先為【你自己】設定翻譯語言，輸入 /re /reset /resetlang 會出現語言卡片。\nSet your language with /re."
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

            # B6) 扣费 + 中止逻辑
            chars_used = len(text) * max(1, len(translations))
            cur.execute("SELECT plan_type, plan_remaining, plan_owner, expires_at FROM groups WHERE group_id=%s", (group_id,))
            group_plan = cur.fetchone()

            used_paid = False
            if group_plan:
                plan_type, plan_remaining, plan_owner, expires_at = group_plan
                expired = False
                if expires_at:
                    import datetime
                    try:
                        expired = datetime.datetime.utcnow() > datetime.datetime.fromisoformat(expires_at)
                    except Exception as e:
                        logging.warning(f"expires_at parse failed: {e}")

                if not expired:
                    if atomic_deduct_group_quota(group_id, chars_used):
                        used_paid = True

                # 群套餐过期提示（中英）
                if not used_paid and expired:
                    buy_url = build_buy_link(user_id, group_id)
                    msg = (
                        f"⚠️ 群套餐已到期，請重新購買\n"
                        f"⚠️ Group plan expired. Please renew here:\n{buy_url}"
                    )
                    send_reply_message(reply_token, [{"type": "text", "text": msg}])
                    continue

                # 群额度不足提示
                elif not used_paid and plan_remaining is not None and plan_remaining < chars_used:
                    buy_url = build_buy_link(user_id, group_id)
                    msg = (
                        f"⚠️ 本群翻譯額度不足。\n"
                        f"⚠️ Your group quota is not enough. Please purchase more here:\n{buy_url}"
                    )   
                    send_reply_message(reply_token, [{"type": "text", "text": msg}])
                    continue

            # 没有群套餐时，才走个人免费额度
            if not used_paid:
                ok, _remain = atomic_deduct_user_free_quota(user_id, chars_used)
                if not ok:
                    buy_url = build_buy_link(user_id, group_id)
                    msg = f"Your free quota is used up. Please purchase a plan here:\n{buy_url}"
                    send_reply_message(reply_token, [{"type": "text", "text": msg}])
                    continue

            # B7) 发送翻译结果
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

    return "OK"

# ===================== Group Binding Logic (通用群组绑定逻辑) =====================
def bind_group_tx(user_id: str, group_id: str, plan_name: str, quota: int, expires_at):
    """通用群绑定逻辑：用于 webhook 或 /bind 指令"""
    try:
        # 1️⃣ 检查群是否已被他人占用
        cur.execute("SELECT owner_id FROM group_bindings WHERE group_id=%s", (group_id,))
        row = cur.fetchone()
        if row and row[0] and row[0] != user_id:
            return "bound_elsewhere"

        # 2️⃣ 检查用户当前已绑定的群数
        cur.execute("SELECT COUNT(*) FROM group_bindings WHERE owner_id=%s", (user_id,))
        used = cur.fetchone()[0] or 0
        max_groups = PLANS[plan_name]["max_groups"]

        # 超出上限
        if (not row) and (max_groups is not None) and (used >= max_groups):
            return "limit"

        # 3️⃣ 建立绑定（如不存在）
        if not row:
            cur.execute("""
                INSERT INTO group_bindings (group_id, owner_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (group_id, user_id))
            conn.commit()

        # 4️⃣ 同步写入套餐到该群
        cur.execute("""
            INSERT INTO groups (group_id, plan_type, plan_owner, plan_remaining, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (group_id) DO UPDATE
            SET plan_type      = EXCLUDED.plan_type,
                plan_owner     = EXCLUDED.plan_owner,
                plan_remaining = EXCLUDED.plan_remaining,
                expires_at     = EXCLUDED.expires_at
        """, (group_id, plan_name, user_id, quota, expires_at))
        conn.commit()

        return "ok"

    except Exception as e:
        logging.error(f"[bind_group_tx] {e}")
        conn.rollback()
        return "error"

# ===================== Stripe Webhook =====================
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    logging.info("✅ Webhook request received")
    _ensure_tx_clean(force_reconnect=True)

    secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        logging.error("[wh] missing STRIPE_WEBHOOK_SECRET")
        return "Misconfigured", 500

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "") or ""

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=secret
        )
    except stripe.error.SignatureVerificationError as e:
        logging.error(f"[wh] invalid signature: {e}")
        return "Invalid signature", 400
    except Exception as e:
        logging.error(f"[wh] bad payload: {e}")
        return "Bad payload", 400

    try:
        etype = event.get("type")
        obj   = (event.get("data") or {}).get("object") or {}
        logging.info(f"[wh] event type={etype}")

        if etype == "checkout.session.completed":
            session_id = obj.get("id")
            user_id    = obj.get("client_reference_id")
            md         = obj.get("metadata") or {}
            group_id   = (md.get("group_id") or "").strip()
            plan_name  = (md.get("plan") or "").strip().capitalize()

            # 兜底：從 price_id 推斷 plan
            price_id = None
            try:
                li = stripe.checkout.Session.list_line_items(session_id, limit=1)
                if li and li.get("data"):
                    price_id = li["data"][0]["price"]["id"]
            except Exception as e:
                logging.error(f"[wh] fetch line_items failed: {e}")

            if not plan_name:
                plan_name = PRICE_TO_PLAN.get(price_id, "Basic")

            if not user_id or not plan_name or plan_name not in PLANS:
                logging.warning(f"[wh] invalid webhook payload user={user_id} plan={plan_name}")
                return "Invalid data", 400

            max_groups = PLANS[plan_name]["max_groups"]
            quota      = PLANS[plan_name]["quota"]
            import datetime
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)

            # ✅ 1. 更新 user_plans
            try:
                cur.execute("""
                    INSERT INTO user_plans (user_id, plan_type, max_groups, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET plan_type = EXCLUDED.plan_type,
                        max_groups = EXCLUDED.max_groups,
                        expires_at = EXCLUDED.expires_at
                """, (user_id, plan_name, max_groups, expires_at))
                conn.commit()
            except Exception as e:
                logging.error(f"[wh] user_plans upsert failed: {e}")
                conn.rollback()
                return "DB error", 400

            # ✅ 2. 綁定購買所在的群（如果有 group_id）
            if group_id:
                try:
                    bind_group_tx(user_id, group_id, plan_name, quota, expires_at)
                    cur.execute("""
                        INSERT INTO group_settings (group_id, authorized, card_sent)
                        VALUES (%s, TRUE, FALSE)
                        ON CONFLICT (group_id) DO UPDATE
                        SET authorized = TRUE, card_sent = FALSE
                    """, (group_id,))
                    conn.commit()
                    logging.info(f"[wh] group {group_id} authorized")
                except Exception as e:
                    logging.error(f"[wh] group bind failed: {e}")
                    conn.rollback()

            # ✅ 3. 發送通知
            send_push_text(
                user_id,
                f"✅ {plan_name} 套餐已啟用，最多可綁定 {max_groups} 個群組。\n"
                f"購買的群已立即啟用，其餘名額將在新群首次使用時自動生效。"
            )

        logging.info("✅ Webhook logic executed successfully")
        return "OK", 200

    except Exception as e:
        logging.error(f"[wh] unexpected error: {e}")
        return "Webhook internal error", 400


# ---------------- 启动服务 ----------------
if __name__ == "__main__":
    init_db()  # ✅ 首次执行时建表
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=False)

