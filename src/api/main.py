from flask import Flask, render_template, redirect, request, jsonify, send_from_directory
import os
import csv
import json
import sys
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Init DB and auth will be configured below

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), '../../frontend/templates'),
    static_folder=os.path.join(os.path.dirname(__file__), '../../frontend/static'),
)

# DÃ©finir chemins importants avant config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')
MODELS_DIR = os.path.join(DATA_DIR, 'models')
INTERACTIONS_FILE = os.path.join(PROCESSED_DIR, 'interactions.csv')

# Application configuration
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DB_PATH = os.path.join(PROCESSED_DIR, 'shopai.db')
os.makedirs(PROCESSED_DIR, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')
app.config['SECRET_KEY'] = os.environ.get('SHOPAI_SECRET', 'dev-secret')

from api.models import db, User, Product, Interaction, RecommendationLog, Favorite, UserPreference, CartItem
from api.auth import init_auth, admin_required
from api.models import Order, Invoice, OrderTracking

# Initialize extensions
db.init_app(app)
init_auth(app)

# Create DB and demo users if needed
with app.app_context():
    db.create_all()
    # Ensure demo accounts exist (compatibility with frontend auth.js)
    admin = User.query.filter_by(email='admin@shopai.com').first()
    if not admin:
        admin = User(username='admin', email='admin@shopai.com', password='admin123', role='admin')
        db.session.add(admin)
    user = User.query.filter_by(email='user@shopai.com').first()
    if not user:
        user = User(username='user', email='user@shopai.com', password='user123', role='user')
        db.session.add(user)
    db.session.commit()


ONBOARDING_CATEGORY_MAP = {
    'electronique': 'Tech',
    'Ã©lectronique': 'Tech',
    'tech': 'Tech',
    'smartphones': 'Tech',
    'laptops': 'Tech',
    'mode': 'Mode',
    'beaute': 'Beaute',
    'beautÃ©': 'Beaute',
    'sport': 'Sport',
    'maison': 'Maison',
    'maison & deco': 'Maison',
    'maison & dÃ©co': 'Maison',
    'cuisine': 'Maison',
    'jouets': 'Accessoires',
    'livres': 'Bureau',
    'bureau': 'Bureau',
    'audio': 'Audio',
    'accessoires': 'Accessoires',
}


def _normalize_category_name(category):
    raw = (category or '').strip()
    key = raw.lower().replace('ÃƒÂ©', 'Ã©').replace('Ãƒâ€°', 'Ã©').replace('Ã©', 'e')
    key = key.replace('&amp;', '&')
    return ONBOARDING_CATEGORY_MAP.get(key, ONBOARDING_CATEGORY_MAP.get(raw.lower(), raw or 'Tech'))


def _get_auth_user():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        return verify_jwt(token)
    return None


def _get_user_preferences(user_id):
    return [
        pref.category
        for pref in UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.category.asc()).all()
    ]


def _product_rank(product):
    try:
        meta = json.loads(product.product_metadata) if product.product_metadata else {}
    except Exception:
        meta = {}
    return (
        float(meta.get('popularity', 0)),
        float(meta.get('rating', 0)),
        product.id or 0,
    )


def _products_by_preferences(categories, limit=10):
    normalized = {_normalize_category_name(c).lower() for c in categories if c}
    products = Product.query.all()
    if normalized:
        products = [p for p in products if (p.category or '').lower() in normalized]
    products = sorted(products, key=_product_rank, reverse=True)
    if not products:
        products = sorted(Product.query.all(), key=_product_rank, reverse=True)

    result = []
    for product in products[:limit]:
        item = product.to_dict()
        item['score'] = item.get('note', 4.5) * 20
        item['raison'] = 'Choisi selon vos preferences'
        item['source'] = 'onboarding'
        result.append(item)
    return result


def _resolve_als_products(recommendations, limit=10):
    resolved = []
    for rec in recommendations:
        external_id = str(rec.get('itemId') or rec.get('external_id') or rec.get('id') or '')
        product = Product.query.filter_by(external_id=external_id).first() if external_id else None
        if product:
            item = product.to_dict()
            rating = float(rec.get('rating', rec.get('score', item.get('note', 4.5))))
            item['score'] = round(min(max(rating, 0), 5) * 20, 2)
            item['raison'] = 'Recommande par le modele ALS'
            item['source'] = 'als'
            resolved.append(item)
        elif rec:
            resolved.append(rec)
        if len(resolved) >= limit:
            break
    return resolved

