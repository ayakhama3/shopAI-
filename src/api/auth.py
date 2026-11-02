from flask import Blueprint, request, jsonify, current_app
from flask_login import LoginManager, login_user, logout_user, current_user
from functools import wraps
import jwt
import datetime
from werkzeug.security import check_password_hash

from api.models import db, User, UserPreference

auth_bp = Blueprint('auth', __name__)

login_manager = LoginManager()

# In-memory session store: token -> user_id
_SESSIONS = {}


def init_auth(app):
    login_manager.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None


def generate_jwt(user):
    payload = {
        'sub': user.id,
        'role': user.role,
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    }
    token = jwt.encode(payload, current_app.config.get('SECRET_KEY', 'dev-secret'), algorithm='HS256')
    # Keep in-memory for quick session validation
    _SESSIONS[token] = {'user_id': user.id, 'expires': payload['exp']}
    return token


def user_payload(user):
    preferences = [
        pref.category
        for pref in UserPreference.query.filter_by(user_id=user.id).order_by(UserPreference.category.asc()).all()
    ]
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'preferences': preferences,
        'onboarding_completed': len(preferences) > 0,
    }


def verify_jwt(token):
    if not token:
        return None
    try:
        payload = jwt.decode(token, current_app.config.get('SECRET_KEY', 'dev-secret'), algorithms=['HS256'])
        return User.query.get(int(payload.get('sub')))
    except Exception:
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Try flask-login first
        if current_user and getattr(current_user, 'is_authenticated', False):
            return f(*args, **kwargs)

        # Fallback to Authorization header JWT
        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]

        user = verify_jwt(token)
        if user:
            return f(*args, **kwargs)

        return jsonify({'error': 'Authentication required'}), 401

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # First check flask-login current_user
        user = None
        if current_user and getattr(current_user, 'is_authenticated', False):
            user = current_user

        # Else try JWT
        if user is None:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1]
                user = verify_jwt(token)

        if not user:
            return jsonify({'error': 'Authentication required'}), 401

        if getattr(user, 'role', 'user') != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403

        return f(*args, **kwargs)

    return decorated


@auth_bp.route('/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username') or data.get('email')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'username/email and password required'}), 400

    user = User.query.filter((User.username == username) | (User.email == username)).first()
    if not user:
        return jsonify({'error': 'invalid credentials'}), 401

    # Support demo plaintext password for compatibility: if password stored is plaintext
    if user.password.startswith('pbkdf2:'):
        valid = check_password_hash(user.password, password)
    else:
        valid = user.password == password

    if not valid:
        return jsonify({'error': 'invalid credentials'}), 401

    # flask-login login
    login_user(user)

    token = generate_jwt(user)
    return jsonify({'token': token, 'user': user_payload(user)})


@auth_bp.route('/logout', methods=['POST'])
def api_logout():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        _SESSIONS.pop(token, None)
    logout_user()
    return jsonify({'status': 'ok'})


@auth_bp.route('/signup', methods=['POST'])
def api_signup():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    username = data.get('username', '').strip() or email.split('@')[0]
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    phone = data.get('phone', '')
    
    # Validation
    if not email or not password:
        return jsonify({'error': 'email and password required'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400
    
    # Check if user already exists
    existing = User.query.filter((User.email == email) | (User.username == username)).first()
    if existing:
        return jsonify({'error': 'user already exists'}), 409
    
    # Create new user
    try:
        user = User(
            username=username,
            email=email,
            password=password,
            role='user'
        )
        db.session.add(user)
        db.session.commit()
        
        # Auto-login
        login_user(user)
        token = generate_jwt(user)
        
        return jsonify({
            'status': 'ok',
            'token': token,
            'user': user_payload(user)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
