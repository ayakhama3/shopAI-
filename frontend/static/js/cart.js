// ============================================================
// cart.js v2.6 – FINAL FONCTIONNEL
// ============================================================

(function() {
  'use strict';

  const API_BASE_URL = '/api';
  const CART_STORAGE_KEY = 'shopai_cart_guest';

  const ROUTES = {
    GET_CART: `${API_BASE_URL}/cart`,
    ADD_ITEM: `${API_BASE_URL}/cart`,
    MERGE_CART: `${API_BASE_URL}/cart/merge`,
    REMOVE_ITEM: (id) => `${API_BASE_URL}/cart/item/${id}`,
    UPDATE_ITEM: (id) => `${API_BASE_URL}/cart/item/${id}`,
    CLEAR_CART: `${API_BASE_URL}/cart/clear`,
  };

  let cartData = { items: [], count: 0, total: 0 };
  let isLoading = false;

  function getToken() {
    return sessionStorage.getItem('shopai_token') || 
           localStorage.getItem('shopai_token') || 
           sessionStorage.getItem('token') || 
           localStorage.getItem('token') || 
           '';
  }

  function isLoggedIn() {
    return !!getToken();
  }

  function getAuthHeaders() {
    const token = getToken();
    return token ? { 'Authorization': 'Bearer ' + token } : {};
  }

  // ─── API Helpers ───────────────────────────────────────────

  async function apiCall(method, endpoint, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }
    };
    if (body) opts.body = JSON.stringify(body);
    
    const res = await fetch(endpoint, opts);
    if (res.status === 401) { 
      sessionStorage.removeItem('shopai_token');
      localStorage.removeItem('shopai_token');
      throw new Error('Session expirée'); 
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Erreur ' + res.status);
    }
    return res.status === 204 ? {} : res.json();
  }

  const apiGet = (endpoint) => apiCall('GET', endpoint);
  const apiPost = (endpoint, body) => apiCall('POST', endpoint, body);
  const apiPut = (endpoint, body) => apiCall('PUT', endpoint, body);
  const apiDelete = (endpoint) => apiCall('DELETE', endpoint);

  // ─── Guest Cart (localStorage) ───────────────────────────

  function loadGuestCart() {
    try {
      const raw = localStorage.getItem(CART_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        cartData = { 
          items: parsed.items || [], 
          count: parsed.count || 0, 
          total: parsed.total || 0 
        };
      }
    } catch (e) {
      console.warn('[cart] Impossible de charger le panier invité', e);
      cartData = { items: [], count: 0, total: 0 };
    }
    window.cartData = cartData;
  }

  function saveGuestCart() {
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cartData));
    } catch (e) {
      console.warn('[cart] Impossible de sauvegarder le panier invité', e);
    }
  }

  // ─── Server Sync ───────────────────────────────────────────

  async function syncWithServer() {
    if (!isLoggedIn() || isLoading) return;
    isLoading = true;
    try {
      const serverCart = await apiGet(ROUTES.GET_CART);
      if (serverCart) {
        cartData = {
          items: serverCart.items || [],
          count: serverCart.count || 0,
          total: serverCart.total || 0
        };
        window.cartData = cartData;
        window.dispatchEvent(new Event('cart-updated'));
      }
    } catch (e) {
      console.error('[cart] Erreur sync serveur:', e);
    } finally {
      isLoading = false;
    }
  }

  async function mergeGuestCart() {
    if (!isLoggedIn()) return;
    
    const localRaw = localStorage.getItem(CART_STORAGE_KEY);
    if (!localRaw) {
      // Pas de panier local, juste sync avec le serveur
      await syncWithServer();
      return;
    }
    
    try {
      const localCart = JSON.parse(localRaw);
      if (localCart.items && localCart.items.length > 0) {
        // 🔥 Envoyer le panier local au serveur pour fusion
        await apiPost(ROUTES.MERGE_CART, { items: localCart.items });
        localStorage.removeItem(CART_STORAGE_KEY);
      }
      // 🔥 Toujours re-sync après merge pour avoir les données à jour
      await syncWithServer();
    } catch (e) {
      console.error('[cart] Erreur fusion panier:', e);
      // En cas d'erreur, garder le local et tenter un sync
      await syncWithServer();
    }
  }

  // ─── Public Actions ────────────────────────────────────────

  async function addToCart(product) {
    if (!product || !product.id) {
      console.error('[cart] Produit invalide:', product);
      return;
    }

    if (isLoggedIn()) {
      try {
        await apiPost(ROUTES.ADD_ITEM, {
          product_id: product.id,
          quantity: product.quantity || 1
        });
        await syncWithServer();
      } catch (e) {
        console.error('[cart] Erreur ajout serveur, fallback local:', e);
        addToLocalCart(product);
      }
    } else {
      addToLocalCart(product);
    }
  }

  function addToLocalCart(product) {
    const existing = cartData.items.find(item => 
      item.product_id === product.id || item.id === product.id
    );
    if (existing) {
      existing.quantity = (existing.quantity || 1) + (product.quantity || 1);
    } else {
      cartData.items.push({
        product_id: product.id,
        id: product.id,
        name: product.name,
        price: product.price,
        quantity: product.quantity || 1,
        image: product.image,
        category: product.category
      });
    }
    recalcTotals();
    saveGuestCart();
    window.dispatchEvent(new Event('cart-updated'));
  }

  async function removeFromCart(productId) {
    if (isLoggedIn()) {
      try {
        await apiDelete(ROUTES.REMOVE_ITEM(productId));
        await syncWithServer();
        return;
      } catch (e) {
        console.error('[cart] Erreur suppression serveur, fallback local:', e);
      }
    }
    cartData.items = cartData.items.filter(item => 
      item.product_id !== productId && item.id !== productId
    );
    recalcTotals();
    saveGuestCart();
    window.dispatchEvent(new Event('cart-updated'));
  }

  async function updateQuantity(productId, quantity) {
    if (quantity < 1) {
      await removeFromCart(productId);
      return;
    }

    if (isLoggedIn()) {
      try {
        await apiPut(ROUTES.UPDATE_ITEM(productId), { quantity });
        await syncWithServer();
        return;
      } catch (e) {
        console.error('[cart] Erreur mise à jour serveur, fallback local:', e);
      }
    }
    const item = cartData.items.find(item => 
      item.product_id === productId || item.id === productId
    );
    if (item) {
      item.quantity = quantity;
      recalcTotals();
      saveGuestCart();
      window.dispatchEvent(new Event('cart-updated'));
    }
  }

  async function clearCart() {
    if (isLoggedIn()) {
      try {
        await apiDelete(ROUTES.CLEAR_CART);
      } catch (e) {
        console.error('[cart] Erreur vidage serveur:', e);
      }
    }
    cartData = { items: [], count: 0, total: 0 };
    localStorage.removeItem(CART_STORAGE_KEY);
    window.cartData = cartData;
    window.dispatchEvent(new Event('cart-updated'));
  }

  function recalcTotals() {
    let count = 0;
    let total = 0;
    for (let i = 0; i < cartData.items.length; i++) {
      const item = cartData.items[i];
      const qty = parseInt(item.quantity) || 1;
      const price = parseFloat(item.price) || 0;
      count += qty;
      total += qty * price;
    }
    cartData.count = count;
    cartData.total = Math.round(total * 100) / 100;
    window.cartData = cartData;
  }

  // ─── Exposition ────────────────────────────────────────────

  window.cartData = cartData;
  window.cartAPI = {
    addToCart,
    removeFromCart,
    updateQuantity,
    clearCart,
    syncWithServer,
    mergeGuestCart,
    getToken,
    isLoggedIn,
    loadGuestCart
  };
 window.addToCart = addToCart;
  // ─── Init ──────────────────────────────────────────────────

  function init() {
    loadGuestCart();
    
    if (isLoggedIn()) {
      // Sync serveur puis merge si panier local existe
      syncWithServer().then(() => {
        mergeGuestCart();
      });
    }
    
    // 🔥 Recharger au focus (retour de paiement_1, etc.)
    window.addEventListener('focus', () => {
      if (isLoggedIn()) {
        syncWithServer();
      } else {
        loadGuestCart();
        window.dispatchEvent(new Event('cart-updated'));
      }
    });
    
    console.log('[cart] Initialisé v2.6. Token:', isLoggedIn() ? 'connecté' : 'invité');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();