(function () {
  'use strict';

  let miniMap = null;
  let miniMarker = null;
  let modalMap = null;
  let modalMarker = null;
  let pollInterval = null;
  const POLL_MS = 20000;

  function getToken() {
    return window.ShopAIAuth?.getToken?.() || 
           sessionStorage.getItem('shopai_token') || 
           localStorage.getItem('shopai_token') || 
           null;
  }

  function getOrderId() {
    return sessionStorage.getItem('shopai_last_order_id');
  }

  async function apiGet(url) {
    const token = getToken();
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "API error");
    return data;
  }

  function setText(sel, val) {
    document.querySelectorAll(sel).forEach(el => el.textContent = val);
  }

  /* =======================
     FACTURE PDF
  ======================= */
  function renderInvoice(invoice) {
    const btn = document.getElementById("invoice-pdf-link");
    if (!btn) return;
    if (invoice?.pdf_url) {
      btn.disabled = false;
      btn.onclick = () => {
        window.open(invoice.pdf_url, "_blank");
      };
    } else {
      btn.disabled = true;
    }
  }

  /* =======================
     TIMELINE (page principale)
  ======================= */
  function renderTimeline(timeline = []) {
    const container = document.getElementById("timeline-steps");
    const progress = document.getElementById("progress-line");
    if (!container) return;
    container.innerHTML = "";
    timeline.forEach((step) => {
      const div = document.createElement("div");
      div.className = "flex md:flex-col items-center gap-3 md:w-1/6";
      div.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center">
          <span class="material-symbols-outlined text-[18px]">check</span>
        </div>
        <div>
          <p class="font-bold">${step.status}</p>
          <p class="text-sm text-gray-500">${new Date(step.at).toLocaleString('fr-FR')}</p>
        </div>
      `;
      container.appendChild(div);
    });
    if (progress) {
      progress.style.width = Math.min(100, timeline.length * 20) + "%";
    }
  }

  /* =======================
     HISTORIQUE (modale)
  ======================= */
  function renderModalTimeline(timeline = []) {
    const container = document.getElementById("modal-timeline");
    if (!container) return;
    container.innerHTML = "";
    timeline.forEach((step, i) => {
      const isLast = i === timeline.length - 1;
      const div = document.createElement("div");
      div.className = "flex items-start gap-3";
      div.innerHTML = `
        <div class="w-6 h-6 rounded-full flex items-center justify-center text-[12px] flex-shrink-0 ${isLast ? 'bg-secondary text-on-secondary' : 'bg-primary text-on-primary'}">
          <span class="material-symbols-outlined text-[14px]">${isLast ? 'local_shipping' : 'check'}</span>
        </div>
        <div>
          <p class="font-bold text-label-sm">${step.status}</p>
          <p class="text-[12px] text-on-surface-variant">${new Date(step.at).toLocaleString('fr-FR')} ${step.location ? '· ' + step.location : ''}</p>
        </div>
      `;
      container.appendChild(div);
    });
  }

  /* =======================
     CARTES LEAFLET
  ======================= */
  function ensureMiniMap(lat, lng) {
    if (!document.getElementById('mini-map') || typeof L === 'undefined') return;
    if (!miniMap) {
      miniMap = L.map('mini-map', { zoomControl: false, attributionControl: false }).setView([lat, lng], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(miniMap);
      miniMarker = L.marker([lat, lng]).addTo(miniMap);
    } else {
      miniMap.setView([lat, lng], miniMap.getZoom());
      miniMarker.setLatLng([lat, lng]);
    }
    setTimeout(() => miniMap.invalidateSize(), 100);
  }

  function ensureModalMap(lat, lng) {
    if (!document.getElementById('carrier-map') || typeof L === 'undefined') return;
    if (!modalMap) {
      modalMap = L.map('carrier-map').setView([lat, lng], 13);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(modalMap);
      modalMarker = L.marker([lat, lng]).addTo(modalMap);
    } else {
      modalMap.setView([lat, lng], modalMap.getZoom());
      modalMarker.setLatLng([lat, lng]);
    }
    setTimeout(() => modalMap.invalidateSize(), 100);
  }

  /* =======================
     TRACKING (rendu commun)
  ======================= */
  function renderTracking(tracking) {
    if (!tracking) return;
    setText("[data-tracking-number]", tracking.tracking_number || "-");
    setText("[data-carrier]", tracking.carrier || "-");
    setText("[data-last-location]", tracking.last_location || "-");
    renderTimeline(tracking.timeline || []);

    if (tracking.last_lat != null && tracking.last_lng != null) {
      ensureMiniMap(tracking.last_lat, tracking.last_lng);
    }
  }

  function renderModalTracking(tracking) {
    if (!tracking) return;
    setText("[data-modal-carrier]", tracking.carrier || "-");
    setText("[data-modal-tracking-number]", tracking.tracking_number || "-");
    setText("[data-modal-status]", tracking.status || "-");
    setText("[data-modal-updated]", "Mise à jour : " + new Date().toLocaleTimeString('fr-FR'));
    renderModalTimeline(tracking.timeline || []);

    if (tracking.last_lat != null && tracking.last_lng != null) {
      ensureModalMap(tracking.last_lat, tracking.last_lng);
    }
  }

  /* =======================
     MODALE TRANSPORTEUR + POLLING
  ======================= */
  function openModal() {
    const modal = document.getElementById('carrier-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');

    const refresh = async () => {
      try {
        // Utiliser /api/orders/me pour le tracking aussi
        const me = await apiGet('/api/orders/me');
        if (me.tracking) {
          renderModalTracking(me.tracking);
          renderTracking(me.tracking);
        }
      } catch (err) {
        console.error('Erreur de rafraîchissement du suivi', err);
      }
    };

    refresh();
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(refresh, POLL_MS);
  }

  function closeModal() {
    const modal = document.getElementById('carrier-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  function setupCarrierButton() {
    document.getElementById("carrier-btn")?.addEventListener("click", openModal);
    document.getElementById("carrier-modal-close")?.addEventListener("click", closeModal);
    document.getElementById("carrier-modal")?.addEventListener("click", (e) => {
      if (e.target.id === 'carrier-modal') closeModal();
    });
  }

  /* =======================
     MAIN LOAD — Utilise /api/orders/me en priorité
  ======================= */
  async function load() {
    const token = getToken();
    if (!token) {
      showLoginPrompt();
      return;
    }

    try {
      // Utiliser /api/orders/me (plus fiable que l'ID stocké)
      const me = await apiGet('/api/orders/me');
      
      if (!me.order) {
        showEmptyState();
        return;
      }

      // Mettre à jour l'ID en session pour la prochaine fois
      sessionStorage.setItem('shopai_last_order_id', me.order.id);

      // Mettre à jour l'UI
      setText("[data-order-id]", `#ORD-${String(me.order.id).padStart(4, '0')}`);
      setText("[data-order-date]", me.order.created_at ? new Date(me.order.created_at).toLocaleDateString('fr-FR') : '—');
      setText("[data-order-total]", `${(me.order.total || 0).toFixed(2)} DH`);

      renderTracking(me.tracking);
      renderInvoice(me.invoice);

    } catch (err) {
      console.error("Erreur chargement suivi:", err);
      // Fallback sur l'ID stocké si /api/orders/me échoue
      const id = getOrderId();
      if (id) {
        try {
          const order = await apiGet(`/api/orders/${id}`);
          const tracking = await apiGet(`/api/orders/${id}/tracking`);
          const invoice = await apiGet(`/api/orders/${id}/invoice`);
          
          setText("[data-order-id]", `#ORD-${String(order.id).padStart(4, '0')}`);
          setText("[data-order-date]", order.created_at ? new Date(order.created_at).toLocaleDateString('fr-FR') : '—');
          setText("[data-order-total]", `${(order.total || 0).toFixed(2)} DH`);
          
          renderTracking(tracking);
          renderInvoice(invoice);
        } catch (fallbackErr) {
          showEmptyState();
        }
      } else {
        showEmptyState();
      }
    }
  }

  function showLoginPrompt() {
    const main = document.querySelector('main');
    if (main) {
      main.innerHTML = `
        <div class="flex flex-col items-center justify-center py-24 text-center">
          <span class="material-symbols-outlined text-6xl text-on-surface-variant mb-4">login</span>
          <h2 class="font-headline-lg text-headline-lg text-primary mb-2">Connexion requise</h2>
          <p class="text-on-surface-variant mb-6">Veuillez vous connecter pour voir vos commandes.</p>
          <a href="/login" class="bg-primary text-on-primary px-8 py-3 rounded-lg font-bold">Se connecter</a>
        </div>
      `;
    }
  }

  function showEmptyState() {
    const main = document.querySelector('main');
    if (main) {
      main.innerHTML = `
        <div class="flex flex-col items-center justify-center py-24 text-center">
          <span class="material-symbols-outlined text-6xl text-on-surface-variant mb-4">package_2</span>
          <h2 class="font-headline-lg text-headline-lg text-primary mb-2">Aucune commande trouvée</h2>
          <p class="text-on-surface-variant mb-6">Vous n'avez pas encore passé de commande.</p>
          <a href="/catalogue" class="bg-primary text-on-primary px-8 py-3 rounded-lg font-bold">Parcourir le catalogue</a>
        </div>
      `;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    load().catch(console.error);
    setupCarrierButton();
  });
})();