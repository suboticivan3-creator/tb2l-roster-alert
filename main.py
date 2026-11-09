
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
SEASON = 2027

LEAGUES = {
    "tbl": {"name": "TBL", "competition": "tbl"},
    "tb2l": {"name": "TB2L", "competition": "tbl"},
    "tkbl": {"name": "TKBL", "competition": "kbsl"}
}

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))

def send_message(chat_id, message):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    req = urllib.request.Request(TG_URL + "sendMessage", data=data)
    urllib.request.urlopen(req, timeout=20)

def get_value(obj, *names):
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return None

def walk_objects(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_objects(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_objects(item)

def get_league_id(short_name):
    url = TBF_URL + "League/get-leagues-for-filter?" + urllib.parse.urlencode({
        "season": SEASON
    })

    result = get_json(url)

    if not result.get("isSuccess", False):
        raise Exception("TBF nije vratio spisak liga.")

    for item in walk_objects(result.get("data", [])):
        display = get_value(item, "displayName", "display_name")
        activity = get_value(item, "activityId", "activity_id")

        if display == short_name and activity is not None:
            return int(float(activity))

    raise Exception("Nije pronađena liga " + short_name)

def get_matches(short_name):
    league = LEAGUES[short_name]
    activity_id = get_league_id(league["name"])

    params = urllib.parse.urlencode({
        "season": SEASON,
        "competition": league["competition"]
    })

    url = TBF_URL + "Match/get-all-matches-for-filter?" + params
    result = get_json(url)

    if not result.get("isSuccess", False):
        raise Exception("TBF greška pri učitavanju rasporeda.")

    matches = []

    for item in walk_objects(result.get("data", [])):
        match_id = get_value(item, "matchId", "match_id")
        match_activity = get_value(item, "activityId", "activity_id")

        if match_id is None or match_activity is None:
            continue

        if int(float(match_activity)) != activity_id:
            continue

        home = get_value(item, "homeTeam", "home_team")
        away = get_value(item, "awayTeam", "away_team")

        if not home or not away:
            continue

        date = get_value(item, "matchDate", "match_date")
        tipoff = get_value(item, "tipoff", "tipOff", "matchTime")

        matches.append({
            "home": str(home),
            "away": str(away),
            "date": str(date or tipoff or "Datum nije objavljen"),
            "home_score": get_value(item, "homeScore", "home_score"),
            "away_score": get_value(item, "awayScore", "away_score"),
            "status": get_value(item, "status", "matchStatus")
        })

    return matches

def show_league(chat_id, short_name, today_only=False):
    league_name = LEAGUES[short_name]["name"]

    try:
        matches = get_matches(short_name)

        if not matches:
            send_message(
                chat_id,
                league_name + "\nTBF nije vratio utakmice za ovu ligu."
            )
            return

        now = datetime.now(ZoneInfo("Europe/Istanbul"))
        today = now.strftime("%Y-%m-%d")

        if today_only:
            matches = [
                m for m in matches
                if m["date"][:10] == today
            ]
        else:
            matches.sort(key=lambda m: m["date"])
            matches = [
                m for m in matches
                if m["date"][:10] >= today
            ][:15]

        if not matches:
            send_message(chat_id, league_name + "\nNema utakmica za traženi period.")
            return

        lines = [league_name + " — TBF", ""]

        for match in matches:
            lines.append(match["home"] + " — " + match["away"])
            lines.append("Termin: " + match["date"])

            hs = match["home_score"]
            aws = match["away_score"]

            if hs is not None and aws is not None:
                lines.append("Rezultat: " + str(hs) + ":" + str(aws))

            lines.append("")

        send_message(chat_id, "\n".join(lines))

    except Exception as error:
        print("TBF ERROR:", error)
        send_message(
            chat_id,
            league_name + "\nGreška pri čitanju TBF rasporeda. "
            "Detalji su zabeleženi u Railway logu."
        )

def handle_update(update):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    command = message.get("text", "").strip().lower()

    if not chat_id:
        return

    if command == "/start":
        send_message(
            chat_id,
            "TBF BASKETBALL BOT\n\n"
            "/tbl - TBL\n"
            "/tb2l - TB2L\n"
            "/tkbl - Ženska TKBL\n"
            "/today - Današnje utakmice svih liga\n"
            "/id - Tvoj Chat ID"
        )

    elif command == "/id":
        send_message(chat_id, "Tvoj Chat ID je: " + str(chat_id))

    elif command == "/tbl":
        show_league(chat_id, "tbl")

    elif command == "/tb2l":
        show_league(chat_id, "tb2l")

    elif command == "/tkbl":
        show_league(chat_id, "tkbl")

    elif command == "/today":
        for name in ("tbl", "tb2l", "tkbl"):
            show_league(chat_id, name, today_only=True)
            time.sleep(1)

offset = 0
print("TBF BOT STARTED")

while True:
    try:
        url = TG_URL + "getUpdates?" + urllib.parse.urlencode({
            "offset": offset,
            "timeout": 25
        })

        response = get_json(url)

        for update in response.get("result", []):
            offset = update["update_id"] + 1
            handle_update(update)

    except Exception as error:
        print("BOT ERROR:", error)
        time.sleep(5)
