# ⚽ Futbol Analítico - Liga 1 Perú

Este proyecto construye un pipeline analítico local para recolectar, transformar y explorar datos de partidos de la Liga 1 del Perú. El flujo se compone de microservicios en contenedores Docker, orquestados con Docker Compose, y permite mantener un dataset actualizado jornada a jornada.

## 🎯 Objetivo

Transformar datos crudos del sitio FBref en datasets procesados (formato Parquet) que permitan análisis táctico y exploratorio del rendimiento de equipos, tendencias por jornada, métricas por localía, entre otros.

## ⚙️ Tecnologías

- **Python 3.12**
- **Pandas, PyArrow, Requests-HTML, BeautifulSoup4**
- **Apache Spark (PySpark)**
- **Docker & Docker Compose**

> Toda la infraestructura fue desarrollada e implementada utilizando microservicios en Docker.

## 🔁 Pipeline de procesamiento

1. **Scraping con JS Rendering**  
   Se usa `requests-html` (con Pyppeteer) para renderizar las páginas dinámicas de FBref. Se extraen los partidos de cada temporada disponible, incluyendo la actual.

2. **Transformación con PySpark**  
   Se limpia y tipifica el dataset (`Date`, `Score`, `Attendance`, etc.) y se guarda como Parquet particionado por temporada.

3. **Exploración inicial (Notebook)**  
   Se provee un notebook interactivo que carga los `.parquet` para análisis exploratorio y visualización rápida de tendencias.

## 🐳 Uso con Docker Compose

```bash
# Ejecutar el pipeline completo
docker-compose up --build
```

Esto:
- Lanza el scraper (`fbref_scraper.py`)
- Espera a que se generen los `.csv`
- Ejecuta la transformación Spark (`transform_fbref_data.py`)
- Guarda resultados en formato Parquet en `data/processed/fbref/`

## 🧪 Dataset generado (hasta ahora)

- **Temporadas**: 2024, 2025
- **Variables**:
  - `Date`, `Time`, `Home`, `Away`, `Score`, `Attendance`, `Venue`, `Referee`, entre otras.

## 📌 Pendientes / próximos pasos

- Tablero de visualización
- Publicación automática de KPIs por fecha en redes
- Enlace con otras fuentes como Understat para xG (Si es que podemos hacerle scraping jeje)

## 👨‍💻 Autor

Fabio Morante
_Data Engineer & Analista_  
📍 Lima, Perú  