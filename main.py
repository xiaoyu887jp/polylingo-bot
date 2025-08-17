# -*- coding: utf-8 -*-
import os, json, time, sqlite3, hmac, hashlib, base64, html
import requests
from flask import Flask, request, jsonify, abort
from concurrent.futures import ThreadPoolExecutor

# ===================== 全局会话：长连接/连接池 =====================
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
from requests.adapters import HTTPAdapter
HTTP.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20))
HTTP.mount("http://",  HTTPAdapter(pool_connections=10, pool_maxsize=10))

# ===================== 环境变量 =====================
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "<LINE_ACCESS_TOKEN>"
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET") or "<LINE_CHANNEL_SECRET>"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # 如使用官方 API，可切换 translate_official()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "<STRIPE_WEBHOOK_SECRET>")

# 机器人兜底头像
BOT_AVATAR_FALLBACK = "https://i.imgur.com/sTqykvy.png"

# ===================== Flask & DB =====================
app = Flask(__name__)
DATABASE = '/var/data/data.db'

def db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ===================== 语言卡片（保留你的样式） =====================
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

# ===================== LINE 基础 I/O（全部走 HTTP，会更快） =====================
def reply_to_line(reply_token, messages):
    HTTP.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
                 "Content-Type": "application/json"},
        data=json.dumps({"replyToken": reply_token, "messages": messages}),
        timeout=8
    )

def send_language_selection_card(reply_token):
    reply_to_line(reply_token, [{
        "type":"flex",
        "altText":"Please select translation language",
        "contents": flex_message_json
    }])

# ===================== 头像/好友关系（带 1 小时缓存） =====================
_friend_cache = {}  # user_id -> (flag, expires_ts)

def is_friend(user_id: str):
    now = time.time()
    cached = _friend_cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]
    try:
        r = HTTP.get(
            f"https://api.line.me/v2/bot/friendship/status?userId={user_id}",
            headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"},
            timeout=5
        )
        if r.status_code == 200:
            flag = bool(r.json().get("friendFlag"))
            _friend_cache[user_id] = (flag, now + 3600)  # 缓存 1h
            return flag
    except Exception:
        pass
    _friend_cache[user_id] = (None, now + 300)  # 失败也短暂缓存
    return None

def get_user_avatar(user_id: str):
    # 只有在已加好友时才取用户头像；否则用机器人头像
    flag = is_friend(user_id)
    if flag is True:
        try:
            r = HTTP.get(
                f"https://api.line.me/v2/bot/profile/{user_id}",
                headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"},
                timeout=5
            )
            if r.status_code == 200:
                return r.json().get("pictureUrl") or BOT_AVATAR_FALLBACK
        except Exception:
            return BOT_AVATAR_FALLBACK
    return BOT_AVATAR_FALLBACK

# ===================== 额度相关（沿用你现有逻辑） =====================
# group_quota: group_id, quota
def update_group_quota(group_id, text_length):
    conn = db(); cur = conn.cursor()
    cur.execute('SELECT quota FROM group_quota WHERE group_id=?', (group_id,))
    row = cur.fetchone()
    if row:
        new_quota = max((row[0] or 0) - text_length, 0)
        cur.execute('UPDATE group_quota SET quota=? WHERE group_id=?', (new_quota, group_id))
    else:
        new_quota = max(5000 - text_length, 0)  # 首次默认 5000（你的旧逻辑）
        cur.execute('INSERT INTO group_quota (group_id, quota) VALUES (?, ?)', (group_id, new_quota))
    conn.commit(); conn.close()
    return new_quota

def update_group_quota_to_amount(group_id, quota_amount):
    conn = db(); cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO group_quota (group_id, quota) VALUES (?, ?)', (group_id, quota_amount))
    conn.commit(); conn.close()

def update_usage(group_id, user_id, text_length):
    conn = db(); cur = conn.cursor()
    current_month = time.strftime("%Y-%m")
    cur.execute('SELECT usage FROM usage_records WHERE group_id=? AND user_id=? AND month=?',
                (group_id, user_id, current_month))
    row = cur.fetchone()
    if row:
        cur.execute('UPDATE usage_records SET usage=? WHERE group_id=? AND user_id=? AND month=?',
                    ((row[0] or 0) + text_length, group_id, user_id, current_month))
    else:
        cur.execute('INSERT INTO usage_records (group_id, user_id, month, usage) VALUES (?,?,?,?)',
                    (group_id, user_id, current_month, text_length))
    conn.commit(); conn.close()

