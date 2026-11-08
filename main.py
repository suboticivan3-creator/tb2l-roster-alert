import os
import json
import time
import urllib.request
import urllib.parse

TOKEN = os.environ["BOT_TOKEN"]

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

def send_message(chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text
    }).encode()

    req = urllib.request.Request(
        BASE_URL + "sendMessage",
        data=data
    )

    urllib.request.urlopen(req)

offset = 0

print("TB2L BOT STARTED")

while True:
    try:
        url = BASE_URL + "getUpdates?offset=" + str(offset)
        response = urllib.request.urlopen(url)
        updates = json.loads(response.read())

        for update in updates["result"]:
            offset = update["update_id"] + 1

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")

            if text == "/start":
                send_message(
                    chat_id,
                    "TB2L ROSTER ALERT\nBot je aktivan!"
                )

            elif text == "/id":
                send_message(
                    chat_id,
                    f"Tvoj Chat ID je: {chat_id}"
                )

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
