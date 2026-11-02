// admin_commandes.js - Gestion dynamique des commandes admin

let currentPage = 1;
let perPage = 10;
let currentStatus = '';

function getToken() {
    if (window.ShopAIAuth && window.ShopAIAuth.getToken) {
        return window.ShopAIAuth.getToken();
    }
    return sessionStorage.getItem('shopai_token') 
        || localStorage.getItem('shopai_token') 
        || '';
}

function getHeaders() {
    const token = getToken();
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// ========== EXPORT CSV ==========
async function exportCSV() {
    try {
        showToast('Génération du CSV...', 'info');
        
        // Récupérer TOUTES les commandes (pas seulement la page)
        const res = await fetch('/api/admin/orders?per_page=10000', { headers: getHeaders() });
        const data = await res.json();
        
        if (!data.orders || data.orders.length === 0) {
            showToast('Aucune commande à exporter', 'warning');
            return;
        }

        // Headers CSV
        const headers = ['ID', 'Reference', 'Client', 'Email', 'Date', 'Statut', 'Total', 'Methode_Paiement'];
        
        // Lignes
        const rows = data.orders.map(o => [
            o.id,
            o.reference,
            o.user,
            o.email || '',
            o.date,
            getStatusConfig(o.status).label,
            o.total,
            'Carte'
        ]);

        // Générer CSV
        const csvContent = [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
        
        // Télécharger
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const date = new Date().toISOString().split('T')[0];
        
        link.href = URL.createObjectURL(blob);
        link.download = `shopai_orders_${date}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showToast(`✅ ${data.orders.length} commandes exportées !`, 'success');
        
    } catch (e) {
        console.error(e);
        showToast('❌ Erreur export CSV', 'error');
    }
}

// ========== CREATE MANUAL ORDER ==========
function createManualOrder() {
    const modal = document.getElementById('modal-create-order');
    if (modal) {
        modal.classList.remove('hidden');
    } else {
        showToast('Modal non trouvé - vérifiez le HTML', 'error');
    }
}

function closeModal() {
    const modal = document.getElementById('modal-create-order');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// Soumettre la commande manuelle
async function submitManualOrder() {
    const form = document.getElementById('form-create-order');
    if (!form) return;

    const formData = new FormData(form);
    
    const price = parseFloat(formData.get('price')) || 0;
    const quantity = parseInt(formData.get('quantity')) || 1;
    
    const data = {
        items: [{
            name: formData.get('product_name'),
            price: price,
            quantity: quantity,
            product_id: formData.get('product_id') || null
        }],
        total: price * quantity,
        payment_method: formData.get('payment_method'),
        user_id: parseInt(formData.get('user_id')) || null
    };

    try {
        const res = await fetch('/api/commandes', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify(data)
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Erreur création');
        }
        
        const result = await res.json();
        showToast('✅ Commande créée avec succès !', 'success');
        closeModal();
        form.reset();
        loadOrders(1, currentStatus); // Recharger la liste
        
    } catch (e) {
        console.error(e);
        showToast(`❌ ${e.message}`, 'error');
    }
}

async function loadOrders(page = 1, status = '') {
    currentPage = page;
    currentStatus = status;
    
    const token = getToken();
    if (!token) {
        document.getElementById('orders-tbody').innerHTML = `
            <tr><td colspan="7" class="p-8 text-center text-error">
                <span class="material-symbols-outlined text-3xl">lock</span>
                <p class="mt-2">Non connecté. Veuillez vous connecter.</p>
                <button onclick="window.location.href='/login'" class="mt-2 px-4 py-2 bg-primary text-on-primary rounded">Se connecter</button>
            </td></tr>
        `;
        return;
    }
    
    try {
        const url = `/api/admin/orders?page=${page}&per_page=${perPage}${status ? '&status=' + status : ''}`;
        const res = await fetch(url, { headers: getHeaders() });
        
        if (!res.ok) {
            if (res.status === 403) {
                showToast('Accès refusé - Admin requis', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Session expirée. Reconnectez-vous.', 'error');
                window.location.href = '/login';
                return;
            }
            throw new Error('Erreur ' + res.status);
        }
        
        const data = await res.json();
        renderOrders(data.orders, data.total, data.pages);
        
    } catch (e) {
        console.error(e);
        document.getElementById('orders-tbody').innerHTML = `
            <tr><td colspan="7" class="p-8 text-center text-error">
                <span class="material-symbols-outlined text-3xl">error</span>
                <p class="mt-2">Erreur de chargement</p>
            </td></tr>
        `;
    }
}

function renderOrders(orders, total, totalPages) {
    const tbody = document.getElementById('orders-tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (orders.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="7" class="p-8 text-center text-on-surface-variant">
                <span class="material-symbols-outlined text-3xl">inbox</span>
                <p class="mt-2">Aucune commande trouvée</p>
            </td></tr>
        `;
        renderPagination(0, 0);
        return;
    }
    
    orders.forEach(order => {
        const statusConfig = getStatusConfig(order.status);
        const row = document.createElement('tr');
        row.className = 'hover:bg-surface-container transition-colors group cursor-pointer';
        row.onclick = () => toggleDetails(`order-${order.id}`);
        
        row.innerHTML = `
            <td class="p-4" onclick="event.stopPropagation()">
                <input type="checkbox" class="rounded border-outline-variant text-primary focus:ring-primary order-checkbox" data-id="${order.id}"/>
            </td>
            <td class="p-4">
                <p class="font-label-sm font-bold">#${order.reference}</p>
                <p class="text-[10px] text-on-surface-variant uppercase">Standard</p>
            </td>
            <td class="p-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-bold text-xs">
                        ${getInitials(order.user)}
                    </div>
                    <div>
                        <p class="font-label-sm font-medium">${order.user}</p>
                        <p class="text-[11px] text-on-surface-variant">${order.email || 'N/A'}</p>
                    </div>
                </div>
            </td>
            <td class="p-4">
                <p class="font-label-sm">${formatDate(order.date)}</p>
                <p class="text-[11px] text-on-surface-variant">${formatTime(order.date)}</p>
            </td>
            <td class="p-4">
                <span class="px-2 py-1 ${statusConfig.bg} ${statusConfig.text} text-[11px] font-bold rounded-full uppercase tracking-tighter">
                    ${statusConfig.label}
                </span>
            </td>
            <td class="p-4 text-right">
                <p class="font-price-display text-price-display">${formatPrice(order.total)}</p>
                <p class="text-[10px] text-green-600 uppercase">Paid</p>
            </td>
            <td class="p-4 text-center" onclick="event.stopPropagation()">
                <div class="relative group/action">
                    <button class="p-1 hover:bg-surface-container-highest rounded transition-all text-on-surface-variant" onclick="toggleActionMenu(${order.id})">
                        <span class="material-symbols-outlined text-[20px]">more_vert</span>
                    </button>
                    <div id="action-menu-${order.id}" class="hidden absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-outline-variant z-50">
                        <button onclick="updateStatus(${order.id}, 'paid')" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">💳 Marquer Payée</button>
                        <button onclick="updateStatus(${order.id}, 'processing')" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">📦 En préparation</button>
                        <button onclick="updateStatus(${order.id}, 'shipped')" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">🚚 Expédiée</button>
                        <button onclick="updateStatus(${order.id}, 'delivered')" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">✅ Livrée</button>
                        <button onclick="updateStatus(${order.id}, 'cancelled')" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-error">❌ Annuler</button>
                        <div class="border-t border-outline-variant my-1"></div>
                        <button onclick="viewInvoice(${order.id})" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">📄 Voir Facture</button>
                        <button onclick="viewTracking(${order.id})" class="w-full text-left px-4 py-2 text-sm hover:bg-surface-container text-on-surface">🚛 Suivi</button>
                    </div>
                </div>
            </td>
        `;
        
        tbody.appendChild(row);
        
        const detailRow = document.createElement('tr');
        detailRow.id = `order-${order.id}`;
        detailRow.className = 'hidden bg-surface-container-low/30';
        detailRow.innerHTML = `
            <td colspan="7" class="p-6">
                <div class="flex items-center justify-center py-4">
                    <span class="material-symbols-outlined animate-spin">refresh</span>
                    <span class="ml-2 text-on-surface-variant">Chargement...</span>
                </div>
            </td>
        `;
        tbody.appendChild(detailRow);
    });
    
    renderPagination(totalPages, total);
    updateStats(orders, total);
}

function getStatusConfig(status) {
    const configs = {
        'created':   { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Créée' },
        'paid':      { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Payée' },
        'processing':{ bg: 'bg-purple-100', text: 'text-purple-700', label: 'En préparation' },
        'shipped':   { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'Expédiée' },
        'delivered': { bg: 'bg-green-100', text: 'text-green-700', label: 'Livrée' },
        'cancelled': { bg: 'bg-red-100', text: 'text-red-700', label: 'Annulée' }
    };
    return configs[status] || configs['created'];
}

async function updateStatus(orderId, newStatus) {
    try {
        const res = await fetch(`/api/admin/orders/${orderId}/status`, {
            method: 'PUT',
            headers: getHeaders(),
            body: JSON.stringify({ status: newStatus })
        });
        
        if (!res.ok) throw new Error('Erreur');
        
        const data = await res.json();
        showToast(`✅ ${data.message}`, 'success');
        loadOrders(currentPage, currentStatus);
        
    } catch (e) {
        showToast('❌ Erreur mise à jour', 'error');
    }
}

function toggleActionMenu(orderId) {
    const menu = document.getElementById(`action-menu-${orderId}`);
    document.querySelectorAll('[id^="action-menu-"]').forEach(m => {
        if (m.id !== `action-menu-${orderId}`) m.classList.add('hidden');
    });
    menu.classList.toggle('hidden');
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.group\\/action')) {
        document.querySelectorAll('[id^="action-menu-"]').forEach(m => m.classList.add('hidden'));
    }
});

function viewInvoice(orderId) {
    window.open(`/api/invoices/${orderId}/download`, '_blank');
}

async function viewTracking(orderId) {
    try {
        const res = await fetch(`/api/orders/${orderId}/tracking`, { headers: getHeaders() });
        const data = await res.json();
        if (data) {
            alert(`📦 Suivi: ${data.tracking_number}\n🚚 Transporteur: ${data.carrier}\n📍 Localisation: ${data.last_location}`);
        }
    } catch (e) {
        showToast('Erreur chargement suivi', 'error');
    }
}

function getInitials(name) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function formatPrice(price) {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'MAD' }).format(price || 0);
}

