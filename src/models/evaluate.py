"""src/models/evaluate.py

Évaluation d'un modèle ALS Spark MLlib pour des recommandations e-commerce.

Objectifs:
- Fournir une fonction `evaluate_model(model, test_df, k=10)` qui retourne un dict
  contenant RMSE + Precision@k + Recall@k + NDCG@k.
- Générer un rapport HTML (matplotlib) à partir des résultats d'une grid search.

Hypothèses de format `test_df`:
- Colonnes: userId (int), itemId (int), rating (float)
- `rating` > 0 indique un item "positif" (pertinent) pour l'utilisateur.

Note importante:
- En recommandation top-k, on ne compare pas item à item les scores bruts.
  On calcule des métriques ranking en:
    1) recommandant les k items les plus probables pour chaque user
    2) comparant ces items aux items positifs présents dans le test.
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, List

import numpy as np

import matplotlib
matplotlib.use("Agg")  # garantit que ça marche sans GUI
import matplotlib.pyplot as plt


def _safe_div(n: float, d: float) -> float:
    return float(n) / float(d) if d else 0.0


def precision_recall_ndcg_at_k(recommended_items: List[int], relevant_items: set, k: int) -> tuple:
    """Calcule Precision@k, Recall@k et NDCG@k pour une liste recommandée."""
    recommended_k = recommended_items[:k]
    if not recommended_k:
        return 0.0, 0.0, 0.0

    hits = [1 if item in relevant_items else 0 for item in recommended_k]
    num_hits = sum(hits)

    precision = num_hits / k
    recall = _safe_div(num_hits, len(relevant_items))

    # DCG@k
    dcg = 0.0
    for i, h in enumerate(hits, start=1):
        if h:
            dcg += 1.0 / np.log2(i + 1)

    # IDCG@k: idéalement on aurait min(|relevant|, k) hits au début
    ideal_hits = min(len(relevant_items), k)
    idcg = 0.0
    for i in range(1, ideal_hits + 1):
        idcg += 1.0 / np.log2(i + 1)

    ndcg = _safe_div(dcg, idcg)
    return float(precision), float(recall), float(ndcg)


def evaluate_model(model, test_df, k: int = 10) -> Dict[str, Any]:
    """Évalue un modèle ALS.

    Paramètres:
    - model: modèle ALS Spark (objet ALSModel)
    - test_df: Spark DF avec userId, itemId, rating
    - k: top-k

    Retour:
    dict avec:
      - rmse
      - precision_at_k
      - recall_at_k
      - ndcg_at_k
      - k
      - num_users_eval (nombre d'utilisateurs ayant au moins 1 item positif dans le test)
    """
    # Imports Spark localement (pour ne pas forcer au chargement hors spark)
    from pyspark.ml.evaluation import RegressionEvaluator

    # --- RMSE ---
    # Pour RMSE, on a besoin de prédictions itemwise.
    # ALSModel peut produire des predictions pour (user,item) présents dans test_df.
    preds = model.transform(test_df)
    evaluator = RegressionEvaluator(
        metricName="rmse",
        labelCol="rating",
        predictionCol="prediction",
    )
    rmse = float(evaluator.evaluate(preds))

    # --- Top-k metrics ---
    # On prépare:
    # - relevant_items par user: items avec rating > 0 dans le test
    # - recommendations: model.recommendForUserSubset
    relevant = (
        test_df
        .where(test_df.rating > 0)
        .select("userId", "itemId")
        .distinct()
        .rdd
        .map(lambda row: (int(row["userId"]), int(row["itemId"])))
        .groupByKey()
        .mapValues(lambda items: set(items))
        .collect()
    )
    relevant_by_user = {u: items for u, items in relevant}

    users = list(relevant_by_user.keys())
    if not users:
        return {
            "rmse": rmse,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "k": k,
            "num_users_eval": 0,
        }

    spark = test_df.sql_ctx.sparkSession
    from pyspark.sql import Row

    user_rows = [Row(userId=int(u)) for u in users]
    user_df = spark.createDataFrame(user_rows)

    recs_df = model.recommendForUserSubset(user_df, k)
    recs = recs_df.collect()

    precisions = []
    recalls = []
    ndcgs = []

    for row in recs:
        u = int(row["userId"])
        rec_list = row["recommendations"] or []
        recommended_items = [int(rec["itemId"]) for rec in rec_list]
        relevant_items = relevant_by_user.get(u, set())

        if not relevant_items:
            continue

        p, r, n = precision_recall_ndcg_at_k(recommended_items, relevant_items, k)
        precisions.append(p)
        recalls.append(r)
        ndcgs.append(n)

    num_users_eval = len(precisions)
    precision_at_k = float(np.mean(precisions)) if precisions else 0.0
    recall_at_k = float(np.mean(recalls)) if recalls else 0.0
    ndcg_at_k = float(np.mean(ndcgs)) if ndcgs else 0.0

    return {
        "rmse": rmse,
        "precision_at_k": precision_at_k,
        "recall_at_k": recall_at_k,
        "ndcg_at_k": ndcg_at_k,
        "k": k,
        "num_users_eval": int(num_users_eval),
    }


def generate_html_report(
    grid_results: List[Dict[str, Any]],
    best_result: Dict[str, Any],
    output_path: str,
) -> None:
    """Génère un rapport HTML avec graphes.

    grid_results: liste de dicts contenant au minimum:
      - rank
      - regParam
      - maxIter
      - metrics: {rmse, precision_at_k, recall_at_k, ndcg_at_k}

    best_result: dict avec hyperparams + metrics
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Préparation arrays
    ranks = sorted({r["rank"] for r in grid_results})
    regparams = sorted({r["regParam"] for r in grid_results})

    # RMSE vs rank (moyenné sur regParam & maxIter pour lisibilité)
    rmse_by_rank = {r: [] for r in ranks}
    for res in grid_results:
        rmse_by_rank[res["rank"]].append(res["metrics"]["rmse"])
    rmse_avg = [float(np.mean(rmse_by_rank[r])) if rmse_by_rank[r] else None for r in ranks]

    # Heatmap regParam vs rank pour NDCG@10 (moyenné sur maxIter)
    heat = np.zeros((len(regparams), len(ranks)), dtype=float)
    for i, rp in enumerate(regparams):
        for j, rk in enumerate(ranks):
            vals = [
                res["metrics"]["ndcg_at_k"]
                for res in grid_results
                if res["regParam"] == rp and res["rank"] == rk
            ]
            heat[i, j] = float(np.mean(vals)) if vals else 0.0

    # --- Graphiques ---
    fig1 = plt.figure(figsize=(8, 4.5))
    plt.plot(ranks, rmse_avg, marker="o")
    plt.title("RMSE vs rank (moyenne sur regParam/maxIter)")
    plt.xlabel("rank")
    plt.ylabel("RMSE")
    plt.grid(True, alpha=0.3)

    rmse_png = os.path.join(os.path.dirname(output_path), "rmse_vs_rank.png")
    fig1.tight_layout()
    fig1.savefig(rmse_png, dpi=160)
    plt.close(fig1)

    fig2 = plt.figure(figsize=(8, 5.5))
    im = plt.imshow(heat, aspect="auto", origin="lower")
    plt.colorbar(im, label="NDCG@10")
    plt.xticks(range(len(ranks)), ranks)
    plt.yticks(range(len(regparams)), [str(x) for x in regparams])
    plt.xlabel("rank")
    plt.ylabel("regParam")
    plt.title("Heatmap NDCG@10 (moyenne sur maxIter)")

    heat_png = os.path.join(os.path.dirname(output_path), "heatmap_regParam_rank.png")
    fig2.tight_layout()
    fig2.savefig(heat_png, dpi=160)
    plt.close(fig2)

    # Conversion images en base64 pour un HTML autonome (évite problèmes de chemins)
    import base64

    def _img_to_b64(p: str) -> str:
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    rmse_b64 = _img_to_b64(rmse_png)
    heat_b64 = _img_to_b64(heat_png)

    # --- Table results ---
    rows_html = []
    for res in sorted(grid_results, key=lambda x: x["metrics"]["ndcg_at_k"], reverse=True):
        m = res["metrics"]
        rows_html.append(
            "<tr>"
            f"<td>{res['rank']}</td>"
            f"<td>{res['regParam']}</td>"
            f"<td>{res['maxIter']}</td>"
            f"<td>{m['rmse']:.5f}</td>"
            f"<td>{m['precision_at_k']:.5f}</td>"
            f"<td>{m['recall_at_k']:.5f}</td>"
            f"<td>{m['ndcg_at_k']:.5f}</td>"
            "</tr>"
        )

    best = best_result
    best_metrics = best["metrics"]

    best_html = (
        f"<p><b>Meilleur modèle</b> (sélection: max NDCG@{best_metrics.get('k', 10)}):</p>"
        f"<ul>"
        f"<li>rank: {best.get('rank')}</li>"
        f"<li>regParam: {best.get('regParam')}</li>"
        f"<li>maxIter: {best.get('maxIter')}</li>"
        f"<li>RMSE: {best_metrics['rmse']:.5f}</li>"
        f"<li>Precision@{best_metrics.get('k', 10)}: {best_metrics['precision_at_k']:.5f}</li>"
        f"<li>Recall@{best_metrics.get('k', 10)}: {best_metrics['recall_at_k']:.5f}</li>"
        f"<li>NDCG@{best_metrics.get('k', 10)}: {best_metrics['ndcg_at_k']:.5f}</li>"
        f"</ul>"
    )

    # --- HTML final ---
    html = f"""<!DOCTYPE html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\">
  <title>Évaluation ALS - ShopAI</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
    th {{ background: #f2f2f2; }}
    .grid img {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <h1>Évaluation ALS (Grid Search)</h1>
  {best_html}

  <h2>Graphes</h2>
  <div class=\"grid\">
    <h3>RMSE vs rank</h3>
    <img alt=\"RMSE vs rank\" src=\"data:image/png;base64,{rmse_b64}\">

    <h3>Heatmap regParam vs rank (NDCG@10)</h3>
    <img alt=\"Heatmap NDCG\" src=\"data:image/png;base64,{heat_b64}\">
  </div>

  <h2>Résultats (triés par NDCG décroissant)</h2>
  <table>
    <thead>
      <tr>
        <th>rank</th>
        <th>regParam</th>
        <th>maxIter</th>
        <th>RMSE</th>
        <th>Precision@{best_metrics.get('k', 10)}</th>
        <th>Recall@{best_metrics.get('k', 10)}</th>
        <th>NDCG@{best_metrics.get('k', 10)}</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