def generate_invoice_pdf(order_id, invoice_number, items, total, order_date=None, customer_name=None, customer_email=None):
    """GÃ©nÃ¨re un PDF de facture incluant la liste des produits de la commande."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'], fontSize=20, spaceAfter=4)
    normal = styles['Normal']

    elements = []
    elements.append(Paragraph("FACTURE", title_style))
    elements.append(Paragraph(f"NÂ° {invoice_number}", normal))
    date_str = (order_date or datetime.now()).strftime('%d/%m/%Y')
    elements.append(Paragraph(f"Date : {date_str}", normal))
    elements.append(Paragraph(f"Commande : #{order_id}", normal))
    if customer_name:
        elements.append(Paragraph(f"Client : {customer_name}", normal))
    if customer_email:
        elements.append(Paragraph(f"Email : {customer_email}", normal))
    elements.append(Spacer(1, 10 * mm))

    data = [["Produit", "Vendeur", "Prix unitaire", "QuantitÃ©", "Sous-total"]]
    computed_total = 0.0
    for item in items:
        name = item.get('name', 'N/A')
        vendor = item.get('vendor') or '-'
        price = float(item.get('price', 0))
        qty = int(item.get('quantity', 1))
        subtotal = price * qty
        computed_total += subtotal
        data.append([name, vendor, f"{price:.2f} MAD", str(qty), f"{subtotal:.2f} MAD"])

    table = Table(data, colWidths=[60 * mm, 30 * mm, 30 * mm, 20 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    final_total = total if total else computed_total
    total_table = Table([["TOTAL", f"{final_total:.2f} MAD"]], colWidths=[140 * mm, 30 * mm])
    total_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.black),
    ]))
    elements.append(total_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# NOTE IMPORTANTE :
# La protection des pages (auth + rÃ´les) est gÃ©rÃ©e UNIQUEMENT
# cÃ´tÃ© JavaScript via checkAuth() et checkRole() dans auth.js.
# Flask sert juste les fichiers HTML sans redirection serveur,
# car la session est dans sessionStorage du navigateur.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PAGES PUBLIQUES (login, inscription, otp)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/inscription')
def inscription():
    return render_template('inscription.html')


@app.route('/otp')
def otp():
    return render_template('otp.html')


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PAGES UTILISATEUR
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/')
def accueil():
    return render_template('accueil.html')


@app.route('/onboarding')
def onboarding():
    return render_template('onboarding.html')


@app.route('/api/onboarding', methods=['GET'])
def get_onboarding_status():
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    preferences = _get_user_preferences(user.id)
    return jsonify({
        'user_id': user.id,
        'preferences': preferences,
        'onboarding_completed': len(preferences) > 0,
    }), 200


@app.route('/api/onboarding', methods=['POST'])
def save_onboarding():
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    categories = data.get('categories') or []
    if not isinstance(categories, list):
        return jsonify({'error': 'categories doit etre une liste'}), 400

    normalized_categories = []
    for category in categories:
        normalized = _normalize_category_name(str(category))
        if normalized and normalized not in normalized_categories:
            normalized_categories.append(normalized)

    if not normalized_categories:
        return jsonify({'error': 'Selectionnez au moins une categorie'}), 400

    try:
        UserPreference.query.filter_by(user_id=user.id).delete()
        for category in normalized_categories:
            db.session.add(UserPreference(user_id=user.id, category=category))

        # Seeds applicatifs: utiles pour le cold-start et pour un futur retrain ALS.
        seed_products = _products_by_preferences(normalized_categories, limit=12)
        for item in seed_products:
            product_id = item.get('id')
            if product_id:
                existing = Interaction.query.filter_by(
                    user_id=user.id,
                    product_id=product_id,
                    event_type='preference_seed'
                ).first()
                if not existing:
                    db.session.add(Interaction(
                        user_id=user.id,
                        product_id=product_id,
                        event_type='preference_seed',
                        timestamp=datetime.utcnow()
                    ))

        db.session.commit()
        return jsonify({
            'status': 'ok',
            'preferences': normalized_categories,
            'onboarding_completed': True,
            'seed_products': seed_products,
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/catalogue')
def catalogue():
    return render_template('catalogue.html')


@app.route('/produit')
def produit():
    return render_template('produit.html')


@app.route('/api/favorites')
def get_favorites():
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    favorites = Favorite.query.filter_by(user_id=user.id).order_by(Favorite.created_at.desc()).all()
    product_ids = [f.product_id for f in favorites]
    products = Product.query.filter(Product.id.in_(product_ids)).all() if product_ids else []
    products_by_id = {p.id: p.to_dict() for p in products}

    # On garde l'ordre des favoris (plus rÃ©cent en premier) et on attache le produit complet
    result = []
    for f in favorites:
        product = products_by_id.get(f.product_id)
        if product:
            result.append({
                'favorite_id': f.id,
                'product': product,
                'created_at': f.created_at.isoformat() if f.created_at else None
            })

    return jsonify({'favorites': result, 'count': len(result)}), 200


@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({'error': 'product_id requis'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Produit introuvable'}), 404

    existing = Favorite.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        return jsonify({'message': 'DÃ©jÃ  en favoris', 'favorite': existing.to_dict()}), 200

    favorite = Favorite(user_id=user.id, product_id=product_id)
    db.session.add(favorite)
    db.session.commit()

    return jsonify({'message': 'AjoutÃ© aux favoris', 'favorite': favorite.to_dict()}), 201


@app.route('/api/favorites/<int:product_id>', methods=['DELETE'])
def remove_favorite(product_id):
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    favorite = Favorite.query.filter_by(user_id=user.id, product_id=product_id).first()
    if not favorite:
        return jsonify({'error': 'Favori introuvable'}), 404

    db.session.delete(favorite)
    db.session.commit()

    return jsonify({'message': 'RetirÃ© des favoris'}), 200


@app.route('/favoris')
def favoris():
    return render_template('favoris.html')


@app.route('/panier_ia')
def panier_ia():
    return render_template('panier_ia.html')


@app.route('/paiement_1')
def paiement_1():
    return render_template('paiement_1.html')


@app.route('/paiement_2')
def paiement_2():
    return render_template('paiement_2.html')


@app.route('/historique')
def historique():
    return render_template('historique.html')




@app.route('/messagerie')
def messagerie():
    return render_template('messagerie.html')


@app.route('/suivi_1')
def suivi_1():
    return render_template('suivi_1.html')


@app.route('/suivi_2')
def suivi_2():
    return render_template('suivi_2.html')


@app.route('/portefeuille')
def portefeuille():
    return render_template('portefeuille.html')


@app.route('/parametres')
def parametres():
    return render_template('parametres.html')


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PAGES ADMIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/dashboard_2')
def dashboard_2():
    return render_template('dashboard_2.html')


@app.route('/dashboard_stats')
def dashboard_stats():
    return render_template('dashboard_stats.html')


@app.route('/admin_catalogue')
def admin_catalogue():
    return render_template('admin_catalogue.html')

@app.route('/admin_add_product')
def admin_add_product():
    return render_template('admin_add_product.html')

@app.route('/admin_commandes')
def admin_commandes():
    return render_template('admin_commandes.html')


@app.route('/admin_messagerie')
def admin_messagerie():
    return render_template('admin_messagerie.html')


@app.route('/admin_parametres')
def admin_parametres():
    return render_template('admin_parametres.html')


@app.route('/admin_portefeuille')
def admin_portefeuille():
    return render_template('admin_portefeuille.html')


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ALIASES (compatibilitÃ© anciens liens)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/panier')
def panier_legacy():
    return redirect('/panier_ia')


@app.route('/paiement')
def paiement_legacy():
    return redirect('/paiement_1')


@app.route('/paiement/confirmation')
def paiement2_legacy():
    return redirect('/paiement_2')


@app.route('/commandes')
def commandes_legacy():
    return redirect('/historique')


@app.route('/favicon.ico')
def favicon():
    """Evite les 404 navigateur sur le favicon."""
    return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def chrome_devtools_probe():
    """Chrome DevTools sonde cette URL en developpement : reponse vide volontaire."""
    return jsonify({})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  API â€” RECOMMANDATIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/api/recommandations/<int:user_id>')
def get_recommandations(user_id):
    """Retourne les produits recommandÃ©s pour un utilisateur."""
    try:
        # Essayer de charger le modÃ¨le ALS
        from recommender import RecommendationEngine
        engine = RecommendationEngine()
        produits = engine.get_recommendations(user_id, n=10)
        return jsonify({'user_id': user_id, 'produits': produits, 'source': 'als'})
    except Exception:
        # Fallback : produits populaires simulÃ©s
        produits = _get_fallback_products()
        return jsonify({'user_id': user_id, 'produits': produits, 'source': 'fallback'})


@app.route('/api/recommendations/<int:user_id>')
def get_recommendations_hybrid(user_id):
    """Hybrid recommendations for cold-start users and ALS-ready users."""
    user = User.query.get(user_id)
    preferences = _get_user_preferences(user_id) if user else []

    try:
        real_interactions = Interaction.query.filter(
            Interaction.user_id == user_id,
            Interaction.event_type.in_(['view', 'addtocart', 'transaction', 'favorite', 'cart', 'purchase'])
        ).count()

        if preferences and real_interactions == 0:
            produits = _products_by_preferences(preferences, limit=10)
            return jsonify({
                'user_id': user_id,
                'produits': produits,
                'preferences': preferences,
                'source': 'onboarding'
            })

        from recommender import RecommendationEngine
        engine = RecommendationEngine()
        als_raw = engine.get_recommendations(user_id, n=20)
        produits = _resolve_als_products(als_raw, limit=10)
        if produits:
            return jsonify({
                'user_id': user_id,
                'produits': produits,
                'preferences': preferences,
                'source': 'als'
            })
    except Exception:
        pass

    produits = _products_by_preferences(preferences, limit=10) if preferences else []
    if produits:
        return jsonify({
            'user_id': user_id,
            'produits': produits,
            'preferences': preferences,
            'source': 'onboarding_fallback'
        })

    return jsonify({
        'user_id': user_id,
        'produits': _get_fallback_products(),
        'preferences': [],
        'source': 'fallback'
    })


@app.route('/api/recommendations/me')
def get_my_recommendations_hybrid():
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401
    return get_recommendations_hybrid(user.id)


def _get_fallback_products():
    """Produits de dÃ©monstration si le modÃ¨le n'est pas disponible."""
    return [
        {
            'id': 1, 'nom': 'Ã‰couteurs Sony WH-1000XM5',
            'prix': 249.99, 'categorie': 'Tech',
            'image': 'https://via.placeholder.com/200x200?text=Sony',
            'note': 4.8, 'score': 95,
            'raison': 'Populaire dans votre catÃ©gorie prÃ©fÃ©rÃ©e'
        },
        {
            'id': 2, 'nom': 'Nike Air Max 270',
            'prix': 149.99, 'categorie': 'Mode',
            'image': 'https://via.placeholder.com/200x200?text=Nike',
            'note': 4.6, 'score': 88,
            'raison': 'Tendance cette semaine'
        },
        {
            'id': 3, 'nom': 'MacBook Pro M3',
            'prix': 1999.99, 'categorie': 'Tech',
            'image': 'https://via.placeholder.com/200x200?text=MacBook',
            'note': 4.9, 'score': 92,
            'raison': 'Les clients comme vous ont aussi achetÃ©'
        },
        {
            'id': 4, 'nom': 'Lampe de bureau LED',
            'prix': 49.99, 'categorie': 'Maison',
            'image': 'https://via.placeholder.com/200x200?text=Lampe',
            'note': 4.5, 'score': 81,
            'raison': 'ComplÃ¨te votre achat prÃ©cÃ©dent'
        },
        {
            'id': 5, 'nom': 'Montre connectÃ©e Samsung',
            'prix': 299.99, 'categorie': 'Tech',
            'image': 'https://via.placeholder.com/200x200?text=Samsung',
            'note': 4.7, 'score': 90,
            'raison': 'BasÃ© sur votre historique de navigation'
        },
    ]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  API â€” PRODUITS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/api/produits')
