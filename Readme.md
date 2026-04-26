# futbol-analitico

Pipeline local y reproducible para construir una base analítica de la Liga 1 de Perú a partir de scraping multi-fuente.

El proyecto está en refactor completo. La primera versión funcional del nuevo core se enfoca en extracción y auditoría de calidad para dos modelos base:

- `fct_match`
- `fct_team_match`

La fuente principal actual es **PromediosInfo**. **BeSoccer** se usa como fallback selectivo cuando PromediosInfo no entrega estadísticas de detalle o devuelve placeholders en cero.

---

## Objetivo del proyecto

Construir una plataforma analítica reproducible para evaluar rendimiento competitivo y perfil estadístico de equipos de Liga 1.

El MVP busca responder preguntas como:

- qué equipos suman más puntos por partido
- qué equipos rinden mejor de local vs visita
- qué equipos llegan en mejor forma reciente
- qué equipos generan más remates y remates al arco
- qué equipos convierten mejor sus remates en goles
- qué equipos dominan más la posesión y el pase
- qué equipos tienen perfil más directo
- qué equipos cometen más faltas o reciben más tarjetas
- qué equipos mejoran o empeoran por tramo de temporada

El proyecto **no** pretende todavía hacer análisis táctico profundo, xG, mapas de tiro, tracking, redes de pase o scouting individual robusto.

---

## Estado actual

### Implementado

- Extracción de partidos por jornada desde PromediosInfo.
- Construcción de `fct_match`.
- Extracción de estadísticas de detalle desde PromediosInfo.
- Construcción de `fct_team_match`.
- Detección de partidos con estadísticas faltantes o placeholders en cero.
- Fallback selectivo desde BeSoccer para partidos problemáticos.
- Auditoría de calidad sobre outputs intermedios.
- Exportación local de CSVs en `data/interim/` y `data/audit/`.

### Pendiente

- Normalización de entidades y nombres de equipos.
- Construcción de capa curated.
- Métricas derivadas.
- Agregados por equipo, temporada y forma reciente.
- Dashboard web.
- Dockerización final del flujo.

---

## Arquitectura actual

```text
futbol-analitico/
  config/
    settings.yaml
    teams.yaml

  data/
    raw/
    interim/
    audit/
    curated/

  notebooks/
    exploration/
    debugging/
    validation/

  src/futbol_analitico/
    extract/
      promedios_showround.py
      promedios_match_detail.py
      besoccer_fallback.py
      pipeline_extract.py

    audit/
      pipeline_audit.py

    normalize/
    analytics/
    dashboard/

    utils/
      http.py
      io.py
      paths.py

  scripts/
    run_extract.py
    run_audit.py
    run_normalize.py
    run_analytics.py
    run_dashboard.py

  docker/
    base/
      Dockerfile

  tests/
```

---

## Fuentes

### PromediosInfo

Fuente principal para:

- jornadas
- partidos
- marcadores
- tarjetas
- estadísticas de detalle cuando están disponibles

PromediosInfo permite obtener partidos por jornada mediante el endpoint `showRound`.

### BeSoccer

Fuente fallback para:

- partidos donde PromediosInfo no entrega bloque de estadísticas
- partidos donde PromediosInfo devuelve estadísticas en cero que representan ausencia de dato, no valores reales

BeSoccer se consulta mediante el endpoint AJAX de jornadas:

```text
https://www.besoccer.com/ajax/getCompetitionRounds
```

y luego se extraen estadísticas desde el bloque de detalle:

```html
<div class="panel detail-match-stats general-stats" data-cy="stats">
```

---

## Modelos generados

### `fct_match`

Una fila por partido detectado.

Campos principales:

- `competition_id`
- `round_number`
- `round_name`
- `match_date`
- `home_team_name_raw`
- `away_team_name_raw`
- `home_score`
- `away_score`
- `match_status`
- `home_yellow_cards`
- `away_yellow_cards`
- `home_red_cards`
- `away_red_cards`
- `source_match_id`
- `source_match_href`

Output:

```text
data/interim/fct_match.csv
```

### `fct_team_match`

Dos filas por partido con estadísticas a nivel equipo-partido.

Campos principales:

- `match_id`
- `team_name_raw`
- `opponent_team_name_raw`
- `is_home`
- `goals_for`
- `goals_against`
- `shots`
- `shots_on_target`
- `possession_pct`
- `corners`
- `offsides`
- `fouls_committed`
- `yellow_cards`
- `red_cards`
- `total_passes`
- `pass_accuracy_pct`
- `detail_stats_source`
- `detail_stats_status`