def check_user_quota(user_id, text_length):
    conn = db(); cur = conn.cursor()
    cur.execute('SELECT quota, is_paid FROM user_quota WHERE user_id=?', (user_id,))
    row = cur.fetchone()
    if row:
        current_quota, is_paid = row[0] or 0, row[1] or 0
        if is_paid:
            conn.close(); return True
        if current_quota <= 0:
            conn.close(); return False
        if current_quota >= text_length:
            cur.execute('UPDATE user_quota SET quota = quota - ? WHERE user_id=?', (text_length, user_id))
            conn.commit(); conn.close(); return True
        conn.close(); return False
    else:
        initial_quota = 5000 - text_length
        cur.execute('INSERT INTO user_quota (user_id, quota, is_paid) VALUES (?,?,0)', (user_id, initial_quota))
        conn.commit(); conn.close()
        return initial_quota >= 0

# ===================== 翻译：gtx 快速端点 + 并发 =====================
translation_cache = {}  # (text, sl, tl) -> translated_text

def translate_gtx(text, target_lang, source_lang=None):
    cache_key = (text, source_lang or 'auto', target_lang)
    if cache_key in translation_cache:
        return translation_cache[cache_key], (source_lang or 'auto')
    sl = source_lang if source_lang else 'auto'
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t"
           f"&sl={sl}&tl={target_lang}&q=" + requests.utils.requote_uri(text))
    try:
        resp = HTTP.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        segs = [seg[0] for seg in data[0] if seg[0]]
        translated_text = "".join(segs)
        detected_src = source_lang or (data[2] if len(data) > 2 else '')
        translated_text = html.unescape(translated_text)
        translation_cache[cache_key] = translated_text
        return translated_text, detected_src
    except Exception:
        return None

LANGUAGES = {"en","ja","zh-tw","zh-cn","th","vi","fr","es","de","id","hi","it","pt","ru","ar","ko"}
RESET_ALIASES = {"/re", "/reset", "/resetlang"}

# 内存选择：key= f"{group_id}_{user_id}" -> [langs]
user_language_settings = {}

