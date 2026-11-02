/* admin_catalogue_list.js — charge les vrais produits depuis /api/products */
(function () {
  'use strict';

  function getToken() {
    return window.ShopAIAuth?.getToken?.() ||
           sessionStorage.getItem('shopai_token') ||
           localStorage.getItem('shopai_token') || '';
  }

  async function apiGet(url) {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function apiDelete(url) {
    const res = await fetch(url, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  const STATUS_LABELS = {
    in_stock: { label: 'EN STOCK', cls: 'bg-green-100 text-green-700' },
    low_stock: { label: 'STOCK FAIBLE', cls: 'bg-orange-100 text-orange-700' },
    out_of_stock: { label: 'RUPTURE', cls: 'bg-red-100 text-red-700' },
  };

  let currentPage = 1;

  function renderGrid(products) {
    const grid = document.getElementById('product-grid');
    if (!grid) return;
    grid.innerHTML = '';

    if (!products.length) {
      grid.innerHTML = '<p class="col-span-4 text-center text-on-surface-variant py-12">Aucun produit trouvé.</p>';
      return;
    }

    products.forEach(p => {
      const st = STATUS_LABELS[p.status] || STATUS_LABELS.in_stock;
      const card = document.createElement('div');
      card.className = 'bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden shadow-sm group hover:shadow-xl transition-all duration-300';
      card.innerHTML = `
        <div class="relative h-48 overflow-hidden bg-surface-container">
          <img src="${p.image}" alt="${p.name}"
               class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
               onerror="this.src='https://placehold.co/400x300?text=Produit'"/>
          <div class="absolute top-3 left-3 flex flex-col gap-1">
            <span class="bg-primary text-on-primary text-[10px] font-bold px-2 py-1 rounded-full uppercase">${p.category || 'N/A'}</span>
            <span class="${st.cls} text-[10px] font-bold px-2 py-1 rounded-full">${st.label}</span>
          </div>
          <div class="absolute bottom-3 right-3 bg-surface-container-lowest px-2 py-1 rounded-lg border border-outline-variant">
            <span class="font-bold text-sm text-primary">${(p.price || 0).toFixed(2)} MAD</span>
          </div>
        </div>
        <div class="p-4">
          <h4 class="font-bold text-sm line-clamp-1 mb-1">${p.name || 'Sans nom'}</h4>
          <div class="flex gap-3 text-xs text-on-surface-variant mb-3">
            <span>Stock: <strong>${p.stock ?? '—'}</strong></span>
            <span>Ventes: <strong>${p.sales ?? 0}</strong></span>
          </div>
          <div class="flex items-center justify-between border-t border-outline-variant pt-3">
            <a href="/admin_add_product?edit=${p.id}"
               class="flex items-center gap-1 text-sm text-on-surface-variant hover:text-primary font-bold transition-colors">
              <span class="material-symbols-outlined text-base">edit</span> Modifier
            </a>
            <button data-id="${p.id}" class="btn-delete p-1 text-on-surface-variant hover:text-error transition-colors">
              <span class="material-symbols-outlined text-base">delete</span>
            </button>
          </div>
        </div>`;
      grid.appendChild(card);
    });

    // Boutons supprimer
    grid.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        if (!confirm('Supprimer ce produit ?')) return;
        try {
          await apiDelete(`/api/products/${id}`);
          await loadPage(currentPage);
        } catch (e) {
          alert('Erreur suppression : ' + e.message);
        }
      });
    });
  }

  function renderPagination(data) {
    const el = document.getElementById('pagination-info');
    if (el) el.textContent = `Affichage de ${(data.page - 1) * data.per_page + 1}–${Math.min(data.page * data.per_page, data.total)} sur ${data.total} produits`;

    const prev = document.getElementById('btn-prev');
    const next = document.getElementById('btn-next');
    if (prev) prev.disabled = data.page <= 1;
    if (next) next.disabled = data.page >= data.pages;
  }

  async function loadPage(page = 1) {
    currentPage = page;
    const q = document.getElementById('search-input')?.value || '';
    const category = document.getElementById('filter-category')?.value || '';
    try {
      const data = await apiGet(`/api/products?page=${page}&per_page=12&q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`);
      renderGrid(data.products || []);
      renderPagination(data);

      // Stats rapides
      const statTotal = document.getElementById('stat-total-products');
      if (statTotal) statTotal.textContent = data.total.toLocaleString();
    } catch (e) {
      console.error('Catalogue admin : erreur', e);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadPage(1);

    document.getElementById('search-input')?.addEventListener('input', () => loadPage(1));
    document.getElementById('filter-category')?.addEventListener('change', () => loadPage(1));
    document.getElementById('btn-prev')?.addEventListener('click', () => loadPage(currentPage - 1));
    document.getElementById('btn-next')?.addEventListener('click', () => loadPage(currentPage + 1));
    document.getElementById('btn-add-product')?.addEventListener('click', () => {
      window.location.href = '/admin_add_product';
    });
  });
})();