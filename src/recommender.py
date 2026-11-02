"""
src/recommender.py

Moteur de recommandation ALS pour ShopAI.

CORRECTIONS APPLIQUÉES :
1. Singleton lazy : Spark ne démarre QU'À LA PREMIÈRE REQUÊTE, jamais au
   chargement du module. Flask ne plante plus au démarrage même si Spark
   ou le modèle est indisponible.
2. USER_ID_OFFSET : les user_id Flask (1, 2, 3…) sont décalés de 10 000 000
   avant d'être envoyés à ALS, pour éviter la collision silencieuse avec les
   visitorid Retailrocket (qui incluent aussi des petits entiers).
3. Logging explicite : les erreurs sont toujours loggées, jamais avalées
   silencieusement.
4. _format_item retourne uniquement l'item_id et le score ALS — c'est
   _resolve_als_products() dans main.py qui fait le vrai lookup en base.
"""
import os
import sys
import tarfile
import logging

logger = logging.getLogger("shopai.recommender")

MODEL_DIR = os.path.join('data', 'models', 'als_model')

# Les user_id Flask (1, 2, 3...) chevauchent les visitorid Retailrocket.
# Ce décalage garantit qu'un utilisateur Flask n'obtient jamais par accident
# les recommandations d'un visiteur anonyme du dataset d'entraînement.
USER_ID_OFFSET = 10_000_000

# Singleton lazy
_engine_instance = None


def get_engine():
    """Retourne le singleton RecommendationEngine, en le créant si besoin."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RecommendationEngine()
    return _engine_instance


FALLBACK_PRODUCTS = [
    {
        'id': 1,
        'nom': 'Écouteurs Premium',
        'prix': 249.99,
        'categorie': 'Tech',
        'image': 'https://placehold.co/200x200?text=Audio',
        'note': 4.8,
        'score': 95,
        'raison': 'Populaire dans votre catégorie préférée',
    },
    {
        'id': 2,
        'nom': 'Sneakers Tendance',
        'prix': 149.99,
        'categorie': 'Mode',
        'image': 'https://placehold.co/200x200?text=Mode',
        'note': 4.6,
        'score': 88,
        'raison': 'Tendance cette semaine',
    },
    {
        'id': 3,
        'nom': 'Laptop Pro',
        'prix': 1999.99,
        'categorie': 'Tech',
        'image': 'https://placehold.co/200x200?text=Laptop',
        'note': 4.9,
        'score': 92,
        'raison': 'Les clients comme vous ont aussi acheté',
    },
    {
        'id': 4,
        'nom': 'Lampe de bureau LED',
        'prix': 49.99,
        'categorie': 'Maison',
        'image': 'https://placehold.co/200x200?text=Maison',
        'note': 4.5,
        'score': 81,
        'raison': 'Complète votre achat précédent',
    },
    {
        'id': 5,
        'nom': 'Montre connectée',
        'prix': 299.99,
        'categorie': 'Tech',
        'image': 'https://placehold.co/200x200?text=Watch',
        'note': 4.7,
        'score': 90,
        'raison': 'Basé sur votre historique de navigation',
    },
]


class RecommendationEngine:
    def __init__(self):
        self.model = None
        self.spark = None
        self.model_available = False
        self._try_load()

    def _try_load(self):
        if not os.path.exists(MODEL_DIR):
            logger.info("Modèle ALS absent localement, tentative MinIO...")
            self._try_download_from_minio()

        if os.path.exists(MODEL_DIR):
            try:
                os.environ.setdefault('PYSPARK_PYTHON', sys.executable)
                os.environ.setdefault('PYSPARK_DRIVER_PYTHON', sys.executable)
                java_home = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot"
                hadoop_home = r"C:\hadoop"
                if os.path.exists(java_home):
                    os.environ.setdefault("JAVA_HOME", java_home)
                if os.path.exists(hadoop_home):
                    os.environ.setdefault("HADOOP_HOME", hadoop_home)
                    os.environ["PATH"] = (
                        os.path.join(hadoop_home, "bin") + os.pathsep +
                        os.environ.get("PATH", "")
                    )

                import findspark
                findspark.init()

                from pyspark.sql import SparkSession
                from pyspark.ml.recommendation import ALSModel

                self.spark = (
                    SparkSession.builder
                    .appName('ShopAI-RecommendationEngine')
                    .config("spark.driver.memory", "4g")
                    .config("spark.sql.shuffle.partitions", "10")
                    .config("spark.local.dir", "C:/tmp/spark")
                    .getOrCreate()
                )
                self.spark.sparkContext.setLogLevel("ERROR")
                self.model = ALSModel.load(MODEL_DIR)
                self.model_available = True
                logger.info("Modèle ALS chargé depuis %s", MODEL_DIR)
            except Exception as e:
                logger.warning("Impossible de charger le modèle ALS : %s", e)
                self.model_available = False
        else:
            logger.warning(
                "Dossier modèle ALS introuvable (%s). "
                "Lance refit_best_model.py pour entraîner et sauvegarder le modèle.",
                MODEL_DIR,
            )
            self.model_available = False

    def _try_download_from_minio(self):
        try:
            from minio import Minio
            MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT',  'localhost:9000')
            MINIO_ACCESS   = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
            MINIO_SECRET   = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
            MINIO_SECURE   = os.environ.get('MINIO_SECURE', 'false').lower() in ('1','true','yes')
            client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=MINIO_SECURE)
            if client.bucket_exists('models'):
                archive_path = os.path.join('data', 'models', 'als_model.tar.gz')
                os.makedirs(os.path.dirname(MODEL_DIR), exist_ok=True)
                client.fget_object('models', 'als_model.tar.gz', archive_path)
                with tarfile.open(archive_path, 'r:gz') as tar:
                    tar.extractall(path=os.path.join('data', 'models'))
                logger.info("Modèle téléchargé depuis MinIO")
        except Exception as e:
            logger.warning("MinIO indisponible : %s", e)

    def get_recommendations(self, user_id: int, n: int = 10):
        if self.model_available:
            try:
                return self._get_als_recommendations(user_id, n)
            except Exception as e:
                logger.warning("ALS a échoué pour user_id=%s : %s", user_id, e)
        return self._get_fallback_recommendations(user_id, n)

    def _get_als_recommendations(self, user_id: int, n: int):
        from pyspark.sql import Row
        if self.model is None or self.spark is None:
            raise RuntimeError('Modèle ALS non chargé')

        als_user_id = int(user_id) + USER_ID_OFFSET
        user_df = self.spark.createDataFrame([Row(userId=als_user_id)])
        recs_df = self.model.recommendForUserSubset(user_df, n)
        recs = recs_df.collect()
        if not recs:
            raise RuntimeError(f'Aucune recommandation ALS pour als_user_id={als_user_id}')

        recommendations = []
        for row in recs:
            for rec in row.recommendations:
                recommendations.append({
                    'itemId': int(rec.itemId),
                    'score':  round(float(rec.rating), 4),
                    'raison': 'Recommandé par le modèle ALS',
                    'source': 'als',
                })
        return recommendations

    def _get_fallback_recommendations(self, user_id: int, n: int):
        idx = int(user_id) % len(FALLBACK_PRODUCTS) if user_id else 0
        products = FALLBACK_PRODUCTS[idx:] + FALLBACK_PRODUCTS[:idx]
        return [dict(p, source='fallback') for p in products[:n]]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    print('Model available:', engine.model_available)
    print(engine.get_recommendations(1, 3))
    