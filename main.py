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
SEASON = 2027  # 2026-2027 season

LEAGUES = {
    "tbl": {"name": "TBL", "display_names": {"TBL"}},
    "tb2l": {"name": "TB2L", "display_names": {"TB2L"}},
    "tkbl": {"name": "TKBL", "display_names": {"TKBL"}},
}


def get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_data(result):
    if not isinstance(result, dict):
        raise Exception("TBF API je vratio neispravan odgovor.")
    if result.get("isSuccess") is False:
        raise Exception(str(result.get("message") or "TBF API greška"))
    return result.get("data") or []


def get_league_activity_ids():
    return {"TBL": 22215, "TB2L": 22223, "TKBL": 22210}

    def walk(value):
        if isinstance(value, dict):
            display = str(
                value.get("displayName")
                or value.get("display_name")
                or value.get("shortName")
                or ""
            ).strip().upper()
            activity = (
                value.get("activityId")
                or value.get("activity_id")
            )
            if display in {"TBL", "TB2L", "TKBL"} and activity is not None:
                try:
                    found[display] = int(float(activity))
                except (TypeError, ValueError):
                    pass
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(rows)

    missing = [name for name in ("TBL", "TB2L", "TKBL") if name not in found]
    if missing:
        raise Exception(
            "TBF lista liga za sezonu "
            + str(SEASON)
            + " nije vratila ID za: "
            + ", ".join(missing)
            + ". Dobijene lige: "
            + ", ".join(sorted(found))
        )
    return found


def send_message(chat_id, message):
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
            "text": chunk,
        }).encode()
        request = urllib.request.Request(TG_URL + "sendMessage", data=data)
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()


def get_daily_matches(date_string):
    params = urllib.parse.urlencode({
        "match_date": date_string,
        "season": SEASON,
    })
    url = TBF_URL + "Match/get-daily-matches?" + params
    data = api_data(get_json(url))
    matches = []

    def walk(value, inherited_activity=None, inherited_name=""):
        if isinstance(value, dict):
            activity = (
                value.get("activityId")
                or value.get("activity_id")
                or inherited_activity
            )
            league_name = (
                value.get("displayName")
                or value.get("display_name")
                or value.get("activityName")
                or value.get("activity_name")
                or inherited_name
            )
            for key in ("matches", "matchList", "match_list"):
                items = value.get(key)
                if isinstance(items, list):
                    for match in items:
                        if isinstance(match, dict):
                            copied = dict(match)
                            copied["_group_activity_id"] = activity
                            copied["_group_activity_name"] = league_name
                            matches.append(copied)
            # Also support API responses where match records are nested differently.
            for key, child in value.items():
                if key not in ("matches", "matchList", "match_list"):
                    walk(child, activity, league_name)
        elif isinstance(value, list):
            for child in value:
                walk(child, inherited_activity, inherited_name)

    walk(data)
    return matches


def get_matches(short_name, days=30):
    league = LEAGUES[short_name]
    activity_ids = get_league_activity_ids()
    wanted_id = activity_ids[league["name"]]

    today = datetime.now(TZ).date()
    all_matches = []
    seen = set()

    for day_number in range(days):
        date_string = (today + timedelta(days=day_number)).strftime("%Y-%m-%d")
        for match in get_daily_matches(date_string):
            activity_id = (
                match.get("activityId")
                or match.get("activity_id")
                or match.get("_group_activity_id")
            )
            try:
                match_activity_id = int(float(activity_id))
            except (TypeError, ValueError):
                continue

            if match_activity_id != wanted_id:
                continue

            match_id = match.get("matchId") or match.get("match_id")
            if match_id is not None:
                if str(match_id) in seen:
                    continue
                seen.add(str(match_id))

            home_team = match.get("homeTeam") or match.get("home_team") or {}
            away_team = match.get("awayTeam") or match.get("away_team") or {}
            home = home_team.get("name") if isinstance(home_team, dict) else None
            away = away_team.get("name") if isinstance(away_team, dict) else None
            if not home or not away:
                continue

            all_matches.append({
                "home": str(home),
                "away": str(away),
                "date": str(match.get("matchDateOnly") or match.get("matchDate") or date_string),
                "time": str(match.get("matchTime") or ""),
                "status": str(match.get("matchStatus") or ""),
                "home_score": home_team.get("score") if isinstance(home_team, dict) else None,
                "away_score": away_team.get("score") if isinstance(away_team, dict) else None,
                "venue": str(match.get("venueName") or ""),
                "broadcast": str(match.get("broadcastChannel") or ""),
            })
        time.sleep(1.0)  # TBF API request spacing

    all_matches.sort(key=lambda m: (m["date"], m["time"]))
    return all_matches


def show_league(chat_id, short_name, today_only=False):
    league_name = LEAGUES[short_name]["name"]
    try:
        matches = get_matches(short_name, days=1 if today_only else 30)
        if today_only:
            today = datetime.now(TZ).strftime("%Y-%m-%d")
            matches = [m for m in matches if m["date"][:10] == today]

        if not matches:
            send_message(
                chat_id,
                league_name + "\nNema pronadjenih utakmica za traženi period.",
            )
            return

        lines = [
            league_name + " - ZVANIČNI TBF",
            "Raspored za danas" if today_only else "Raspored za narednih 30 dana",
            "",
        ]
        for match in matches[:40]:
            lines.append(match["home"] + " - " + match["away"])
            lines.append(
                "Datum: " + match["date"]
                + " | Vreme: " + (match["time"] or "Nije objavljeno")
            )
            if match["home_score"] not in (None, "") and match["away_score"] not in (None, ""):
                lines.append(
                    "Rezultat: " + str(match["home_score"])
                    + " : " + str(match["away_score"])
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
            send_message(chat_id, league_name + " GREŠKA:\n" + str(error)[:2000])
        except Exception as telegram_error:
            print("TELEGRAM ERROR:", repr(telegram_error))


def handle_update(update):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    command = message.get("text", "").strip().lower().split("@")[0]
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
            "/id - Tvoj Chat ID",
        )
    elif command == "/id":
        send_message(chat_id, "Tvoj Chat ID je: " + str(chat_id))
    elif command in ("/tbl", "/tb2l", "/tkbl"):
        show_league(chat_id, command[1:])
    elif command == "/today":
        for league in ("tbl", "tb2l", "tkbl"):
            show_league(chat_id, league, today_only=True)
            time.sleep(1)


offset = 0
print("TBF BASKETBALL BOT STARTED", flush=True)

while True:
    try:
        url = TG_URL + "getUpdates?" + urllib.parse.urlencode({
            "offset": offset,
            "timeout": 25,
        })
        response = get_json(url)
        for update in response.get("result", []):
            offset = update["update_id"] + 1
            handle_update(update)
    except Exception as error:
        print("BOT ERROR:", repr(error), flush=True)
        time.sleep(5)
