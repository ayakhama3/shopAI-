/*
  ShopAI — Navigation et gestion de l'état actif des menus
  Assure que tous les liens et boutons naviguent vers les bonnes pages
  et que l'état actif du menu est reflété.
*/

const MAIN_ROUTES = {
  '/': 'Accueil',
  '/catalogue': 'Catalogue',
  '/deals': 'Offres Flash',
  '/favoris': 'Favoris',
  '/panier_ia': 'Panier',
  '/historique': 'Commandes',
  '/messagerie': 'Messages',
  '/parametres': 'Paramètres',
  '/portefeuille': 'Portefeuille',
  '/dashboard': 'Tableau de bord',
  '/dashboard_2': 'Dashboard 2',
  '/dashboard_stats': 'Statistiques',
  '/admin_catalogue': 'Catalogue (Admin)',
  '/admin_commandes': 'Commandes (Admin)',
  '/admin_fidelite': 'Fidélité (Admin)',
  '/admin_messagerie': 'Messages (Admin)',
  '/admin_parametres': 'Paramètres (Admin)',
  '/admin_portefeuille': 'Portefeuille (Admin)',
};

// Mettre à jour l'état actif des menus
function updateActiveMenus() {
  const currentPath = window.location.pathname;
  
  // Marquer tous les liens
  document.querySelectorAll('a[href], button[data-href]').forEach(el => {
    const href = el.getAttribute('href') || el.getAttribute('data-href');
    if (!href || href === '#') return;
    
    const isActive = href === currentPath;
    const parent = el.closest('.flex.items-center.gap-3');
    
    if (isActive && parent) {
      parent.classList.remove('text-on-surface-variant', 'hover:bg-surface-container-high', 'hover:bg-surface-variant');
      parent.classList.add('bg-secondary-container', 'text-on-secondary-container', 'rounded-lg', 'font-bold', 'shadow-sm');
    } else if (parent) {
      parent.classList.remove('bg-secondary-container', 'text-on-secondary-container', 'rounded-lg', 'font-bold', 'shadow-sm');
      parent.classList.add('text-on-surface-variant', 'hover:bg-surface-container-high', 'hover:bg-surface-variant');
    }
  });
}

// Fixer tous les liens avec données manquantes
function fixSidebarLinks() {
  const sidebarLinks = {
    'Accueil': '/',
    'Home': '/',
    'Catalog': '/catalogue',
    'Catalogue': '/catalogue',
    'Grid_view': '/catalogue',
    'Deals': '/deals',
    'Sell': '/deals',
    'Search': '/catalogue',
    'Favorite': '/favoris',
    'Package': '/historique',
    'Chat': '/messagerie',
    'Account_balance_wallet': '/portefeuille',
    'Stars': '/admin_fidelite',
    'Settings': '/parametres',
    'Conduit': '/messagerie',
    'Dashboard': '/dashboard',
    'Dashboard 2': '/dashboard_2',
    'Statistics': '/dashboard_stats',
  };

  document.querySelectorAll('a[href="#"]').forEach(link => {
    const text = (link.textContent || link.getAttribute('title') || '').trim().toLowerCase();
    let route = null;

    // Chercher par texte
    for (const [key, val] of Object.entries(sidebarLinks)) {
      if (text.includes(key.toLowerCase())) {
        route = val;
        break;
      }
    }

    // Chercher par data-icon
    const icon = link.querySelector('.material-symbols-outlined');
    if (icon && !route) {
      const iconName = (icon.getAttribute('data-icon') || icon.textContent || '').toLowerCase();
      for (const [key, val] of Object.entries(sidebarLinks)) {
        if (iconName.includes(key.toLowerCase())) {
          route = val;
          break;
        }
      }
    }

    if (route) {
      link.setAttribute('href', route);
    }
  });
}

// Initialiser
document.addEventListener('DOMContentLoaded', () => {
  fixSidebarLinks();
  updateActiveMenus();
});

// Mettre à jour quand on navigue (via pushState hook)
window.addEventListener('popstate', updateActiveMenus);
const origPushState = window.history.pushState;
window.history.pushState = function(...args) {
  const result = origPushState.apply(this, args);
  setTimeout(updateActiveMenus, 0);
  return result;
};

window.ShopAINavigation = {
  updateActiveMenus,
  fixSidebarLinks,
  MAIN_ROUTES,
};
