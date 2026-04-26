from __future__ import annotations

import html as html_lib
import json
import re
import time
from urllib.parse import unquote, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from futbol_analitico.config import load_settings


BESOCCER_BASE_URL = "https://www.besoccer.com"
BESOCCER_COMPETITION_URL = "https://www.besoccer.com/competition/peru_apertura"
BESOCCER_ROUNDS_ENDPOINT = "https://www.besoccer.com/ajax/getCompetitionRounds"

BESOCCER_COMPETITION_PARAMS = {
    "dataInfo[req]": "competition_matches_v2",
    "dataInfo[id]": "45",
    "dataInfo[league_id]": "81958",
    "dataInfo[group]": "1",
    "dataInfo[year]": "2026",
    "dataInfo[league]": "45",
    "offsetName": "America/Lima",
    "onchange": "1",
    "isCompetition": "1",
}

BESOCCER_LABEL_MAP = {
    "ball possession": "possession_pct",
    "offsides": "offsides",
    "corner kicks": "corners",
    "total shots": "shots",
    "blocked shots": "blocked_shots",
    "goalkeeper saves": "goalkeeper_saves",
    "tackles": "tackles",
    "total passes": "total_passes",
    "completed passes": "completed_passes",
    "fouls": "fouls_committed",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def normalize_team_name(text: str) -> str:
    value = normalize_space(text).lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }

    for src, dst in replacements.items():
        value = value.replace(src, dst)

    value = re.sub(r"[^a-z0-9]+", " ", value)
    return normalize_space(value)


def build_headers_get() -> dict:
    settings = load_settings()
    user_agent = settings["scraping"]["user_agent"]

    return {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }


def build_headers_post() -> dict:
    return {
        **build_headers_get(),
        "Origin": "https://www.besoccer.com",
        "Referer": BESOCCER_COMPETITION_URL,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }


def get_html(url: str, sleep_seconds: float = 0.5) -> str:
    time.sleep(sleep_seconds)
    settings = load_settings()
    timeout = settings["scraping"]["timeout_seconds"]

    response = requests.get(url, headers=build_headers_get(), timeout=timeout)
    response.raise_for_status()
    return response.text


