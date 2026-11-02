"""
Dashboard analytique ShopAI.

Application Streamlit professionnelle pour suivre les donnees e-commerce,
les recommandations et les metriques du modele ML.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# -----------------------------------------------------------------------------
# Configuration generale
# -----------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"

DB_PATH = Path(os.getenv("SHOPAI_DB_PATH", PROCESSED_DIR / "shopai.db"))
API_BASE_URL = os.getenv("SHOPAI_API_URL", "http://127.0.0.1:8000").rstrip("/")
PRIMARY_COLOR = "#7F77DD"

EVENT_WEIGHTS = {
    "view": 1,
    "addtocart": 3,
    "add_to_cart": 3,
    "cart": 3,
    "transaction": 5,
    "purchase": 5,
}


st.set_page_config(
    page_title="ShopAI Analytics",
    page_icon="SA",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_theme() -> None:
    """Ajoute un style leger pour un rendu dashboard propre."""
    st.markdown(
        f"""
        <style>
        :root {{
            --shopai-primary: {PRIMARY_COLOR};
        }}
        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #f7f6ff 0%, #ffffff 100%);
            border-right: 1px solid #e7e5ff;
        }}
        .shopai-title {{
            font-size: 1.8rem;
            font-weight: 800;
            color: #1f2340;
            margin-bottom: 0.1rem;
        }}
        .shopai-subtitle {{
            color: #6b7280;
            margin-bottom: 1rem;
        }}
        div[data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid #ecebff;
            border-left: 5px solid var(--shopai-primary);
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 12px 30px rgba(31, 35, 64, 0.06);
        }}
        .stButton > button {{
            border-radius: 8px;
            border: 1px solid var(--shopai-primary);
            color: white;
            background: var(--shopai-primary);
            font-weight: 700;
        }}
        .stDownloadButton > button {{
            border-radius: 8px;
            border: 1px solid var(--shopai-primary);
            color: var(--shopai-primary);
            background: white;
            font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_theme()


# -----------------------------------------------------------------------------
# Helpers donnees
# -----------------------------------------------------------------------------


def empty_frame(columns: list[str]) -> pd.DataFrame:
    """Retourne un DataFrame vide avec colonnes stables."""
    return pd.DataFrame(columns=columns)


def sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Verifie qu'une table existe dans SQLite."""
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    return conn.execute(query, (table_name,)).fetchone() is not None


@st.cache_data(ttl=60)
def load_sqlite_tables(db_path: str) -> dict[str, pd.DataFrame]:
    """Charge les tables principales depuis SQLite avec gestion DB vide."""
    tables = {
        "users": empty_frame(["id", "username", "email", "role", "created_at"]),
        "products": empty_frame(["id", "external_id", "name", "price", "category"]),
        "interactions": empty_frame(["id", "user_id", "product_id", "event_type", "timestamp"]),
        "recommendation_logs": empty_frame(["id", "user_id", "products", "source", "created_at"]),
    }

    path = Path(db_path)
    if not path.exists():
        return tables

    try:
        with sqlite3.connect(path) as conn:
            for table_name in tables:
                if sqlite_table_exists(conn, table_name):
                    tables[table_name] = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    except Exception as exc:
        st.warning(f"Impossible de lire la base SQLite: {exc}")

    return tables


@st.cache_data(ttl=120)
def load_clean_interactions(processed_dir: str) -> pd.DataFrame:
    """Charge les interactions Parquet nettoyees si disponibles."""
    base = Path(processed_dir)
    candidates = [base / "events_clean", base / "amazon_clean"]
    frames: list[pd.DataFrame] = []

    for folder in candidates:
        if not folder.exists():
            continue
        try:
            parquet_files = [p for p in folder.glob("*.parquet") if not p.name.startswith(".")]
            if parquet_files:
                frames.append(pd.concat((pd.read_parquet(p) for p in parquet_files), ignore_index=True))
        except Exception:
            # Si pyarrow/fastparquet manque, on garde SQLite comme source fiable.
            continue

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def normalize_interactions(interactions: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes et types des interactions."""
    if interactions.empty:
        return empty_frame(["id", "user_id", "product_id", "event_type", "timestamp", "date"])

    df = interactions.copy()

    rename_map = {
        "userId": "user_id",
        "user": "user_id",
        "visitorid": "user_id",
        "itemid": "product_id",
        "productId": "product_id",
        "event": "event_type",
        "eventType": "event_type",
        "datetime": "timestamp",
        "time": "timestamp",
    }
    df = df.rename(columns={old: new for old, new in rename_map.items() if old in df.columns})

    for col in ["user_id", "product_id", "event_type", "timestamp"]:
        if col not in df.columns:
            df[col] = np.nan

    df["event_type"] = df["event_type"].fillna("view").astype(str).str.lower()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["timestamp"] = df["timestamp"].fillna(pd.Timestamp.utcnow().tz_localize(None))
    df["date"] = df["timestamp"].dt.date
    return df


def filter_by_date(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Filtre un DataFrame sur une plage de dates si la colonne date existe."""
    if df.empty or "date" not in df.columns:
        return df
    return df[(df["date"] >= start) & (df["date"] <= end)].copy()


def get_interactions_source(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Combine SQLite et Parquet avec preference SQLite si elle contient des donnees."""
    sqlite_interactions = normalize_interactions(tables["interactions"])
    if not sqlite_interactions.empty:
        return sqlite_interactions
    return normalize_interactions(load_clean_interactions(str(PROCESSED_DIR)))


def product_label_map(products: pd.DataFrame) -> dict[Any, str]:
    """Cree un mapping id produit vers nom lisible."""
    if products.empty or "id" not in products.columns:
        return {}
    name_col = "name" if "name" in products.columns else "external_id"
    return dict(zip(products["id"], products[name_col].fillna("Produit")))


def product_category_map(products: pd.DataFrame) -> dict[Any, str]:
    """Cree un mapping id produit vers categorie."""
    if products.empty or "id" not in products.columns or "category" not in products.columns:
        return {}
    return dict(zip(products["id"], products["category"].fillna("Non categorise")))


def conversion_rate(interactions: pd.DataFrame) -> float:
    """Calcule transaction / view en pourcentage."""
    if interactions.empty:
        return 0.0
    events = interactions["event_type"].astype(str).str.lower()
    views = int(events.eq("view").sum())
    transactions = int(events.isin(["transaction", "purchase"]).sum())
    return round((transactions / views) * 100, 2) if views else 0.0


def load_evaluation_report() -> dict[str, Any]:
    """Charge le rapport ML avec fallback vers metrics.json."""
    for filename in ["evaluation_report.json", "metrics.json"]:
        path = MODELS_DIR / filename
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def metric_value(report: dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    """Recupere une metrique avec plusieurs noms possibles."""
    for key in keys:
        if key in report:
            try:
                return float(report[key])
            except Exception:
                return default
    return default


def parse_retrain_log() -> pd.DataFrame:
    """Extrait l'evolution RMSE depuis retrain_log.txt si elle existe."""
    log_path = MODELS_DIR / "retrain_log.txt"
    if not log_path.exists():
        return empty_frame(["training", "rmse"])

    rows = []
    rmse_pattern = re.compile(r"rmse[^0-9]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
    for index, line in enumerate(log_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        match = rmse_pattern.search(line)
        if match:
            rows.append({"training": index, "rmse": float(match.group(1))})

    return pd.DataFrame(rows) if rows else empty_frame(["training", "rmse"])


def best_hyperparameters(report: dict[str, Any]) -> pd.DataFrame:
    """Retourne les hyperparametres du meilleur modele."""
    params = (
        report.get("best_params")
        or report.get("best_hyperparameters")
        or report.get("hyperparameters")
        or {}
    )
    if not isinstance(params, dict) or not params:
        params = {
            "algorithm": "ALS",
            "rank": "Non renseigne",
            "regParam": "Non renseigne",
            "maxIter": "Non renseigne",
            "implicitPrefs": "Non renseigne",
        }
    return pd.DataFrame([{"parametre": key, "valeur": value} for key, value in params.items()])


def api_get(path: str, token: str | None = None, timeout: int = 8) -> tuple[bool, Any]:
    """Effectue un GET API avec gestion d'erreur lisible."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.get(f"{API_BASE_URL}{path}", headers=headers, timeout=timeout)
        data = response.json() if response.content else {}
        return response.ok, data
    except Exception as exc:
        return False, {"error": str(exc)}


def api_post(path: str, token: str | None = None, timeout: int = 10) -> tuple[bool, Any]:
    """Effectue un POST API avec gestion d'erreur lisible."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.post(f"{API_BASE_URL}{path}", headers=headers, timeout=timeout)
        data = response.json() if response.content else {}
        return response.ok, data
    except Exception as exc:
        return False, {"error": str(exc)}


def themed_chart(fig):
    """Applique le theme Plotly ShopAI."""
    fig.update_layout(
        template="plotly_white",
        colorway=[PRIMARY_COLOR, "#19A7CE", "#F59E0B", "#10B981", "#EF4444"],
        margin=dict(l=20, r=20, t=45, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    return fig


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------


def render_sidebar() -> tuple[str, date, date, str]:
    """Affiche la sidebar et retourne les choix utilisateur."""
    st.sidebar.markdown('<div class="shopai-title">ShopAI</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="shopai-subtitle">Analytics & Recommandations</div>', unsafe_allow_html=True)

    page = st.sidebar.radio(
        "Navigation",
        ["Vue Generale", "Recommandations", "Modele ML", "Utilisateurs"],
        label_visibility="collapsed",
    )

    default_end = date.today()
    default_start = default_end - timedelta(days=30)
    selected_range = st.sidebar.date_input(
        "Plage de dates",
        value=(default_start, default_end),
        max_value=default_end,
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = default_start, default_end

    st.sidebar.divider()
    st.sidebar.caption(f"API Flask: `{API_BASE_URL}`")
    token = st.sidebar.text_input(
        "Token admin JWT (optionnel)",
        value=os.getenv("SHOPAI_ADMIN_TOKEN", ""),
        type="password",
        help="Necessaire si /api/admin/retrain est protege.",
    )

    if st.sidebar.button("Reentrainer le modele", use_container_width=True):
        with st.sidebar.spinner("Appel API en cours..."):
            ok, payload = api_post("/api/admin/retrain", token=token or None)
        if ok:
            st.sidebar.success(payload.get("message", "Reentrainement lance."))
        else:
            st.sidebar.error(payload.get("error", "Echec du reentrainement."))

    return page, start_date, end_date, token


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


def render_overview(
    users: pd.DataFrame,
    products: pd.DataFrame,
    interactions: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> None:
    """Page Vue Generale."""
    st.title("Vue Generale")
    st.caption("Synthese des donnees e-commerce et activite utilisateur.")

    filtered = filter_by_date(interactions, start_date, end_date)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nb Utilisateurs", f"{len(users):,}".replace(",", " "))
    c2.metric("Nb Produits", f"{len(products):,}".replace(",", " "))
    c3.metric("Nb Interactions", f"{len(filtered):,}".replace(",", " "))
    c4.metric("Taux de conversion", f"{conversion_rate(filtered):.2f}%")

    if filtered.empty:
        st.info("Aucune interaction disponible sur cette plage de dates.")
        return

    daily = (
        filtered.groupby("date", as_index=False)
        .size()
        .rename(columns={"size": "interactions"})
        .sort_values("date")
        .tail(30)
    )
    fig_daily = px.line(daily, x="date", y="interactions", markers=True, title="Evolution des interactions par jour")
    fig_daily.update_traces(line_color=PRIMARY_COLOR)
    st.plotly_chart(themed_chart(fig_daily), use_container_width=True)

    left, right = st.columns(2)
    event_counts = filtered["event_type"].value_counts().reset_index()
    event_counts.columns = ["event_type", "count"]
    fig_pie = px.pie(
        event_counts,
        values="count",
        names="event_type",
        hole=0.45,
        title="Repartition des evenements",
    )
    left.plotly_chart(themed_chart(fig_pie), use_container_width=True)

    product_names = product_label_map(products)
    top_products = (
        filtered.groupby("product_id", as_index=False)
        .size()
        .rename(columns={"size": "interactions"})
        .sort_values("interactions", ascending=False)
        .head(10)
    )
    top_products["produit"] = top_products["product_id"].map(product_names).fillna(top_products["product_id"].astype(str))
    fig_bar = px.bar(
        top_products,
        x="interactions",
        y="produit",
        orientation="h",
        title="Top 10 produits les plus interactes",
        color="interactions",
        color_continuous_scale=["#E8E6FF", PRIMARY_COLOR],
    )
    fig_bar.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
    right.plotly_chart(themed_chart(fig_bar), use_container_width=True)


def render_recommendations(users: pd.DataFrame, products: pd.DataFrame, interactions: pd.DataFrame) -> None:
    """Page Recommandations."""
    st.title("Recommandations")
    st.caption("Inspection des recommandations et de la matrice utilisateurs x produits.")

    user_ids = sorted(users["id"].dropna().astype(int).unique().tolist()) if not users.empty and "id" in users else [1]
    selected_user = st.selectbox("Selectionner un user_id", user_ids)

    ok, payload = api_get(f"/api/recommandations/{selected_user}")
    if ok:
        raw_products = payload.get("produits", [])
        rows = []
        for index, product in enumerate(raw_products[:10], start=1):
            rows.append(
                {
                    "produit": product.get("nom") or product.get("name") or product.get("title") or f"Produit {index}",
                    "score": product.get("score", product.get("rating", product.get("note", np.nan))),
                    "categorie": product.get("categorie") or product.get("category") or "Non categorise",
                    "raison": product.get("raison") or product.get("reason") or payload.get("source", "recommandation"),
                }
            )
        recs = pd.DataFrame(rows)
        st.dataframe(recs, use_container_width=True, hide_index=True)
    else:
        st.error(payload.get("error", "Impossible de charger les recommandations depuis l'API."))

    st.subheader("Heatmap utilisateurs x produits")
    if interactions.empty:
        st.info("Aucune interaction disponible pour construire la heatmap.")
        return

    matrix_source = interactions.copy()
    matrix_source["weight"] = matrix_source["event_type"].map(EVENT_WEIGHTS).fillna(1)
    sample_users = matrix_source["user_id"].dropna().astype(str).unique()[:20]
    sample_products = matrix_source["product_id"].dropna().astype(str).unique()[:20]
    sample = matrix_source[
        matrix_source["user_id"].astype(str).isin(sample_users)
        & matrix_source["product_id"].astype(str).isin(sample_products)
    ]
    pivot = sample.pivot_table(index="user_id", columns="product_id", values="weight", aggfunc="sum", fill_value=0)

    if pivot.empty:
        st.info("Pas assez de donnees pour afficher une heatmap.")
        return

    fig_heatmap = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale=["#F7F6FF", PRIMARY_COLOR],
        title="Matrice d'intensite des interactions",
    )
    st.plotly_chart(themed_chart(fig_heatmap), use_container_width=True)


def render_model_page() -> None:
    """Page Modele ML."""
    st.title("Modele ML")
    st.caption("Suivi des metriques ALS et des rapports d'evaluation.")

    report = load_evaluation_report()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("RMSE", f"{metric_value(report, 'rmse', 'RMSE', default=0.0):.4f}")
    c2.metric("Precision@10", f"{metric_value(report, 'precision_at_10', 'precision@10', 'Precision@10', default=0.0):.4f}")
    c3.metric("Recall@10", f"{metric_value(report, 'recall_at_10', 'recall@10', 'Recall@10', default=0.0):.4f}")
    c4.metric("NDCG@10", f"{metric_value(report, 'ndcg_at_10', 'ndcg@10', 'NDCG@10', default=0.0):.4f}")

    rmse_history = parse_retrain_log()
    if rmse_history.empty:
        st.info("Aucun historique RMSE trouve dans data/models/retrain_log.txt.")
    else:
        fig_rmse = px.line(rmse_history, x="training", y="rmse", markers=True, title="Evolution RMSE au fil des entrainements")
        fig_rmse.update_traces(line_color=PRIMARY_COLOR)
        st.plotly_chart(themed_chart(fig_rmse), use_container_width=True)

    st.subheader("Hyperparametres du meilleur modele")
    st.dataframe(best_hyperparameters(report), use_container_width=True, hide_index=True)

    report_bytes = json.dumps(report or {"message": "Aucun rapport disponible"}, indent=2, ensure_ascii=False).encode("utf-8")
    st.download_button(
        "Telecharger le rapport d'evaluation complet",
        data=report_bytes,
        file_name="evaluation_report.json",
        mime="application/json",
        use_container_width=True,
    )


def render_users_page(users: pd.DataFrame, products: pd.DataFrame, interactions: pd.DataFrame) -> None:
    """Page Utilisateurs."""
    st.title("Utilisateurs")
    st.caption("Segmentation comportementale et activite par utilisateur.")

    if interactions.empty:
        st.info("Aucune interaction disponible pour analyser les utilisateurs.")
        return

    per_user = (
        interactions.groupby("user_id", as_index=False)
        .agg(nb_interactions=("event_type", "count"), nb_categories=("product_id", "nunique"))
        .sort_values("nb_interactions", ascending=False)
    )

    categories = product_category_map(products)
    if categories:
        enriched = interactions.copy()
        enriched["category"] = enriched["product_id"].map(categories).fillna("Non categorise")
        cat_count = enriched.groupby("user_id")["category"].nunique().reset_index(name="nb_categories")
        per_user = per_user.drop(columns=["nb_categories"]).merge(cat_count, on="user_id", how="left")
        per_user["nb_categories"] = per_user["nb_categories"].fillna(0)

    active_count = int((per_user["nb_interactions"] > 10).sum())
    inactive_count = int((per_user["nb_interactions"] <= 10).sum())

    c1, c2 = st.columns(2)
    segmentation = pd.DataFrame(
        {
            "segment": ["Actifs (>10 interactions)", "Inactifs"],
            "utilisateurs": [active_count, inactive_count],
        }
    )
    fig_segment = px.pie(
        segmentation,
        names="segment",
        values="utilisateurs",
        hole=0.45,
        title="Segmentation utilisateurs",
    )
    c1.plotly_chart(themed_chart(fig_segment), use_container_width=True)

    fig_hist = px.histogram(
        per_user,
        x="nb_interactions",
        nbins=30,
        title="Distribution du nombre d'interactions par utilisateur",
        color_discrete_sequence=[PRIMARY_COLOR],
    )
    c2.plotly_chart(themed_chart(fig_hist), use_container_width=True)

    left, right = st.columns(2)
    top_users = per_user.head(10).copy()
    fig_top = px.bar(
        top_users,
        x="user_id",
        y="nb_interactions",
        title="Top 10 utilisateurs les plus actifs",
        color="nb_interactions",
        color_continuous_scale=["#E8E6FF", PRIMARY_COLOR],
    )
    fig_top.update_layout(coloraxis_showscale=False)
    left.plotly_chart(themed_chart(fig_top), use_container_width=True)

    fig_scatter = px.scatter(
        per_user,
        x="nb_interactions",
        y="nb_categories",
        size="nb_interactions",
        hover_data=["user_id"],
        title="Interactions vs categories explorees",
        color="nb_categories",
        color_continuous_scale=["#E8E6FF", PRIMARY_COLOR],
    )
    right.plotly_chart(themed_chart(fig_scatter), use_container_width=True)

    st.subheader("Table utilisateurs actifs")
    display = per_user.merge(users[["id", "username", "email"]] if not users.empty else pd.DataFrame(), left_on="user_id", right_on="id", how="left")
    st.dataframe(display.drop(columns=["id"], errors="ignore").head(50), use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    """Point d'entree Streamlit."""
    page, start_date, end_date, _token = render_sidebar()

    tables = load_sqlite_tables(str(DB_PATH))
    users = tables["users"]
    products = tables["products"]
    interactions = get_interactions_source(tables)

    if not DB_PATH.exists():
        st.warning(f"Base SQLite introuvable: {DB_PATH}")

    if page == "Vue Generale":
        render_overview(users, products, interactions, start_date, end_date)
    elif page == "Recommandations":
        render_recommendations(users, products, interactions)
    elif page == "Modele ML":
        render_model_page()
    elif page == "Utilisateurs":
        render_users_page(users, products, interactions)


if __name__ == "__main__":
    main()
