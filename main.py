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

@app.route('/callback', methods=['POST'])  # ✅ 这是 LINE 要访问的 webhook 路径
def webhook():
    return 'OK', 200  # ✅ 一定要返回 200，否则 LINE 会报错

@app.route('/translate')  # 备用测试接口
def do_translation():
    result = translate("Hello", "ja")
    return result

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)  # ✅ 必须开放 0.0.0.0 的端口，Render 才能侦测到服务
