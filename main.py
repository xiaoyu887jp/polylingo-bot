import requests

def translate(text, target_lang):
    url = "https://translate.argosopentech.com/translate"
    payload = {
        "q": text,
        "source": "auto",
        "target": target_lang,
        "format": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()["translatedText"]

# 示例调用
print(translate("Hello", "ja"))