def get_produits():
    """Retourne la liste des produits depuis la DB (et fallback si vide)."""
    try:
        category = request.args.get('category', '')
        sort     = request.args.get('sort', '')
        query    = request.args.get('q', '')

        q = Product.query
        if category:
            q = q.filter(Product.category.ilike(category))
        if query:
            q = q.filter(Product.name.ilike(f"%{query}%"))

        produits_db = [p.to_dict() for p in q.all()]
        produits = produits_db if produits_db else _get_fallback_products()

        if sort == 'price_asc':
            produits.sort(key=lambda x: x.get('prix') or 0)
        elif sort == 'price_desc':
            produits.sort(key=lambda x: x.get('prix') or 0, reverse=True)

        return jsonify({'produits': produits, 'total': len(produits)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/products/<int:product_id>/similar')
def get_similar_products(product_id):
    """Produits similaires basés sur la catégorie du produit consulté."""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'produits': []}), 404

    similar = Product.query.filter(
        Product.category == product.category,
        Product.id != product.id
    ).all()

    similar = sorted(similar, key=_product_rank, reverse=True)[:8]

    result = []
    for p in similar:
        item = p.to_dict()
        item['raison'] = 'Similaire à votre sélection'
        item['source'] = 'similarity'
        result.append(item)

    return jsonify({'produits': result, 'category': product.category}), 200



# ════════════════════════════════════════════════════════════════
#  API — PANIER (persisté en DB) + ALIAS cart.js
# ════════════════════════════════════════════════════════════════

@app.route('/api/cart', methods=['GET'])
def get_cart():
    """Récupère le panier de l'utilisateur connecté."""
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    product_ids = [item.product_id for item in cart_items]
    products = {p.id: p.to_dict() for p in Product.query.filter(Product.id.in_(product_ids)).all()}

    items = []
    for item in cart_items:
        product = products.get(item.product_id)
        if product:
            items.append({
                'cart_item_id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'name': product.get('nom'),
                'price': product.get('prix'),
                'image': product.get('image'),
                'category': product.get('categorie'),
            })

    total = sum(item['price'] * item['quantity'] for item in items)

    return jsonify({
        'items': items,
        'count': len(items),
        'total': round(total, 2)
    }), 200


