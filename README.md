# ShopAI — Recommender System (Data & AI)

Projet PFA (Ingénieur Data & AI) : un système de recommandation **e-commerce** end-to-end, intégrant **données → entraînement ALS → évaluation ranking → refit → déploiement via API** et une stratégie **cold-start hybride**.

> Objectif : recommander des produits pertinents à chaque utilisateur et fournir un mécanisme robuste et démontrable pour une soutenance.

---

## 1. Vue d’ensemble du système

Le système est composé de 3 briques principales :

1. **Pipeline de données**
   - Ingestion et nettoyage (dataset d’événements / interactions)
   - Transformation en **signal implicite** utilisable par un modèle de recommandation

2. **Modèle de recommandation**
   - **ALS (Alternating Least Squares)** en **PySpark MLlib** pour filtrage collaboratif
   - Entraînement avec **grid search** sur des hyperparamètres clés
   - Choix du meilleur modèle selon une métrique ranking (NDCG@10)

3. **Évaluation & Déploiement**
   - Évaluation offline : **RMSE + Precision@K + Recall@K + NDCG@K**
   - Génération de rapports : JSON + HTML + courbes
   - Déploiement : chargement modèle **lazy**, API Flask, fallback si modèle indisponible

---

## 2. Pourquoi ALS ? (concept)

ALS est un modèle de **filtrage collaboratif** basé sur une factorisation de matrice :

- On modélise chaque utilisateur et chaque item par des vecteurs latents.
- La prédiction score(u, i) provient du produit scalaire des facteurs.
- En e-commerce, on dispose souvent d’**interactions implicites** (vue, ajout au panier, achat) plutôt que de notes explicites.

Dans ce projet, ALS est donc un choix naturel :
- rapide à entraîner sur Spark
- robuste en cold-start relatif (avec stratégie hybride)
- compatible avec une recommandation top-K.

---

## 3. Transformation des événements en signal d’entraînement

Dans `src/models/train_als.py` :

- Les données proviennent de `data/processed/events_clean`.
- Les colonnes d’événements (selon schéma : `event_type` / `event` / `weight`) sont converties en `rating`.

Exemple d’idée (implémentée dans le code) :
- `view` → rating = 1
- `addtocart` → rating = 3
- `transaction` → rating = 5
- sinon : `weight` si disponible

On obtient ensuite un DataFrame au format ALS :
- **userId**
- **itemId**
- **rating (float)**

---

## 4. Split train/test (rigueur expérimentale)

Toujours dans `src/models/train_als.py` :

- Split **stratifié par utilisateur** (80/20)
- Pour chaque user, on choisit aléatoirement un sous-ensemble interactions pour le test.

Pourquoi c’est important à dire en soutenance :
- évite les “fuites” temporelles/ID
- garantit que l’évaluation reflète réellement la capacité à recommander des items à partir de l’historique de chaque user.

---

## 5. Entraînement ALS avec Grid Search

Dans `src/models/train_als.py` :

- Grid search sur :
  - `rank` (dimension des facteurs latents)
  - `regParam` (régularisation)
  - `maxIter` (itérations de l’optimisation)
- Cold-start strategy ALS :
  - `coldStartStrategy="drop"`
- Contrainte positive :
  - `nonnegative=True`

Ensuite :
- on entraîne `ALS.fit(train_df)`
- on évalue le modèle sur `test_df`
- on conserve le modèle qui maximise **NDCG@10**.

---

## 6. Évaluation : métriques ranking top-K

Dans `src/models/evaluate.py` :

### 6.1 RMSE
- RMSE est calculé via `RegressionEvaluator` sur `model.transform(test_df)`.

### 6.2 Metrics ranking
L’évaluation top-K est construite ainsi :

1. On extrait pour chaque user les **items pertinents** du test : `rating > 0`.
2. On demande au modèle une recommandation **top-K** via `recommendForUserSubset`.
3. On calcule :
   - **Precision@K** : proportion de hits dans les K
   - **Recall@K** : proportion des pertinents récupérés
   - **NDCG@K** : pertinence ordonnée (positions dans le top-K)

Pourquoi c’est un point fort :
- un recommender doit être jugé sur la qualité de classement, pas uniquement sur RMSE.

---

## 7. Refit du meilleur modèle

Après grid search :

- le meilleur modèle (selon NDCG@10) est **refit** sur le `train_df`.
- cela donne un modèle final prêt pour le service.

---

## 8. Génération de preuves expérimentales (rapports)

Dans `src/models/train_als.py`, le projet produit :

- `data/models/evaluation_report.json`
- `data/models/evaluation_report.html`
- des graphes (plots) :
  - `rmse_vs_rank.png`
  - `heatmap_regParam_rank.png`
  - `precision_at_k_best.png`

Ce que tu peux dire au jury :
> “J’ai produit une documentation automatique des résultats pour justifier le choix des hyperparamètres.”

---

## 9. Déploiement & robustesse d’inférence

### 9.1 Chargement lazy
Dans `src/recommender.py` :

- Le chargement Spark/modèle est fait via un singleton **lazy**.
- Résultat : le serveur Flask ne plante pas au démarrage si Spark/modèle n’est pas disponible.

### 9.2 Gestion du modèle (local + MinIO)
Toujours dans `src/recommender.py` :
- Si `data/models/als_model` n’existe pas :
  - tentative de téléchargement depuis **MinIO** (`als_model.tar.gz`)

### 9.3 Fallback produits
- Si le modèle ALS échoue :
  - le système retourne une liste de produits de démonstration.

Point fort à mentionner : **le système est résilient**, ce qui est crucial en soutenance démo.

---

## 10. Cold-start : solution hybride (onboarding + seeds)

Dans `src/api/main.py` :

- Si l’utilisateur a des préférences (onboarding) mais peu/pas d’interactions “réelles”,
  - on recommande via des règles : catégories choisies → produits seed.
- Quand les signaux d’interactions existent,
  - on passe aux recommandations ALS.

Pourquoi c’est fort :
- le cold-start est un problème central en recommandation
- tu montres une stratégie hybride pragmatique orientée expérience utilisateur.

---

## 11. Intégration produit : API Flask

Le recommender est exposé via des endpoints, notamment :

- `GET /api/recommendations/<int:user_id>`
- `GET /api/recommendations/me`

L’API intègre aussi :
- sauvegarde des interactions `POST /api/interactions`
- mécanismes de favoris / panier (pour enrichir l’écosystème)

Point fort “engineering” : tu as fait le pont entre modèle et application.

---

## 12. Faits concrets à dire pendant ta soutenance

1. **ALS pour filtrage collaboratif implicite**
2. **Grid search** sur `rank/regParam/maxIter`
3. **Split par utilisateur 80/20** (évaluation fiable)
4. **Évaluation ranking** : Precision@K, Recall@K, NDCG@K
5. **Choix du meilleur modèle via NDCG@10** + refit
6. **Preuves** : JSON/HTML + graphes générés
7. **Déploiement robuste** : lazy init + fallback + support MinIO
8. **Cold-start hybride** : onboarding → seeds → ALS
9. **Intégration** : API Flask + logique produit

---

## 13. Commandes utiles (à adapter selon ton environnement)

### Entraîner le modèle
```bash
python -m src.models.train_als
```

### Évaluer / produire les rapports
- inclus dans le script d’entraînement (generate JSON + HTML + PNG)

---

## 14. Résultats et artefacts

- `data/models/evaluation_report.json`
- `data/models/evaluation_report.html`
- `data/models/*.png`
- `data/models/als_model/` (modèle sauvegardé)

Ces artefacts constituent la base de tes captures pendant la soutenance.

