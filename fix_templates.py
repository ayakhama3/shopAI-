"""
fix_templates.py
────────────────
Supprime les séquences `\r\n` LITTÉRALES (le texte backslash-r-backslash-n)
qui ont été injectées par erreur entre les balises <script> dans les templates.

Usage :
  python fix_templates.py
  python fix_templates.py --dir chemin/vers/templates
"""

import os
import re
import argparse

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_TEMPLATES_DIR = os.path.join("frontend", "templates")

# Ce que l'on cherche : la séquence LITTÉRALE `r`n (pas un vrai retour chariot)
# Elle apparaît par exemple dans :
#   <script src="/static/js/cart.js"></script>`r`n<script src="/static/js/nav.js">
PATTERN = re.compile(r'`r`n', re.IGNORECASE)

# ── Fonctions ─────────────────────────────────────────────────────────────────

def fix_file(filepath: str) -> bool:
    """Lit le fichier, remplace les `r`n littéraux, réécrit si nécessaire.
    Retourne True si le fichier a été modifié."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
    except OSError as e:
        print(f"  [ERREUR] Impossible de lire {filepath} : {e}")
        return False

    fixed = PATTERN.sub("", original)

    if fixed == original:
        return False  # Rien à changer

    try:
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(fixed)
    except OSError as e:
        print(f"  [ERREUR] Impossible d'écrire {filepath} : {e}")
        return False

    count = len(PATTERN.findall(original))
    print(f"  [OK] {filepath}  →  {count} occurrence(s) supprimée(s)")
    return True


def fix_directory(directory: str) -> None:
    """Parcourt récursivement le dossier et corrige tous les .html"""
    if not os.path.isdir(directory):
        print(f"[ERREUR] Dossier introuvable : {directory}")
        return

    modified = 0
    total = 0

    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.lower().endswith(".html"):
                continue
            total += 1
            filepath = os.path.join(root, filename)
            if fix_file(filepath):
                modified += 1

    print(f"\n{'─'*50}")
    print(f"Résultat : {modified}/{total} fichier(s) corrigé(s) dans '{directory}'")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Supprime les `r`n littéraux dans les templates HTML.")
    parser.add_argument(
        "--dir", "-d",
        default=DEFAULT_TEMPLATES_DIR,
        help=f"Chemin vers le dossier des templates (défaut : {DEFAULT_TEMPLATES_DIR})"
    )
    args = parser.parse_args()

    print(f"Correction des templates dans : {args.dir}\n")
    fix_directory(args.dir)


if __name__ == "__main__":
    main()