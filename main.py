import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["BOT_TOKEN"]

TG_URL = f"https://api.telegram.org/bot{TOKEN}/"
TBF_URL = "https://miniappapi.tbf.org.tr/webapi-service/api/"

TZ = ZoneInfo("Europe/Istanbul")

LEAGUES = {
    "tbl": {
        "name": "TBL",
        "activity_id": 22215,
        "activity_code": "tbl"
    },
    "tb2l": {
        "name": "TB2L",
        "activity_id": 22223,
        "activity_code": "tb2l"
    },
    "tkbl": {
        "name": "TKBL",
        "activity_id": 22210,
        "activity_code": "tkbl"
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
    # Telegram ograničava dužinu poruke.
    chunks = []

    while len(message) > 3500:
        split_at = message.rfind("\n", 0, 3500)

        if split_at == -1:
            split_at = 3500

        chunks.append(message[:split_at])
        message = message[split_at:].lstrip()

    if message:
        chunks.append(message)

    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk
        }).encode()

        request = urllib.request.Request(
            TG_URL + "sendMessage",
            data=data
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()


def get_daily_matches(date_string):
    params = urllib.parse.urlencode({
        "match_date": date_string
    })

    url = (
        TBF_URL
        + "Match/get-daily-matches?"
        + params
    )

    result = get_json(url)

    if not isinstance(result, dict):
        raise Exception("Neispravan odgovor TBF API-ja.")

    if result.get("isSuccess") is False:
        raise Exception(
            str(result.get("message", "TBF API greška"))
        )

    data = result.get("data") or []
    matches = []

    for group in data:
        if not isinstance(group, dict):
            continue

        group_matches = group.get("matches") or []

        for match in group_matches:
            if isinstance(match, dict):
                matches.append(match)

    return matches


def get_matches(short_name, days=7):
    league = LEAGUES[short_name]

    today = datetime.now(TZ).date()
    all_matches = []
    seen = set()

    for day_number in range(days):
        match_date = today + timedelta(days=day_number)
        date_string = match_date.strftime("%Y-%m-%d")

        daily_matches = get_daily_matches(date_string)

        for match in daily_matches:
            activity_id = match.get("activityId")
            activity_code = str(
                match.get("activityCode", "")
            ).lower()

            try:
                correct_id = (
                    int(float(activity_id))
                    == league["activity_id"]
                )
            except (TypeError, ValueError):
                correct_id = False

            if not correct_id and activity_code != league["activity_code"]:
                continue

            match_id = match.get("matchId")

            if match_id is not None:
                if str(match_id) in seen:
                    continue
                seen.add(str(match_id))

            home_team = match.get("homeTeam") or {}
            away_team = match.get("awayTeam") or {}

            home = home_team.get("name")
            away = away_team.get("name")

            if not home or not away:
                continue

            all_matches.append({
                "id": match_id,
                "home": str(home),
                "away": str(away),
                "date": str(
                    match.get("matchDateOnly", date_string)
                ),
                "time": str(
                    match.get("matchTime", "")
                ),
                "status": str(
                    match.get("matchStatus", "")
                ),
                "home_score": home_team.get("score"),
                "away_score": away_team.get("score"),
                "venue": str(
                    match.get("venueName") or ""
                ),
                "broadcast": str(
                    match.get("broadcastChannel") or ""
                ),
                "week": str(
                    match.get("week") or ""
                )
            })

        time.sleep(0.15)

    all_matches.sort(
        key=lambda m: (m["date"], m["time"])
    )

    return all_matches


def show_league(chat_id, short_name, today_only=False):
    league_name = LEAGUES[short_name]["name"]

    try:
        matches = get_matches(
            short_name,
            days=1 if today_only else 7
        )

        if not matches:
            send_message(
                chat_id,
                league_name
                + "\nTBF trenutno nema utakmica u ovom periodu."
            )
            return

        if today_only:
            today = datetime.now(TZ).strftime("%Y-%m-%d")

            matches = [
                m for m in matches
                if m["date"] == today
            ]

        if not matches:
            send_message(
                chat_id,
                league_name + "\nNema utakmica za danas."
            )
            return

        lines = [
            league_name + " — ZVANIČNI TBF",
            "Raspored za narednih 7 dana",
            ""
        ]

        for match in matches[:40]:
            lines.append(
                match["home"] + " — " + match["away"]
            )

            lines.append(
                "Datum: " + match["date"]
                + " | Vreme: " + (match["time"] or "Nije objavljeno")
            )

            if (
                match["home_score"] not in (None, "")
                and match["away_score"] not in (None, "")
            ):
                lines.append(
                    "Rezultat: "
                    + str(match["home_score"])
                    + " : "
                    + str(match["away_score"])
                )

            if match["status"]:
                lines.append("Status: " + match["status"])

            if match["venue"]:
                lines.append("Dvorana: " + match["venue"])

            if match["broadcast"]:
                lines.append("Prenos: " + match["broadcast"])

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

print("TBF BASKETBALL BOT STARTED")

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
