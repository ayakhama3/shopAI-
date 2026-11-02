/* admin_add_product.js — formulaire produit (création + édition) avec upload image */
(function () {
  'use strict';

  function getToken() {
    return window.ShopAIAuth?.getToken?.() ||
           sessionStorage.getItem('shopai_token') ||
           localStorage.getItem('shopai_token') || '';
  }

  function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    const text = document.getElementById('toast-text');
    text.textContent = message;
    toast.classList.toggle('error', isError);
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
  }

  const params = new URLSearchParams(window.location.search);
  const editId = params.get('edit');

  const dropzone = document.getElementById('dropzone');
  const placeholder = document.getElementById('dropzone-placeholder');
  const preview = document.getElementById('preview');
  const removeBtn = document.getElementById('remove-image');
  const fileInput = document.getElementById('file-input');
  const spinner = document.getElementById('upload-spinner');
  const submitBtn = document.getElementById('submit-btn');

  let uploadedImageUrl = '';
  let isUploading = false;

  function setPreview(url) {
    preview.src = url;
    preview.classList.remove('hidden');
    placeholder.classList.add('hidden');
    removeBtn.classList.remove('hidden');
    dropzone.classList.add('has-image');
  }

  function clearPreview() {
    preview.src = '';
    preview.classList.add('hidden');
    placeholder.classList.remove('hidden');
    removeBtn.classList.add('hidden');
    dropzone.classList.remove('has-image');
    uploadedImageUrl = '';
  }

  async function uploadImage(file) {
    if (!file || !file.type.startsWith('image/')) {
      showToast('Fichier non supporté : choisissez une image', true);
      return;
    }
    isUploading = true;
    spinner.classList.remove('hidden');
    submitBtn.disabled = true;

    try {
      const base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      setPreview(base64);

      const res = await fetch('/api/admin/upload-image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ image: base64, filename: file.name }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      uploadedImageUrl = data.url;
      setPreview(data.url);
      showToast('Image envoyée');
    } catch (e) {
      console.error(e);
      showToast('Erreur upload image : ' + e.message, true);
      clearPreview();
    } finally {
      isUploading = false;
      spinner.classList.add('hidden');
      submitBtn.disabled = false;
    }
  }

  dropzone.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) uploadImage(fileInput.files[0]);
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) uploadImage(file);
  });

  document.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) uploadImage(file);
        e.preventDefault();
        break;
      }
    }
  });

  removeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearPreview();
  });

  async function loadExistingProduct() {
    try {
      const all = await fetch(`/api/products?per_page=1000`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      }).then(r => r.json()).catch(() => ({ products: [] }));
      const product = (all.products || []).find(p => String(p.id) === String(editId));

      if (!product) {
        showToast('Produit introuvable', true);
        return;
      }

      document.getElementById('name').value = product.name || '';
      document.getElementById('price').value = product.price ?? '';
      document.getElementById('category').value = product.category || 'Tech';
      document.getElementById('stock').value = product.stock ?? '';
      document.getElementById('status').value = product.status || 'in_stock';
      if (product.image) {
        uploadedImageUrl = product.image;
        setPreview(product.image);
      }

      document.getElementById('page-title').textContent = 'Modifier le produit';
      submitBtn.textContent = 'Enregistrer les modifications';
    } catch (e) {
      console.error('Erreur chargement produit:', e);
      showToast('Erreur lors du chargement du produit', true);
    }
  }

  if (editId) loadExistingProduct();

  document.getElementById('productForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    if (isUploading) {
      showToast("Attendez la fin de l'envoi de l'image", true);
      return;
    }

    const name = document.getElementById('name').value.trim();
    const price = document.getElementById('price').value;

    if (!name || !price) {
      showToast('Nom et prix sont obligatoires', true);
      return;
    }

    const payload = {
      name,
      ref: document.getElementById('ref').value.trim(),
      price: parseFloat(price),
      stock: parseInt(document.getElementById('stock').value || '0', 10),
      category: document.getElementById('category').value,
      description: document.getElementById('description').value.trim(),
      status: document.getElementById('status').value,
      image: uploadedImageUrl || '',
    };

    submitBtn.disabled = true;
    submitBtn.textContent = editId ? 'Enregistrement...' : 'Création...';

    try {
      const url = editId ? `/api/products/${editId}` : '/api/products';
      const method = editId ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }

      showToast(editId ? 'Produit mis à jour' : 'Produit créé');
      setTimeout(() => { window.location.href = '/admin_catalogue'; }, 700);
    } catch (e) {
      console.error(e);
      showToast('Erreur : ' + e.message, true);
      submitBtn.disabled = false;
      submitBtn.textContent = editId ? 'Enregistrer les modifications' : 'Ajouter le produit';
    }
  });

  document.getElementById('cancel').addEventListener('click', () => {
    window.location.href = '/admin_catalogue';
  });
})();
