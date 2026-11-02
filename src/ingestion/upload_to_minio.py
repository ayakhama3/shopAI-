from minio import Minio
import os
import tarfile

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
MINIO_SECURE = os.environ.get('MINIO_SECURE', 'false').lower() in ('1', 'true', 'yes')

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

RAW_FILES = [
    ("data/raw/events.csv", "retailrocket/events.csv"),
    ("data/raw/category_tree.csv", "retailrocket/category_tree.csv"),
    ("data/raw/item_properties_part1.csv", "retailrocket/item_properties_part1.csv"),
    ("data/raw/item_properties_part2.csv", "retailrocket/item_properties_part2.csv"),
    ("data/raw/ratings_Beauty.csv", "amazon/ratings_Beauty.csv"),
    ("data/raw/Reviews.csv", "amazon/Reviews.csv"),
]

PROCESSED_DIRS = [
    ("data/processed/events_clean", "retailrocket/events_clean/"),
    ("data/processed/amazon_clean", "amazon/amazon_clean/"),
]

MODEL_DIR = "data/models/als_model"
MODEL_ARCHIVE = "data/models/als_model.tar.gz"

BUCKETS = ["raw-data", "processed-data", "models"]


def ensure_buckets():
    for b in BUCKETS:
        try:
            if not client.bucket_exists(b):
                client.make_bucket(b)
                print(f"Création du bucket : {b}")
        except Exception as e:
            print(f"Erreur bucket {b} : {e}")


def upload_raw():
    for local_path, object_name in RAW_FILES:
        if not os.path.exists(local_path):
            print(f"✗ Fichier non trouvé : {local_path}")
            continue
        try:
            client.fput_object('raw-data', object_name, local_path)
            print(f"✓ raw-data/{object_name} uploadé")
        except Exception as e:
            print(f"✗ Erreur upload raw {object_name} : {e}")


def upload_processed():
    for local_dir, prefix in PROCESSED_DIRS:
        if not os.path.exists(local_dir):
            print(f"✗ Dossier non trouvé : {local_dir}")
            continue
        for root, _, files in os.walk(local_dir):
            for fname in files:
                local_path = os.path.join(root, fname)
                # object name inside bucket
                rel = os.path.relpath(local_path, local_dir)
                object_name = os.path.join(prefix, rel).replace('\\', '/')
                try:
                    client.fput_object('processed-data', object_name, local_path)
                    print(f"✓ processed-data/{object_name} uploadé")
                except Exception as e:
                    print(f"✗ Erreur upload processed {object_name} : {e}")


def upload_model():
    if not os.path.exists(MODEL_DIR):
        print(f"✗ Modèle introuvable : {MODEL_DIR}")
        return
    # Create archive
    try:
        with tarfile.open(MODEL_ARCHIVE, "w:gz") as tar:
            tar.add(MODEL_DIR, arcname=os.path.basename(MODEL_DIR))
        client.fput_object('models', 'als_model.tar.gz', MODEL_ARCHIVE)
        print("✓ Modèle uploadé : models/als_model.tar.gz")
    except Exception as e:
        print(f"✗ Erreur upload modèle : {e}")


def main():
    print("Début de l'upload vers MinIO...")
    print(f"Connexion MinIO : {MINIO_ENDPOINT} (secure={MINIO_SECURE})")
    ensure_buckets()
    upload_raw()
    upload_processed()
    upload_model()
    print("\nTerminé !")


if __name__ == '__main__':
    main()