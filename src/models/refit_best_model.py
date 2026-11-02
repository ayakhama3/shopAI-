"""ecommerce-recommender/refit_best_model.py

Réentraîne UNIQUEMENT la meilleure configuration ALS identifiée par le grid
search du 17-18/06/2026 (rank=100, regParam=0.01, maxIter=10, NDCG@10≈0.02046),
sans relancer les 18 runs (12h30 de calcul). Sauvegarde correctement le
modèle avec overwrite() et régénère evaluation_report.json/.html en
réutilisant les résultats déjà connus du log.

À placer à la racine du projet (même niveau que enrich_catalog.py,
create_favorites_table.py) et lancer avec :
    python refit_best_model.py

Conseil : désactive la mise en veille Windows avant de lancer (un run
comparable a pris ~30-40 min, mais un run du grid précédent a mis 6h
probablement à cause d'une mise en veille).
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import logging
from typing import Any, Dict, List

from pyspark.ml.recommendation import ALS

try:
    from src.models.train_als import (
        _configure_spark,
        _load_events,
        _stratified_split_80_20_by_user,
        _save_best_json,
        _generate_html_report,
        _save_and_upload_minio,
        _evaluate_model,
    )
except Exception:
    from models.train_als import (  # type: ignore
        _configure_spark,
        _load_events,
        _stratified_split_80_20_by_user,
        _save_best_json,
        _generate_html_report,
        _save_and_upload_minio,
        _evaluate_model,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("refit_best_model")

BEST_HPARAMS: Dict[str, Any] = {"rank": 100, "regParam": 0.01, "maxIter": 10}

# Résultats des 18 runs du grid search du 17-18/06/2026 (recopiés depuis le
# log), pour que le rapport JSON/HTML final montre le grid complet sans
# avoir à le recalculer.
GRID_LOG_RESULTS: List[Dict[str, Any]] = [
    {"rank": 10, "regParam": 0.01, "maxIter": 10, "metrics": {"rmse": 0.85088, "precision_at_k": 0.00011, "recall_at_k": 0.00097, "ndcg_at_k": 0.00051, "k": 10}},
    {"rank": 10, "regParam": 0.01, "maxIter": 20, "metrics": {"rmse": 0.82286, "precision_at_k": 0.00012, "recall_at_k": 0.00099, "ndcg_at_k": 0.00054, "k": 10}},
    {"rank": 10, "regParam": 0.1, "maxIter": 10, "metrics": {"rmse": 0.76385, "precision_at_k": 0.00013, "recall_at_k": 0.00067, "ndcg_at_k": 0.00037, "k": 10}},
    {"rank": 10, "regParam": 0.1, "maxIter": 20, "metrics": {"rmse": 0.75789, "precision_at_k": 0.00011, "recall_at_k": 0.00052, "ndcg_at_k": 0.00030, "k": 10}},
    {"rank": 10, "regParam": 1.0, "maxIter": 10, "metrics": {"rmse": 1.17798, "precision_at_k": 0.00004, "recall_at_k": 0.00026, "ndcg_at_k": 0.00015, "k": 10}},
    {"rank": 10, "regParam": 1.0, "maxIter": 20, "metrics": {"rmse": 1.17166, "precision_at_k": 0.00003, "recall_at_k": 0.00021, "ndcg_at_k": 0.00012, "k": 10}},
    {"rank": 50, "regParam": 0.01, "maxIter": 10, "metrics": {"rmse": 0.81573, "precision_at_k": 0.00229, "recall_at_k": 0.01778, "ndcg_at_k": 0.01169, "k": 10}},
    {"rank": 50, "regParam": 0.01, "maxIter": 20, "metrics": {"rmse": 0.80319, "precision_at_k": 0.00230, "recall_at_k": 0.01724, "ndcg_at_k": 0.01057, "k": 10}},
    {"rank": 50, "regParam": 0.1, "maxIter": 10, "metrics": {"rmse": 0.76556, "precision_at_k": 0.00063, "recall_at_k": 0.00406, "ndcg_at_k": 0.00254, "k": 10}},
    {"rank": 50, "regParam": 0.1, "maxIter": 20, "metrics": {"rmse": 0.75816, "precision_at_k": 0.00049, "recall_at_k": 0.00290, "ndcg_at_k": 0.00180, "k": 10}},
    {"rank": 50, "regParam": 1.0, "maxIter": 10, "metrics": {"rmse": 1.17769, "precision_at_k": 0.00005, "recall_at_k": 0.00042, "ndcg_at_k": 0.00026, "k": 10}},
    {"rank": 50, "regParam": 1.0, "maxIter": 20, "metrics": {"rmse": 1.17165, "precision_at_k": 0.00003, "recall_at_k": 0.00027, "ndcg_at_k": 0.00019, "k": 10}},
    {"rank": 100, "regParam": 0.01, "maxIter": 10, "metrics": {"rmse": 0.81199, "precision_at_k": 0.00374, "recall_at_k": 0.02819, "ndcg_at_k": 0.02046, "k": 10}},
    {"rank": 100, "regParam": 0.01, "maxIter": 20, "metrics": {"rmse": 0.80250, "precision_at_k": 0.00344, "recall_at_k": 0.02511, "ndcg_at_k": 0.01746, "k": 10}},
    {"rank": 100, "regParam": 0.1, "maxIter": 10, "metrics": {"rmse": 0.76594, "precision_at_k": 0.00077, "recall_at_k": 0.00508, "ndcg_at_k": 0.00315, "k": 10}},
    {"rank": 100, "regParam": 0.1, "maxIter": 20, "metrics": {"rmse": 0.75833, "precision_at_k": 0.00055, "recall_at_k": 0.00329, "ndcg_at_k": 0.00209, "k": 10}},
    {"rank": 100, "regParam": 1.0, "maxIter": 10, "metrics": {"rmse": 1.17774, "precision_at_k": 0.00005, "recall_at_k": 0.00043, "ndcg_at_k": 0.00027, "k": 10}},
    {"rank": 100, "regParam": 1.0, "maxIter": 20, "metrics": {"rmse": 1.17166, "precision_at_k": 0.00003, "recall_at_k": 0.00027, "ndcg_at_k": 0.00019, "k": 10}},
]


def main() -> None:
    spark = _configure_spark()
    logger.info("✓ Spark démarré !")

    df = _load_events(spark)
    logger.info("Interactions totales : %s", df.count())

    # Même split que le grid search original (seed=42) pour rester cohérent
    # avec les métriques déjà loggées.
    train_df, test_df = _stratified_split_80_20_by_user(df, train_ratio=0.8, seed=42)
    logger.info("Train : %s | Test : %s", train_df.count(), test_df.count())
    train_df = train_df.cache()
    test_df = test_df.cache()

    logger.info(
        "Entraînement de la meilleure config : rank=%s | regParam=%s | maxIter=%s",
        BEST_HPARAMS["rank"], BEST_HPARAMS["regParam"], BEST_HPARAMS["maxIter"],
    )

    als = ALS(
        maxIter=int(BEST_HPARAMS["maxIter"]),
        regParam=float(BEST_HPARAMS["regParam"]),
        rank=int(BEST_HPARAMS["rank"]),
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
    logger.info(
        "  (référence log précédent : RMSE=0.81199 | P@10=0.00374 | "
        "R@10=0.02819 | NDCG@10=0.02046 — un léger écart est normal, "
        "ALS n'est pas initialisé avec un seed fixe)"
    )

    # Precision@K pour K=5,10,20 (pour le rapport HTML)
    precisions: Dict[str, float] = {}
    for k in [5, 10, 20]:
        res_k = _evaluate_model(model, test_df, k=k)
        precisions[str(k)] = float(res_k.get("precision_at_k", 0.0))

    best = {
        "rank": BEST_HPARAMS["rank"],
        "regParam": float(BEST_HPARAMS["regParam"]),
        "maxIter": BEST_HPARAMS["maxIter"],
        "metrics": metrics,
        "extra": {"precision_at": precisions},
    }

    # Sauvegarde avec overwrite() — c'est la ligne qui manquait dans
    # train_als.py et qui a fait perdre 12h30 de calcul.
    model_dir = "data/models/als_model"
    os.makedirs("data/models", exist_ok=True)
    model.write().overwrite().save(model_dir)
    logger.info("✓ Modèle sauvegardé (overwrite) : %s", model_dir)

    _save_best_json("data/models/evaluation_report.json", GRID_LOG_RESULTS, best)
    logger.info("✓ Rapport JSON généré : data/models/evaluation_report.json")

    _generate_html_report("data/models/evaluation_report.html", GRID_LOG_RESULTS, best)

    _save_and_upload_minio(model_dir, "data/models/als_model.tar.gz")

    logger.info("✅ Refit terminé ! Redémarre le serveur Flask pour charger le nouveau modèle.")
    spark.stop()


if __name__ == "__main__":
    main()