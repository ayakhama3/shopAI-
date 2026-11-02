"""
ShopAI - Migration SQLite -> PostgreSQL (Neon).
Usage : python Migrate.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

import sqlite3
from sqlalchemy import create_engine, text

SQLITE_PATH = "data/processed/shopai.db"
POSTGRES_URL = os.environ.get('DATABASE_URL', '').replace('-pooler', '')

if not POSTGRES_URL:
    print("ERREUR : DATABASE_URL manquant dans .env")
    sys.exit(1)

TABLES_ORDER = [
    'users', 'products', 'interactions', 'cart_items',
    'recommendation_logs', 'user_preferences',
    'invoices', 'orders', 'order_tracking', 'favorites',
]

# Tables sans FK — Flask/SQLAlchemy gere l'integrite applicativement.
# On evite ainsi tout probleme de privilege ou d'ordre d'insertion.
DDL = [
    """CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, username VARCHAR(128) UNIQUE NOT NULL,
        email VARCHAR(256) UNIQUE, password VARCHAR(256) NOT NULL,
        role VARCHAR(32) DEFAULT 'user', created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY, external_id VARCHAR(128),
        name VARCHAR(512), price FLOAT, category VARCHAR(128),
        product_metadata TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS interactions (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL, event_type VARCHAR(64) NOT NULL,
        timestamp TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS cart_items (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL, quantity INTEGER DEFAULT 1,
        added_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_user_product_cart UNIQUE (user_id, product_id)
    )""",
    """CREATE TABLE IF NOT EXISTS recommendation_logs (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        products TEXT, source VARCHAR(64), created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS user_preferences (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        category VARCHAR(128) NOT NULL, created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_user_preference_category UNIQUE (user_id, category)
    )""",
    """CREATE TABLE IF NOT EXISTS invoices (
        id SERIAL PRIMARY KEY, user_id INTEGER, order_id INTEGER,
        invoice_number VARCHAR(64) UNIQUE, status VARCHAR(64) DEFAULT 'pending',
        pdf_url TEXT, created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY, user_id INTEGER, items TEXT,
        total FLOAT DEFAULT 0.0, status VARCHAR(64) DEFAULT 'created',
        created_at TIMESTAMP DEFAULT NOW(), invoice_id INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS order_tracking (
        id SERIAL PRIMARY KEY, user_id INTEGER, order_id INTEGER NOT NULL UNIQUE,
        tracking_number VARCHAR(64) UNIQUE, carrier VARCHAR(128),
        status VARCHAR(64) DEFAULT 'created', last_location VARCHAR(256),
        last_lat FLOAT, last_lng FLOAT, timeline TEXT,
        created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_user_product_favorite UNIQUE (user_id, product_id)
    )""",
]


def get_sqlite_conn():
    if not os.path.exists(SQLITE_PATH):
        print(f"ERREUR : SQLite introuvable : {SQLITE_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def run(sqlite_conn, engine):
    # On utilise psycopg2 directement pour avoir un controle total
    raw = engine.raw_connection()
    cur = raw.cursor()

    try:
        # ── 1. Creer les tables ───────────────────────────────────────────
        # Supprimer les tables existantes (qui ont des FK des tentatives precedentes)
        print("Suppression des anciennes tables...")
        drop_order = ['favorites','order_tracking','orders','invoices',
                      'user_preferences','recommendation_logs','cart_items',
                      'interactions','products','users']
        for t in drop_order:
            cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
        raw.commit()

        print("Creation des tables (sans FK)...")
        for ddl in DDL:
            cur.execute(ddl)
        raw.commit()

        # Verification
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        found = [r[0] for r in cur.fetchall()]
        print(f"  Tables : {', '.join(found)}\n")

        # ── 2. Migrer table par table ─────────────────────────────────────
        print("Migration des donnees...")
        total = 0
        sc = sqlite_conn.cursor()

        for table in TABLES_ORDER:
            try:
                sc.execute(f"SELECT * FROM {table}")
            except sqlite3.OperationalError:
                print(f"  [SKIP] '{table}' absent de SQLite.")
                continue

            rows = sc.fetchall()
            if not rows:
                print(f"  [VIDE] '{table}'")
                continue

            cols = list(rows[0].keys())
            cols_sql = ', '.join([f'"{c}"' for c in cols])
            placeholders = ', '.join(['%s'] * len(cols))
            sql = (f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})'
                   f' ON CONFLICT DO NOTHING')

            count = 0
            for row in rows:
                cur.execute(sql, [row[c] for c in cols])
                count += 1

            raw.commit()
            print(f"  [OK] '{table}' : {count} lignes.")
            total += count

        # ── 3. Sequences ──────────────────────────────────────────────────
        print("\nMise a jour des sequences...")
        for table in TABLES_ORDER:
            try:
                cur.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM "{table}"), 1)
                    )
                """)
                raw.commit()
                print(f"  [OK] '{table}'")
            except Exception as e:
                raw.rollback()
                print(f"  [SKIP] '{table}' : {e}")

        # ── 4. Verification ───────────────────────────────────────────────
        print("\n--- Verification ---")
        sc2 = sqlite_conn.cursor()
        all_ok = True
        for table in TABLES_ORDER:
            try:
                sc2.execute(f"SELECT COUNT(*) FROM {table}")
                n_sqlite = sc2.fetchone()[0]
            except Exception:
                n_sqlite = 0
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                n_pg = cur.fetchone()[0]
            except Exception:
                n_pg = 0
            ok = "OK" if n_sqlite == n_pg else "MISMATCH"
            if ok != "OK":
                all_ok = False
            print(f"  {table:25s} SQLite={n_sqlite:5d}  PG={n_pg:5d}  [{ok}]")

        return total, all_ok

    finally:
        cur.close()
        raw.close()


def main():
    print("=" * 70)
    print("ShopAI - Migration SQLite -> PostgreSQL (Neon)")
    print("=" * 70)

    sqlite_conn = get_sqlite_conn()
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print("Connexion PostgreSQL OK.\n")
    except Exception as e:
        print(f"ERREUR connexion : {e}")
        sys.exit(1)

    total, all_ok = run(sqlite_conn, engine)
    sqlite_conn.close()
    engine.dispose()

    print("\n" + "=" * 70)
    if all_ok:
        print(f"MIGRATION REUSSIE — {total} lignes copiees.")
        print("Prochaine etape : ajouter DATABASE_URL dans main.py.")
    else:
        print("ATTENTION : des MISMATCH ont ete detectes.")
    print("=" * 70)


if __name__ == '__main__':
    main()