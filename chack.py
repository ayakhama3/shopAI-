import sys, os
sys.path.insert(0, 'src')
from api.main import app
from api.models import db, Order, User

with app.app_context():
    users = User.query.all()
    for u in users:
        print(f"User id={u.id} username={u.username}")
    print("---")
    orders = Order.query.all()
    print(f"Total commandes en base : {len(orders)}")
    for o in orders:
        print(f"  Order id={o.id} user_id={o.user_id} total={o.total} status={o.status}")