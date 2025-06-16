FROM bitnami/spark:3.5

WORKDIR /app

COPY scripts/transform/fbref_transformer.py /app/fbref_transformer.py
COPY data /app/data

RUN pip install pyspark

CMD ["spark-submit", "--master", "local[*]", "fbref_transformer.py"]
