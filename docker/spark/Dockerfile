FROM bitnami/spark:3.5

WORKDIR /app

COPY scripts/transform/fbref_transformer.py /app/fbref_transformer.py
COPY scripts/metrics/compute_metrics.py /app/compute_metrics.py
COPY data /app/data

RUN pip install pyspark

CMD spark-submit --master local[*] fbref_transformer.py && \
    spark-submit --master local[*] compute_metrics.py
