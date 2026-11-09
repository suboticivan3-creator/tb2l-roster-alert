
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
        "competition": "bsl",
        "activity_id": 22215
    },
    "tb2l": {
        "name": "TB2L",
        "competition": "tbl",
        "activity_id": 22223
    },
    "tkbl": {
        "name": "TKBL",
        "competition": "kbsl",
        "activity_id": 22210
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

    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def normalize(value):
    return "".join(
        character.lower()
        for character in str(value)
        if character.isalnum()
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


def get_matches(short_name):
    league = LEAGUES[short_name]

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
            item,
            "matchId",
            "match_id"
        )

        activity_id = get_field(
            item,
            "activityId",
            "activity_id"
        )

        if match_id is None or activity_id is None:
            continue

        try:
            if int(float(activity_id)) != league["activity_id"]:
                continue
        except (TypeError, ValueError):
            continue

        home = get_field(
            item,
            "homeTeam",
            "home_team",
            "homeTeamName",
            "home_team_name"
        )

        away = get_field(
            item,
            "awayTeam",
            "away_team",
            "awayTeamName",
            "away_team_name"
        )

        if not home or not away:
            continue

        match_date = get_field(
            item,
            "matchDate",
            "match_date",
            "tipoff",
            "matchTime"
        )

        home_score = get_field(
            item,
            "homeScore",
            "home_score"
        )

        away_score = get_field(
            item,
            "awayScore",
            "away_score"
        )

        matches.append({
            "home": str(home),
            "away": str(away),
            "date": str(
                match_date or "Termin nije objavljen"
            ),
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

        today = datetime.now(
            ZoneInfo("Europe/Istanbul")
        ).strftime("%Y-%m-%d")

        if today_only:
            matches = [
                match for match in matches
                if match["date"][:10] == today
            ]
        else:
            matches.sort(
                key=lambda match: match["date"]
            )

        if not matches:
            send_message(
                chat_id,
                league_name + "\nNema utakmica za danas."
                if today_only
                else league_name + "\nNema utakmica u rasporedu."
            )
            return

        lines = [
            league_name + " — ZVANIČNI TBF",
            ""
        ]

        for match in matches[:20]:
            lines.append(
                match["home"] + " — " + match["away"]
            )

            lines.append(
                "Termin: " + match["date"]
            )

            home_score = match["home_score"]
            away_score = match["away_score"]

            if home_score is not None and away_score is not None:
                lines.append(
                    "Rezultat: "
                    + str(home_score)
                    + ":"
                    + str(away_score)
                )

            lines.append("")

        send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception as error:
        print("TBF ERROR:", repr(error))

        try:
            send_message(
                chat_id,
                league_name
                + " GREŠKA:\n"
                + str(error)[:2500]
            )
        except Exception as telegram_error:
            print("TELEGRAM ERROR:", repr(telegram_error))


def handle_update(update):
    message = update.get("message", {})

    chat_id = message.get(
        "chat", {}
    ).get("id")

    command = message.get(
        "text", ""
    ).strip().lower()

    if not chat_id:
        return

    if command == "/start":
        send_message(
            chat_id,
            "TBF BASKETBALL BOT\n\n"
            "/tbl - TBL\n"
            "/tb2l - TB2L\n"
            "/tkbl - Zenska TKBL\n"
            "/today - Danasnje utakmice svih liga\n"
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
            show_league(
                chat_id,
                league,
                today_only=True
            )
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
