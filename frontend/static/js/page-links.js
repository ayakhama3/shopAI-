/*
  ShopAI - Liens et actions de pages.
  Role: corriger les href temporaires, brancher les boutons et garder les helpers HTML inline.
*/

(function () {
  'use strict';

  const USER_ROUTES = {
    accueil: '/',
    home: '/',
    shopai: '/',
    catalogue: '/catalogue',
    catalog: '/catalogue',
    nouveautes: '/catalogue',
    produit: '/produit',
    favoris: '/favoris',
    favorite: '/favoris',
    panier: '/panier_ia',
    cart: '/panier_ia',
    historique: '/historique',
    commandes: '/historique',
    'mes commandes': '/historique',
    deals: '/deals',
    offres: '/deals',
    promotions: '/deals',
    messagerie: '/messagerie',
    messages: '/messagerie',
    suivi: '/suivi_1',
    'suivi de commande': '/suivi_1',

    parametres: '/parametres',
    settings: '/parametres',
    legal: '/parametres',
    confidentialite: '/parametres',
    cgv: '/parametres',
    conditions: '/parametres',
    privacy: '/parametres',
    'privacy policy': '/parametres',
    'terms of service': '/parametres',
    contact: '/messagerie',
    'contact us': '/messagerie',
    support: '/messagerie',
    login: '/login',
    'se connecter': '/login',
    inscription: '/inscription',
    'creer un compte': '/inscription',
    'verifier votre numero': '/otp',
    'contacter le support': '/messagerie',
    'acheter maintenant': '/catalogue',
    'en savoir plus': '/catalogue',
    'voir tout': '/catalogue',
    commander: '/paiement_1',
    'passer la commande': '/paiement_1',
    payer: '/paiement_1',
    'confirmer paiement': '/paiement_2',
    'suivre commande': '/suivi_1',
  };

  const ADMIN_ROUTES = {
    dashboard: '/dashboard',
    'tableau de bord': '/dashboard',
    statistiques: '/dashboard_stats',
    stats: '/dashboard_stats',
    catalogue: '/admin_catalogue',
    catalog: '/admin_catalogue',
    produits: '/admin_catalogue',
    commandes: '/admin_commandes',
    orders: '/admin_commandes',
  
    loyalty: '/admin_fidelite',
    messagerie: '/admin_messagerie',
    messages: '/admin_messagerie',
    parametres: '/admin_parametres',
    settings: '/admin_parametres',
    portefeuille: '/admin_portefeuille',
    wallet: '/admin_portefeuille',
  };

  function toast(message, type) {
    if (window.ShopAIToast && typeof window.ShopAIToast.show === 'function') {
      window.ShopAIToast.show(message, type);
    } else if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    }
  }

  function normalize(text) {
    return (text || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  function visibleText(element) {
    const clone = element.cloneNode(true);
    clone.querySelectorAll('.material-symbols-outlined, svg, path, style, script').forEach((node) => node.remove());
    return clone.textContent || element.getAttribute('aria-label') || element.getAttribute('title') || '';
  }

  function isAdminPage() {
    const path = window.location.pathname;
    return path.startsWith('/admin_') || path.startsWith('/dashboard');
  }

  function routeForText(text) {
    const key = normalize(text);
    if (!key) return null;

    const primary = isAdminPage() ? ADMIN_ROUTES : USER_ROUTES;
    const secondary = isAdminPage() ? USER_ROUTES : ADMIN_ROUTES;
    if (primary[key]) return primary[key];
    if (secondary[key]) return secondary[key];

    const merged = Object.assign({}, secondary, primary);
    for (const label of Object.keys(merged)) {
      if (key.includes(label)) return merged[label];
    }
    return null;
  }

  function navigate(route) {
    if (route) window.location.href = route;
  }

  function isPlaceholderHref(href) {
    return !href || href === '#' || href === 'javascript:void(0)' || href === 'javascript:;';
  }

  function fixPlaceholderLinks() {
    document.querySelectorAll('a[href]').forEach((anchor) => {
      const href = anchor.getAttribute('href');
      if (!isPlaceholderHref(href)) return;
      const route = routeForText(visibleText(anchor));
      if (route) anchor.setAttribute('href', route);
    });
  }

  function addVisualFeedback(button, label = 'Ajoute') {
    const oldHtml = button.innerHTML;
    button.disabled = true;
    button.classList.add('opacity-80');
    button.innerHTML = `${label} <span aria-hidden="true">✓</span>`;
    window.setTimeout(() => {
      button.disabled = false;
      button.classList.remove('opacity-80');
      button.innerHTML = oldHtml;
    }, 1200);
  }

  function productFromElement(element) {
    const card = element.closest('[data-product], .product-card, .group, .rounded-xl, .border') || document;
    const name =
      card.querySelector('[data-product-name]')?.textContent?.trim() ||
      card.querySelector('h1, h2, h3, h4')?.textContent?.trim() ||
      'Produit ShopAI';
    const priceText =
      card.querySelector('[data-product-price], .font-price-display, .text-price-display')?.textContent ||
      '';
    const price = Number((priceText.match(/[\d.,]+/) || ['0'])[0].replace(',', '.')) || 0;
    const id =
      card.getAttribute('data-product-id') ||
      sessionStorage.getItem('shopai_selected_product_id') ||
      String(Date.now());
    return { id, name, price, quantity: 1 };
  }

  function addProductToCart(button) {
    const item = productFromElement(button);
    if (typeof window.addToCart === 'function') {
      window.addToCart(item);
    } else {
      const cart = JSON.parse(sessionStorage.getItem('shopai_cart') || '[]');
      const existing = cart.find((entry) => String(entry.id) === String(item.id));
      if (existing) existing.quantity = (existing.quantity || 1) + 1;
      else cart.push(item);
      sessionStorage.setItem('shopai_cart', JSON.stringify(cart));
    }
    addVisualFeedback(button, 'Ajoute');
    toast('Produit ajoute au panier.', 'success');
    if (window.ShopAINav && typeof window.ShopAINav.updateCartBadge === 'function') {
      window.ShopAINav.updateCartBadge();
    }
    window.setTimeout(() => navigate('/panier_ia'), 650);
  }

  function viewProduct(button) {
    const item = productFromElement(button);
    sessionStorage.setItem('shopai_selected_product_id', item.id);
    navigate('/produit');
  }

  async function runRetrain(button) {
    const originalHtml = button.innerHTML;
    const token = window.ShopAIAuth && typeof window.ShopAIAuth.getToken === 'function'
      ? window.ShopAIAuth.getToken()
      : sessionStorage.getItem('shopai_token') || localStorage.getItem('shopai_token');

    button.disabled = true;
    button.innerHTML = '<span class="inline-block animate-spin material-symbols-outlined text-[18px]">progress_activity</span> Retrain...';

    try {
      const response = await fetch('/api/admin/retrain', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Erreur retrain');
      toast(data.message || 'Reentrainement lance.', 'success');
    } catch (error) {
      console.error('[ShopAI][page-links] retrain', error);
      toast(error.message || 'Impossible de lancer le retrain.', 'error');
    } finally {
      button.disabled = false;
      button.innerHTML = originalHtml;
    }
  }

  function bindSemanticButtons() {
    document.querySelectorAll('button, [role="button"]').forEach((button) => {
      if (button.dataset.shopaiBound === 'true') return;
      const text = normalize(visibleText(button));
      const onclick = button.getAttribute('onclick') || '';
      const hasInlineAction = onclick && !onclick.includes("location.href='#'");

      if (text.includes('voir produit') || text.includes('voir le produit')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          viewProduct(button);
        });
        return;
      }

      if (text.includes('ajouter au panier') || text === 'ajouter' || text.includes('add_shopping_cart')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          addProductToCart(button);
        });
        return;
      }

      if (
        window.location.pathname === '/paiement_1' &&
        (text.includes('continuer vers le paiement') ||
          text.includes('continuer vers paiement') ||
          text.includes('confirmer la commande'))
      ) {
        button.dataset.shopaiBound = 'true';
        button.removeAttribute('onclick');
        button.addEventListener('click', (event) => {
          event.preventDefault();
          navigate('/paiement_2');
        });
        return;
      }

      if (text.includes('confirmer paiement')) {
        button.dataset.shopaiBound = 'true';
        button.removeAttribute('onclick');
        button.addEventListener('click', (event) => {
          event.preventDefault();
          navigate('/paiement_2');
        });
        return;
      }

      if (text === 'payer' || text.includes('payer maintenant')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          navigate('/paiement_1');
        });
        return;
      }

      if (text.includes('suivre commande')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          navigate('/suivi_1');
        });
        return;
      }

      if (text.includes('logout') || text.includes('deconnexion')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          window.ShopAIAuth ? window.ShopAIAuth.logout() : navigate('/login');
        });
        return;
      }

      if (text.includes('retrain') || text.includes('reentrain') || text.includes('reentrainement')) {
        button.dataset.shopaiBound = 'true';
        button.addEventListener('click', (event) => {
          event.preventDefault();
          runRetrain(button);
        });
        return;
      }

      if (!hasInlineAction && button.type !== 'submit') {
        const route = routeForText(text);
        if (route) {
          button.dataset.shopaiBound = 'true';
          button.addEventListener('click', (event) => {
            event.preventDefault();
            navigate(route);
          });
        }
      }
    });
  }

  function bindDataRoutes() {
    document.querySelectorAll('[data-route]').forEach((element) => {
      if (element.dataset.shopaiRouteBound === 'true') return;
      element.dataset.shopaiRouteBound = 'true';
      element.addEventListener('click', (event) => {
        event.preventDefault();
        navigate(element.getAttribute('data-route'));
      });
    });
  }

  function bindHeaderIconButtons() {
    const iconRoutes = {
      shopping_cart: '/panier_ia',
      favorite: '/favoris',
      notifications: '/messagerie',
      chat: '/messagerie',
      account_balance_wallet: '/portefeuille',
      settings: '/parametres',
    };

    document.querySelectorAll('button').forEach((button) => {
      if (button.dataset.shopaiIconBound === 'true') return;
      const icon = normalize(button.querySelector('.material-symbols-outlined')?.textContent || button.dataset.icon || button.textContent);
      const route = iconRoutes[icon];
      if (!route) return;
      button.dataset.shopaiIconBound = 'true';
      button.addEventListener('click', (event) => {
        if (button.getAttribute('onclick')) return;
        event.preventDefault();
        navigate(route);
      });
    });
  }

  function goToProduct(productId) {
    if (productId) sessionStorage.setItem('shopai_selected_product_id', String(productId));
    navigate('/produit');
  }

  function addFlashToCart(productId, productName, price) {
    const item = { id: productId, name: productName || 'Produit ShopAI', price: Number(price) || 0, quantity: 1 };
    if (typeof window.addToCart === 'function') window.addToCart(item);
    else {
      const cart = JSON.parse(sessionStorage.getItem('shopai_cart') || '[]');
      cart.push(item);
      sessionStorage.setItem('shopai_cart', JSON.stringify(cart));
    }
    toast('Produit ajoute au panier.', 'success');
    window.setTimeout(() => navigate('/panier_ia'), 350);
  }

  function toggleDropdown() {
    const dropdown = document.getElementById('avatar-dropdown');
    if (!dropdown) return;
    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
  }

  function toggleDetails(id) {
    const row = document.getElementById(id);
    const detail = row && row.querySelector('.order-details');
    if (detail) detail.style.display = detail.style.display === 'block' ? 'none' : 'block';
  }

  function toggleCategory(button) {
    if (!button) return;
    button.classList.toggle('selected');
    button.classList.toggle('bg-primary');
    button.classList.toggle('text-on-primary');
  }

  function selectPayment(mode) {
    sessionStorage.setItem('shopai_payment_method', mode);
    ['cod', 'card'].forEach((item) => {
      document.getElementById(`payment-${item}`)?.classList.toggle('border-primary', item === mode);
    });
  }

  function goToStep(step) {
    document.querySelectorAll('[data-step]').forEach((panel) => {
      panel.style.display = panel.dataset.step === String(step) ? 'block' : 'none';
    });
  }

  function switchTab(name) {
    document.querySelectorAll('.settings-tab-btn').forEach((button) => {
      button.classList.remove('bg-primary', 'text-on-primary');
    });
    document.getElementById(`btn-${name}`)?.classList.add('bg-primary', 'text-on-primary');
    document.querySelectorAll('.settings-tab-panel').forEach((panel) => {
      panel.style.display = panel.id === `tab-${name}` ? 'block' : 'none';
    });
  }

  function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) field.type = field.type === 'password' ? 'text' : 'password';
  }

  function initShopAIPageLinks() {
    fixPlaceholderLinks();
    bindDataRoutes();
    bindSemanticButtons();
    bindHeaderIconButtons();
    if (window.ShopAIAuth && typeof window.ShopAIAuth.protectCurrentPage === 'function') {
      window.ShopAIAuth.protectCurrentPage();
    }
    if (typeof window.initNav === 'function') window.initNav();
  }

  document.addEventListener('click', (event) => {
    if (!event.target.closest('.avatar-btn') && !event.target.closest('#avatar-dropdown')) {
      const dropdown = document.getElementById('avatar-dropdown');
      if (dropdown) dropdown.style.display = 'none';
    }
  });

  window.ShopAIPageLinks = {
    initShopAIPageLinks,
    fixPlaceholderLinks,
    bindSemanticButtons,
    routeForText,
    runRetrain,
  };

  window.goToProduct = goToProduct;
  window.addFlashToCart = addFlashToCart;
  window.toggleDropdown = toggleDropdown;
  window.toggleDetails = toggleDetails;
  window.toggleCategory = toggleCategory;
  window.selectPayment = selectPayment;
  window.goToStep = goToStep;
  window.switchTab = switchTab;
  window.togglePassword = togglePassword;

  document.addEventListener('DOMContentLoaded', initShopAIPageLinks);
})();
