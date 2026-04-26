from __future__ import annotations

import re
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from futbol_analitico.config import load_settings
from futbol_analitico.utils.http import build_headers, get_json


SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def slugify_team(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", s).strip("_")


def build_match_id(competition_id: str, match_date: str | None, home: str, away: str) -> str:
    return f"{competition_id}__{match_date or 'unknown'}__{slugify_team(home)}__{slugify_team(away)}"


def parse_score_token(token: str):
    token = str(token).strip()
    return int(token) if re.fullmatch(r"\d+", token) else None


def parse_spanish_date_text(text: str, season_year: int):
    txt = normalize_space(text).lower()
    match = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)", txt)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2)
    month = SPANISH_MONTHS.get(month_name)
    if month is None:
        return None
    return f"{season_year:04d}-{month:02d}-{day:02d}"


def parse_date_from_match_href(href: str | None):
    if not href:
        return None
    match = re.search(r"_(\d{4}-\d{2}-\d{2})_", href)
    return match.group(1) if match else None


def badge_value_strict(td, badge_class: str) -> int:
    if td is None:
        return 0

    badges = td.select(f".{badge_class}")
    if not badges:
        return 0

    values = []
    for badge in badges:
        txt = normalize_space(badge.get_text(" ", strip=True))
        match = re.search(r"\d+", txt)
        if match:
            values.append(int(match.group()))

    return sum(values) if values else 0


def fetch_showround_payload(round_number: int) -> dict:
    settings = load_settings()
    sources = settings["sources"]
    scraping = settings["scraping"]

    url = f"{sources['promediosinfo_show_round']}?id={scraping['league_id']}&f={round_number}"
    headers = build_headers(
        user_agent=scraping["user_agent"],
        referer=sources["promediosinfo_competition"],
        origin="https://promediosinfo.com",
    )
    return get_json(url=url, headers=headers, timeout_seconds=scraping["timeout_seconds"])


def parse_round_html_fragment(round_html: str, round_number: int) -> pd.DataFrame:
    settings = load_settings()
    project = settings["project"]
    sources = settings["sources"]

    soup = BeautifulSoup(round_html, "lxml")
    selected_option = soup.select_one("select.fx option[selected]")
    round_name = normalize_space(selected_option.get_text(" ", strip=True)) if selected_option else f"Fecha {round_number}"

    parsed_rows = []
    current_date_raw = None
    current_date_iso = None

    for table in soup.find_all("table"):
        for child in table.children:
            name = getattr(child, "name", None)

            if name == "thead":
                th = child.find("th")
                if th:
                    current_date_raw = normalize_space(th.get_text(" ", strip=True))
                    current_date_iso = parse_spanish_date_text(current_date_raw, int(project["season"]))
                continue

            if name != "tr":
                continue

            tr = child
            tr_id = tr.get("id")
            tr_class = tr.get("class", [])

            if tr_id and tr_id.endswith("_rowG"):
                continue
            if "lineR" not in tr_class:
                continue

            time_td = tr.select_one("td.time")
            home_td = tr.select_one("td.team.tr")
            away_td = tr.select_one("td.team.tl")
            cards_tds = tr.select("td.cards")
            home_cards_td = cards_tds[0] if len(cards_tds) >= 1 else None
            away_cards_td = cards_tds[1] if len(cards_tds) >= 2 else None
            r1_td = tr.select_one("td.r1")
            r2_td = tr.select_one("td.r2")
            plus_a = tr.select_one('a[id^="plus_"]')

            time_value = normalize_space(time_td.get_text(" ", strip=True)) if time_td else None
            home_team = normalize_space(home_td.get_text(" ", strip=True)) if home_td else None
            away_team = normalize_space(away_td.get_text(" ", strip=True)) if away_td else None
            home_score = parse_score_token(r1_td.get_text(" ", strip=True)) if r1_td else None
            away_score = parse_score_token(r2_td.get_text(" ", strip=True)) if r2_td else None
            href = plus_a.get("href") if plus_a else None
            href_date = parse_date_from_match_href(href)

            if not home_team or not away_team:
                continue

            match_date = href_date or current_date_iso

            row = {
                "competition_id": project["competition_id"],
                "round_number": round_number,
                "round_name": round_name,
                "match_date_raw": current_date_raw,
                "match_date": match_date,
                "match_datetime": None,
                "home_team_name_raw": home_team,
                "away_team_name_raw": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "match_status": None,
                "home_yellow_cards": badge_value_strict(home_cards_td, "badgeY"),
                "away_yellow_cards": badge_value_strict(away_cards_td, "badgeY"),
                "home_red_cards": badge_value_strict(home_cards_td, "badgeR"),
                "away_red_cards": badge_value_strict(away_cards_td, "badgeR"),
                "source_name": "PromediosInfo",
                "source_url": f"{sources['promediosinfo_show_round']}?id={settings['scraping']['league_id']}&f={round_number}",
                "source_match_id": None,
                "source_match_href": urljoin(sources["promediosinfo_base"], href) if href else None,
            }

            if time_value and re.fullmatch(r"\d{1,2}:\d{2}", time_value):
                row["match_datetime"] = time_value
                row["match_status"] = "scheduled"
            elif time_value and time_value.lower() == "final" and home_score is not None and away_score is not None:
                row["match_status"] = "finished"
            else:
                continue

            row["source_match_id"] = build_match_id(
                competition_id=project["competition_id"],
                match_date=row["match_date"],
                home=home_team,
                away=away_team,
            )

            parsed_rows.append(row)

    return pd.DataFrame(parsed_rows)


def extract_fct_match() -> pd.DataFrame:
    settings = load_settings()
    round_from = settings["scraping"]["round_from"]
    round_to = settings["scraping"]["round_to"]

    all_rounds = []
    for round_number in range(round_from, round_to + 1):
        payload = fetch_showround_payload(round_number)
        html_fragment = payload.get("data", "")
        parsed_df = parse_round_html_fragment(html_fragment, round_number)
        if not parsed_df.empty:
            all_rounds.append(parsed_df)

    if not all_rounds:
        return pd.DataFrame()

    return pd.concat(all_rounds, ignore_index=True)