function renderPagination(totalPages, total) {
    const container = document.getElementById('pagination');
    if (!container) return;
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = `
        <button onclick="loadOrders(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''} class="w-8 h-8 flex items-center justify-center rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-30">
            <span class="material-symbols-outlined text-[18px]">chevron_left</span>
        </button>
    `;
    
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
            html += `
                <button onclick="loadOrders(${i})" class="w-8 h-8 flex items-center justify-center rounded-lg ${i === currentPage ? 'bg-primary text-on-primary font-bold' : 'hover:bg-surface-container font-label-sm text-xs'}">
                    ${i}
                </button>
            `;
        } else if (i === currentPage - 2 || i === currentPage + 2) {
            html += `<span class="px-1 py-1 text-on-surface-variant">...</span>`;
        }
    }
    
    html += `
        <button onclick="loadOrders(${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''} class="w-8 h-8 flex items-center justify-center rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-30">
            <span class="material-symbols-outlined text-[18px]">chevron_right</span>
        </button>
    `;
    
    container.innerHTML = html;
    
    const showingText = document.getElementById('showing-text');
    if (showingText) {
        const start = total === 0 ? 0 : (currentPage - 1) * perPage + 1;
        const end = Math.min(start + perPage - 1, total);
        showingText.textContent = `Showing ${start} to ${end} of ${total} entries`;
    }
}

