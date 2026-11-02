from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
import json

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=True)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role
        }


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(128), nullable=True)
    name = db.Column(db.String(512))
    price = db.Column(db.Float)
    category = db.Column(db.String(128))

    # ⚠️ metadata est un mot réservé SQLAlchemy
    product_metadata = db.Column(db.Text)

    def to_dict(self):
        try:
            meta = json.loads(self.product_metadata) if self.product_metadata else {}
        except Exception:
            meta = {}

        return {
            'id': self.id,
            'external_id': self.external_id,
            'nom': self.name,
            'prix': self.price,
            'categorie': self.category,
            'image': meta.get('image_url', 'https://placehold.co/400x400?text=Produit'),
            'note': meta.get('rating', 4.5),
            'vendor': meta.get('vendor', 'ShopAI Store'),
            'metadata': meta
        }



class Interaction(db.Model):
    __tablename__ = 'interactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    event_type = db.Column(db.String(64), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat()
        }
class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_user_product_cart'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'added_at': self.added_at.isoformat() if self.added_at else None
        }


class RecommendationLog(db.Model):
    __tablename__ = 'recommendation_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    products = db.Column(db.Text)
    source = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        try:
            prods = json.loads(self.products) if self.products else []
        except Exception:
            prods = []

        return {
            'id': self.id,
            'user_id': self.user_id,
            'products': prods,
            'source': self.source,
            'created_at': self.created_at.isoformat()
        }


class UserPreference(db.Model):
    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'category', name='uq_user_preference_category'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'category': self.category,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    items = db.Column(db.Text)  # JSON list of items
    total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(64), default='created')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Shipping / Invoice links (optionally null until created) ---
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)

    def to_dict(self):
        try:
            items = json.loads(self.items) if self.items else []
        except Exception:
            items = []
        return {
            'id': self.id,
            'user_id': self.user_id,
            'items': items,
            'total': self.total,
            'status': self.status,
            'invoice_id': self.invoice_id,
            'created_at': self.created_at.isoformat()
        }


class Invoice(db.Model):
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)

    invoice_number = db.Column(db.String(64), unique=True, nullable=True)
    status = db.Column(db.String(64), default='pending')  # pending/ready/failed

    # Storage location (MinIO ou local). For now we store a URL/path.
    pdf_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'order_id': self.order_id,
            'invoice_number': self.invoice_number,
            'status': self.status,
            'pdf_url': self.pdf_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class OrderTracking(db.Model):
    __tablename__ = 'order_tracking'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, unique=True)

    tracking_number = db.Column(db.String(64), unique=True, nullable=True)
    carrier = db.Column(db.String(128), nullable=True)

    status = db.Column(db.String(64), default='created')

    # Last known location / address (store as strings for now)
    last_location = db.Column(db.String(256), nullable=True)
    last_lat = db.Column(db.Float, nullable=True)
    last_lng = db.Column(db.Float, nullable=True)

    timeline = db.Column(db.Text, nullable=True)  # JSON list of {status, at, location}

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        try:
            timeline = json.loads(self.timeline) if self.timeline else []
        except Exception:
            timeline = []

        return {
            'id': self.id,
            'user_id': self.user_id,
            'order_id': self.order_id,
            'tracking_number': self.tracking_number,
            'carrier': self.carrier,
            'status': self.status,
            'last_location': self.last_location,
            'last_lat': self.last_lat,
            'last_lng': self.last_lng,
            'timeline': timeline,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Favorite(db.Model):
    __tablename__ = 'favorites'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_user_product_favorite'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
