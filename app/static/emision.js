// JS compartido para formularios de emisión

function fmtGs(n) {
  return '₲ ' + Math.round(n).toLocaleString('es-PY');
}

// ── Items dinámicos ────────────────────────────────────────────────────────────
function addItem(showPrice = true) {
  const tbody = document.getElementById('items-body');
  const tr = document.createElement('tr');
  tr.className = 'item-row';
  tr.innerHTML = `
    <td><input type="text" class="form-control form-control-sm item-codigo" placeholder="001"></td>
    <td><input type="text" class="form-control form-control-sm item-desc" placeholder="Descripción" required></td>
    <td><input type="number" class="form-control form-control-sm item-qty" value="1" min="0.01" step="0.01" required></td>
    ${showPrice ? `
    <td><input type="number" class="form-control form-control-sm item-price" min="1" placeholder="0" required></td>
    <td>
      <select class="form-select form-select-sm item-iva">
        <option value="10">10%</option>
        <option value="5">5%</option>
        <option value="0">Exento</option>
      </select>
    </td>
    <td class="text-end fw-semibold item-total text-muted">—</td>` : ''}
    <td>
      <button type="button" class="btn btn-outline-danger btn-sm" onclick="removeItem(this)">
        <i class="bi bi-trash"></i>
      </button>
    </td>`;
  tbody.appendChild(tr);
  if (showPrice) {
    tr.querySelector('.item-qty').addEventListener('input', updateTotal);
    tr.querySelector('.item-price').addEventListener('input', updateTotal);
  }
}

function removeItem(btn) {
  const rows = document.querySelectorAll('.item-row');
  if (rows.length > 1) { btn.closest('tr').remove(); updateTotal(); }
}

function updateTotal() {
  let total = 0;
  document.querySelectorAll('.item-row').forEach(row => {
    const qty   = parseFloat(row.querySelector('.item-qty')?.value)   || 0;
    const price = parseInt(row.querySelector('.item-price')?.value)   || 0;
    const sub   = qty * price;
    total += sub;
    const el = row.querySelector('.item-total');
    if (el) el.textContent = sub > 0 ? fmtGs(sub) : '—';
  });
  const t = document.getElementById('total-general');
  if (t) t.textContent = fmtGs(total);
}

function getItems(withPrice = true) {
  return Array.from(document.querySelectorAll('.item-row')).map(row => {
    const item = {
      descripcion:   row.querySelector('.item-desc').value.trim(),
      cantidad:      parseFloat(row.querySelector('.item-qty').value) || 0,
      codigo:        row.querySelector('.item-codigo')?.value.trim() || null,
      unidad_medida: 77,
    };
    if (withPrice) {
      item.precio_unitario = parseInt(row.querySelector('.item-price').value) || 0;
      item.iva = parseInt(row.querySelector('.item-iva').value);
    }
    return item;
  }).filter(i => i.descripcion && i.cantidad > 0);
}

// ── Resultado ─────────────────────────────────────────────────────────────────
function mostrarResultado(data, ok) {
  const el = document.getElementById('resultado');
  if (ok) {
    const estado = data.estado === 'aprobado'
      ? '<span class="badge bg-success">Aprobado</span>'
      : '<span class="badge bg-danger">Rechazado</span>';
    el.innerHTML = `
      <div class="alert alert-${data.estado === 'aprobado' ? 'success' : 'danger'} mt-3">
        <div class="d-flex justify-content-between align-items-start">
          <h6 class="mb-2"><i class="bi bi-check-circle me-1"></i>Documento emitido</h6>
          ${data.estado === 'aprobado' ? `<a href="${data.kude_url}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="bi bi-file-earmark-pdf me-1"></i>Descargar KuDE</a>` : ''}
        </div>
        <div class="row g-1 small">
          <div class="col-12"><strong>CDC:</strong> <code class="small">${data.cdc}</code></div>
          <div class="col-md-3"><strong>N° Doc:</strong> ${data.numero_doc}</div>
          <div class="col-md-3"><strong>Estado:</strong> ${estado}</div>
          <div class="col-md-6"><strong>SIFEN:</strong> ${data.codigo_sifen} — ${data.descripcion_sifen}</div>
          ${data.protocolo_autorizacion ? `<div class="col-12"><strong>Protocolo:</strong> ${data.protocolo_autorizacion}</div>` : ''}
        </div>
      </div>`;
  } else {
    el.innerHTML = `<div class="alert alert-danger mt-3"><i class="bi bi-exclamation-triangle me-1"></i>${data.detail || JSON.stringify(data)}</div>`;
  }
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Envío al API ───────────────────────────────────────────────────────────────
async function enviarAPI(endpoint, payload) {
  const btn = document.getElementById('btn-emitir');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Emitiendo...';
  document.getElementById('resultado').innerHTML = '';

  try {
    const apiKey = document.getElementById('api-key')?.value || '';
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    mostrarResultado(data, resp.ok);
  } catch (e) {
    document.getElementById('resultado').innerHTML =
      `<div class="alert alert-danger mt-3">Error de conexión: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-send me-1"></i>Emitir';
  }
}
