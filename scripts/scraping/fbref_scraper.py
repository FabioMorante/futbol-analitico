import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from utils.logger import get_logger
from requests_html import HTMLSession

logger = get_logger("scraper")

BASE_URL = "https://fbref.com"
LEAGUE_URL = "https://fbref.com/en/comps/44/history/Liga-1-Seasons"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0 Safari/537.36"
}


def fetch_season_urls():
    logger.info("Buscando temporadas con requests-html...")
    session = HTMLSession()
    r = session.get(LEAGUE_URL)
    logger.info(f"Status code del request: {r.status_code}")

    try:
        r.html.render(timeout=20)
        logger.info("Página renderizada con JavaScript.")
    except Exception as e:
        logger.warning(f"Error al renderizar JS: {e}")

    html = r.html.html
    with open("temp_rendered.html", "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Archivo temp_rendered.html guardado para inspección.")

    seasons_table = r.html.find("#seasons", first=True)
    if not seasons_table:
        logger.warning("No se encontró la tabla con id 'seasons' tras render.")
        return {}

    rows = seasons_table.find("tbody > tr")
    urls = {}
    for row in rows:
        season_cell = row.find("th[data-stat='year_id']", first=True)
        if not season_cell:
            continue
        link = season_cell.find("a", first=True)
        if not link:
            continue
        season_text = link.text.strip()
        if "Liga-1" in link.attrs.get("href", ""):
            if season_text == rows[0].find("th[data-stat='year_id']", first=True).text.strip():
                # Temporada actual
                fixture_url = "https://fbref.com/en/comps/44/schedule/Liga-1-Scores-and-Fixtures"
            else:
                # Temporadas anteriores
                fixture_url = f"https://fbref.com/en/comps/44/{season_text}/schedule/{season_text}-Liga-1-Scores-and-Fixtures"
            urls[season_text] = fixture_url

    logger.info(f"Temporadas encontradas: {list(urls.keys())}")
    return urls


def fetch_match_data(season_url, season):
    logger.info(f"Descargando partidos desde {season_url}")
    try:
        response = requests.get(season_url, headers=HEADERS)
        if response.status_code != 200:
            logger.warning(f"Request fallido con status {response.status_code}")
            return pd.DataFrame()
        soup = BeautifulSoup(response.content, "lxml")
        table_id = "sched_2025_44_1" if season == "2025" else "sched_all"
        match_table = soup.find("table", id=table_id)
        if not match_table:
            logger.warning(f"No se encontró tabla de partidos con id '{table_id}'.")
            return pd.DataFrame()
        df = pd.read_html(str(match_table))[0]
        df = df.dropna(subset=["Date"])
        df = df[df["Score"].notna()]
        return df
    except Exception as e:
        logger.warning(f"Error al extraer tabla: {e}")
        return pd.DataFrame()

def save_data(df, season):
    OUTPUT_DIR = "/app/data/raw/fbref/"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"matches_{season}.csv")
    df.to_csv(path, index=False)
    logger.info(f"Temporada {season} guardada en {path}")

def main():
    urls = fetch_season_urls()
    for season, url in urls.items():
        if "2024" in season or "2025" in season:
            df = fetch_match_data(url, season)
            if not df.empty:
                save_data(df, season)

if __name__ == "__main__":
    main()