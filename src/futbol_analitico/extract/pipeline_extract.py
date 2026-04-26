from __future__ import annotations

import pandas as pd

from futbol_analitico.config import load_settings
from futbol_analitico.extract.besoccer_fallback import extract_besoccer_fallback_for_matches
from futbol_analitico.extract.promedios_match_detail import extract_fct_team_match
from futbol_analitico.extract.promedios_showround import extract_fct_match
from futbol_analitico.utils.io import write_csv
from futbol_analitico.utils.paths import get_data_paths


def get_problem_matches_for_fallback(
    fct_match: pd.DataFrame,
    team_match_failures: pd.DataFrame,
) -> pd.DataFrame:
    if team_match_failures.empty:
        return pd.DataFrame()

    fallback_reasons = {
        "placeholder_zero_stats",
        "stats_segment_not_detected",
        "stats_values_not_detected",
        "stats_block_not_detected",
    }

    failures = team_match_failures[
        team_match_failures["reason"].isin(fallback_reasons)
    ].copy()

    if failures.empty:
        return pd.DataFrame()

    problem_matches = fct_match[
        fct_match["source_match_id"].isin(failures["match_id"])
    ].copy()

    return problem_matches


def merge_fallback_team_match(
    fct_team_match: pd.DataFrame,
    fallback_team_match: pd.DataFrame,
) -> pd.DataFrame:
    if fallback_team_match.empty:
        return fct_team_match

    fallback_match_ids = fallback_team_match["match_id"].unique().tolist()

    cleaned_primary = fct_team_match[
        ~fct_team_match["match_id"].isin(fallback_match_ids)
    ].copy()

    merged = pd.concat(
        [cleaned_primary, fallback_team_match],
        ignore_index=True,
        sort=False,
    )

    return merged


def remove_resolved_failures(
    team_match_failures: pd.DataFrame,
    fallback_log: pd.DataFrame,
) -> pd.DataFrame:
    if team_match_failures.empty or fallback_log.empty:
        return team_match_failures

    resolved_ids = fallback_log.loc[
        fallback_log["fallback_status"] == "fallback_extracted",
        "match_id",
    ].tolist()

    unresolved = team_match_failures[
        ~team_match_failures["match_id"].isin(resolved_ids)
    ].copy()

    return unresolved


def run_extract() -> None:
    settings = load_settings()
    paths = get_data_paths()

    fct_match = extract_fct_match()
    fct_team_match, team_match_failures = extract_fct_team_match(fct_match)

    problem_matches = get_problem_matches_for_fallback(
        fct_match=fct_match,
        team_match_failures=team_match_failures,
    )

    if not problem_matches.empty:
        fallback_team_match, fallback_log = extract_besoccer_fallback_for_matches(
            problem_matches=problem_matches,
            round_from=settings["scraping"]["round_from"],
            round_to=settings["scraping"]["round_to"],
        )

        fct_team_match = merge_fallback_team_match(
            fct_team_match=fct_team_match,
            fallback_team_match=fallback_team_match,
        )

        team_match_failures = remove_resolved_failures(
            team_match_failures=team_match_failures,
            fallback_log=fallback_log,
        )
    else:
        fallback_team_match = pd.DataFrame()
        fallback_log = pd.DataFrame()

    write_csv(fct_match, paths["interim"] / "fct_match.csv")
    write_csv(fct_team_match, paths["interim"] / "fct_team_match.csv")
    write_csv(team_match_failures, paths["interim"] / "fct_team_match_failures.csv")
    write_csv(fallback_team_match, paths["interim"] / "fct_team_match_besoccer_fallback.csv")
    write_csv(fallback_log, paths["interim"] / "fct_team_match_fallback_log.csv")

    print("Extracción completada.")
    print(f"fct_match filas: {len(fct_match)}")
    print(f"fct_team_match filas: {len(fct_team_match)}")
    print(f"fct_team_match_failures filas: {len(team_match_failures)}")
    print(f"fallback_team_match filas: {len(fallback_team_match)}")
    print(f"fallback_log filas: {len(fallback_log)}")
    print(f"Output dir: {paths['interim']}")