function updateStats(orders, total) {
    const totalEl = document.getElementById('stat-total');
    const pendingEl = document.getElementById('stat-pending');
    const shippedEl = document.getElementById('stat-shipped');
    const revenueEl = document.getElementById('stat-revenue');
    
    if (totalEl) totalEl.textContent = total;
    if (pendingEl) pendingEl.textContent = orders.filter(o => o.status === 'created').length;
    if (shippedEl) shippedEl.textContent = orders.filter(o => o.status === 'shipped').length;
    
    const revenue = orders.reduce((sum, o) => sum + (parseFloat(o.total) || 0), 0);
    if (revenueEl) revenueEl.textContent = formatPrice(revenue);
}

function setupFilters() {
    const container = document.getElementById('status-filters');
    if (!container) return;
    
    container.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        
        container.querySelectorAll('button').forEach(b => {
            b.className = 'px-4 py-1.5 font-label-sm text-label-sm text-on-surface-variant hover:text-on-surface transition-all';
        });
        btn.className = 'px-4 py-1.5 rounded-md bg-white shadow-sm font-label-sm text-label-sm transition-all';
        
        loadOrders(1, btn.dataset.status || '');
    });
}

function setupBulkActions() {
    const selectAll = document.getElementById('select-all');
    if (selectAll) {
        selectAll.addEventListener('change', (e) => {
            document.querySelectorAll('.order-checkbox').forEach(cb => cb.checked = e.target.checked);
        });
    }
}

