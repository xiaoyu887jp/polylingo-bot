from flask import Flask, request, jsonify
import requests

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

@app.route('/', methods=['POST'])  # 👈 加上 POST 方法
def webhook():
    return 'OK', 200  # ✅ 一定要回傳 200 給 LINE

@app.route('/translate')
def do_translation():
    result = translate("Hello", "ja")
    return result

if __name__ == '__main__':
    app.run()
