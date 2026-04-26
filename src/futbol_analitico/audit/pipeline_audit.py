from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from futbol_analitico.utils.io import read_csv, write_csv
from futbol_analitico.utils.paths import get_data_paths


def pct(n, d):
    if d == 0:
        return 0.0
    return round((n / d) * 100, 2)


def safe_num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def check_result(
    issue_name: str,
    universe_df: pd.DataFrame,
    issue_df: pd.DataFrame,
    section: str,
    universe_label: str,
    severity: str = "warning",
):
    return {
        "section": section,
        "issue": issue_name,
        "severity": severity,
        "universe_label": universe_label,
        "universe_total": int(len(universe_df)),
        "affected_count": int(len(issue_df)),
        "affected_pct": pct(len(issue_df), len(universe_df)),
        "sample": issue_df.head(5).to_dict(orient="records"),
    }


def load_interim_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = get_data_paths()

    fct_match_path = paths["interim"] / "fct_match.csv"
    fct_team_match_path = paths["interim"] / "fct_team_match.csv"

    if not fct_match_path.exists():
        raise FileNotFoundError(f"No existe: {fct_match_path}")

    if not fct_team_match_path.exists():
        raise FileNotFoundError(f"No existe: {fct_team_match_path}")

    fct_match = read_csv(fct_match_path)
    fct_team_match = read_csv(fct_team_match_path)

    return fct_match, fct_team_match


