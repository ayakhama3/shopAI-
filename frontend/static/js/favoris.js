/*
  ShopAI - Page Favoris (dynamique)
  Role: charger les favoris reels depuis l'API, les afficher,
  et permettre l'ajout/suppression en direct.
*/

(function () {
  'use strict';

  const GRID_ID = 'favorites-grid';
  const COUNT_ID = 'favorites-count';
  const EMPTY_STATE_ID = 'favorites-empty';

  function getToken() {
    if (window.ShopAIAuth && typeof window.ShopAIAuth.getToken === 'function') {
      return window.ShopAIAuth.getToken();
    }
    return sessionStorage.getItem('shopai_token') || localStorage.getItem('shopai_token');
  }

  function showToast(message, type) {
    if (window.ShopAIToast && typeof window.ShopAIToast.show === 'function') {
      window.ShopAIToast.show(message, type);
    } else {
      console[type === 'error' ? 'error' : 'log'](message);
    }
  }

  function formatPrice(price) {
    if (price === null || price === undefined) return '';
    return `${Number(price).toFixed(0)} MAD`;
  }

  function buildCard(entry) {
    const product = entry.product;
    const card = document.createElement('div');
    card.className = 'bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm hover:shadow-md transition-shadow overflow-hidden flex flex-col group';
    card.dataset.productId = product.id;

    const imageUrl = (product.metadata && product.metadata.image_url) || 'https://placehold.co/400x400?text=Produit';

    card.innerHTML = `
      <div class="relative aspect-square overflow-hidden">
        <img src="${imageUrl}" alt="${product.name || ''}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105">
        <button class="remove-favorite-btn absolute top-3 right-3 bg-white/90 p-2 rounded-full shadow-sm hover:bg-white transition-colors" aria-label="Retirer des favoris">
          <span class="material-symbols-outlined text-error" style="font-variation-settings: 'FILL' 1;">favorite</span>
        </button>
      </div>
      <div class="p-stack-md flex-1 flex flex-col">
        <div class="mb-2">
          <p class="text-on-surface-variant font-label-sm mb-1">${product.category || ''}</p>
          <h3 class="font-body-md text-on-surface font-semibold line-clamp-1">${product.name || 'Produit'}</h3>
        </div>
        <div class="mt-auto flex items-end justify-between mb-4">
          <span class="font-price-display text-primary">${formatPrice(product.price)}</span>
        </div>
        <button class="add-to-cart-btn w-full bg-primary text-white py-3 rounded-lg font-label-sm flex items-center justify-center gap-2 hover:bg-primary/90 transition-all active:scale-95">
          <span class="material-symbols-outlined">shopping_cart</span>
          Ajouter au panier
        </button>
      </div>
    `;

    card.querySelector('.remove-favorite-btn').addEventListener('click', () => {
      removeFavorite(product.id, card);
    });

    card.querySelector('.add-to-cart-btn').addEventListener('click', () => {
      if (window.ShopAICart && typeof window.ShopAICart.add === 'function') {
        window.ShopAICart.add(product.id);
      }
      showToast('Produit ajoute au panier', 'success');
    });

    return card;
  }

  function updateCount(count) {
    const countEl = document.getElementById(COUNT_ID);
    if (countEl) countEl.textContent = `Mes Favoris (${count})`;
  }

  function toggleEmptyState(isEmpty) {
    const emptyEl = document.getElementById(EMPTY_STATE_ID);
    const gridEl = document.getElementById(GRID_ID);
    if (emptyEl) emptyEl.classList.toggle('hidden', !isEmpty);
    if (gridEl) gridEl.classList.toggle('hidden', isEmpty);
  }

  async function loadFavorites() {
    const token = getToken();
    if (!token) {
      showToast('Veuillez vous connecter pour voir vos favoris.', 'error');
      toggleEmptyState(true);
      return;
    }

    try {
      const response = await fetch('/api/favorites', {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.status === 401) {
        showToast('Session expiree, veuillez vous reconnecter.', 'error');
        toggleEmptyState(true);
        return;
      }

      const data = await response.json();
      const grid = document.getElementById(GRID_ID);
      if (!grid) return;

      grid.innerHTML = '';
      const favorites = data.favorites || [];

      updateCount(favorites.length);
      toggleEmptyState(favorites.length === 0);

      favorites.forEach((entry) => {
        grid.appendChild(buildCard(entry));
      });
    } catch (error) {
      console.error('[ShopAI][favoris] loadFavorites', error);
      showToast('Erreur lors du chargement des favoris.', 'error');
    }
  }

  async function removeFavorite(productId, cardEl) {
    const token = getToken();
    if (!token) return;

    try {
      const response = await fetch(`/api/favorites/${productId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });

      if (!response.ok) {
        showToast('Impossible de retirer ce favori.', 'error');
        return;
      }

      cardEl.remove();
      showToast('Retire des favoris.', 'info');

      const grid = document.getElementById(GRID_ID);
      const remaining = grid ? grid.children.length : 0;
      updateCount(remaining);
      toggleEmptyState(remaining === 0);
    } catch (error) {
      console.error('[ShopAI][favoris] removeFavorite', error);
      showToast('Erreur reseau.', 'error');
    }
  }

  async function addFavorite(productId) {
    const token = getToken();
    if (!token) {
      showToast('Veuillez vous connecter.', 'error');
      return false;
    }

    try {
      const response = await fetch('/api/favorites', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ product_id: productId })
      });

      if (!response.ok) {
        showToast('Impossible d\'ajouter ce favori.', 'error');
        return false;
      }

      showToast('Ajoute aux favoris.', 'success');
      return true;
    } catch (error) {
      console.error('[ShopAI][favoris] addFavorite', error);
      showToast('Erreur reseau.', 'error');
      return false;
    }
  }

  window.ShopAIFavorites = {
    load: loadFavorites,
    add: addFavorite,
    remove: removeFavorite
  };

  document.addEventListener('DOMContentLoaded', loadFavorites);
})();