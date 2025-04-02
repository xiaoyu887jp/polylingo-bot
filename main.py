from flask import Flask, request
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

@app.route('/callback', methods=['POST'])  # LINE 用这个路径来 POST
def webhook():
    return 'OK', 200  # 一定要返回 200，LINE 才会判定成功

@app.route('/translate')  # 测试用，不给 LINE 用
def do_translation():
    result = translate("Hello", "ja")
    return result

if __name__ == '__main__':
    print("✅ Flask server is starting...")
    app.run(host='0.0.0.0', port=10000)  # 一定是 0.0.0.0，不是 localhost
