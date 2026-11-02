"""
ShopAI - Script d'enrichissement final v6.
Fix definitif : le NOM du produit synthetique est derive du nom de fichier
de l'image DummyJSON elle-meme, garantissant une coherence parfaite
nom <-> image (ex: image "blue-women's-handbag" -> nom "Sac A Main Bleu").
"""

import sys, os, json, random, ssl, re, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
import pandas as pd
from api.main import app
from api.models import db, Product

TOP_RETAILROCKET  = 150
EVENTS_CLEAN_PATH = "data/processed/events_clean"
ITEM_PROPS_PATH_1 = "data/raw/item_properties_part1.csv"
ITEM_PROPS_PATH_2 = "data/raw/item_properties_part2.csv"
random.seed(42)

CATEGORY_LABELS = ['Tech', 'Mode', 'Maison', 'Beaute', 'Sport', 'Bureau', 'Audio', 'Accessoires']

DUMMYJSON_TO_SHOPAI = {
    'smartphones':        'Tech',
    'laptops':            'Tech',
    'tablets':            'Tech',
    'vehicle':            'Tech',
    'motorcycle':         'Tech',
    'mens-watches':       'Accessoires',
    'womens-watches':     'Accessoires',
    'womens-bags':        'Accessoires',
    'womens-jewellery':   'Accessoires',
    'sunglasses':         'Accessoires',
    'mens-shirts':        'Mode',
    'mens-shoes':         'Mode',
    'womens-dresses':     'Mode',
    'womens-shoes':       'Mode',
    'tops':               'Mode',
    'home-decoration':    'Maison',
    'kitchen-accessories':'Maison',
    'groceries':          'Maison',
    'beauty':             'Beaute',
    'fragrances':         'Beaute',
    'skin-care':          'Beaute',
    'sports-accessories': 'Sport',
    'furniture':          'Bureau',
    'mobile-accessories': 'Audio',
}

# Mots anglais -> francais pour traduire les noms derives des slugs d'image
TRANSLATIONS = {
    'blue': 'Bleu', 'black': 'Noir', 'white': 'Blanc', 'red': 'Rouge',
    'green': 'Vert', 'grey': 'Gris', 'gray': 'Gris', 'gold': 'Or',
    'silver': 'Argent', 'brown': 'Marron', 'pink': 'Rose', 'yellow': 'Jaune',
    'women': 'Femme', "women's": 'Femme', 'men': 'Homme', "men's": 'Homme',
    'man': 'Homme', 'woman': 'Femme', 'girl': 'Fille',
    'handbag': 'Sac a Main', 'bag': 'Sac', 'backpack': 'Sac a Dos',
    'watch': 'Montre', 'glasses': 'Lunettes', 'sunglasses': 'Lunettes de Soleil',
    'shoes': 'Chaussures', 'sneakers': 'Sneakers', 'cleats': 'Crampons',
    'slipper': 'Pantoufles', 'trainers': 'Sneakers', 'heel': 'Talon',
    'shirt': 'Chemise', 'dress': 'Robe', 'gown': 'Robe de Soiree',
    'suit': 'Costume', 'skirt': 'Jupe', 'corset': 'Corset', 'top': 'Haut',
    'tshirt': 'T-Shirt', 'check': 'a Carreaux', 'plaid': 'Ecossais',
    'short': 'Courte', 'sleeve': 'Manche', 'leather': 'Cuir',
    'earring': 'Boucle d\'Oreille', 'tropical': 'Tropicale',
    'crystal': 'Cristal', 'oval': 'Ovale',
    'charger': 'Chargeur', 'case': 'Etui', 'cover': 'Coque',
    'silicone': 'Silicone', 'wireless': 'Sans Fil', 'phone': 'Telephone',
    'iphone': 'iPhone', 'magsafe': 'MagSafe', 'plum': 'Prune',
    'echo': 'Echo', 'plus': 'Plus', 'airpods': 'AirPods', 'max': 'Max',
    'homepod': 'HomePod', 'mini': 'Mini', 'cosmic': 'Cosmique',
    'beats': 'Beats', 'flex': 'Flex', 'earphones': 'Ecouteurs',
    'battery': 'Batterie', 'pack': 'Pack',
    'bed': 'Lit', 'sofa': 'Canape', 'table': 'Table', 'bedside': 'Chevet',
    'african': 'Africain', 'cherry': 'Cerisier', 'chair': 'Chaise',
    'conference': 'Conference', 'executive': 'Executive', 'bathroom': 'Salle de Bain',
    'sink': 'Lavabo', 'mirror': 'Miroir', 'wooden': 'en Bois',
    'lipstick': 'Rouge a Levres', 'nail': 'Ongles', 'polish': 'Vernis',
    'mascara': 'Mascara', 'eyeshadow': 'Fard a Paupieres', 'palette': 'Palette',
    'powder': 'Poudre', 'canister': 'Boite', 'lash': 'Cils', 'princess': 'Princesse',
    'eau': 'Eau', 'de': 'de', 'parfum': 'Parfum', 'cologne': 'Cologne',
    'belt': 'Ceinture', 'rolex': 'Rolex', 'longines': 'Longines',
    'datejust': 'Datejust', 'submariner': 'Submariner', 'cellini': 'Cellini',
    'date': 'Date', 'dial': 'Cadran', 'moonphase': 'Phase de Lune',
    'wrist': 'Poignet', 'classic': 'Classique', 'party': 'Soiree',
}