@app.route('/api/cart', methods=['POST'])
def add_to_cart():
    """Ajoute un produit au panier."""
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))

    if not product_id:
        return jsonify({'error': 'product_id requis'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Produit introuvable'}), 404

    existing = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        existing.quantity += quantity
    else:
        cart_item = CartItem(user_id=user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)

    db.session.commit()
    return jsonify({'message': 'Ajouté au panier'}), 201


@app.route('/api/cart/<int:product_id>', methods=['PUT'])
def update_cart_item(product_id):
    """Met à jour la quantité d'un produit dans le panier."""
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    quantity = int(data.get('quantity', 1))

    cart_item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if not cart_item:
        return jsonify({'error': 'Produit non trouvé dans le panier'}), 404

    if quantity <= 0:
        db.session.delete(cart_item)
    else:
        cart_item.quantity = quantity

    db.session.commit()
    return jsonify({'message': 'Quantité mise à jour'}), 200


@app.route('/api/cart/<int:product_id>', methods=['DELETE'])
def remove_from_cart(product_id):
    """Supprime un produit du panier."""
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    cart_item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if not cart_item:
        return jsonify({'error': 'Produit non trouvé dans le panier'}), 404

    db.session.delete(cart_item)
    db.session.commit()
    return jsonify({'message': 'Retiré du panier'}), 200


@app.route('/api/cart/clear', methods=['DELETE'])
def clear_cart():
    """Vide complètement le panier."""
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    CartItem.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({'message': 'Panier vidé'}), 200


# ════════════════════════════════════════════════════════════════
#  ALIAS cart.js (compatibilité anciennes routes)
# ════════════════════════════════════════════════════════════════

@app.route('/api/cart/merge', methods=['POST'])
def merge_guest_cart():
    """
    Fusionne le panier invité (localStorage) dans le panier serveur.
    Retourne le panier complet mis à jour.
    """
    user = _get_auth_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    guest_items = data.get('items') or []

    for item in guest_items:
        product_id = item.get('product_id') or item.get('id')
        quantity = int(item.get('quantity', 1))
        if not product_id:
            continue

        # Vérifier que le produit existe
        try:
            pid = int(product_id)
        except (ValueError, TypeError):
            continue

        product = Product.query.get(pid)
        if not product:
            continue

        existing = CartItem.query.filter_by(user_id=user.id, product_id=pid).first()
        if existing:
            existing.quantity += quantity
        else:
            db.session.add(CartItem(user_id=user.id, product_id=pid, quantity=quantity))

    db.session.commit()
    
    # 🔥 Retourner le panier complet (même format que get_cart)
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    product_ids = [item.product_id for item in cart_items]
    products = {p.id: p.to_dict() for p in Product.query.filter(Product.id.in_(product_ids)).all()}

    items = []
    for item in cart_items:
        product = products.get(item.product_id)
        if product:
            items.append({
                'cart_item_id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'name': product.get('nom'),
                'price': product.get('prix'),
                'image': product.get('image'),
                'category': product.get('categorie'),
            })

    total = sum(item['price'] * item['quantity'] for item in items)

    return jsonify({
        'items': items,
        'count': len(items),
        'total': round(total, 2)
    }), 200

@app.route('/api/cart/item/<int:product_id>', methods=['DELETE'])
def remove_from_cart_item_alias(product_id):
    """Alias: DELETE /api/cart/item/<id> → appelle la route principale."""
    return remove_from_cart(product_id)


@app.route('/api/cart/item/<int:product_id>', methods=['PUT'])
def update_cart_item_alias(product_id):
    """Alias: PUT /api/cart/item/<id> → appelle la route principale."""
    return update_cart_item(product_id)




# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  API â€” INTERACTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/api/interactions', methods=['POST'])
def save_interaction():
    """Sauvegarde une interaction utilisateur pour amÃ©liorer le modÃ¨le ALS."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'DonnÃ©es manquantes'}), 400

        user_id = data.get('userId', '')
        product_id = data.get('productId', '')
        event_type = data.get('eventType', '')
        timestamp = data.get('timestamp')

        if not all([user_id, product_id, event_type]):
            return jsonify({'error': 'userId, productId et eventType requis'}), 400

        # Normalize IDs as strings
        # Find or create user
        db_user = None
        try:
            uid = int(user_id)
            db_user = User.query.get(uid)
        except Exception:
            db_user = User.query.filter((User.username == str(user_id)) | (User.email == str(user_id))).first()

        if not db_user:
            db_user = User(username=f'user_{user_id}', email=None, password='')
            db.session.add(db_user)
            db.session.flush()

        # Find or create product by external_id
        db_product = Product.query.filter_by(external_id=str(product_id)).first()
        if not db_product:
            db_product = Product(external_id=str(product_id), name=f'Product {product_id}')
            db.session.add(db_product)
            db.session.flush()

        # Parse timestamp if provided
        ts = None
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp)
            except Exception:
                ts = datetime.utcnow()
        else:
            ts = datetime.utcnow()

        interaction = Interaction(user_id=db_user.id, product_id=db_product.id, event_type=event_type, timestamp=ts)
        db.session.add(interaction)
        db.session.commit()

        return jsonify({'status': 'ok', 'message': 'Interaction sauvegardÃ©e', 'id': interaction.id}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/interactions/<int:user_id>')
def get_interactions(user_id):
    """Retourne l'historique des interactions d'un utilisateur."""
    try:
        interactions = Interaction.query.filter_by(user_id=user_id).order_by(Interaction.timestamp.desc()).all()
        return jsonify({'user_id': user_id, 'interactions': [i.to_dict() for i in interactions]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  API â€” ADMIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    """Retourne les statistiques pour le dashboard admin."""
    try:
        stats = {
            'nb_interactions': 0,
            'nb_users': 2,
            'rmse': None,
            'precision_at_10': None,
            'dernier_entrainement': None,
            'revenue_total': 0,
            'recommandations_servies': 0,
        }

        # Lire les mÃ©triques du modÃ¨le
        metrics_file = os.path.join(MODELS_DIR, 'metrics.json')
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r', encoding='utf-8') as f:
                metrics = json.load(f)
                stats.update(metrics)

        # Compter les interactions
        if os.path.exists(INTERACTIONS_FILE):
            with open(INTERACTIONS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                stats['nb_interactions'] = sum(1 for _ in reader)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/retrain', methods=['POST'])
@admin_required
def admin_retrain():
    """Lance le rÃ©entraÃ®nement du modÃ¨le ALS en arriÃ¨re-plan."""
    try:
        import subprocess
        train_script = os.path.join(BASE_DIR, 'src', 'models', 'train_als.py')
        if not os.path.exists(train_script):
            return jsonify({'error': 'Script train_als.py introuvable'}), 404

        subprocess.Popen(
            ['python', train_script],
            stdout=open(os.path.join(MODELS_DIR, 'retrain_log.txt'), 'w'),
            stderr=subprocess.STDOUT
        )
        return jsonify({'status': 'ok', 'message': 'RÃ©entraÃ®nement lancÃ© en arriÃ¨re-plan'}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/orders/me')
def orders_me():
    # Renvoie la derniÃ¨re commande + invoice + tracking du user connectÃ©
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    order = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).first()
    if not order:
        return jsonify({'order': None, 'invoice': None, 'tracking': None}), 200

    invoice = Invoice.query.filter_by(id=order.invoice_id).first() if order.invoice_id else None
    tracking = OrderTracking.query.filter_by(order_id=order.id).first() if order else None
    return jsonify({ 'order': order.to_dict(), 'invoice': invoice.to_dict() if invoice else None, 'tracking': tracking.to_dict() if tracking else None }), 200


@app.route('/api/orders/<int:order_id>')
def get_order(order_id):
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    order = Order.query.filter_by(id=order_id, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify(order.to_dict()), 200


@app.route('/api/orders/<int:order_id>/invoice')
def get_order_invoice(order_id):
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    order = Order.query.filter_by(id=order_id, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    invoice = Invoice.query.filter_by(id=order.invoice_id).first() if order.invoice_id else None
    return jsonify(invoice.to_dict() if invoice else None), 200


@app.route('/api/orders/<int:order_id>/tracking')
def get_order_tracking(order_id):
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    order = Order.query.filter_by(id=order_id, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    tracking = OrderTracking.query.filter_by(order_id=order.id).first()
    return jsonify(tracking.to_dict() if tracking else None), 200


@app.route('/api/invoices/<int:order_id>/download')
def download_invoice(order_id):
    from flask import Response

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    invoice = Invoice.query.get(order.invoice_id) if order.invoice_id else None
    invoice_number = invoice.invoice_number if invoice else f"INV-{order.id:06d}"

    try:
        items = json.loads(order.items) if order.items else []
    except (json.JSONDecodeError, TypeError):
        items = []

    customer_name = None
    customer_email = None
    if order.user_id:
        user = User.query.get(order.user_id)
        if user:
            customer_name = user.username
            customer_email = user.email

    pdf_bytes = generate_invoice_pdf(
        order_id=order.id,
        invoice_number=invoice_number,
        items=items,
        total=order.total,
        order_date=order.created_at,
        customer_name=customer_name,
        customer_email=customer_email,
    )

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=invoice-{order_id}.pdf'}
    )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  API â€” ORDERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Retourne les commandes actives (toutes) + les 2 dernières commandes
    terminées du user connecté. Exclut les commandes anonymes."""
    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        from api.auth import verify_jwt
        user = verify_jwt(token)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    ACTIVE_STATUSES = ['created', 'paid', 'shipped']
    DONE_STATUSES   = ['delivered', 'cancelled']

    active_orders = (
        Order.query
        .filter(Order.user_id == user.id, Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.created_at.desc())
        .all()
    )

    done_orders = (
        Order.query
        .filter(Order.user_id == user.id, Order.status.in_(DONE_STATUSES))
        .order_by(Order.created_at.desc())
        .limit(2)
        .all()
    )

    orders = active_orders + done_orders

    def enrich(order):
        try:
            items = json.loads(order.items) if order.items else []
        except Exception:
            items = []

        raw_ids = [item.get('product_id') or item.get('id') for item in items if item]
        product_ids = []
        for pid in raw_ids:
            try:
                product_ids.append(int(pid))
            except (ValueError, TypeError):
                continue

        products = {}
        if product_ids:
            for p in Product.query.filter(Product.id.in_(product_ids)).all():
                products[p.id] = p.to_dict()

        enriched_items = []
        for item in items:
            pid = item.get('product_id') or item.get('id')
            prod = products.get(pid, {})
            enriched_items.append({
                'name':     item.get('name',     prod.get('nom',   'Article')),
                'image':    item.get('image',    prod.get('image', '')),
                'price':    item.get('price',    prod.get('prix',  0)),
                'quantity': item.get('quantity', 1),
            })

        return {
            'id':        order.id,
            'reference': f"ORD-{order.id:04d}",
            'date':      order.created_at.strftime('%d %b %Y') if order.created_at else '—',
            'status':    order.status,
            'total':     order.total,
            'items':     enriched_items,
        }

    result = [enrich(o) for o in orders]

    return jsonify({
        'orders':   result,
        'total':    len(result),
        'page':     1,
        'per_page': len(result),
        'pages':    1,
        'has_more': False,
    }), 200

@app.route('/api/commandes', methods=['POST'])
def create_order():
    """Crée une commande + initialise invoice + tracking. AUTH REQUISE."""
    try:
        data = request.get_json() or {}
        items = data.get('items') or []
        total = float(data.get('total', 0.0))
        payment_method = data.get('payment_method')

        # ========== AUTH OBLIGATOIRE ==========
        user = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            from api.auth import verify_jwt
            user = verify_jwt(token)

        if not user:
            return jsonify({'error': 'Authentication required. Veuillez vous connecter pour passer une commande.'}), 401
        
        user_id = user.id
        # ========== FIN AUTH ==========

        order = Order(user_id=user_id, items=json.dumps(items), total=total, status='created')
        db.session.add(order)
        db.session.flush()

        # Create Invoice
        invoice = Invoice(
            user_id=user_id,
            order_id=order.id,
            invoice_number=f"INV-{order.id:06d}",
            status='ready',
            pdf_url=f"/api/invoices/{order.id}/download"
        )
        db.session.add(invoice)
        db.session.flush()

        # Create Tracking
        tracking = OrderTracking(
            user_id=user_id,
            order_id=order.id,
            tracking_number=f"SAI-{order.id:07d}X",
            carrier='Moroccan Express Logistics',
            status='created',
            last_location='Casablanca, Maroc',
            last_lat=33.5731,
            last_lng=-7.5898,
            timeline=json.dumps([
                {'status': 'Commande passée', 'at': datetime.utcnow().isoformat(), 'location': 'Casablanca, Maroc'},
                {'status': 'Paiement confirmé', 'at': datetime.utcnow().isoformat(), 'location': 'Casablanca, Maroc'},
                {'status': 'En préparation', 'at': datetime.utcnow().isoformat(), 'location': 'Casablanca, Maroc'},
            ])
        )
        db.session.add(tracking)

        order.invoice_id = invoice.id
        order.status = 'paid' if payment_method in ('card', 'wallet', 'paypal') else 'created'

        db.session.commit()

        return jsonify({
            'status': 'ok', 
            'order': order.to_dict(), 
            'invoice': invoice.to_dict(), 
            'tracking': tracking.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

import re
import uuid
import json
import os
from datetime import datetime
from groq import Groq

class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'
    id = db.Column(db.String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title = db.Column(db.String(200), default='Nouvelle conversation')
    status = db.Column(db.String(20), default='active')
    context_summary = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship('ChatMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'message_count': self.messages.count()
        }


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(50), db.ForeignKey('chat_conversations.id'), nullable=False)
    sender = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(30), default='text')
    metadata_json = db.Column(db.Text, default='{}')
    intent = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        meta = {}
        try:
            meta = json.loads(self.metadata_json) if self.metadata_json else {}
        except:
            pass
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'content': self.content,
            'message_type': self.message_type,
            'metadata': meta,
            'intent': self.intent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# CrÃ©er les tables
with app.app_context():
    db.create_all()




class ShopAIEngine:
    SYSTEM_PROMPT = """Tu es ShopAI, l'assistant virtuel intelligent de ShopAI Marketplace Maroc.

MISSIONS:
1. RECOMMANDER des produits pertinents selon le budget et les besoins du client
2. SUIVRE les commandes et donner les infos de livraison precises
3. RESOUDRE les problemes (retours, remboursements, articles defectueux)
4. AIDER a la navigation (catalogue, panier, paiement)

REGLES STRICTES:
- Reponds en francais ou darija marocaine selon la langue du client
- Sois chaleureux, professionnel et concis (max 3-4 phrases)
- Prix toujours en MAD (Dirhams)
- Pour les commandes: donne le numero de suivi, statut exact, derniere localisation
- Si probleme grave -> propose de connecter avec un agent humain
- Utilise des emojis pertinents

FORMAT REPONSE:
- Texte normal pour conversation
- [PRODUCTS] pour suggestions produits
- [ORDER] pour infos commande
- [ESCALATE] pour transfert humain"""

    MODELS = {
        'fast': 'llama-3.1-8b-instant',
        'balanced': 'llama-3.3-70b-versatile',
        'smart': 'deepseek-r1-distill-llama-70b',
        'mixtral': 'mixtral-8x7b-32768',
    }

    def __init__(self, model='balanced'):
        self.api_key = os.environ.get('GROQ_API_KEY', '')
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self.model = self.MODELS.get(model, self.MODELS['balanced'])
        self.groq_available = self.client is not None
        print(f"[ShopAI] Modele: {self.model} | Groq disponible: {self.groq_available}")

    def detect_intent(self, message: str) -> str:
        msg = message.lower()
        patterns = {
            'order_tracking': [r'commande', r'colis', r'livraison', r'suivi', r'expedie', r'arrive', r'numero de suivi', r'ou est', r'quand'],
            'product_search': [r'cherche', r'trouve', r'recommande', r'suggere', r'besoin', r'quel', r'quelle', r'je veux', r'je cherche'],
            'price_query': [r'prix', r'budget', r'combien', r'moins cher', r'pas cher', r'solde', r'promo', r'reduction', r'dh', r'mad'],
            'support_issue': [r'probleme', r'retour', r'remboursement', r'casse', r'defectueux', r'erreur', r'plainte', r'insatisfait', r'mauvais'],
            'payment_help': [r'paiement', r'carte', r'paypal', r'virement', r'cash', r'livraison', r'comment payer'],
            'greeting': [r'salam', r'bonjour', r'bonsoir', r'ca va', r'hello', r'hi', r'coucou', r'hey'],
            'cart_help': [r'panier', r'ajouter', r'supprimer', r'vider', r'modifier'],
        }
        for intent, regex_list in patterns.items():
            if any(re.search(p, msg) for p in regex_list):
                return intent
        return 'general'

    def get_order_context(self, user_id: int) -> str:
        orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(5).all()
        if not orders:
            return "Aucune commande trouvee pour cet utilisateur."
        
        context = "COMMANDES RECENTES:\n"
        for o in orders:
            tracking = OrderTracking.query.filter_by(order_id=o.id).first()
            status_map = {
                'created': 'Creee', 'paid': 'Payee', 'processing': 'En preparation',
                'shipped': 'Expediee', 'delivered': 'Livree', 'cancelled': 'Annulee'
            }
            status = status_map.get(o.status, o.status)
            tracking_num = tracking.tracking_number if tracking else 'N/A'
            location = tracking.last_location if tracking else 'Casablanca'
            context += f"- Commande #{o.id}: {status}, Suivi: {tracking_num}, Localisation: {location}, Total: {o.total} MAD\n"
        return context

    def get_product_context(self, query: str, max_price: float = None) -> str:
        q = Product.query
        if query:
            q = q.filter(
                db.or_(
                    Product.name.ilike(f'%{query}%'),
                    Product.category.ilike(f'%{query}%'),
                )
            )
        if max_price:
            q = q.filter(Product.price <= max_price)
        
        products = q.order_by(Product.price.asc()).limit(5).all()
        if not products:
            return "Aucun produit trouve pour cette recherche."
        
        context = "PRODUITS DISPONIBLES:\n"
        for p in products:
            try:
                meta = json.loads(p.product_metadata) if p.product_metadata else {}
            except:
                meta = {}
            context += f"- {p.name}: {p.price} MAD, Categorie: {p.category}, Stock: {meta.get('stock', 'disponible')}\n"
        return context

    def get_user_preferences_context(self, user_id: int) -> str:
        if not user_id:
            return ""
        prefs = UserPreference.query.filter_by(user_id=user_id).all()
        if prefs:
            cats = [p.category for p in prefs]
            return f"PREFERENCES CLIENT: {', '.join(cats)}\n"
        return ""

    def generate_response(self, message: str, user_id: int = None, conversation_history: list = None) -> dict:
        intent = self.detect_intent(message)
        
        context_parts = [self.SYSTEM_PROMPT]
        
        if user_id:
            context_parts.append(self.get_user_preferences_context(user_id))
            context_parts.append(self.get_order_context(user_id))
        
        budget_match = re.search(r'(\d+)\s*(?:dh|mad|DH|MAD|â‚¬|\$)', message.lower())
        max_price = float(budget_match.group(1)) if budget_match else None
        
        if intent in ['product_search', 'price_query']:
            context_parts.append(self.get_product_context(message, max_price))
        
        if conversation_history:
            hist_text = "\n".join([
                f"{'Client' if h['sender'] == 'user' else 'ShopAI'}: {h['content'][:200]}"
                for h in conversation_history[-6:]
            ])
            context_parts.append(f"HISTORIQUE:\n{hist_text}")
        
        full_prompt = "\n\n".join(context_parts) + f"\n\nClient: {message}\nShopAI:"
        
        if self.groq_available:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500,
                    top_p=0.9,
                )
                ai_text = response.choices[0].message.content.strip()
                return self._parse_response(ai_text, intent, user_id, max_price)
            except Exception as e:
                print(f"[ShopAI] Erreur Groq: {e}")
                return self._try_fallback_model(message, intent, user_id, max_price)
        
        return self._fallback_response(message, intent, user_id, max_price)

    def _try_fallback_model(self, message: str, intent: str, user_id: int, max_price: float) -> dict:
        fallback_models = ['llama-3.1-8b-instant', 'mixtral-8x7b-32768']
        for model in fallback_models:
            if model == self.model:
                continue
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.7,
                    max_tokens=400,
                )
                ai_text = response.choices[0].message.content.strip()
                return self._parse_response(ai_text, intent, user_id, max_price)
            except Exception:
                continue
        return self._fallback_response(message, intent, user_id, max_price)

    def _parse_response(self, text: str, intent: str, user_id: int, max_price: float) -> dict:
        result = {
            'text': text,
            'intent': intent,
            'message_type': 'text',
            'metadata': {}
        }
        
        if '[PRODUCTS]' in text or intent in ['product_search', 'price_query']:
            result['message_type'] = 'product_suggestions'
            products = self._get_products_for_response(user_id, max_price)
            result['metadata']['products'] = products
            # Ajouter texte avec produits si IA n'a pas pu les afficher
            if products and 'image' not in result['text']:
                result['text'] += "\n\nVoici les produits disponibles avec leurs images 👇"
        elif '[ORDER]' in text or intent == 'order_tracking':
            result['message_type'] = 'order_status'
            result['metadata']['orders'] = self._get_user_orders_summary(user_id)
        elif '[ESCALATE]' in text or intent == 'support_issue':
            result['message_type'] = 'escalate'
            result['metadata']['action'] = 'connect_human_agent'
        
        result['text'] = re.sub(r'\[(PRODUCTS|ORDER|ESCALATE)\]', '', text).strip()
        return result

    def _fallback_response(self, message: str, intent: str, user_id: int, max_price: float) -> dict:
        responses = {
            'greeting': {
                'text': "Salam ! ðŸ‘‹ Je suis ShopAI, votre assistant shopping. Je peux vous aider a trouver des produits, suivre vos commandes ou resoudre un probleme. Comment puis-je vous aider ?",
                'message_type': 'text',
                'metadata': {'quick_replies': ['Suivre ma commande', 'Recommandations', 'Probleme avec ma commande']}
            },
            'order_tracking': {
                'text': self._get_order_status_text(user_id),
                'message_type': 'order_status',
                'metadata': {'orders': self._get_user_orders_summary(user_id), 'show_orders': True}
            },
            'product_search': {
                'text': "Voici ce que j'ai trouve pour vous ! ðŸ”",
                'message_type': 'product_suggestions',
                'metadata': {'products': self._get_products_for_response(user_id, max_price)}
            },
            'price_query': {
                'text': f"Je cherche des produits dans votre budget {'de ' + str(int(max_price)) + ' MAD' if max_price else 'optimal'} ! ðŸ’°",
                'message_type': 'product_suggestions',
                'metadata': {'products': self._get_products_for_response(user_id, max_price)}
            },
            'support_issue': {
                'text': "Je suis desole pour ce probleme. ðŸ˜” Je vais vous connecter avec un agent qui pourra vous aider immediatement. Voulez-vous que je prepare un recapitulatif ?",
                'message_type': 'escalate',
                'metadata': {'action': 'connect_human_agent', 'estimated_wait': '2 min'}
            },
            'payment_help': {
                'text': "Nous acceptons plusieurs moyens de paiement securises : ðŸ’³ Carte bancaire (Visa/Mastercard), ðŸ“± PayPal, ðŸ’° Paiement a la livraison (Cash on Delivery). Lequel preferez-vous ?",
                'message_type': 'text',
                'metadata': {'quick_replies': ['Carte bancaire', 'PayPal', 'Paiement a la livraison']}
            },
            'cart_help': {
                'text': "Je peux vous aider avec votre panier ! ðŸ›’ Vous pouvez ajouter des produits, modifier les quantites ou vider le panier. Que souhaitez-vous faire ?",
                'message_type': 'text',
                'metadata': {'quick_replies': ['Voir mon panier', 'Ajouter un produit', 'Vider le panier']}
            },
            'general': {
                'text': "Je suis la pour vous aider ! ðŸ˜Š Vous pouvez me demander de trouver un produit, suivre une commande, ou obtenir de l'aide. Que souhaitez-vous faire ?",
                'message_type': 'text',
                'metadata': {'quick_replies': ['Chercher un produit', 'Mes commandes', 'Aide']}
            }
        }
        return responses.get(intent, responses['general'])

    def _get_order_status_text(self, user_id: int) -> str:
        if not user_id:
            return "Pour consulter vos commandes, veuillez vous connecter à votre compte. 🔐"
        orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(5).all()
        if not orders:
            return "Vous n'avez pas encore de commande. Découvrez notre catalogue ! 🛍️"
        
        status_map = {
            'created': '🕐 En attente',
            'paid': '💳 Payée',
            'processing': '📦 En préparation',
            'shipped': '🚚 Expédiée',
            'delivered': '✅ Livrée',
            'cancelled': '❌ Annulée'
        }
        
        lines = ["Voici vos commandes récentes. De laquelle souhaitez-vous le suivi ?\n"]
        for o in orders:
            tracking = OrderTracking.query.filter_by(order_id=o.id).first()
            status = status_map.get(o.status, o.status)
            track_num = tracking.tracking_number if tracking else 'N/A'
            location = tracking.last_location if tracking else 'Casablanca'
            date = o.created_at.strftime('%d/%m/%Y') if o.created_at else '—'
            lines.append(
                f"• Commande #{o.id} ({date}) — {status}\n"
                f"  Suivi: {track_num} | 📍 {location} | Total: {o.total} MAD"
            )
        
        lines.append("\nRépondez avec le numéro de commande pour plus de détails.")
        return "\n".join(lines)
    def _get_user_orders_summary(self, user_id: int) -> list:
        if not user_id:
            return []
        orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(5).all()
        result = []
        for o in orders:
            tracking = OrderTracking.query.filter_by(order_id=o.id).first()
            result.append({
                'id': o.id,
                'reference': f"ORD-{o.id:04d}",
                'status': o.status,
                'total': o.total,
                'tracking_number': tracking.tracking_number if tracking else None,
                'carrier': tracking.carrier if tracking else 'Moroccan Express Logistics',
                'last_location': tracking.last_location if tracking else 'Casablanca, Maroc',
                'date': o.created_at.strftime('%d/%m/%Y') if o.created_at else 'â€”'
            })
        return result

    def _get_products_for_response(self, user_id: int, max_price: float = None) -> list:
        q = Product.query
        if max_price:
            q = q.filter(Product.price <= max_price)
        
        if user_id:
            prefs = UserPreference.query.filter_by(user_id=user_id).all()
            categories = [p.category for p in prefs if p.category]
            if categories:
                q = q.filter(Product.category.in_(categories))
        
        products = q.order_by(Product.price.asc()).limit(4).all()
        if not products:
            products = Product.query.order_by(Product.price.asc()).limit(4).all()
        
        result = []
        for p in products:
            try:
                meta = json.loads(p.product_metadata) if p.product_metadata else {}
            except:
                meta = {}
            result.append({
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'category': p.category,
                'image': meta.get('image_url') or 'https://placehold.co/300x300?text=' + (p.name or 'Produit').replace(' ', '+'),
                'stock': meta.get('stock', 10),
                'description': meta.get('description', '')[:100]
            })
        return result


# Instance globale
shopai_engine = ShopAIEngine(model='balanced')




@app.route('/api/chat/conversations', methods=['GET'])
def get_conversations():
    """Liste les conversations de l'utilisateur connectÃ©, ou liste vide en anonyme"""
    user = _get_auth_user()

    if user:
        conversations = ChatConversation.query.filter_by(user_id=user.id).order_by(ChatConversation.updated_at.desc()).all()
        return jsonify({
            'conversations': [c.to_dict() for c in conversations],
            'anonymous': False
        }), 200
    else:
        # Pour les utilisateurs non connectÃ©s, ne pas renvoyer d'erreur
        return jsonify({'conversations': [], 'anonymous': True}), 200


@app.route('/api/chat/conversations', methods=['POST'])
def create_conversation():
    """CrÃ©e une nouvelle conversation (anonyme ou authentifiÃ©e)"""
    user = _get_auth_user()

    data = request.get_json(silent=True) or {}
    title = data.get('title', 'Nouvelle conversation')

    conv = ChatConversation(
        user_id=user.id if user else None,
        title=title
    )
    db.session.add(conv)
    db.session.commit()

    # Message de bienvenue
    welcome = ChatMessage(
        conversation_id=conv.id,
        sender='ai',
        content="Salam ! ðŸ‘‹ Je suis ShopAI. Comment puis-je vous aider aujourd'hui ?",
        message_type='text',
        intent='greeting'
    )
    db.session.add(welcome)
    db.session.commit()

    return jsonify({
        'conversation': conv.to_dict(),
        'welcome_message': welcome.to_dict()
    }), 201


@app.route('/api/chat/conversations/<conv_id>/messages', methods=['GET'])
def get_messages(conv_id):
    """RÃ©cupÃ¨re les messages d'une conversation (anonyme ou authentifiÃ©e)"""
    user = _get_auth_user()

    conv = ChatConversation.query.get_or_404(conv_id)

    # VÃ©rifier l'accÃ¨s : soit l'utilisateur est le propriÃ©taire, soit c'est une conversation anonyme
    if user and conv.user_id and conv.user_id != user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    messages = ChatMessage.query.filter_by(conversation_id=conv_id).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({
        'conversation': conv.to_dict(),
        'messages': [m.to_dict() for m in messages]
    }), 200


@app.route('/api/chat/conversations/<conv_id>/messages', methods=['POST'])
def send_chat_message(conv_id):
    """Envoie un message et reÃ§oit la rÃ©ponse IA (anonyme ou authentifiÃ©)"""
    user = _get_auth_user()

    conv = ChatConversation.query.get_or_404(conv_id)

    # VÃ©rifier l'accÃ¨s
    if user and conv.user_id and conv.user_id != user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'error': 'Message vide'}), 400

    # Sauvegarder le message utilisateur
    user_msg = ChatMessage(
        conversation_id=conv_id,
        sender='user',
        content=content,
        intent=shopai_engine.detect_intent(content)
    )
    db.session.add(user_msg)
    db.session.commit()

    # RÃ©cupÃ©rer l'historique
    history = [m.to_dict() for m in ChatMessage.query.filter_by(conversation_id=conv_id).order_by(ChatMessage.created_at.asc()).all()]

    # GÃ©nÃ©rer la rÃ©ponse IA
    user_id = user.id if user else None
    ai_result = shopai_engine.generate_response(content, user_id=user_id, conversation_history=history)

    # Sauvegarder la rÃ©ponse IA
    ai_msg = ChatMessage(
        conversation_id=conv_id,
        sender='ai',
        content=ai_result['text'],
        message_type=ai_result['message_type'],
        metadata_json=json.dumps(ai_result.get('metadata', {})),
        intent=ai_result['intent']
    )
    db.session.add(ai_msg)

    # Mettre Ã  jour la conversation
    conv.updated_at = datetime.utcnow()
    if ai_result['intent'] == 'escalate':
        conv.status = 'escalated'

    db.session.commit()

    return jsonify({
        'user_message': user_msg.to_dict(),
        'ai_response': ai_msg.to_dict(),
        'metadata': ai_result.get('metadata', {})
    }), 201


