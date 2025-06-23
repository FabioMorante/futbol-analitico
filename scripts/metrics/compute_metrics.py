from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, lit, row_number, sum as _sum, lag, count
from pyspark.sql.window import Window
import os

def main():
    spark = SparkSession.builder \
        .appName("FBRef Advanced Metrics") \
        .getOrCreate()

    input_path = "data/processed/fbref"
    output_path = "data/metrics/fbref"

    seasons = [d for d in os.listdir(input_path) if d.startswith("season_")]

    for season_dir in seasons:
        season = season_dir.split("_")[1]
        season_path = os.path.join(input_path, season_dir)

        print(f"Procesando métricas para temporada {season}...")

        df = spark.read.parquet(season_path)

        # Expandimos los datos por equipo-local y equipo-visitante
        home_df = df.select(
            col("Date"),
            col("Home").alias("Team"),
            col("Away").alias("Opponent"),
            col("Home_Goals").alias("GF"),
            col("Away_Goals").alias("GA"),
        ).withColumn("Venue", lit("Home"))

        away_df = df.select(
            col("Date"),
            col("Away").alias("Team"),
            col("Home").alias("Opponent"),
            col("Away_Goals").alias("GF"),
            col("Home_Goals").alias("GA"),
        ).withColumn("Venue", lit("Away"))

        matches = home_df.unionByName(away_df)

        matches = matches.withColumn("GD", col("GF") - col("GA"))
        matches = matches.withColumn(
            "Result",
            when(col("GF") > col("GA"), lit("W"))
            .when(col("GF") < col("GA"), lit("L"))
            .otherwise(lit("D"))
        )
        matches = matches.withColumn(
            "Points",
            when(col("Result") == "W", lit(3))
            .when(col("Result") == "D", lit(1))
            .otherwise(lit(0))
        )

        window_spec = Window.partitionBy("Team").orderBy("Date")

        matches = matches.withColumn("Matchday", row_number().over(window_spec))
        matches = matches.withColumn("CumulativePoints", _sum("Points").over(window_spec))

        # Acumulamos rachas: WWDL...
        matches = matches.withColumn("Streak",
            _sum(when(col("Result") == "W", lit(1)).otherwise(0)).over(window_spec.rowsBetween(Window.unboundedPreceding, 0))
        )

        # Métrica adicional: efectividad local vs visitante
        effectiveness = matches.groupBy("Team", "Venue").agg(
            _sum("Points").alias("TotalPoints"),
            count("Points").alias("GamesPlayed")
        ).withColumn("PointsPerGame", col("TotalPoints") / col("GamesPlayed"))

        output_dir = os.path.join(output_path, f"season_{season}")
        matches.write.mode("overwrite").parquet(output_dir)
        effectiveness.write.mode("overwrite").parquet(os.path.join(output_dir, "effectiveness_by_venue"))

        print(f"Métricas guardadas en {output_dir}")

    spark.stop()

if __name__ == "__main__":
    main()
