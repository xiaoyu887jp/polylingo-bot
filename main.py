# 假设你已获取原始消息 text
# 并完成了 Google Translate 的两次翻译（zh → th, zh → en）

translated_th = translator.translate(text, dest='th').text
translated_en = translator.translate(text, dest='en').text

# 按你新要求组合格式：原文 → 空行 → 泰文 → 英文（并用简写标签）
formatted_reply = f"{text}\n\n[TH] {translated_th}\n[EN] {translated_en}"

line_bot_api.reply_message(
    event.reply_token,
    TextSendMessage(text=formatted_reply)
)
