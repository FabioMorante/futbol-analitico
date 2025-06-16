from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split, to_date, trim
import os

def main():
    spark = SparkSession.builder \
        .appName("FBRef Match Transformer") \
        .getOrCreate()

    raw_path = "data/raw/fbref"
    processed_path = "data/processed/fbref"

    # Listar archivos CSV
    csv_files = [f for f in os.listdir(raw_path) if f.endswith(".csv")]

    for file in csv_files:
        season = file.replace("matches_", "").replace(".csv", "")
        full_path = os.path.join(raw_path, file)

        print(f"Procesando temporada {season}...")

        df = spark.read.option("header", True).csv(full_path)

        # Limpieza básica
        df_clean = df.withColumn("Date", to_date(col("Date"), "yyyy-MM-dd")) \
                     .withColumn("Home_Goals", split(col("Score"), "–").getItem(0).cast("int")) \
                     .withColumn("Away_Goals", split(col("Score"), "–").getItem(1).cast("int")) \
                     .withColumn("Home", trim(col("Home"))) \
                     .withColumn("Away", trim(col("Away"))) \
                     .drop("Match Report", "Notes")

        output_dir = os.path.join(processed_path, f"season_{season}")
        df_clean.write.mode("overwrite").parquet(output_dir)
        print(f"Temporada {season} guardada en {output_dir}")

    spark.stop()

if __name__ == "__main__":
    main()