@app.route('/api/chat/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    """Supprime une conversation"""
    user = _get_auth_user()

    conv = ChatConversation.query.get_or_404(conv_id)

    # VÃ©rifier l'accÃ¨s : soit le propriÃ©taire, soit conversation anonyme
    if user and conv.user_id and conv.user_id != user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    db.session.delete(conv)
    db.session.commit()

    return jsonify({'message': 'Conversation supprimee'}), 200


@app.route('/api/chat/quick-actions', methods=['GET'])
def get_quick_actions():
    """Actions rapides disponibles pour le chatbot (public)"""
    return jsonify({
        'actions': [
            {'id': 'track_order', 'label': 'ðŸ“¦ Suivre ma commande', 'intent': 'order_tracking'},
            {'id': 'find_product', 'label': 'ðŸ” Trouver un produit', 'intent': 'product_search'},
            {'id': 'best_deals', 'label': 'ðŸ’° Meilleures offres', 'intent': 'price_query'},
            {'id': 'support', 'label': 'ðŸ†˜ Support client', 'intent': 'support_issue'},
            {'id': 'payment_help', 'label': 'ðŸ’³ Aide paiement', 'intent': 'payment_help'},
        ]
    }), 200


@app.route('/api/admin/chatbot/model', methods=['POST'])
@admin_required
def change_chatbot_model():
    data = request.get_json() or {}
    model = data.get('model', 'balanced')
    if model not in ShopAIEngine.MODELS:
        return jsonify({'error': f'Modele invalide. Choix: {list(ShopAIEngine.MODELS.keys())}'}), 400

    global shopai_engine
    shopai_engine = ShopAIEngine(model=model)
    return jsonify({
        'status': 'ok',
        'model': model,
        'model_id': ShopAIEngine.MODELS[model]
    }), 200


@app.route('/api/admin/chatbot/model', methods=['GET'])
@admin_required
def get_chatbot_model():
    return jsonify({
        'current_model': shopai_engine.model,
        'available_models': ShopAIEngine.MODELS
    }), 200



# ════════════════════════════════════════════════════════════════
#  UPLOAD IMAGE PRODUIT — MinIO
# ════════════════════════════════════════════════════════════════

import base64
import re
import uuid as uuid_lib
from io import BytesIO
from minio import Minio
from minio.error import S3Error

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
MINIO_SECURE = os.environ.get('MINIO_SECURE', 'false').lower() == 'true'
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'shopai-products')
MINIO_PUBLIC_URL = os.environ.get('MINIO_PUBLIC_URL', f"http://{MINIO_ENDPOINT}")

_minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

# Création bucket + policy PUBLIC au démarrage
try:
    if not _minio_client.bucket_exists(MINIO_BUCKET):
        _minio_client.make_bucket(MINIO_BUCKET)
        print(f"[MinIO] Bucket '{MINIO_BUCKET}' créé")
    
    # Rendre le bucket public pour les images
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{MINIO_BUCKET}/*"
            }
        ]
    }
    _minio_client.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
    print(f"[MinIO] Bucket '{MINIO_BUCKET}' configuré comme PUBLIC")
    
except S3Error as e:
    print(f"[MinIO] Erreur: {e}")

@app.route('/api/admin/upload-image', methods=['POST'])
def admin_upload_image():
    """Recoit une image en base64 et la pousse vers MinIO."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    data = request.get_json(silent=True) or {}
    raw = data.get('image', '')

    if not raw:
        return jsonify({'error': 'Aucune image fournie'}), 400

    match = re.match(r'data:image/(\w+);base64,(.+)', raw)
    if not match:
        return jsonify({'error': 'Format image invalide (base64 attendu)'}), 400

    ext = match.group(1).lower()
    if ext == 'jpeg':
        ext = 'jpg'
    b64_data = match.group(2)

    try:
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        return jsonify({'error': 'Decodage base64 echoue'}), 400

    if len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({'error': 'Image trop volumineuse (max 8 Mo)'}), 400

    object_name = f"products/{uuid_lib.uuid4().hex}.{ext}"
    content_type = f"image/{ext}" if ext != 'jpg' else 'image/jpeg'

    try:
        _minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            BytesIO(image_bytes),
            length=len(image_bytes),
            content_type=content_type,
        )
    except S3Error as e:
        return jsonify({'error': f'Erreur MinIO : {e}'}), 500

    public_url = f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{object_name}"

    return jsonify({'status': 'ok', 'url': public_url, 'object_name': object_name}), 201

@app.route('/api/products', methods=['GET'])
def get_products_admin():
    """Liste tous les produits pour l'admin (avec stats)."""
    try:
        q = request.args.get('q', '')
        category = request.args.get('category', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 12, type=int)

        query = Product.query
        if q:
            query = query.filter(Product.name.ilike(f'%{q}%'))
        if category:
            query = query.filter(Product.category.ilike(category))

        total = query.count()
        products = query.offset((page - 1) * per_page).limit(per_page).all()

        result = []
        for p in products:
            try:
                meta = json.loads(p.product_metadata) if p.product_metadata else {}
            except Exception:
                meta = {}
            result.append({
                'id': p.id,
                'external_id': p.external_id,
                'name': p.name,
                'price': p.price,
                'category': p.category,
                'image': meta.get('image_url', 'https://placehold.co/400x400?text=Produit'),
                'rating': meta.get('rating', 4.5),
                'vendor': meta.get('vendor', 'ShopAI Store'),
                'stock': meta.get('stock', 99),
                'sales': meta.get('sales', 0),
                'status': meta.get('status', 'in_stock'),
            })

        return jsonify({
            'products': result,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/products', methods=['POST'])
def create_product():
    """CrÃ©e un nouveau produit (admin)."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    data = request.get_json(silent=True) or {}
    try:
        meta = {
            'image_url': data.get('image', ''),
            'rating': 4.5,
            'vendor': 'ShopAI Store',
            'stock': int(data.get('stock', 0)),
            'sales': 0,
            'status': data.get('status', 'in_stock'),
            'description': data.get('description', ''),
            'ref': data.get('ref', ''),
        }
        product = Product(
            name=data.get('name'),
            price=float(data.get('price', 0)),
            category=data.get('category', 'Tech'),
            product_metadata=json.dumps(meta),
        )
        db.session.add(product)
        db.session.commit()
        return jsonify({'status': 'ok', 'id': product.id, 'message': 'Produit crÃ©Ã©'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Met Ã  jour un produit (admin)."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Produit introuvable'}), 404

    data = request.get_json(silent=True) or {}
    try:
        meta = json.loads(product.product_metadata) if product.product_metadata else {}
        if 'name' in data:
            product.name = data['name']
        if 'price' in data:
            product.price = float(data['price'])
        if 'category' in data:
            product.category = data['category']
        if 'image' in data:
            meta['image_url'] = data['image']
        if 'stock' in data:
            meta['stock'] = int(data['stock'])
        if 'status' in data:
            meta['status'] = data['status']
        if 'description' in data:
            meta['description'] = data['description']
        product.product_metadata = json.dumps(meta)
        db.session.commit()
        return jsonify({'status': 'ok', 'message': 'Produit mis Ã  jour'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Supprime un produit (admin)."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Produit introuvable'}), 404

    try:
        db.session.delete(product)
        db.session.commit()
        return jsonify({'status': 'ok', 'message': 'Produit supprimÃ©'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/stats/full')
def admin_stats_full():
    """Stats complÃ¨tes depuis la DB pour le dashboard admin."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    try:
        nb_users = User.query.count()
        nb_products = Product.query.count()
        nb_orders = Order.query.count()
        nb_interactions = Interaction.query.count()

        # Revenus totaux
        revenue = db.session.query(db.func.sum(Order.total)).filter(
            Order.status.in_(['paid', 'created'])
        ).scalar() or 0

        # Commandes rÃ©centes (10 derniÃ¨res)
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
        orders_data = []
        for o in recent_orders:
            user_obj = User.query.get(o.user_id) if o.user_id else None
            orders_data.append({
                'id': o.id,
                'reference': f'ORD-{o.id:04d}',
                'user': user_obj.username if user_obj else 'Anonyme',
                'total': o.total,
                'status': o.status,
                'date': o.created_at.strftime('%d %b %Y') if o.created_at else 'â€”',
            })

        # RÃ©partition par catÃ©gorie
        from sqlalchemy import func
        categories = db.session.query(
            Product.category, func.count(Product.id)
        ).group_by(Product.category).all()

        return jsonify({
            'nb_users': nb_users,
            'nb_products': nb_products,
            'nb_orders': nb_orders,
            'nb_interactions': nb_interactions,
            'revenue_total': round(float(revenue), 2),
            'recent_orders': orders_data,
            'categories': [{'name': c[0] or 'Autre', 'count': c[1]} for c in categories],
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/orders', methods=['GET'])
def admin_get_orders():
    """Toutes les commandes pour l'admin."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    status_filter = request.args.get('status', '')

    query = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        query = query.filter(Order.status == status_filter)

    total = query.count()
    orders = query.offset((page - 1) * per_page).limit(per_page).all()

    result = []
    for o in orders:
        user_obj = User.query.get(o.user_id) if o.user_id else None
        result.append({
            'id': o.id,
            'reference': f'ORD-{o.id:04d}',
            'user': user_obj.username if user_obj else 'Anonyme',
            'email': user_obj.email if user_obj else 'â€”',
            'total': o.total,
            'status': o.status,
            'date': o.created_at.strftime('%d %b %Y %H:%M') if o.created_at else 'â€”',
        })

    return jsonify({
        'orders': result,
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page,
    }), 200


@app.route('/api/admin/orders/<int:order_id>/status', methods=['PUT'])
def admin_update_order_status(order_id):
    """Met Ã  jour le statut d'une commande (admin)."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Commande introuvable'}), 404

    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if not new_status:
        return jsonify({'error': 'status requis'}), 400

    try:
        order.status = new_status
        db.session.commit()
        return jsonify({'status': 'ok', 'message': f'Commande #{order_id} â†’ {new_status}'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
#  LANCEMENT
@app.route('/api/admin/sales-chart')
def admin_sales_chart():
    """Données du graphique ventes journalières pour le dashboard admin."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    try:
        days = int(request.args.get('days', 7))
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        from sqlalchemy import func

        results = db.session.query(
            func.date(Order.created_at).label('day'),
            func.sum(Order.total).label('revenue')
        ).filter(
            Order.created_at >= start_date,
            Order.status.in_(['paid', 'created', 'processing', 'shipped', 'delivered'])
        ).group_by(
            func.date(Order.created_at)
        ).order_by('day').all()

        # Construire un dict date → revenue
        data_map = {str(r.day): float(r.revenue or 0) for r in results}

        labels = []
        data = []
        for i in range(days):
            day = (start_date + timedelta(days=i + 1)).date()
            day_str = str(day)

            if days <= 7:
                label = day.strftime('%a %d')   # "Lun 23"
            else:
                label = day.strftime('%d %b')   # "23 Jun"

            labels.append(label)
            data.append(data_map.get(day_str, 0))

        return jsonify({'labels': labels, 'data': data}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/api/admin/top-products')

def admin_top_products():
    """Top produits par nombre de ventes pour le dashboard admin."""
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    try:
        products = Product.query.all()
        result = []
        for p in products:
            try:
                meta = json.loads(p.product_metadata) if p.product_metadata else {}
            except Exception:
                meta = {}

            sales = meta.get('sales', 0)
            result.append({
                'id': p.id,
                'name': p.name,
                'category': p.category or 'N/A',
                'price': p.price or 0,
                'sales': sales,
                'revenue': round(float(p.price or 0) * int(sales), 2),
            })

        # Trier par ventes décroissantes
        result.sort(key=lambda x: x['sales'], reverse=True)

        return jsonify({'products': result[:10]}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403
    
    try:
        users = User.query.order_by(User.id.asc()).all()
        result = []
        for u in users:
            order_count = Order.query.filter_by(user_id=u.id).count()
            result.append({
                'id': u.id,
                'username': u.username,
                'email': u.email or '—',
                'role': u.role or 'user',
                'order_count': order_count,
            })
        return jsonify({'users': result, 'total': len(result)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users', methods=['POST'])
def admin_create_user():
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    data = request.get_json(silent=True) or {}
    if not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'username, email et password requis'}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email déjà utilisé'}), 409

    try:
        new_user = User(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            role=data.get('role', 'user')
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'status': 'ok', 'id': new_user.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
def admin_update_user(user_id):
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    data = request.get_json(silent=True) or {}
    try:
        if 'username' in data:
            target.username = data['username']
        if 'email' in data:
            target.email = data['email']
        if 'role' in data:
            target.role = data['role']
        if data.get('password'):
            target.password = data['password']
        db.session.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    user = _get_auth_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin required'}), 403

    if user.id == user_id:
        return jsonify({'error': 'Impossible de supprimer votre propre compte'}), 400

    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    try:
        db.session.delete(target)
        db.session.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print('[ShopAI] Serveur dÃ©marrÃ© sur http://127.0.0.1:8000')
    print('[ShopAI] Routes disponibles :')
    print('  Pages  : /, /login, /inscription, /dashboard, /catalogue...')
    print('  API    : /api/recommandations/<id>, /api/produits, /api/interactions')
    print('  Admin  : /api/admin/stats, /api/admin/retrain')
    app.run(debug=True, port=5000)
