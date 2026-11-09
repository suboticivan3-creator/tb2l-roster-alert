import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["BOT_TOKEN"]
TG_URL = f"https://api.telegram.org/bot{TOKEN}/"
TBF_URL = "https://miniappapi.tbf.org.tr/webapi-service/api/"

def send_message(chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text
    }).encode()

    req = urllib.request.Request(TG_URL + "sendMessage", data=data)
    urllib.request.urlopen(req, timeout=20)

def get_tbf_games(competition):
    today = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")

    params = urllib.parse.urlencode({
        "match_date": today,
        "season": 2027,
        "competition": competition
    })

    req = urllib.request.Request(
        TBF_URL + "Match/get-daily-matches?" + params,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("isSuccess", False):
        raise Exception(str(result.get("message", "TBF greška")))

    games = []

    def find_games(obj):
        if isinstance(obj, dict):
            if "match_id" in obj and "home_team" in obj and "away_team" in obj:
                games.append(obj)
            else:
                for value in obj.values():
                    find_games(value)
        elif isinstance(obj, list):
            for item in obj:
                find_games(item)

    find_games(result.get("data", []))
    return games

def show_games(chat_id, competition, title):
    try:
        games = get_tbf_games(competition)

        if not games:
            send_message(chat_id, f"{title}\nNema utakmica za danas.")
            return

        lines = [f"{title} — TBF", ""]

        for game in games:
            home = game.get("home_team", "?")
            away = game.get("away_team", "?")
            tipoff = game.get("tipoff", "")
            home_score = game.get("home_score")
            away_score = game.get("away_score")

            if home_score not in (None, "") and away_score not in (None, ""):
                score = f"{home_score}:{away_score}"
            else:
                score = "Još nije počelo"

            if tipoff:
                tipoff = tipoff.replace("T", " ")[:16]

            lines.append(f"{home} — {away}")
            lines.append(f"Vreme: {tipoff or 'Nije objavljeno'}")
            lines.append(f"Rezultat: {score}")
            lines.append("")

        send_message(chat_id, "\n".join(lines))

    except Exception as e:
        print("TBF ERROR:", e)
        send_message(chat_id, "Greška pri čitanju TBF podataka. Pokušaj ponovo.")

offset = 0

print("TBF BASKETBALL BOT STARTED")

while True:
    try:
        url = TG_URL + "getUpdates?" + urllib.parse.urlencode({
            "offset": offset,
            "timeout": 25
        })

        with urllib.request.urlopen(url, timeout=35) as response:
            updates = json.loads(response.read())

        for update in updates.get("result", []):
            offset = update["update_id"] + 1

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip().lower()

            if not chat_id:
                continue

            if text == "/start":
                send_message(
                    chat_id,
                    "TBF BASKETBALL ALERT\n\n"
                    "Bot je aktivan!\n\n"
                    "/tbl - TBL utakmice\n"
                    "/tb2l - TB2L utakmice\n"
                    "/today - sve utakmice\n"
                    "/id - tvoj Chat ID"
                )

            elif text == "/id":
                send_message(chat_id, f"Tvoj Chat ID je: {chat_id}")

            elif text == "/tbl":
                show_games(chat_id, "bsl", "TBL")

            elif text == "/tb2l":
                show_games(chat_id, "tbl", "TB2L")

            elif text == "/today":
                show_games(chat_id, "bsl", "TBL")
                time.sleep(1)
                show_games(chat_id, "tbl", "TB2L")

    except Exception as e:
        print("BOT ERROR:", e)
        time.sleep(5)
