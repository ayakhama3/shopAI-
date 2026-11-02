"""
Script de nettoyage de l'historique des commandes.

REGLES APPLIQUEES :
1. Supprime TOUTES les commandes anonymes (user_id IS NULL), ainsi que
   leur facture et leur suivi associes.
2. Pour chaque utilisateur authentifie :
   - on garde ses 2 commandes les plus recentes (peu importe le statut)
   - on garde aussi TOUTES les commandes "en cours" (pas encore livrees
     ni annulees) -> considerees comme "a venir"
   - on supprime le reste (+ facture + tracking lies)

⚠️ FAIS UNE SAUVEGARDE DE TA BASE AVANT DE LANCER CE SCRIPT (operation
irreversible). Pour SQLite il suffit de copier le fichier .db.

A lancer depuis le dossier qui contient ton fichier Flask principal
(adapte l'import "from app import app, db" si ton fichier s'appelle
autrement, ex: server.py -> "from server import app, db") :

    python cleanup_orders.py            # mode reel
    python cleanup_orders.py --dry-run  # simulation, n'efface rien
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from main import app, db  # <-- adapte si besoin
from api.models import Order, Invoice, OrderTracking, User

# Statuts consideres comme "en cours" / "a venir" -> jamais supprimes
STATUTS_A_CONSERVER = {'created', 'paid', 'processing', 'shipped'}
NB_A_GARDER_PAR_USER = 2

DRY_RUN = '--dry-run' in sys.argv


def supprimer_commande(order):
    print(f"  - suppression commande #{order.id} (status={order.status}, user_id={order.user_id})")
    if DRY_RUN:
        return
    if order.invoice_id:
        Invoice.query.filter_by(id=order.invoice_id).delete()
    OrderTracking.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)


def main():
    with app.app_context():
        total_supprimees = 0

        # 1) Toutes les commandes anonymes
        print("== Commandes anonymes ==")
        commandes_anonymes = Order.query.filter(Order.user_id.is_(None)).all()
        for o in commandes_anonymes:
            supprimer_commande(o)
            total_supprimees += 1

        # 2) Par utilisateur : on garde les 2 dernieres + celles en cours
        print("== Commandes par utilisateur ==")
        users = User.query.all()
        for user in users:
            commandes = (
                Order.query.filter_by(user_id=user.id)
                .order_by(Order.created_at.desc())
                .all()
            )
            if not commandes:
                continue

            recentes_ids = {c.id for c in commandes[:NB_A_GARDER_PAR_USER]}

            for c in commandes:
                a_garder = (c.id in recentes_ids) or (c.status in STATUTS_A_CONSERVER)
                if not a_garder:
                    supprimer_commande(c)
                    total_supprimees += 1

        if DRY_RUN:
            print(f"\n[DRY-RUN] {total_supprimees} commande(s) seraient supprimees. Rien n'a ete modifie.")
        else:
            db.session.commit()
            print(f"\nTotal commandes supprimees : {total_supprimees}")


if __name__ == '__main__':
    main()