def run_audit() -> None:
    paths = get_data_paths()
    audit_dir = paths["audit"]

    fct_match, fct_team_match = load_interim_data()

    match_checks = []
    team_match_checks = []
    semantic_checks = []
    pair_checks = []
    parsing_checks = []

    # =========================================================
    # 1. Auditoría estructural fct_match
    # =========================================================
    dup_match_ids = fct_match[fct_match["source_match_id"].duplicated(keep=False)].copy()
    match_checks.append(
        check_result(
            "duplicated_source_match_id",
            fct_match,
            dup_match_ids,
            "fct_match_structure",
            "rows_in_fct_match",
            "critical",
        )
    )

    finished_universe = fct_match[fct_match["match_status"] == "finished"].copy()
    finished_missing_href = finished_universe[
        finished_universe["source_match_href"].isna()
        | (finished_universe["source_match_href"].astype(str).str.strip() == "")
    ]
    match_checks.append(
        check_result(
            "finished_missing_href",
            finished_universe,
            finished_missing_href,
            "fct_match_structure",
            "finished_rows_in_fct_match",
            "critical",
        )
    )

    # =========================================================
    # 2. Auditoría estructural fct_team_match
    # =========================================================
    cardinality = (
        fct_team_match.groupby("match_id")
        .size()
        .reset_index(name="row_count")
    )

    bad_cardinality = cardinality[cardinality["row_count"] != 2]
    team_match_checks.append(
        check_result(
            "match_id_not_equal_2_rows",
            cardinality,
            bad_cardinality,
            "fct_team_match_structure",
            "distinct_match_id_in_fct_team_match",
            "critical",
        )
    )

    home_away_check = (
        fct_team_match.groupby("match_id")["is_home"]
        .agg(["sum", "count"])
        .reset_index()
    )

    bad_home_away = home_away_check[
        (home_away_check["count"] != 2)
        | (home_away_check["sum"] != 1)
    ]
    team_match_checks.append(
        check_result(
            "invalid_home_away_distribution",
            home_away_check,
            bad_home_away,
            "fct_team_match_structure",
            "distinct_match_id_in_fct_team_match",
            "critical",
        )
    )

    # =========================================================
    # 3. Auditoría semántica
    # =========================================================
    if {"shots", "shots_on_target"}.issubset(fct_team_match.columns):
        bad = fct_team_match[
            safe_num(fct_team_match, "shots_on_target").fillna(0)
            > safe_num(fct_team_match, "shots").fillna(0)
        ]
        semantic_checks.append(
            check_result(
                "shots_on_target_gt_shots",
                fct_team_match,
                bad,
                "fct_team_match_semantic",
                "rows_in_fct_team_match",
                "critical",
            )
        )

    if "possession_pct" in fct_team_match.columns:
        bad = fct_team_match[
            (safe_num(fct_team_match, "possession_pct").fillna(0) < 0)
            | (safe_num(fct_team_match, "possession_pct").fillna(0) > 100)
        ]
        semantic_checks.append(
            check_result(
                "possession_pct_out_of_range",
                fct_team_match,
                bad,
                "fct_team_match_semantic",
                "rows_in_fct_team_match",
                "critical",
            )
        )

    if "pass_accuracy_pct" in fct_team_match.columns:
        bad = fct_team_match[
            (safe_num(fct_team_match, "pass_accuracy_pct").fillna(0) < 0)
            | (safe_num(fct_team_match, "pass_accuracy_pct").fillna(0) > 100)
        ]
        semantic_checks.append(
            check_result(
                "pass_accuracy_pct_out_of_range",
                fct_team_match,
                bad,
                "fct_team_match_semantic",
                "rows_in_fct_team_match",
                "critical",
            )
        )

    # =========================================================
    # 4. Consistencia por partido
    # =========================================================
    if "possession_pct" in fct_team_match.columns:
        possession_sum = (
            fct_team_match.groupby("match_id")["possession_pct"]
            .sum(min_count=1)
            .reset_index(name="possession_sum")
        )

        bad_possession_sum = possession_sum[
            possession_sum["possession_sum"].notna()
            & (~possession_sum["possession_sum"].between(99, 101))
        ]

        pair_checks.append(
            check_result(
                "possession_sum_not_100ish",
                possession_sum,
                bad_possession_sum,
                "fct_team_match_pairwise",
                "distinct_match_id_with_possession",
                "critical",
            )
        )

    # =========================================================
    # 5. Parsing sospechoso por ceros
    # =========================================================
    critical_zero_metrics = [
        "shots",
        "shots_on_target",
        "possession_pct",
        "corners",
        "offsides",
        "fouls_committed",
        "total_passes",
        "pass_accuracy_pct",
    ]

    available_zero_metrics = [c for c in critical_zero_metrics if c in fct_team_match.columns]

    team_match_numeric = fct_team_match.copy()
    for c in available_zero_metrics:
        team_match_numeric[c] = safe_num(team_match_numeric, c)

    team_match_numeric["zero_metric_count"] = (
        team_match_numeric[available_zero_metrics]
        .fillna(np.nan)
        .eq(0)
        .sum(axis=1)
    )

    suspicious_zero_rows = team_match_numeric[
        team_match_numeric["zero_metric_count"] >= 6
    ].copy()

    parsing_checks.append(
        check_result(
            "suspicious_zero_rows_ge_6_metrics",
            team_match_numeric,
            suspicious_zero_rows,
            "parsing_suspicion",
            "rows_in_fct_team_match",
            "critical",
        )
    )

    agg_zero_by_match = (
        team_match_numeric.groupby("match_id")[available_zero_metrics]
        .sum(min_count=1)
        .reset_index()
    )

    all_zero_conditions = pd.Series(True, index=agg_zero_by_match.index)
    for c in available_zero_metrics:
        all_zero_conditions &= agg_zero_by_match[c].fillna(0).eq(0)

    all_zero_stat_profile_match = agg_zero_by_match[all_zero_conditions].copy()
    parsing_checks.append(
        check_result(
            "all_zero_stat_profile_match",
            agg_zero_by_match,
            all_zero_stat_profile_match,
            "parsing_suspicion",
            "distinct_match_id_in_fct_team_match",
            "critical",
        )
    )

    volume_cols = [c for c in ["shots", "shots_on_target", "total_passes"] if c in agg_zero_by_match.columns]
    zero_volume_matches = agg_zero_by_match[
        agg_zero_by_match[volume_cols].fillna(0).sum(axis=1) == 0
    ].copy()

    parsing_checks.append(
        check_result(
            "zero_volume_matches",
            agg_zero_by_match,
            zero_volume_matches,
            "parsing_suspicion",
            "distinct_match_id_in_fct_team_match",
            "critical",
        )
    )

    if "possession_pct" in agg_zero_by_match.columns:
        zero_possession_matches = agg_zero_by_match[
            agg_zero_by_match["possession_pct"].fillna(0) == 0
        ].copy()
    else:
        zero_possession_matches = pd.DataFrame(columns=agg_zero_by_match.columns)

    parsing_checks.append(
        check_result(
            "zero_possession_matches",
            agg_zero_by_match,
            zero_possession_matches,
            "parsing_suspicion",
            "distinct_match_id_in_fct_team_match",
            "critical",
        )
    )

    # =========================================================
    # 6. Consistencia cruzada entre tablas
    # =========================================================
    match_final = fct_match[fct_match["match_status"] == "finished"].copy()
    match_cols = [
        "source_match_id",
        "home_team_name_raw",
        "away_team_name_raw",
        "home_score",
        "away_score",
    ]
    match_final = match_final[match_cols].rename(columns={"source_match_id": "match_id"})

    team_home = (
        fct_team_match[fct_team_match["is_home"] == True][
            ["match_id", "team_name_raw", "goals_for", "goals_against"]
        ]
        .rename(
            columns={
                "team_name_raw": "home_team_teammatch",
                "goals_for": "home_goals_for_teammatch",
                "goals_against": "home_goals_against_teammatch",
            }
        )
    )

    team_away = (
        fct_team_match[fct_team_match["is_home"] == False][
            ["match_id", "team_name_raw", "goals_for", "goals_against"]
        ]
        .rename(
            columns={
                "team_name_raw": "away_team_teammatch",
                "goals_for": "away_goals_for_teammatch",
                "goals_against": "away_goals_against_teammatch",
            }
        )
    )

    cross = (
        match_final
        .merge(team_home, on="match_id", how="left")
        .merge(team_away, on="match_id", how="left")
    )

    cross_mismatch = cross[
        (cross["home_team_name_raw"] != cross["home_team_teammatch"])
        | (cross["away_team_name_raw"] != cross["away_team_teammatch"])
        | (cross["home_score"] != cross["home_goals_for_teammatch"])
        | (cross["away_score"] != cross["away_goals_for_teammatch"])
    ]

    audit_cross_table = pd.DataFrame([
        check_result(
            "cross_table_team_or_score_mismatch",
            match_final,
            cross_mismatch,
            "cross_table_consistency",
            "finished_match_id_in_fct_match",
            "critical",
        )
    ])

    # =========================================================
    # 7. Cobertura y nulls
    # =========================================================
    finished_match_count = fct_match[fct_match["match_status"] == "finished"]["source_match_id"].nunique()
    team_match_covered = fct_team_match["match_id"].nunique()

    coverage_summary = pd.DataFrame([
        {
            "metric": "finished_matches_in_fct_match",
            "value": finished_match_count,
            "notes": "universo finalizado en fct_match",
        },
        {
            "metric": "match_ids_in_fct_team_match",
            "value": team_match_covered,
            "notes": "partidos con detalle en fct_team_match",
        },
        {
            "metric": "coverage_pct",
            "value": pct(team_match_covered, finished_match_count),
            "notes": "cobertura de team_match sobre partidos finalizados",
        },
    ])

    critical_metrics = [
        "goals_for",
        "goals_against",
        "shots",
        "shots_on_target",
        "possession_pct",
        "corners",
        "offsides",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "total_passes",
        "pass_accuracy_pct",
    ]

    available_critical = [c for c in critical_metrics if c in fct_team_match.columns]

    nulls_team_match = (
        fct_team_match[available_critical]
        .isna()
        .sum()
        .reset_index()
    )
    nulls_team_match.columns = ["column_name", "null_count"]
    nulls_team_match["universe_total"] = len(fct_team_match)
    nulls_team_match["null_pct"] = round(
        nulls_team_match["null_count"] / len(fct_team_match) * 100,
        2,
    )
    nulls_team_match = nulls_team_match.sort_values(
        ["null_pct", "null_count"],
        ascending=False,
    )

    # =========================================================
    # 8. Consolidado
    # =========================================================
    audit_summary = pd.concat(
        [
            pd.DataFrame(match_checks),
            pd.DataFrame(team_match_checks),
            pd.DataFrame(semantic_checks),
            pd.DataFrame(pair_checks),
            pd.DataFrame(parsing_checks),
            audit_cross_table,
        ],
        ignore_index=True,
    )

    failed_checks = audit_summary[audit_summary["affected_count"] > 0].copy()
    passed_checks = audit_summary[audit_summary["affected_count"] == 0].copy()

    critical_failed_checks = failed_checks[failed_checks["severity"] == "critical"].copy()
    critical_issue_count = int(len(critical_failed_checks))

    has_cross_mismatch = (failed_checks["issue"] == "cross_table_team_or_score_mismatch").any()
    has_zero_profile_issue = failed_checks["issue"].isin(
        [
            "all_zero_stat_profile_match",
            "zero_volume_matches",
            "zero_possession_matches",
        ]
    ).any()

    coverage_pct_value = float(
        coverage_summary.loc[
            coverage_summary["metric"] == "coverage_pct",
            "value",
        ].iloc[0]
    )

    if critical_issue_count == 0 and coverage_pct_value >= 99:
        readiness = "PASS"
    elif has_zero_profile_issue or has_cross_mismatch:
        readiness = "FAIL"
    elif critical_issue_count <= 5:
        readiness = "PASS WITH WARNINGS"
    else:
        readiness = "FAIL"

    readiness_summary = pd.DataFrame([
        {
            "readiness": readiness,
            "critical_failed_check_count": critical_issue_count,
            "finished_match_coverage_pct": coverage_pct_value,
            "has_cross_mismatch": bool(has_cross_mismatch),
            "has_zero_profile_issue": bool(has_zero_profile_issue),
        }
    ])

    # =========================================================
    # 9. Exportación
    # =========================================================
    write_csv(audit_summary, audit_dir / "audit_summary.csv")
    write_csv(failed_checks, audit_dir / "audit_failed_checks.csv")
    write_csv(passed_checks, audit_dir / "audit_passed_checks.csv")
    write_csv(nulls_team_match, audit_dir / "audit_nulls_by_column.csv")
    write_csv(cardinality, audit_dir / "audit_match_id_cardinality.csv")
    write_csv(cross_mismatch, audit_dir / "audit_cross_table_mismatches.csv")
    write_csv(coverage_summary, audit_dir / "audit_coverage_summary.csv")
    write_csv(readiness_summary, audit_dir / "audit_readiness_summary.csv")
    write_csv(suspicious_zero_rows, audit_dir / "audit_suspicious_zero_rows.csv")
    write_csv(all_zero_stat_profile_match, audit_dir / "audit_all_zero_stat_profile_match.csv")
    write_csv(zero_volume_matches, audit_dir / "audit_zero_volume_matches.csv")
    write_csv(zero_possession_matches, audit_dir / "audit_zero_possession_matches.csv")

    print("Auditoría completada.")
    print(f"fct_match filas: {len(fct_match)}")
    print(f"fct_team_match filas: {len(fct_team_match)}")
    print(f"failed_checks: {len(failed_checks)}")
    print(f"readiness: {readiness}")
    print(f"Output dir: {audit_dir}")