Output:

```text
data/interim/fct_team_match.csv
```

### Fallback log

Registro de partidos donde se intentó fallback desde BeSoccer.

Output:

```text
data/interim/fct_team_match_fallback_log.csv
```

---

## Instalación local

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Si prefieres instalar desde `requirements.txt`:

```bash
pip install -r requirements.txt
pip install -e .
```

---

## Configuración

La configuración principal vive en:

```text
config/settings.yaml
```

Incluye:

- competición
- temporada
- endpoints
- rango de jornadas
- user agent
- rutas de datos

Ejemplo de parámetros relevantes:

```yaml
project:
  competition_id: PER_LIGA1
  competition_name: Liga 1
  country: Peru
  season: 2026

scraping:
  league_id: 281
  round_from: 1
  round_to: 17
  timeout_seconds: 30
```

---

## Ejecución

### 1. Ejecutar extracción

```bash
python scripts/run_extract.py
```

Genera:

```text
data/interim/fct_match.csv
data/interim/fct_team_match.csv
data/interim/fct_team_match_failures.csv
data/interim/fct_team_match_besoccer_fallback.csv
data/interim/fct_team_match_fallback_log.csv
```

### 2. Ejecutar auditoría

```bash
python scripts/run_audit.py
```

Genera:

```text
data/audit/audit_summary.csv
data/audit/audit_failed_checks.csv
data/audit/audit_passed_checks.csv
data/audit/audit_nulls_by_column.csv
data/audit/audit_cross_table_mismatches.csv
data/audit/audit_coverage_summary.csv
data/audit/audit_readiness_summary.csv
data/audit/audit_suspicious_zero_rows.csv
data/audit/audit_all_zero_stat_profile_match.csv
data/audit/audit_zero_volume_matches.csv
data/audit/audit_zero_possession_matches.csv
```

---

## Auditoría de calidad

La auditoría valida:

- unicidad de partidos
- cardinalidad de `fct_team_match`
- una fila local y una visitante por partido
- consistencia de goles entre modelos
- rangos válidos para posesión y precisión de pase
- `shots_on_target <= shots`
- cobertura de partidos finalizados
- perfiles sospechosos con todas las estadísticas en cero
- diferencias entre `fct_match` y `fct_team_match`

El resumen final se encuentra en:

```text
data/audit/audit_readiness_summary.csv
```

Valores posibles:

- `PASS`
- `PASS WITH WARNINGS`
- `FAIL`

---

## Política de calidad de datos

No se debe confundir dato faltante con valor cero.

Reglas actuales:

- Si PromediosInfo entrega estadísticas válidas, se usan.
- Si PromediosInfo no entrega estadísticas, se intenta fallback con BeSoccer.
- Si PromediosInfo entrega todas las métricas clave en cero, se trata como placeholder y se intenta fallback.
- Si BeSoccer recupera el partido, las estadísticas se cargan con `detail_stats_source = besoccer`.
- Si ninguna fuente recupera estadísticas válidas, el partido debe quedar documentado en failures o con flag de calidad en fases posteriores.

---

## Notebooks

Los notebooks no son el flujo operativo principal. Se usan solo para:

- exploración
- debugging
- validación de fuentes
- pruebas de fallback

La lógica oficial debe vivir en `src/` y ejecutarse desde `scripts/`.

---

## Datos versionados

Los outputs generados no deben versionarse en Git.

Se recomienda mantener únicamente la estructura de carpetas con `.gitkeep`:

```text
data/raw/.gitkeep
data/interim/.gitkeep
data/audit/.gitkeep
data/curated/.gitkeep
```

Los CSVs generados en `data/` y `outputs/` deben permanecer ignorados.

---

## Roadmap inmediato

### Fase 1 — Extraction core

Estado: completado.

- PromediosInfo como fuente primaria
- BeSoccer como fallback selectivo
- outputs intermedios
- auditoría reproducible

### Fase 2 — Normalización

Próximo paso.

Objetivo:

- nombres canónicos de equipos
- tipado consistente
- columnas finales limpias
- `fct_match_curated`
- `fct_team_match_curated`

### Fase 3 — Analytics

Objetivo:

- `team_match_analytics`
- `team_season_profile`
- `team_form_last5`
- splits local/visita

### Fase 4 — Dashboard

Objetivo:

- dashboard web local
- lectura desde capa curated/analytics
- despliegue contenedorizado

---

## Comandos útiles

```bash
python scripts/run_extract.py
python scripts/run_audit.py
```

Para revisar archivos generados:

```bash
ls data/interim
ls data/audit
```
