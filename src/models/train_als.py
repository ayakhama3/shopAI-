"""ecommerce-recommender/src/models/train_als.py

Entraînement d'un recommender ALS (PySpark MLlib) avec grid search.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import tarfile
import logging
from typing import Dict, Any, List, Tuple

from minio import Minio

import findspark
findspark.init()
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col,
    lit,
    when,
    rand,
    row_number,
)
from pyspark.ml.recommendation import ALS

# Utilitaire d'évaluation + génération HTML
try:
    from src.models.evaluate import evaluate_model as _evaluate_model
except Exception:
    from models.evaluate import evaluate_model as _evaluate_model  # type: ignore


# --- Logger ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("train_als")


def _configure_spark() -> SparkSession:
    os.environ["JAVA_HOME"] = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot"
    os.environ["HADOOP_HOME"] = r"C:\hadoop"
    os.environ["PATH"] = (
        os.environ["HADOOP_HOME"] + r"\bin" + os.pathsep +
        os.environ["JAVA_HOME"] + r"\bin" + os.pathsep +
        os.environ.get("PATH", "")
    )

    spark = (
        SparkSession.builder.appName("ALS-Recommender-GridSearch")
        .config("spark.driver.memory", "8g")
        .config("spark.executor.memory", "6g")
        .config("spark.driver.maxResultSize", "4g")
        .config("spark.sql.shuffle.partitions", "50")
        .config("spark.local.dir", "C:/tmp/spark")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.kryoserializer.buffer.max", "512m")
        .config("spark.driver.extraJavaOptions", "-Xss4m -XX:+UseG1GC -XX:G1HeapRegionSize=16m")
        .config("spark.executor.extraJavaOptions", "-Xss4m -XX:+UseG1GC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def _load_events(spark: SparkSession) -> DataFrame:
    logger.info("Chargement des données...")
    events = spark.read.parquet("data/processed/events_clean")

    cols = set(events.columns)

    if "event_type" in cols:
        rating_col = when(col("event_type") == lit("view"), lit(1)).otherwise(
            when(col("event_type") == lit("addtocart"), lit(3)).otherwise(
                when(col("event_type") == lit("transaction"), lit(5)).otherwise(lit(None))
            )
        )
    elif "event" in cols:
        rating_col = when(col("event") == lit("view"), lit(1)).otherwise(
            when(col("event") == lit("addtocart"), lit(3)).otherwise(
                when(col("event") == lit("transaction"), lit(5)).otherwise(lit(None))
            )
        )
    elif "weight" in cols:
        rating_col = col("weight")
    else:
        raise ValueError("events_clean ne contient pas event_type/event/weight")

    df = (
        events.select(
            col("visitorid").alias("userId").cast("int"),
            col("itemid").alias("itemId").cast("int"),
            rating_col.alias("rating"),
        )
        .where(col("userId").isNotNull() & col("itemId").isNotNull())
        .where(col("rating").cast("float").isNotNull())
        .select(col("userId"), col("itemId"), col("rating").cast("float").alias("rating"))
        .dropna()
    )

    return df


def _stratified_split_80_20_by_user(
    df: DataFrame, train_ratio: float = 0.8, seed: int = 42
) -> Tuple[DataFrame, DataFrame]:
    """Split stratifié par utilisateur (80/20)."""

    w = Window.partitionBy("userId").orderBy(rand(seed))
    df_r = df.withColumn("rn", row_number().over(w))
    user_counts = (
        df_r.groupBy("userId")
        .agg({"rn": "max"})
        .withColumnRenamed("max(rn)", "user_n")
    )
    df_r = df_r.join(user_counts, on="userId", how="left")

    df_r = df_r.withColumn(
        "train_n",
        when(col("user_n") <= 1, lit(1)).otherwise(
            (col("user_n") * lit(train_ratio)).cast("int")
        ),
    )
    df_r = df_r.withColumn(
        "is_train",
        when(col("rn") <= col("train_n"), lit(True)).otherwise(lit(False)),
    )

    train_df = df_r.where(col("is_train") == lit(True)).drop("rn", "user_n", "train_n", "is_train")
    test_df = df_r.where(col("is_train") == lit(False)).drop("rn", "user_n", "train_n", "is_train")
    return train_df, test_df


def _grid() -> List[Dict[str, Any]]:
    # NDCG@10 progresse encore nettement de rank=50 à rank=100 (sans signe
    # de plafonnement), et regParam=0.01 gagne systématiquement face à 0.1/1.0.
    # Piste d'amélioration future (non activée par défaut, coûteuse en temps) :
    # ranks = [10, 50, 100, 150] et/ou regparams = [0.001, 0.01, 0.1, 1.0]
    ranks = [10, 50, 100]
    regparams = [0.01, 0.1, 1.0]
    max_iters = [10, 20]
    grid = []
    for r in ranks:
        for rp in regparams:
            for it in max_iters:
                grid.append({"rank": r, "regParam": rp, "maxIter": it})
    return grid


def _save_best_json(
    path: str,
    grid_results: List[Dict[str, Any]],
    best: Dict[str, Any],
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "grid": [
            {
                "rank": r["rank"],
                "regParam": r["regParam"],
                "maxIter": r["maxIter"],
                "metrics": r["metrics"],
            }
            for r in grid_results
        ],
        "best_model": {
            "rank": best["rank"],
            "regParam": best["regParam"],
            "maxIter": best["maxIter"],
            "selection_criterion": "NDCG@10",
            "metrics": best["metrics"],
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _generate_html_report(
    path_html: str,
    grid_results: List[Dict[str, Any]],
    best: Dict[str, Any],
) -> None:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64

    os.makedirs(os.path.dirname(path_html), exist_ok=True)
    report_dir = os.path.dirname(path_html)

    ranks = sorted({r["rank"] for r in grid_results})
    regparams = sorted({r["regParam"] for r in grid_results})

    # --- Courbe RMSE vs rank ---
    rmse_by_rank: Dict[int, List[float]] = {r: [] for r in ranks}
    for res in grid_results:
        rmse_by_rank[res["rank"]].append(float(res["metrics"]["rmse"]))
    rmse_avg = [float(np.mean(rmse_by_rank[r])) if rmse_by_rank[r] else 0.0 for r in ranks]

    fig1, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(ranks, rmse_avg, marker="o", color="#7F77DD")
    ax1.set_title("RMSE vs rank")
    ax1.set_xlabel("rank")
    ax1.set_ylabel("RMSE")
    ax1.grid(True, alpha=0.3)
    fig1.tight_layout()
    rmse_png = os.path.join(report_dir, "rmse_vs_rank.png")
    fig1.savefig(rmse_png, dpi=160)
    plt.close(fig1)

    # --- Heatmap regParam × rank (NDCG@10) ---
    heat = np.zeros((len(regparams), len(ranks)), dtype=float)
    for i, rp in enumerate(regparams):
        for j, rk in enumerate(ranks):
            vals = [
                float(res["metrics"]["ndcg_at_k"])
                for res in grid_results
                if res["regParam"] == rp and res["rank"] == rk
            ]
            heat[i, j] = float(np.mean(vals)) if vals else 0.0

    fig2, ax2 = plt.subplots(figsize=(8, 5.5))
    im = ax2.imshow(heat, aspect="auto", origin="lower", cmap="YlOrRd")
    plt.colorbar(im, ax=ax2, label="NDCG@10")
    ax2.set_xticks(range(len(ranks)))
    ax2.set_xticklabels(ranks)
    ax2.set_yticks(range(len(regparams)))
    ax2.set_yticklabels([str(x) for x in regparams])
    ax2.set_xlabel("rank")
    ax2.set_ylabel("regParam")
    ax2.set_title("Heatmap NDCG@10 (moyenne sur maxIter)")
    fig2.tight_layout()
    heat_png = os.path.join(report_dir, "heatmap_regParam_rank.png")
    fig2.savefig(heat_png, dpi=160)
    plt.close(fig2)

    # --- Bar chart Precision@K pour K=5,10,20 ---
    ks = [5, 10, 20]
    precisions = best.get("extra", {}).get("precision_at", {})
    prec_vals = [float(precisions.get(str(k), 0.0)) for k in ks]

    fig3, ax3 = plt.subplots(figsize=(8, 4.5))
    ax3.bar([f"@{k}" for k in ks], prec_vals, color="#7F77DD")
    ax3.set_title("Precision@K — meilleur modèle")
    ax3.set_xlabel("K")
    ax3.set_ylabel("Precision")
    ax3.grid(True, axis="y", alpha=0.3)
    fig3.tight_layout()
    prec_png = os.path.join(report_dir, "precision_at_k_best.png")
    fig3.savefig(prec_png, dpi=160)
    plt.close(fig3)

    def img_b64(p: str) -> str:
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    m = best["metrics"]

    rows = []
    for res in sorted(grid_results, key=lambda x: x["metrics"]["ndcg_at_k"], reverse=True):
        mm = res["metrics"]
        rows.append(
            f"<tr><td>{res['rank']}</td><td>{res['regParam']}</td><td>{res['maxIter']}</td>"
            f"<td>{float(mm['rmse']):.5f}</td><td>{float(mm['precision_at_k']):.5f}</td>"
            f"<td>{float(mm['recall_at_k']):.5f}</td><td>{float(mm['ndcg_at_k']):.5f}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Évaluation ALS — ShopAI</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 30px; color: #222; }}
    h1 {{ color: #7F77DD; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
    th {{ background: #7F77DD; color: white; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .metric {{ display: inline-block; background: #EEEDFE; border-radius: 8px;
               padding: 10px 20px; margin: 8px; text-align: center; }}
    .metric span {{ display: block; font-size: 22px; font-weight: bold; color: #3C3489; }}
    img {{ max-width: 100%; border: 1px solid #eee; border-radius: 8px; margin: 10px 0; }}
  </style>
</head>
<body>
  <h1>Rapport d'évaluation ALS — ShopAI</h1>

  <h2>Meilleur modèle <small>(critère : max NDCG@10)</small></h2>
  <p>rank={best['rank']} | regParam={best['regParam']} | maxIter={best['maxIter']}</p>

  <div>
    <div class="metric">RMSE<span>{float(m['rmse']):.4f}</span></div>
    <div class="metric">Precision@10<span>{float(m.get('precision_at_k', 0)):.4f}</span></div>
    <div class="metric">Recall@10<span>{float(m.get('recall_at_k', 0)):.4f}</span></div>
    <div class="metric">NDCG@10<span>{float(m.get('ndcg_at_k', 0)):.4f}</span></div>
  </div>

  <h2>Graphiques</h2>
  <h3>Courbe RMSE vs rank</h3>
  <img src="data:image/png;base64,{img_b64(rmse_png)}" alt="RMSE vs rank"/>

  <h3>Heatmap regParam × rank (NDCG@10)</h3>
  <img src="data:image/png;base64,{img_b64(heat_png)}" alt="Heatmap"/>

  <h3>Precision@K — meilleur modèle</h3>
  <img src="data:image/png;base64,{img_b64(prec_png)}" alt="Precision@K"/>

  <h2>Tous les résultats (triés par NDCG@10 décroissant)</h2>
  <table>
    <thead>
      <tr><th>rank</th><th>regParam</th><th>maxIter</th>
          <th>RMSE</th><th>Precision@10</th><th>Recall@10</th><th>NDCG@10</th></tr>
    </thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</body>
</html>"""

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("✓ Rapport HTML généré : %s", path_html)


