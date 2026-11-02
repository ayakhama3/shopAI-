/**
 * frontend/static/js/recommendations.js
 *
 * Gère l'affichage des recommandations personnalisées sur l'accueil et les deals.
 *
 * CORRECTIONS :
 * - Utilise /api/recommendations/me (route hybride avec JWT) plutôt que
 *   /api/recommandations/<id> (ancienne route legacy sans résolution produit)
 * - Gestion d'erreur propre : timeout, réseau coupé, serveur indisponible
 * - Affiche un message d'état contextuel selon la source (onboarding / als / fallback)
 * - Enregistre les interactions view en temps réel pour alimenter le futur ALS
 * - Compatible avec auth.js (ShopAIAuth.getToken())
 */

(function () {
  'use strict';

  // ──────────────────────────────────────────────────────────────────────────
  // Configuration
  // ──────────────────────────────────────────────────────────────────────────
  const CONFIG = {
    apiBase:         'http://127.0.0.1:5000',
    timeoutMs:       15000,
    maxCards:        10,
    containerId:     'recommendations-grid',
    sectionId:       'recommendations-section',
    sourceMessageId: 'recommendations-source-message',
    skeletonCount:   5,
  };

  const SOURCE_LABELS = {
    als:               '✨ Recommandé par notre IA',
    onboarding:        '💡 Basé sur vos préférences',
    onboarding_fallback: '💡 Basé sur vos préférences',
    fallback:          '🔥 Produits populaires',
  };

  // ──────────────────────────────────────────────────────────────────────────
  // Utilitaires
  // ──────────────────────────────────────────────────────────────────────────

  function getToken() {
    if (window.ShopAIAuth && typeof ShopAIAuth.getToken === 'function') {
      return ShopAIAuth.getToken();
    }
    return (
      sessionStorage.getItem('shopai_token') ||
      localStorage.getItem('shopai_token') ||
      null
    );
  }

  function fetchWithTimeout(url, options = {}, ms = CONFIG.timeoutMs) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), ms);
    return fetch(url, { ...options, signal: controller.signal }).finally(() =>
      clearTimeout(id)
    );
  }

  function renderStars(note) {
    const full  = Math.floor(note);
    const half  = note - full >= 0.5 ? 1 : 0;
    const empty = 5 - full - half;
    return (
      '★'.repeat(full) +
      (half ? '½' : '') +
      '☆'.repeat(empty)
    );
  }

  function formatPrice(prix) {
    if (prix == null) return '';
    return Number(prix).toLocaleString('fr-MA', {
      style: 'currency', currency: 'MAD', minimumFractionDigits: 2,
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Squelettes de chargement
  // ──────────────────────────────────────────────────────────────────────────

  function showSkeletons(container) {
    container.innerHTML = Array(CONFIG.skeletonCount).fill(0).map(() => `
      <div class="animate-pulse bg-white rounded-2xl shadow p-4 flex flex-col gap-3">
        <div class="bg-gray-200 rounded-xl h-40 w-full"></div>
        <div class="bg-gray-200 rounded h-4 w-3/4"></div>
        <div class="bg-gray-200 rounded h-4 w-1/2"></div>
        <div class="bg-gray-200 rounded h-8 w-full"></div>
      </div>
    `).join('');
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Carte produit
  // ──────────────────────────────────────────────────────────────────────────

  function buildCard(product) {
    const nom      = product.nom || product.name || 'Produit';
    const prix     = product.prix != null ? product.prix : product.price;
    const categorie = product.categorie || product.category || '';
    const note     = parseFloat(product.note || 4.5);
    const raison   = product.raison || '';
    const image    = product.image || `https://placehold.co/200x200?text=${encodeURIComponent(categorie || 'Produit')}`;
    const id       = product.id || product.itemId || '';
    const score    = product.score ? Math.round(product.score) : null;

    const card = document.createElement('div');
    card.className =
      'bg-white rounded-2xl shadow-md hover:shadow-xl transition-all duration-300 ' +
      'flex flex-col overflow-hidden cursor-pointer group';
    card.dataset.productId = id;

    card.innerHTML = `
      <div class="relative overflow-hidden">
        <img
          src="${image}"
          alt="${nom}"
          class="w-full h-44 object-cover group-hover:scale-105 transition-transform duration-300"
          onerror="this.src='https://placehold.co/200x200?text=ShopAI'"
        />
        ${score ? `<span class="absolute top-2 right-2 bg-indigo-600 text-white text-xs font-bold px-2 py-1 rounded-full">Score ${score}</span>` : ''}
        ${categorie ? `<span class="absolute top-2 left-2 bg-white/90 text-indigo-700 text-xs font-semibold px-2 py-1 rounded-full">${categorie}</span>` : ''}
      </div>
      <div class="flex flex-col flex-1 p-4 gap-2">
        <h3 class="font-semibold text-gray-800 text-sm line-clamp-2">${nom}</h3>
        <div class="text-yellow-400 text-xs">${renderStars(note)} <span class="text-gray-500">${note.toFixed(1)}</span></div>
        ${prix != null ? `<p class="text-indigo-700 font-bold text-base">${formatPrice(prix)}</p>` : ''}
        ${raison ? `<p class="text-xs text-gray-400 italic line-clamp-2">${raison}</p>` : ''}
        <button
          onclick="window.ShopAIFavorites && ShopAIFavorites.add(${id}); event.stopPropagation();"
          class="mt-auto flex items-center justify-center gap-1 border border-indigo-200 text-indigo-600
                 hover:bg-indigo-600 hover:text-white rounded-xl py-2 text-sm font-medium transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5
                     2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09
                     C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5
                     c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
          </svg>
          Ajouter aux favoris
        </button>
      </div>
    `;

    // Clic sur la carte → page produit + enregistrement interaction
    card.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      trackInteraction(id, 'view');
      window.location.href = `/produit?id=${id}`;
    });

    return card;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Enregistrement d'interaction (view, addtocart, etc.)
  // ──────────────────────────────────────────────────────────────────────────

  function trackInteraction(productId, eventType) {
    const token = getToken();
    if (!token || !productId) return;
    fetch(`${CONFIG.apiBase}/api/interactions`, {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        productId,
        eventType,
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {}); // non bloquant
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Appel API recommandations
  // ──────────────────────────────────────────────────────────────────────────

  async function fetchRecommendations() {
    const token = getToken();
    if (!token) {
      throw new Error('Utilisateur non connecté');
    }
    const response = await fetchWithTimeout(
      `${CONFIG.apiBase}/api/recommendations/me`,
      {
        headers: { 'Authorization': `Bearer ${token}` },
      }
    );
    if (!response.ok) {
      throw new Error(`Erreur serveur : ${response.status}`);
    }
    return response.json();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Rendu principal
  // ──────────────────────────────────────────────────────────────────────────

  async function renderRecommendations(containerId) {
    const container = document.getElementById(containerId || CONFIG.containerId);
    if (!container) return;

    showSkeletons(container);

    try {
      const data     = await fetchRecommendations();
      const produits = (data.produits || []).slice(0, CONFIG.maxCards);
      const source   = data.source || 'fallback';

      // Message contextuel selon la source
      const msgEl = document.getElementById(CONFIG.sourceMessageId);
      if (msgEl) {
        msgEl.textContent = SOURCE_LABELS[source] || SOURCE_LABELS.fallback;
        msgEl.className   = 'text-sm font-medium text-indigo-600 mb-4';
      }

      container.innerHTML = '';

      if (!produits.length) {
        container.innerHTML = `
          <div class="col-span-full text-center text-gray-400 py-12">
            <p class="text-4xl mb-2">🛍️</p>
            <p>Aucun produit à afficher pour l'instant.</p>
          </div>`;
        return;
      }

      produits.forEach((p) => container.appendChild(buildCard(p)));

    } catch (err) {
      console.warn('Recommandations indisponibles :', err.message);
      container.innerHTML = `
        <div class="col-span-full text-center text-gray-400 py-12">
          <p class="text-4xl mb-2">🛍️</p>
          <p>Découvrez nos produits populaires</p>
          <a href="/catalogue" class="mt-4 inline-block bg-indigo-600 text-white px-6 py-2 rounded-xl text-sm hover:bg-indigo-700 transition-colors">
            Voir le catalogue
          </a>
        </div>`;
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Point d'entrée — attend que le DOM soit prêt
  // ──────────────────────────────────────────────────────────────────────────

  function initRecommendations() {
    // Cherche tous les conteneurs possibles sur la page
    const containers = [
      'recommendations-grid',
      'ai-recommendations-grid',
      'deals-recommendations-grid',
    ];
    containers.forEach((id) => {
      if (document.getElementById(id)) {
        renderRecommendations(id);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRecommendations);
  } else {
    initRecommendations();
  }

  // API publique
  window.ShopAIRecommendations = {
    reload: initRecommendations,
    fetchRaw: fetchRecommendations,
    trackInteraction,
  };

})();