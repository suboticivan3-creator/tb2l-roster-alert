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
        "competition": "tbl",
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
        c.lower() for c in str(value)
        if c.isalnum()
    )


def get_field(obj, *names):
    if not isinstance(obj, dict):
        return None

    fields = {
        normalize(k): v
        for k, v in obj.items()
    }

    for name in names:
        value = fields.get(normalize(name))

        if value is not None and value != "":
            return value

    return None


def find_records(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from find_records(item)

    elif isinstance(obj, dict):
        yield obj

        for value in obj.values():
            yield from find_records(value)


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

    if not isinstance(result, dict):
        raise Exception("Neispravan odgovor TBF API-ja.")

    if result.get("isSuccess") is False:
        raise Exception(
            result.get("message", "TBF API greška")
        )

    data = result.get("data") or []
    matches = []
    seen = set()

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

        activity_name = get_field(
            item,
            "activityName",
            "activity_name"
        )

        if match_id is None:
            continue

        # Filtriranje po tačnom ID-ju lige.
        if activity_id is not None:
            try:
                if int(float(activity_id)) != league["activity_id"]:
                    continue
            except (TypeError, ValueError):
                continue

        elif activity_name:
            if normalize(league["name"]) not in normalize(activity_name):
                continue

        else:
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

        if str(match_id) in seen:
            continue

        seen.add(str(match_id))

        match_date = get_field(
            item,
            "tipoff",
            "matchDate",
            "match_date",
            "matchTime",
            "match_time"
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

        status = get_field(
            item,
            "statusId",
            "status_id"
        )

        matches.append({
            "id": str(match_id),
            "home": str(home),
            "away": str(away),
            "date": str(match_date or "Termin nije objavljen"),
            "home_score": home_score,
            "away_score": away_score,
            "status": status
        })

    matches.sort(key=lambda x: x["date"])

    return matches


def show_league(chat_id, short_name, today_only=False):
    league_name = LEAGUES[short_name]["name"]

    try:
        matches = get_matches(short_name)

        if not matches:
            send_message(
                chat_id,
                league_name
                + "\nTBF API nije vratio utakmice za ovu ligu."
            )
            return

        today = datetime.now(
            ZoneInfo("Europe/Istanbul")
        ).strftime("%Y-%m-%d")

        if today_only:
            matches = [
                m for m in matches
                if m["date"][:10] == today
            ]

        if not matches:
            send_message(
                chat_id,
                league_name + "\nNema utakmica za danas."
            )
            return

        lines = [
            league_name + " — ZVANIČNI TBF",
            ""
        ]

        for match in matches[:30]:
            lines.append(
                match["home"] + " — " + match["away"]
            )

            lines.append(
                "Termin: " + match["date"]
            )

            if (
                match["home_score"] is not None
                and match["away_score"] is not None
            ):
                lines.append(
                    "Rezultat: "
                    + str(match["home_score"])
                    + " : "
                    + str(match["away_score"])
                )

            lines.append("")

        send_message(chat_id, "\n".join(lines))

    except Exception as error:
        print("TBF ERROR:", repr(error))

        try:
            send_message(
                chat_id,
                league_name
                + " GREŠKA:\n"
                + str(error)[:2000]
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
