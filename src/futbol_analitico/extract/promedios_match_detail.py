from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from futbol_analitico.utils.http import build_headers
from futbol_analitico.config import load_settings


STAT_MAP = {
    "posesión de pelota": "possession_pct",
    "posesion de pelota": "possession_pct",
    "remates": "shots",
    "remates al arco": "shots_on_target",
    "faltas": "fouls_committed",
    "córners": "corners",
    "corners": "corners",
    "offsides": "offsides",
    "pases totales": "total_passes",
    "precisión en pases": "pass_accuracy_pct",
    "precision en pases": "pass_accuracy_pct",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def maybe_int(value):
    if value is None:
        return None
    txt = normalize_space(value)
    return int(txt) if re.fullmatch(r"\d+", txt) else None


def maybe_pct(value):
    if value is None:
        return None
    txt = normalize_space(value).replace("%", "")
    try:
        return float(txt)
    except Exception:
        return None


def get_html(url: str) -> str:
    import requests

    settings = load_settings()
    scraping = settings["scraping"]
    sources = settings["sources"]

    headers = build_headers(
        user_agent=scraping["user_agent"],
        referer=sources["promediosinfo_competition"],
        origin="https://promediosinfo.com",
    )
    response = requests.get(url, headers=headers, timeout=scraping["timeout_seconds"])
    response.raise_for_status()
    return response.text


def extract_stats_segment_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    lines = [normalize_space(x) for x in text.splitlines() if normalize_space(x)]

    start_idx = None
    for i, line in enumerate(lines):
        if line.lower() in ("estadísticas", "estadisticas"):
            start_idx = i
            break

    if start_idx is None:
        return []

    end_markers = [
        "copyright",
        "términos de servicio",
        "terminos de servicio",
        "políticas de privacidad",
        "politicas de privacidad",
    ]

    segment_lines = []
    for line in lines[start_idx + 1:]:
        low = line.lower()
        if any(marker in low for marker in end_markers):
            break
        segment_lines.append(line)
        if len(segment_lines) >= 100:
            break

    return segment_lines


def extract_stats_pairs_from_lines(segment_lines: list[str]) -> dict:
    results = {}
    normalized_labels = {normalize_space(k).lower(): v for k, v in STAT_MAP.items()}
    label_set = set(normalized_labels.keys())

    i = 0
    while i < len(segment_lines):
        current = normalize_space(segment_lines[i]).lower()
        if current not in label_set:
            i += 1
            continue

        field = normalized_labels[current]
        values = []
        j = i + 1

        while j < len(segment_lines):
            nxt = normalize_space(segment_lines[j]).lower()
            if nxt in label_set:
                break

            token = normalize_space(segment_lines[j])
            if re.fullmatch(r"\d+%?", token):
                values.append(token)

            j += 1

        if len(values) >= 2:
            left_value, right_value = values[0], values[1]
        elif len(values) == 1:
            left_value, right_value = values[0], "0"
        else:
            left_value, right_value = None, None

        results[field] = (left_value, right_value, current)
        i = j

    return results


def extract_match_detail_team_stats(match_row: pd.Series) -> tuple[pd.DataFrame, dict]:
    url = match_row["source_match_href"]
    if not url:
        return pd.DataFrame(), {
            "match_id": match_row["source_match_id"],
            "reason": "missing_match_href",
        }

    try:
        html = get_html(url)
    except Exception as exc:
        return pd.DataFrame(), {
            "match_id": match_row["source_match_id"],
            "reason": f"http_error: {repr(exc)}",
        }

    stats_lines = extract_stats_segment_lines(html)
    stats_values = extract_stats_pairs_from_lines(stats_lines)

    if not stats_lines:
        return pd.DataFrame(), {
            "match_id": match_row["source_match_id"],
            "reason": "stats_segment_not_detected",
        }

    if not stats_values:
        return pd.DataFrame(), {
            "match_id": match_row["source_match_id"],
            "reason": "stats_values_not_detected",
        }

    home_row = {
        "match_id": match_row["source_match_id"],
        "team_name_raw": match_row["home_team_name_raw"],
        "opponent_team_name_raw": match_row["away_team_name_raw"],
        "is_home": True,
        "goals_for": match_row["home_score"],
        "goals_against": match_row["away_score"],
        "shots": None,
        "shots_on_target": None,
        "possession_pct": None,
        "corners": None,
        "offsides": None,
        "fouls_committed": None,
        "yellow_cards": match_row.get("home_yellow_cards"),
        "red_cards": match_row.get("home_red_cards"),
        "total_passes": None,
        "pass_accuracy_pct": None,
        "source_name": "PromediosInfo",
        "source_url": url,
    }

    away_row = {
        "match_id": match_row["source_match_id"],
        "team_name_raw": match_row["away_team_name_raw"],
        "opponent_team_name_raw": match_row["home_team_name_raw"],
        "is_home": False,
        "goals_for": match_row["away_score"],
        "goals_against": match_row["home_score"],
        "shots": None,
        "shots_on_target": None,
        "possession_pct": None,
        "corners": None,
        "offsides": None,
        "fouls_committed": None,
        "yellow_cards": match_row.get("away_yellow_cards"),
        "red_cards": match_row.get("away_red_cards"),
        "total_passes": None,
        "pass_accuracy_pct": None,
        "source_name": "PromediosInfo",
        "source_url": url,
    }

    for field, (left_value, right_value, _) in stats_values.items():
        if field in {"possession_pct", "pass_accuracy_pct"}:
            home_row[field] = maybe_pct(left_value)
            away_row[field] = maybe_pct(right_value)
        else:
            home_row[field] = maybe_int(left_value)
            away_row[field] = maybe_int(right_value)

    if has_all_zero_stat_profile(home_row, away_row):
        return pd.DataFrame(), {
            "match_id": match_row["source_match_id"],
            "reason": "placeholder_zero_stats",
        }

    for row in [home_row, away_row]:
        row["detail_stats_source"] = "promediosinfo"
        row["detail_stats_status"] = "ok"

    return pd.DataFrame([home_row, away_row]), {
        "match_id": match_row["source_match_id"],
        "reason": None,
    }

def is_zero_like(value) -> bool:
    if value is None:
        return False

    try:
        return float(value) == 0.0
    except Exception:
        return False


def has_all_zero_stat_profile(home_row: dict, away_row: dict) -> bool:
    check_cols = [
        "shots",
        "shots_on_target",
        "possession_pct",
        "corners",
        "offsides",
        "fouls_committed",
        "total_passes",
        "pass_accuracy_pct",
    ]

    for col in check_cols:
        home_zero = is_zero_like(home_row.get(col))
        away_zero = is_zero_like(away_row.get(col))

        if not (home_zero and away_zero):
            return False

    return True

def extract_fct_team_match(fct_match: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    finished_matches = fct_match[fct_match["match_status"] == "finished"].copy()

    detail_rows = []
    detail_failures = []

    for _, match_row in finished_matches.iterrows():
        rows_df, status = extract_match_detail_team_stats(match_row)
        if rows_df.empty:
            detail_failures.append(status)
        else:
            detail_rows.append(rows_df)

    team_match = pd.concat(detail_rows, ignore_index=True) if detail_rows else pd.DataFrame()
    failures = pd.DataFrame(detail_failures)

    return team_match, failures