def _save_and_upload_minio(best_model_path: str, archive_path: str) -> None:
    """Upload MinIO — non bloquant si indisponible."""
    MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

    try:
        # Créer l'archive tar.gz
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(best_model_path, arcname=os.path.basename(best_model_path))

        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        if not client.bucket_exists("models"):
            client.make_bucket("models")

        client.fput_object("models", "als_model.tar.gz", archive_path)
        logger.info("✓ Modèle uploadé vers MinIO : models/als_model.tar.gz")
    except Exception as e:
        logger.warning("⚠️ MinIO indisponible (non bloquant) : %s", e)


def main() -> None:
    spark = _configure_spark()
    logger.info("✓ Spark démarré !")

    df = _load_events(spark)
    logger.info("Interactions totales : %s", df.count())

    train_df, test_df = _stratified_split_80_20_by_user(df, train_ratio=0.8, seed=42)
    logger.info("Train : %s | Test : %s", train_df.count(), test_df.count())

    train_df = train_df.cache()
    test_df = test_df.cache()

    grid = _grid()
    grid_results: List[Dict[str, Any]] = []
    best_ndcg = -1.0
    best_model_metrics: Dict[str, Any] | None = None
    best_model_hparams: Dict[str, Any] | None = None

    for i, params in enumerate(grid, start=1):
        rank = params["rank"]
        regParam = params["regParam"]
        maxIter = params["maxIter"]

        logger.info(
            "[%d/%d] rank=%s | regParam=%s | maxIter=%s",
            i, len(grid), rank, regParam, maxIter,
        )

        als = ALS(
            maxIter=maxIter,
            regParam=float(regParam),
            rank=int(rank),
            userCol="userId",
            itemCol="itemId",
            ratingCol="rating",
            coldStartStrategy="drop",
            nonnegative=True,
        )

        model = als.fit(train_df)
        metrics = _evaluate_model(model, test_df, k=10)

        logger.info(
            "  → RMSE=%.5f | P@10=%.5f | R@10=%.5f | NDCG@10=%.5f",
            float(metrics["rmse"]),
            float(metrics.get("precision_at_k", 0.0)),
            float(metrics.get("recall_at_k", 0.0)),
            float(metrics.get("ndcg_at_k", 0.0)),
        )

        grid_results.append({
            "rank": rank,
            "regParam": float(regParam),
            "maxIter": int(maxIter),
            "metrics": metrics,
        })

        ndcg = float(metrics.get("ndcg_at_k", 0.0))
        if ndcg > best_ndcg:
            best_ndcg = ndcg
            best_model_metrics = metrics
            best_model_hparams = params

    assert best_model_metrics is not None and best_model_hparams is not None

    # Refit du meilleur modèle
    logger.info(
        "Refit meilleur modèle : rank=%s regParam=%s maxIter=%s",
        best_model_hparams["rank"],
        best_model_hparams["regParam"],
        best_model_hparams["maxIter"],
    )
    best_als = ALS(
        maxIter=int(best_model_hparams["maxIter"]),
        regParam=float(best_model_hparams["regParam"]),
        rank=int(best_model_hparams["rank"]),
        userCol="userId",
        itemCol="itemId",
        ratingCol="rating",
        coldStartStrategy="drop",
        nonnegative=True,
    )
    best_model = best_als.fit(train_df)

    # Precision@K pour K=5,10,20
    precisions: Dict[str, float] = {}
    for k in [5, 10, 20]:
        res_k = _evaluate_model(best_model, test_df, k=k)
        precisions[str(k)] = float(res_k.get("precision_at_k", 0.0))

    best = {
        "rank": best_model_hparams["rank"],
        "regParam": float(best_model_hparams["regParam"]),
        "maxIter": best_model_hparams["maxIter"],
        "metrics": best_model_metrics,
        "extra": {"precision_at": precisions},
    }

    # Sauvegarder le modèle
    # IMPORTANT : on utilise write().overwrite() car Spark refuse d'écrire
    # dans un dossier qui existe déjà (c'est ce qui a fait planter le run
    # précédent juste après 12h30 de grid search, sans rien sauvegarder).
    model_dir = "data/models/als_model"
    os.makedirs("data/models", exist_ok=True)
    best_model.write().overwrite().save(model_dir)
    logger.info("✓ Modèle sauvegardé (overwrite) : %s", model_dir)

    # Rapports
    _save_best_json("data/models/evaluation_report.json", grid_results, best)
    logger.info("✓ Rapport JSON généré")

    _generate_html_report("data/models/evaluation_report.html", grid_results, best)

    # MinIO (non bloquant)
    _save_and_upload_minio(model_dir, "data/models/als_model.tar.gz")

    logger.info("✅ Entraînement terminé !")
    spark.stop()


if __name__ == "__main__":
    main()