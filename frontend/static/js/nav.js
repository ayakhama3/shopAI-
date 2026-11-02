(function () {
  'use strict';

  const USER_LINKS = [
    { label: 'Accueil', icon: 'home', href: '/' },
    { label: 'Catalogue', icon: 'storefront', href: '/catalogue' },
    { label: 'Favoris', icon: 'favorite', href: '/favoris' },
    { label: 'Panier IA', icon: 'shopping_cart', href: '/panier_ia' },
    { label: 'Historique', icon: 'receipt_long', href: '/historique' },
    { label: 'Messagerie', icon: 'chat', href: '/messagerie' },
    { label: 'Suivi', icon: 'local_shipping', href: '/suivi_1' },
    
  ];

  const ADMIN_LINKS = [
    { label: 'Dashboard', icon: 'dashboard', href: '/dashboard' },
    { label: 'Catalogue', icon: 'inventory_2', href: '/admin_catalogue' },
    { label: 'Commandes', icon: 'shopping_cart', href: '/admin_commandes' },
    { label: 'Utilisateurs', icon: 'group', href: '#', onclick: 'showUsersModal()' },
  ];

  const ACTIVE_CLASSES = ['bg-secondary-container', 'text-on-secondary-container', 'font-bold'];
  const INACTIVE_CLASSES = ['text-on-surface-variant'];

  function notify(message, type) {
    if (window.ShopAIToast && typeof window.ShopAIToast.show === 'function') {
      window.ShopAIToast.show(message, type);
    } else if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    }
  }

  function getCurrentUser() {
    try {
      return window.ShopAIAuth && typeof window.ShopAIAuth.getUser === 'function'
        ? window.ShopAIAuth.getUser()
        : null;
    } catch (error) {
      return null;
    }
  }

  function getRole() {
    const path = window.location.pathname;
    const user = getCurrentUser();
    if (user && user.role) return user.role;
    return path.startsWith('/admin_') || path.startsWith('/dashboard') ? 'admin' : 'user';
  }

  function getLinksForRole(role) {
    return role === 'admin' ? ADMIN_LINKS : USER_LINKS;
  }

  function normalizePath(path) {
    if (!path || path === '') return '/';
    return path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path;
  }

  function isActiveLink(href, pathname) {
    const route = normalizePath(href);
    const current = normalizePath(pathname);
    if (route === '/' || route === '#') return current === '/';
    return current === route;
  }

  function linkTemplate(link) {
    return `
      <span class="material-symbols-outlined text-[20px]">${link.icon}</span>
      <span>${link.label}</span>
    `;
  }

  function styleNavLink(anchor, active) {
    anchor.classList.add('transition-all', 'duration-200', 'rounded-lg');
    if (active) {
      anchor.classList.add(...ACTIVE_CLASSES);
      anchor.classList.remove(...INACTIVE_CLASSES);
      anchor.setAttribute('aria-current', 'page');
    } else {
      anchor.classList.remove(...ACTIVE_CLASSES);
      anchor.classList.add(...INACTIVE_CLASSES);
      anchor.removeAttribute('aria-current');
    }
  }

  function isSidebarElement(element) {
    return (
      element.id === 'sidebar' ||
      element.classList.contains('sidebar') ||
      (element.tagName === 'ASIDE' &&
        (element.className || '').includes('fixed') &&
        (element.className || '').includes('w-64'))
    );
  }

  function getSidebarElements() {
    return Array.from(document.querySelectorAll('.sidebar, #sidebar, aside')).filter(isSidebarElement);
  }

  function highlightActiveLinks() {
    const pathname = window.location.pathname || '/';
    const scopedLinks = getSidebarElements().flatMap((s) => Array.from(s.querySelectorAll('a[href]')));
    scopedLinks.forEach((anchor) => {
      const href = anchor.getAttribute('href');
      if (!href || !href.startsWith('/')) return;
      styleNavLink(anchor, isActiveLink(href, pathname));
    });
  }

  function updateIdentity() {
    const user = getCurrentUser();
    if (!user) return;
    const name = user.name || user.username || user.email || 'Admin';
    document.querySelectorAll('#admin-name, .user-name, [data-user-name]').forEach((el) => {
      el.textContent = name;
    });
  }

  function updateCartBadge() {
    try {
      const count = typeof window.getCartCount === 'function' ? window.getCartCount() : 0;
      document.querySelectorAll('[data-cart-count], #cart-count').forEach((el) => {
        el.textContent = String(count);
      });
    } catch (e) {}
  }

  // ========== LOGOUT ==========
  function doLogout() {
    if (window.ShopAIAuth && typeof window.ShopAIAuth.logout === 'function') {
      window.ShopAIAuth.logout();
    } else {
      sessionStorage.clear();
      localStorage.removeItem('shopai_token');
      window.location.href = '/login';
    }
  }

  function bindLogoutButtons() {
    const selector = '[data-action="logout"], .logout-btn';
    document.querySelectorAll(selector).forEach((element) => {
      if (element.dataset.logoutBound === 'true') return;
      element.dataset.logoutBound = 'true';
      element.addEventListener('click', (e) => {
        e.preventDefault();
        doLogout();
      });
    });
  }

  // ========== INJECT LOGOUT BUTTON ==========
  function injectLogoutButton() {
    getSidebarElements().forEach((sidebar) => {
      if (sidebar.querySelector('[data-action="logout"]')) return;
      const footer = sidebar.querySelector('.border-t');
      if (!footer) return;
      const wrapper = footer.querySelector('.flex');
      if (!wrapper || wrapper.querySelector('[data-action="logout"]')) return;

      wrapper.classList.add('items-center');

      const btn = document.createElement('button');
      btn.setAttribute('data-action', 'logout');
      btn.setAttribute('title', 'Se déconnecter');
      btn.className = 'p-2 hover:bg-error-container rounded-lg transition-colors group flex-shrink-0 ml-auto';
      btn.innerHTML = `<span class="material-symbols-outlined text-on-surface-variant group-hover:text-error text-[20px]">logout</span>`;
      wrapper.appendChild(btn);
    });
  }

  // ========== INIT ==========
  function initNav() {
    try {
      const role = getRole();
      updateIdentity();
      updateCartBadge();
      injectLogoutButton();
      bindLogoutButtons();
      highlightActiveLinks();
    } catch (error) {
      console.error('[ShopAI][nav] initNav', error);
      notify('Erreur de chargement de la navigation.', 'error');
    }
  }

  window.ShopAINav = { USER_LINKS, ADMIN_LINKS, initNav, highlightActiveLinks, updateCartBadge };
  window.initNav = initNav;

  document.addEventListener('DOMContentLoaded', initNav);
})();