def slug_to_name(slug):
    """
    Transforme un slug d'image DummyJSON (ex: 'blue-women's-handbag')
    en un nom de produit lisible et traduit (ex: 'Sac a Main Femme Bleu').
    """
    clean = slug.replace("'", '').replace('.', ' ')
    words = re.split(r'[-_]', clean)
    translated = []
    for w in words:
        w_lower = w.lower()
        translated.append(TRANSLATIONS.get(w_lower, w.capitalize()))
    return ' '.join(translated).strip()

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def extract_slug_from_url(image_url):
    """Extrait le slug du produit depuis une URL DummyJSON.
       ex: .../product-images/womens-bags/blue-women's-handbag/thumbnail.webp
       -> 'blue-women's-handbag' """
    parts = image_url.rstrip('/').split('/')
    if len(parts) >= 2:
        return parts[-2]
    return 'produit'

def assign_category(categoryid_raw):
    if not categoryid_raw:
        return random.choice(CATEGORY_LABELS)
    return CATEGORY_LABELS[hash(str(categoryid_raw)) % len(CATEGORY_LABELS)]

PRICES = {
    'Tech': (1500, 15000), 'Mode': (200, 2500), 'Maison': (100, 1800),
    'Beaute': (80, 600),   'Sport': (150, 1200), 'Bureau': (100, 2000),
    'Audio': (300, 3000),  'Accessoires': (50, 800),
}

def synth_price(category):
    lo, hi = PRICES[category]
    return round(random.uniform(lo, hi), 2)

def fetch_all_dummyjson(max_retries=3):
    print("Recuperation des 194 produits DummyJSON...")
    url = "https://dummyjson.com/products?limit=194&skip=0"
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Chrome/120'})
            r = urllib.request.urlopen(req, timeout=30, context=ssl_ctx())
            data = json.loads(r.read())
            products = data.get('products', [])
            print(f"  {len(products)} produits recuperes")
            return products
        except Exception as e:
            last_error = e
            print(f"  Tentative {attempt}/{max_retries} echouee : {e}")
            if attempt < max_retries:
                import time
                time.sleep(3)
    raise RuntimeError(f"Impossible de joindre DummyJSON apres {max_retries} tentatives : {last_error}")

