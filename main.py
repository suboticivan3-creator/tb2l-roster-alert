
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
    "tbl": {
        "name": "TBL",
        "competition": "bsl"
    },
    "tb2l": {
        "name": "TB2L",
        "competition": "tbl"
    },
    "tkbl": {
        "name": "TKBL",
        "competition": "kbsl"
    }
}

def get_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def send_message(chat_id, message):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    request = urllib.request.Request(
        TG_URL + "sendMessage",
        data=data
    )

    urllib.request.urlopen(request, timeout=20)

def normalize(value):
    return "".join(
        c.lower() for c in str(value)
        if c.isalnum()
    )

def get_field(obj, *names):
    if not isinstance(obj, dict):
        return None

    normalized = {
        normalize(key): value
        for key, value in obj.items()
    }

    for name in names:
        value = normalized.get(normalize(name))
        if value is not None and value != "":
            return value

    return None

def find_records(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from find_records(value)

    elif isinstance(obj, list):
        for item in obj:
            yield from find_records(item)

def check_response(result):
    if not isinstance(result, dict):
        raise Exception("TBF je vratio neispravan odgovor.")

    if result.get("isSuccess") is False:
        raise Exception(
            str(result.get("message", "TBF API greška"))
        )

    return result.get("data", [])

def get_league_id(short_name):
    url = TBF_URL + "League/get-leagues-for-filter?" + \
        urllib.parse.urlencode({"season": SEASON})

    result = get_json(url)
    data = check_response(result)

    for item in find_records(data):
        display_name = get_field(
            item, "displayName", "display_name"
        )

        activity_id = get_field(
            item, "activityId", "activity_id"
        )

        if (
            display_name
            and str(display_name).upper() == short_name
            and activity_id is not None
        ):
            return int(float(activity_id))

    raise Exception(
        "TBF nije pronašao ligu " + short_name
    )

def get_matches(short_name):
    league = LEAGUES[short_name]

    activity_id = get_league_id(league["name"])

    params = urllib.parse.urlencode({
        "season": SEASON,
        "competition": league["competition"]
    })

    url = (
        TBF_URL
        + "Match/get-all-matches-for-filter?"
        + params
    )

    result = get_json(url)
    data = check_response(result)

    matches = []

    for item in find_records(data):
        match_id = get_field(
            item, "matchId", "match_id"
        )

        match_activity = get_field(
            item,
            "activityId",
            "activity_id",
            "faaliyetAltAlaniId"
        )

        if match_id is None:
            continue

        if match_activity is None:
            continue

        if int(float(match_activity)) != activity_id:
            continue

        home = get_field(
            item, "homeTeam", "home_team"
        )

        away = get_field(
            item, "awayTeam", "away_team"
        )

        if not home or not away:
            continue

        date = get_field(
            item, "tipoff", "matchDate", "match_date"
        )

        home_score = get_field(
            item, "homeScore", "home_score"
        )

        away_score = get_field(
            item, "awayScore", "away_score"
        )

        matches.append({
            "home": str(home),
            "away": str(away),
            "date": str(date or "Termin nije objavljen"),
            "home_score": home_score,
            "away_score": away_score
        })

    return matches

def show_league(chat_id, short_name, today_only=False):
    league_name = LEAGUES[short_name]["name"]

    try:
        matches = get_matches(short_name)

        if not matches:
            send_message(
                chat_id,
                league_name
                + "\nTBF nije vratio utakmice za ovu ligu."
            )
            return

        now = datetime.now(ZoneInfo("Europe/Istanbul"))
        today = now.strftime("%Y-%m-%d")

        if today_only:
            matches = [
                match for match in matches
                if match["date"][:10] == today
            ]
        else:
            matches.sort(key=lambda match: match["date"])

        if not matches:
            send_message(
                chat_id,
                league_name + "\nNema utakmica za danas."
                if today_only
                else league_name + "\nNema utakmica u rasporedu."
            )
            return

        lines = [league_name + " — ZVANIČNI TBF", ""]

        for match in matches[:20]:
            lines.append(
                match["home"] + " — " + match["away"]
            )

            lines.append("Termin: " + match["date"])

            hs = match["home_score"]
            aws = match["away_score"]

            if hs is not None and aws is not None:
                lines.append(
                    "Rezultat: " + str(hs) + ":" + str(aws)
                )

            lines.append("")

        send_message(chat_id, "\n".join(lines))

    except Exception as error:
    print("TBF ERROR:", repr(error))
    send_message(
        chat_id,
        league_name + " GREŠKA:\n" + str(error)[:3000]
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
            "/today - Današnje utakmice\n"
            "/id - Tvoj Chat ID"
        )

    elif command == "/id":
        send_message(
            chat_id,
            "Tvoj Chat ID je: " + str(chat_id)
        )

    elif command == "/tbl":
        show_league(chat_id, "tbl")

    elif command == "/tb2l":
        show_league(chat_id, "tb2l")

    elif command == "/tkbl":
        show_league(chat_id, "tkbl")

    elif command == "/today":
        for league in ("tbl", "tb2l", "tkbl"):
            show_league(chat_id, league, True)
            time.sleep(1)

offset = 0

print("TBF THREE LEAGUE BOT STARTED")

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
        print("BOT ERROR:", repr(error))
        time.sleep(5)