def post_text(url: str, data: dict, sleep_seconds: float = 0.5) -> str:
    time.sleep(sleep_seconds)
    settings = load_settings()
    timeout = settings["scraping"]["timeout_seconds"]

    response = requests.post(
        url,
        headers=build_headers_post(),
        data=data,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def recursively_collect_strings(obj) -> list[str]:
    values = []

    if isinstance(obj, dict):
        for value in obj.values():
            values.extend(recursively_collect_strings(value))
    elif isinstance(obj, list):
        for value in obj:
            values.extend(recursively_collect_strings(value))
    elif isinstance(obj, str):
        values.append(obj)

    return values


def unwrap_ajax_response(raw_text: str) -> str:
    text = raw_text.strip()

    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            string_values = recursively_collect_strings(obj)
            html_like = [s for s in string_values if "<" in s and ">" in s]

            if html_like:
                text = max(html_like, key=len)
        except Exception:
            pass

    text = html_lib.unescape(text)
    text = text.replace("\\/", "/")
    text = text.replace('\\"', '"')
    text = text.replace("\\n", "\n")
    text = text.replace("\\t", "\t")

    return text


def clean_besoccer_href(raw_href: str) -> str | None:
    if raw_href is None:
        return None

    href = str(raw_href).strip()
    href = html_lib.unescape(href)
    href = href.replace("\\/", "/")
    href = href.replace('\\"', '"')
    href = href.strip('"').strip("'")
    href = href.replace("&amp;", "&")
    href = unquote(href)

    match = re.search(r"https?://[^\"'\s<>]+", href)
    if match:
        return match.group(0)

    if href.startswith("/"):
        return urljoin(BESOCCER_BASE_URL, href)

    if href.startswith("match/") or href.startswith("partido/"):
        return urljoin(BESOCCER_BASE_URL, "/" + href)

    return None


def parse_number_token(value):
    if value is None:
        return None

    text = normalize_space(value).replace("%", "")
    match = re.search(r"\d+(?:\.\d+)?", text)

    if not match:
        return None

    number = float(match.group())
    return int(number) if number.is_integer() else number


def fetch_besoccer_round(round_number: int) -> str:
    payload = dict(BESOCCER_COMPETITION_PARAMS)
    payload["dataInfo[round]"] = str(round_number)

    raw_text = post_text(BESOCCER_ROUNDS_ENDPOINT, data=payload)
    return unwrap_ajax_response(raw_text)


def extract_match_candidates_from_round_html(round_html: str, round_number: int) -> pd.DataFrame:
    soup = BeautifulSoup(round_html, "lxml")
    rows = []

    for anchor in soup.find_all("a", href=True):
        text = normalize_space(anchor.get_text(" ", strip=True))
        raw_href = anchor.get("href")
        href = clean_besoccer_href(raw_href)

        if not href:
            continue

        href_lower = href.lower()

        if "/match/" in href_lower or "/partido/" in href_lower:
            rows.append(
                {
                    "round_number": round_number,
                    "raw_text": text,
                    "raw_href": raw_href,
                    "match_url": href,
                }
            )

    candidates = pd.DataFrame(rows)

    if candidates.empty:
        return candidates

    return candidates.drop_duplicates(subset=["round_number", "match_url"])


def extract_besoccer_match_candidates(round_from: int, round_to: int) -> pd.DataFrame:
    all_candidates = []

    for round_number in range(round_from, round_to + 1):
        html = fetch_besoccer_round(round_number)
        candidates = extract_match_candidates_from_round_html(html, round_number)

        if not candidates.empty:
            all_candidates.append(candidates)

    if not all_candidates:
        return pd.DataFrame()

    return pd.concat(all_candidates, ignore_index=True)


def alias_found(haystack: str, aliases: list[str]) -> bool:
    haystack_norm = normalize_team_name(haystack)

    for alias in aliases:
        alias_norm = normalize_team_name(alias)

        if not alias_norm:
            continue

        if alias_norm in haystack_norm:
            return True

        tokens = [token for token in alias_norm.split() if len(token) >= 4]

        if tokens and all(token in haystack_norm for token in tokens):
            return True

    return False


def build_team_aliases(team_name: str) -> list[str]:
    aliases = [team_name]

    normalized = normalize_team_name(team_name)

    if "sport huancayo" in normalized:
        aliases.append("Huancayo")

    if "alianza lima" in normalized:
        aliases.append("Alianza")

    if "juan pablo" in normalized:
        aliases.extend(["Juan Pablo II", "Juan Pablo"])

    if "cajamarca" in normalized:
        aliases.extend(["FC Cajamarca", "Cajamarca", "UTC Cajamarca"])

    return list(dict.fromkeys(aliases))


def score_candidate_for_match(candidate: pd.Series, match_row: pd.Series) -> dict:
    haystack = f"{candidate.get('raw_text', '')} {candidate.get('match_url', '')}"

    home_aliases = build_team_aliases(match_row["home_team_name_raw"])
    away_aliases = build_team_aliases(match_row["away_team_name_raw"])

    has_home = alias_found(haystack, home_aliases)
    has_away = alias_found(haystack, away_aliases)

    score = 0

    if has_home:
        score += 10

    if has_away:
        score += 10

    return {
        "has_home": has_home,
        "has_away": has_away,
        "candidate_score": score,
    }


def find_besoccer_match_url(match_row: pd.Series, candidates: pd.DataFrame) -> str | None:
    if candidates.empty:
        return None

    scored = candidates.copy()
    score_df = scored.apply(
        lambda row: score_candidate_for_match(row, match_row),
        axis=1,
        result_type="expand",
    )

    scored = pd.concat([scored, score_df], axis=1)

    strict = scored[
        (scored["has_home"] == True)
        & (scored["has_away"] == True)
    ].copy()

    if strict.empty:
        return None

    strict = strict.sort_values("candidate_score", ascending=False)
    return strict.iloc[0]["match_url"]


def clean_stat_label(label: str) -> str:
    label = normalize_space(label).lower()
    label = label.replace("\xa0", " ")
    return normalize_space(label)


def extract_left_right_from_td(td) -> tuple[float | int | None, float | int | None, str]:
    left_element = td.select_one(".td-num.left")
    right_element = td.select_one(".td-num.right")

    left_text = normalize_space(left_element.get_text(" ", strip=True)) if left_element else ""
    right_text = normalize_space(right_element.get_text(" ", strip=True)) if right_element else ""

    left_value = parse_number_token(left_text)
    right_value = parse_number_token(right_text)

    return left_value, right_value, f"left='{left_text}' right='{right_text}'"


def extract_label_from_td(td) -> str | None:
    paragraph = td.find("p")

    if paragraph:
        text = clean_stat_label(paragraph.get_text(" ", strip=True))

        if text:
            return text

    td_clone = BeautifulSoup(str(td), "lxml")

    for div in td_clone.select(".td-num, .stats-graph, .elo-bar-content"):
        div.decompose()

    text = clean_stat_label(td_clone.get_text(" ", strip=True))

    return text if text else None


def first_numeric_from_selector(parent, selector: str):
    elements = parent.select(selector)

    for element in elements:
        value = parse_number_token(element.get_text(" ", strip=True))

        if value is not None:
            return value

    return None


def last_numeric_from_selector(parent, selector: str):
    elements = parent.select(selector)
    values = []

    for element in elements:
        value = parse_number_token(element.get_text(" ", strip=True))

        if value is not None:
            values.append(value)

    return values[-1] if values else None


def extract_shots_breakdown(stats_block) -> dict:
    result = {}

    for table_row in stats_block.find_all("tr"):
        text = clean_stat_label(table_row.get_text(" ", strip=True))

        if "off target" not in text or "on target" not in text:
            continue

        home_off_value = first_numeric_from_selector(table_row, "span.num.left")
        away_off_value = first_numeric_from_selector(table_row, "span.num.right")
        home_on_value = last_numeric_from_selector(table_row, ".box.left span")
        away_on_value = last_numeric_from_selector(table_row, ".box.right span")

        result["shots_off_target"] = (home_off_value, away_off_value)
        result["shots_on_target"] = (home_on_value, away_on_value)

    return result


def extract_besoccer_stats_from_html(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    stats_block = soup.select_one('div.detail-match-stats.general-stats[data-cy="stats"]')

    if stats_block is None:
        return pd.DataFrame()

    rows = []

    for table_row in stats_block.find_all("tr"):
        td = table_row.find("td")

        if td is None:
            continue

        if "title" in (td.get("class") or []):
            continue

        label_raw = extract_label_from_td(td)

        if not label_raw:
            continue

        label = clean_stat_label(label_raw)
        metric = BESOCCER_LABEL_MAP.get(label)

        if metric is None:
            continue

        left_value, right_value, raw_values = extract_left_right_from_td(td)

        rows.append(
            {
                "metric": metric,
                "left_value": left_value,
                "right_value": right_value,
                "label": label,
                "raw_values": raw_values,
            }
        )

    shots_breakdown = extract_shots_breakdown(stats_block)

    for metric, (left_value, right_value) in shots_breakdown.items():
        rows.append(
            {
                "metric": metric,
                "left_value": left_value,
                "right_value": right_value,
                "label": metric,
                "raw_values": "special_shots_breakdown",
            }
        )

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    return result.drop_duplicates(subset=["metric"], keep="last").reset_index(drop=True)


def stats_long_to_team_rows(stats_long: pd.DataFrame, match_row: pd.Series, source_url: str) -> pd.DataFrame:
    if stats_long.empty:
        return pd.DataFrame()

    home_row = {
        "match_id": match_row["source_match_id"],
        "team_name_raw": match_row["home_team_name_raw"],
        "opponent_team_name_raw": match_row["away_team_name_raw"],
        "is_home": True,
        "goals_for": match_row["home_score"],
        "goals_against": match_row["away_score"],
        "source_name": "BeSoccer",
        "source_url": source_url,
        "detail_stats_source": "besoccer",
        "detail_stats_status": "fallback_extracted",
    }

    away_row = {
        "match_id": match_row["source_match_id"],
        "team_name_raw": match_row["away_team_name_raw"],
        "opponent_team_name_raw": match_row["home_team_name_raw"],
        "is_home": False,
        "goals_for": match_row["away_score"],
        "goals_against": match_row["home_score"],
        "source_name": "BeSoccer",
        "source_url": source_url,
        "detail_stats_source": "besoccer",
        "detail_stats_status": "fallback_extracted",
    }

    for _, stat in stats_long.iterrows():
        metric = stat["metric"]
        home_row[metric] = stat["left_value"]
        away_row[metric] = stat["right_value"]

    for row in [home_row, away_row]:
        completed = row.get("completed_passes")
        total = row.get("total_passes")

        if completed is not None and total not in (None, 0):
            row["pass_accuracy_pct"] = round((completed / total) * 100, 2)
        else:
            row["pass_accuracy_pct"] = None

    return pd.DataFrame([home_row, away_row])


def extract_besoccer_fallback_for_matches(
    problem_matches: pd.DataFrame,
    round_from: int,
    round_to: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = extract_besoccer_match_candidates(round_from=round_from, round_to=round_to)

    fallback_rows = []
    fallback_log_rows = []

    for _, match_row in problem_matches.iterrows():
        match_id = match_row["source_match_id"]
        match_url = find_besoccer_match_url(match_row, candidates)

        if not match_url:
            fallback_log_rows.append(
                {
                    "match_id": match_id,
                    "fallback_source": "besoccer",
                    "fallback_status": "match_url_not_found",
                    "fallback_url": None,
                    "metrics_count": 0,
                }
            )
            continue

        try:
            html = get_html(match_url)
            stats_long = extract_besoccer_stats_from_html(html)

            if stats_long.empty:
                fallback_log_rows.append(
                    {
                        "match_id": match_id,
                        "fallback_source": "besoccer",
                        "fallback_status": "stats_not_found",
                        "fallback_url": match_url,
                        "metrics_count": 0,
                    }
                )
                continue

            team_rows = stats_long_to_team_rows(stats_long, match_row, match_url)
            fallback_rows.append(team_rows)

            fallback_log_rows.append(
                {
                    "match_id": match_id,
                    "fallback_source": "besoccer",
                    "fallback_status": "fallback_extracted",
                    "fallback_url": match_url,
                    "metrics_count": len(stats_long),
                    "metrics": sorted(stats_long["metric"].tolist()),
                }
            )

        except Exception as exc:
            fallback_log_rows.append(
                {
                    "match_id": match_id,
                    "fallback_source": "besoccer",
                    "fallback_status": "error",
                    "fallback_url": match_url,
                    "metrics_count": 0,
                    "error": repr(exc),
                }
            )

    fallback_df = pd.concat(fallback_rows, ignore_index=True) if fallback_rows else pd.DataFrame()
    fallback_log = pd.DataFrame(fallback_log_rows)

    return fallback_df, fallback_log