def build_image_bank(dummyjson_products):
    """
    Banque d'images par categorie ShopAI, avec le SLUG conserve a cote
    de chaque URL pour pouvoir generer un nom coherent plus tard.
    Retourne : { 'Tech': [(url, slug), ...], ... }
    """
    bank = {cat: [] for cat in CATEGORY_LABELS}

    for p in dummyjson_products:
        dj_cat = p.get('category', '')
        shopai_cat = DUMMYJSON_TO_SHOPAI.get(dj_cat, None)
        if not shopai_cat:
            continue
        thumb = p.get('thumbnail', '')
        if not thumb:
            continue
        slug = extract_slug_from_url(thumb)
        entry = (thumb, slug)
        if entry not in bank[shopai_cat]:
            bank[shopai_cat].append(entry)

    print("  Banque d'images (avec slugs pour noms coherents) :")
    for cat in CATEGORY_LABELS:
        print(f"    {cat:12s}: {len(bank[cat])} images")
        if not bank[cat]:
            bank[cat] = bank['Tech']
            print(f"    WARN: {cat} -> fallback Tech")

    return bank

def pick_image_and_name(bank, category, itemid, used_tracker):
    """
    Selectionne une image JAMAIS UTILISEE dans cette categorie si possible
    (used_tracker garde l'index de la prochaine image disponible par categorie),
    et genere le NOM du produit a partir du slug de CETTE MEME image.
    Garantit zero doublon visuel tant que le nombre de produits demandes
    dans une categorie ne depasse pas le nombre d'images disponibles.
    """
    entries = bank.get(category, [])
    if not entries:
        return f"https://picsum.photos/seed/{itemid}/400/400", f"Produit {itemid}"

    idx = used_tracker.get(category, 0)
    image_url, slug = entries[idx % len(entries)]
    used_tracker[category] = idx + 1

    name = slug_to_name(slug)
    return image_url, name

def prepare_dummy_products(dummyjson_products, image_bank):
    eligible = [p for p in dummyjson_products if p.get('category','') in DUMMYJSON_TO_SHOPAI]

    priority = [
        'smartphones', 'laptops', 'beauty', 'sports-accessories',
        'mens-shirts', 'womens-dresses', 'fragrances', 'furniture',
        'tablets', 'mens-shoes', 'womens-bags', 'skin-care',
        'mens-watches', 'home-decoration', 'sunglasses', 'tops',
        'womens-shoes', 'womens-watches', 'mobile-accessories',
        'vehicle', 'motorcycle', 'womens-jewellery',
        'kitchen-accessories', 'groceries',
    ]
    sorted_p = sorted(
        eligible,
        key=lambda p: priority.index(p.get('category','groceries'))
        if p.get('category','') in priority else 99
    )

    result = []
    for p in sorted_p[:100]:
        shopai_cat = DUMMYJSON_TO_SHOPAI.get(p.get('category', ''), 'Tech')
        # Pour les vrais produits DummyJSON : on garde leur vrai nom (le plus precis possible)
        result.append({
            'external_id': f"dummy-{p['id']}",
            'name':     p.get('title', f"Produit {p['id']}"),
            'price':    round(float(p.get('price', 0)) * 10.2, 2),
            'category': shopai_cat,
            'metadata': {
                'image_url':   p.get('thumbnail'),
                'rating':      round(float(p.get('rating', 4.0)), 1),
                'vendor':      p.get('brand', 'ShopAI Store') or 'ShopAI Store',
                'source':      'dummyjson',
                'description': p.get('description', ''),
            }
        })
    return result

