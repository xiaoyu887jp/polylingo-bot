from flask import Flask, request
import requests
import os

app = Flask(__name__)

def translate(text, target_lang):
    url = "https://libretranslate.de/translate"
    payload = {
        "q": text,
        "source": "auto",
        "target": target_lang,
        "format": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json().get("translatedText", "Translation failed")
    except Exception as e:
        return f"Error: {e}"

@app.route('/callback', methods=['POST'])
def webhook():
    print("✅ 收到 LINE POST 请求")
    return 'OK', 200

@app.route('/')
def index():
    return "🚀 Polylingo bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # ✅ 允许 Render 自动设定端口
    app.run(host='0.0.0.0', port=port)
