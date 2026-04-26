# futbol-analitico

Proyecto local de scraping y análisis de datos de la Liga 1 de Perú.

Construye dos modelos base:

- `fct_match`: partidos, fechas, equipos, marcador y tarjetas.
- `fct_team_match`: estadísticas por equipo-partido, como remates, posesión, pases, faltas y tarjetas.

La fuente principal es PromediosInfo. BeSoccer se usa como fallback cuando PromediosInfo no trae estadísticas válidas.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Ejecutar extracción

```bash
python scripts/run_extract.py
```

Genera archivos en:

```text
data/interim/
```

## Ejecutar auditoría

```bash
python scripts/run_audit.py
```

Genera archivos en:

```text
data/audit/
```

## Documentación

Más documentación, notas técnicas y actualizaciones de desarrollo estarán disponibles en:

https://retropipeline.dev/