# ===================== LINE 回调 =====================
@app.route("/callback", methods=["POST"])
def callback():
    # 验签
    signature = request.headers.get("X-Line-Signature", "")
    body_text = request.get_data(as_text=True)
    if LINE_CHANNEL_SECRET:
        digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"),
                          body_text.encode("utf-8"),
                          hashlib.sha256).digest()
        valid = base64.b64encode(digest).decode("utf-8")
        if signature != valid:
            abort(400)

    data = json.loads(body_text) if body_text else {}
    for event in data.get("events", []):
        etype = event.get("type")
        source = event.get("source", {}) or {}
        group_id = source.get("groupId", "private")
        user_id = source.get("userId", "unknown")
        reply_token = event.get("replyToken")
        if not reply_token:
            continue

        # 进群即发卡
        if etype == "join":
            send_language_selection_card(reply_token)
            continue

        # 退群清理（保持你的旧逻辑）
        if etype == "leave":
            conn = db(); cur = conn.cursor()
            cur.execute('DELETE FROM group_settings WHERE group_id=?', (group_id,))
            conn.commit(); conn.close()
            continue

        # 文本消息
        if etype == "message" and (event.get("message", {}) or {}).get("type") == "text":
            user_text = (event["message"]["text"] or "").strip()
            key = f"{group_id}_{user_id}"

            # 重置 → 发卡
            if user_text.lower() in RESET_ALIASES:
                user_language_settings[key] = []
                conn = db(); cur = conn.cursor()
                cur.execute('DELETE FROM group_settings WHERE group_id=?', (group_id,))
                conn.commit(); conn.close()
                send_language_selection_card(reply_token)
                continue

            # 额度先判：个人 5000（按你旧逻辑“先个人后群池”或相反，这里沿用你之前写法：先个人）
            if not check_user_quota(user_id, len(user_text)):
                quota_message = (
                    f"⚠️ Your free quota has been exhausted. Subscribe here:\n"
                    f"https://saygo-translator.carrd.co?line_id={user_id}&group_id={group_id}"
                )
                reply_to_line(reply_token, [{"type":"text","text":quota_message}])
                continue

            # 语言选择（message 型按钮）
            low = user_text.lower()
            if low in LANGUAGES:
                langs = user_language_settings.setdefault(key, [])
                if low not in langs:
                    langs.append(low)
                reply_to_line(reply_token, [{"type":"text","text":f"✅ Your languages: {', '.join(langs)}"}])
                continue

            # 未设语言 → 发卡
            langs = user_language_settings.get(key, [])
            if not langs:
                send_language_selection_card(reply_token)
                continue

            # ==== 翻译：先译第一个确定 detected_src，然后并发其它 ====
            translations = []
            first_lang = langs[0]
            r = translate_gtx(user_text, first_lang)
            if not r:
                reply_to_line(reply_token, [{"type":"text","text":"翻譯服務繁忙，請稍後重試 / Translation is busy, please retry."}])
                continue
            first_txt, detected_src = r
            translations.append((first_lang, first_txt))

            others = langs[1:]
            if others:
                with ThreadPoolExecutor(max_workers=min(4, len(others))) as pool:
                    futs = {tl: pool.submit(translate_gtx, user_text, tl, detected_src) for tl in others}
                    for tl in others:
                        rr = futs[tl].result()
                        if rr:
                            translations.append((tl, rr[0]))

            # 群池扣减（沿用你旧逻辑：这里你原来是 update_group_quota；保留）
            chars_used = len(user_text)
            new_quota = update_group_quota(group_id, chars_used)

            messages = []
            if new_quota <= 0:
                quota_message = (
                    f"⚠️ Your free quota is exhausted. Please subscribe here:\n"
                    f"https://saygo-translator.carrd.co?line_id={user_id}\n\n"
                    f"⚠️ 您的免费额度已用完，请点击这里订阅：\n"
                    f"https://saygo-translator.carrd.co?line_id={user_id}"
                )
                messages.append({"type":"text","text":quota_message})
            else:
                # 头像规则：加好友→用户头像；否则→机器人头像
                icon = get_user_avatar(user_id)
                for lang in langs:
                    # 找到对应翻译文本
                    txt = next((t for (lc, t) in translations if lc == lang), None)
                    if txt is None:  # 安全兜底
                        rr = translate_gtx(user_text, lang, detected_src)
                        txt = rr[0] if rr else "Translation error."
                    messages.append({
                        "type":"text",
                        "text": txt,
                        "sender": {"name": f"Saygo ({lang})", "iconUrl": icon}
                    })
                update_usage(group_id, user_id, len(user_text))

            # 一次性回发（最多 5 条，避免超限）
            reply_to_line(reply_token, messages[:5])

    return jsonify(success=True), 200

# ===================== Stripe Webhook（保留你原逻辑） =====================
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    data = request.get_json(silent=True) or {}
    event_type = data.get('type')
    if not event_type:
        return jsonify(ok=False), 400

    # 简单签名校验（可按需加强）
    sig = request.headers.get("Stripe-Signature","")
    if STRIPE_WEBHOOK_SECRET and not sig:
        return jsonify(ok=False), 400

    if event_type == 'checkout.session.completed':
        obj = (data.get('data') or {}).get('object') or {}
        metadata = obj.get('metadata') or {}
        group_id = metadata.get('group_id')
        line_id = metadata.get('line_id')
        plan = metadata.get('plan', 'Unknown')

        quota_mapping = {
            'Starter': 300000,
            'Basic': 1000000,
            'Pro': 2000000,
            'Expert': 4000000
        }
        quota_amount = quota_mapping.get(plan, 0)
        if group_id and quota_amount:
            update_group_quota_to_amount(group_id, quota_amount)

        message = f"🎉 Subscription successful! Plan: {plan}, quota updated to: {quota_amount} characters. Thanks for subscribing!"
        try:
            # 直接用 v2 push（更轻量）
            to_id = line_id or group_id
            if to_id:
                HTTP.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
                             "Content-Type":"application/json"},
                    data=json.dumps({"to": to_id, "messages":[{"type":"text","text":message}]}),
                    timeout=8
                )
        except Exception:
            pass

    return jsonify(success=True), 200

# ===================== 启动 =====================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
