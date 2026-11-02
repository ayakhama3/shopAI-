import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from api.main import app
from api.models import db

with app.app_context():
    db.create_all()
    print("Table favorites créée (ou déjà existante)")