async function executeBulkAction() {
    const select = document.getElementById('bulk-action');
    const action = select.value;
    if (!action || action === 'Choose Action...') {
        showToast('Sélectionnez une action', 'warning');
        return;
    }
    
    const checked = document.querySelectorAll('.order-checkbox:checked');
    if (checked.length === 0) {
        showToast('Sélectionnez au moins une commande', 'warning');
        return;
    }
    
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    
    for (const id of ids) {
        await updateStatus(id, action);
    }
    
    showToast(`${ids.length} commande(s) mise(s) à jour`, 'success');
    select.value = 'Choose Action...';
}

function toggleDetails(id) {
    const el = document.getElementById(id);
    if (!el) return;
    
    if (el.classList.contains('hidden')) {
        document.querySelectorAll('tr[id^="order-"]').forEach(row => row.classList.add('hidden'));
        el.classList.remove('hidden');
        loadOrderDetails(id.replace('order-', ''), el);
    } else {
        el.classList.add('hidden');
    }
}

async function loadOrderDetails(orderId, rowElement) {
    try {
        const res = await fetch(`/api/orders/${orderId}`, { headers: getHeaders() });
        const order = await res.json();
        
        let itemsHtml = '';
        try {
            const items = JSON.parse(order.items) || [];
            itemsHtml = items.map(item => `
                <div class="flex gap-4 mb-3">
                    <div class="w-16 h-16 rounded bg-surface-container border border-outline-variant overflow-hidden flex items-center justify-center">
                        <span class="material-symbols-outlined text-3xl text-on-surface-variant">image</span>
                    </div>
                    <div>
                        <p class="font-label-sm font-medium">${item.name || 'Article'}</p>
                        <p class="text-[12px] text-on-surface-variant">Qty: ${item.quantity || 1}</p>
                        <p class="font-price-display text-[16px] mt-1">${formatPrice(item.price)}</p>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            itemsHtml = '<p class="text-on-surface-variant">Aucun détail disponible</p>';
        }
        
        rowElement.querySelector('td').innerHTML = `
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div class="space-y-4">
                    <h4 class="font-label-sm font-bold border-b border-outline-variant pb-2">Produits</h4>
                    ${itemsHtml}
                </div>
                <div class="space-y-4">
                    <h4 class="font-label-sm font-bold border-b border-outline-variant pb-2">Informations</h4>
                    <p class="text-on-surface-variant text-[13px]">Client: ${order.user?.username || 'N/A'}</p>
                    <p class="text-on-surface-variant text-[13px]">Email: ${order.user?.email || 'N/A'}</p>
                    <p class="text-on-surface-variant text-[13px]">Statut: ${getStatusConfig(order.status).label}</p>
                </div>
                <div class="flex flex-col justify-end gap-2">
                    <button onclick="viewInvoice(${orderId})" class="w-full py-2 bg-primary text-on-primary rounded font-label-sm text-label-sm hover:opacity-90 transition-all">📄 Voir Facture</button>
                    <button onclick="updateStatus(${orderId}, 'shipped')" class="w-full py-2 border border-primary text-primary rounded font-label-sm text-label-sm hover:bg-primary/5 transition-all">🚚 Expédiée</button>
                    <button onclick="updateStatus(${orderId}, 'cancelled')" class="w-full py-2 text-error font-label-sm text-label-sm hover:underline">❌ Annuler</button>
                </div>
            </div>
        `;
    } catch (e) {
        rowElement.querySelector('td').innerHTML = `<div class="text-error p-4">❌ Erreur chargement détails</div>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadOrders();
    setupFilters();
    setupBulkActions();
});