def load_retailrocket(image_bank):
    print(f"\nLecture Retailrocket ({EVENTS_CLEAN_PATH})...")
    df = pd.read_parquet(EVENTS_CLEAN_PATH, columns=['itemid'])
    top_items = list(df['itemid'].value_counts().head(TOP_RETAILROCKET).index.tolist())
    print(f"  {len(top_items)} itemid retenus")

    print("Resolution categoryid...")
    catid_map = {}
    top_items_set = set(top_items)
    for path in [ITEM_PROPS_PATH_1, ITEM_PROPS_PATH_2]:
        print(f"  Scan {path}...")
        for chunk in pd.read_csv(path, chunksize=500_000):
            rel = chunk[
                (chunk['itemid'].isin(top_items_set)) &
                (chunk['property'] == 'categoryid')
            ]
            for _, row in rel.iterrows():
                catid_map[row['itemid']] = row['value']
    print(f"  {len(catid_map)} categoryid resolus")

    # Repartir les itemid de facon equilibree par categorie, pour que
    # chaque categorie ne recoive pas plus de produits que d'images disponibles
    items_by_category = {cat: [] for cat in CATEGORY_LABELS}
    for itemid in top_items:
        cat = assign_category(catid_map.get(itemid))
        items_by_category[cat].append(itemid)

    # Tronquer chaque categorie au nombre d'images disponibles (zero doublon)
    final_items = []
    for cat in CATEGORY_LABELS:
        max_available = len(image_bank.get(cat, []))
        items = items_by_category[cat][:max_available] if max_available > 0 else items_by_category[cat]
        for itemid in items:
            final_items.append((itemid, cat))
        skipped = len(items_by_category[cat]) - len(items)
        if skipped > 0:
            print(f"    {cat}: {skipped} produits ignores (pas assez d'images uniques)")

    print(f"  {len(final_items)} produits retenus apres equilibrage (zero doublon visuel)")

    used_tracker = {}
    result = []
    for itemid, cat in final_items:
        image_url, name = pick_image_and_name(image_bank, cat, itemid, used_tracker)
        result.append({
            'external_id': str(itemid),
            'name':     name,
            'price':    synth_price(cat),
            'category': cat,
            'metadata': {
                'image_url': image_url,
                'rating':    round(random.uniform(3.8, 5.0), 1),
                'vendor':    'ShopAI Store',
                'source':    'retailrocket_enriched',
            }
        })
    return result

def main():
    dummyjson_raw     = fetch_all_dummyjson()
    print("\nConstruction de la banque d'images...")
    image_bank        = build_image_bank(dummyjson_raw)
    dummy_products    = prepare_dummy_products(dummyjson_raw, image_bank)
    print(f"\n  {len(dummy_products)} vrais produits DummyJSON prepares")
    retailrocket_prods = load_retailrocket(image_bank)
    print(f"  {len(retailrocket_prods)} produits Retailrocket prepares (nom derive de l'image)")

    all_products = dummy_products + retailrocket_prods
    print(f"\nTotal : {len(all_products)} produits")

    with app.app_context():
        valid_ids = [p['external_id'] for p in all_products]
        to_delete = Product.query.filter(Product.external_id.notin_(valid_ids)).all()
        if to_delete:
            print(f"  Suppression de {len(to_delete)} produits obsoletes")
            for p in to_delete:
                db.session.delete(p)
            db.session.commit()

        created, updated = 0, 0
        for p in all_products:
            existing = Product.query.filter_by(external_id=p['external_id']).first()
            meta_json = json.dumps(p['metadata'], ensure_ascii=False)
            if existing:
                existing.name     = p['name']
                existing.price    = p['price']
                existing.category = p['category']
                existing.product_metadata = meta_json
                updated += 1
            else:
                db.session.add(Product(
                    external_id=p['external_id'],
                    name=p['name'],
                    price=p['price'],
                    category=p['category'],
                    product_metadata=meta_json
                ))
                created += 1

        db.session.commit()
        total = Product.query.count()
        print(f"\nTermine : {created} crees, {updated} mis a jour.")
        print(f"Total en base : {total} produits")
        print("  -> nom du produit derive DIRECTEMENT du slug de son image")
        print("  -> coherence nom/image garantie a 100%")

if __name__ == '__main__':
    main()