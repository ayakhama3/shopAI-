import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from api.main import app
from api.models import db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    print("Tables existantes :", tables)
    
    if 'cart_items' in tables:
        print("\n✅ Table cart_items existe déjà, rien à faire.")
    else:
        # Créer uniquement la table cart_items (les autres existent déjà)
        db.create_all()
        print("\n✅ Table cart_items créée avec succès !")
    
    # Vérification finale
    inspector = inspect(db.engine)
    print("\nTables finales :", inspector.get_table_names())