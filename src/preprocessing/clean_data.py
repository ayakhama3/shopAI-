from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, count, lit
import os

# Créer la session Spark
spark = SparkSession.builder \
    .appName("Ecommerce-Recommender-Preprocessing") \
    .config("spark.driver.memory", "2g") \
    .getOrCreate()

spark.sparkContext.setLogLevel("ERROR")

print("✓ Spark démarré !")

# ── Charger les données Retailrocket ──
print("\nChargement des données Retailrocket...")
events = spark.read.csv(
    "data/raw/events.csv",
    header=True,
    inferSchema=True
)

print(f"✓ Events chargés : {events.count()} lignes")
events.printSchema()

# ── Nettoyage ──
print("\nNettoyage en cours...")

# Supprimer les lignes nulles
events_clean = events.dropna(subset=["visitorid", "itemid", "event"])

# Supprimer les doublons
events_clean = events_clean.dropDuplicates(["visitorid", "itemid", "event"])

print(f"✓ Après nettoyage : {events_clean.count()} lignes")

# ── Pondération des interactions ──
print("\nPondération des interactions...")
events_weighted = events_clean.withColumn(
    "weight",
    when(col("event") == "view", 1)
    .when(col("event") == "addtocart", 3)
    .when(col("event") == "transaction", 5)
    .otherwise(1)
)

# ── Statistiques ──
print("\nDistribution des interactions :")
events_weighted.groupBy("event").agg(
    count("*").alias("count")
).show()

# ── Charger Amazon ratings ──
print("Chargement Amazon ratings...")
amazon = spark.read.csv(
    "data/raw/ratings_Beauty.csv",
    header=False,
    inferSchema=True
).toDF("userId", "productId", "rating", "timestamp")

amazon_clean = amazon.dropna().dropDuplicates(["userId", "productId"])
print(f"✓ Amazon ratings : {amazon_clean.count()} lignes")

# ── Sauvegarder en Parquet ──
print("\nSauvegarde en Parquet...")
os.makedirs("data/processed", exist_ok=True)

events_weighted.write.mode("overwrite").parquet("data/processed/events_clean")
amazon_clean.write.mode("overwrite").parquet("data/processed/amazon_clean")

print("✓ Données sauvegardées dans data/processed/")
print("\nPhase 3 terminée !")

spark.stop()