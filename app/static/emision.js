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
    <td class="position-relative">
      <input type="text" class="form-control form-control-sm item-desc" placeholder="Descripción (o buscar…)"
             autocomplete="off"
             hx-get="/productos/buscar"
             hx-trigger="keyup changed delay:300ms"
             hx-target="next .producto-dropdown"
             name="q">
      <div class="producto-dropdown list-group shadow-sm position-absolute w-100" style="z-index:1000;top:100%"></div>
    </td>
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
  // Sincronizar monto en el panel de formas de pago si existe (factura.html)
  if (typeof syncMontoEntrega === 'function') syncMontoEntrega();
}

function getItems(withPrice = true) {
  return Array.from(document.querySelectorAll('.item-row')).map(row => {
    const item = {
      descripcion:   row.querySelector('.item-desc').value.trim(),
      cantidad:      parseFloat(row.querySelector('.item-qty').value) || 0,
      codigo:        row.querySelector('.item-codigo')?.value.trim() || null,
      unidad_medida: parseInt(row.querySelector('.item-desc')?.dataset.unidad) || 77,
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
    const aprobado  = data.estado === 'aprobado';
    const pendiente = data.estado === 'pendiente';
    const rechazado = data.estado === 'rechazado';

    const estadoBadge = aprobado  ? '<span class="badge bg-success">Aprobado</span>'
                      : pendiente ? '<span class="badge bg-warning text-dark">Pendiente</span>'
                      : rechazado ? '<span class="badge bg-danger">Rechazado</span>'
                      :             `<span class="badge bg-secondary">${data.estado}</span>`;

    const alertClass = aprobado ? 'success' : pendiente ? 'warning' : 'danger';
    const icon       = aprobado ? 'check' : pendiente ? 'clock' : 'x';
    const sifen      = (data.codigo_sifen != null)
                       ? `${data.codigo_sifen} — ${data.descripcion_sifen}`
                       : pendiente ? 'En cola — se enviará a SIFEN en breve' : '—';

    el.innerHTML = `
      <div class="alert alert-${alertClass} mt-3">
        <div class="d-flex justify-content-between align-items-start">
          <h6 class="mb-2"><i class="bi bi-${icon}-circle me-1"></i>Documento emitido</h6>
          ${aprobado ? `<a href="${data.kude_url}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="bi bi-file-earmark-pdf me-1"></i>KuDE</a>` : ''}
        </div>
        <div class="row g-1 small">
          <div class="col-12"><strong>CDC:</strong> <code class="small">${data.cdc}</code></div>
          <div class="col-md-3"><strong>N° Doc:</strong> ${data.numero_doc}</div>
          <div class="col-md-3"><strong>Estado:</strong> ${estadoBadge}</div>
          <div class="col-md-6"><strong>SIFEN:</strong> ${sifen}</div>
          ${data.protocolo_autorizacion ? `<div class="col-12"><strong>Protocolo:</strong> ${data.protocolo_autorizacion}</div>` : ''}
        </div>
        ${aprobado  ? `<div class="mt-2 small text-success">Redirigiendo al dashboard en <span id="countdown">4</span>s… <a href="/" class="text-success fw-semibold">ir ahora</a></div>` : ''}
        ${pendiente ? `<div class="mt-2 small">El documento quedó guardado. Usá <a href="/reenvio" class="fw-semibold">Reenvío por lote</a> para enviarlo a SIFEN.</div>` : ''}
      </div>`;
    // Si fue aprobado, redirigir al dashboard con countdown
    if (aprobado) {
      let seg = 4;
      const timer = setInterval(() => {
        seg--;
        const cd = document.getElementById('countdown');
        if (cd) cd.textContent = seg;
        if (seg <= 0) { clearInterval(timer); window.location.href = '/'; }
      }, 1000);
    }
  } else {
    el.innerHTML = `<div class="alert alert-danger mt-3"><i class="bi bi-exclamation-triangle me-1"></i>${data.detail || JSON.stringify(data)}</div>`;
  }
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Auto-guardar cliente y productos en maestros ──────────────────────────────
async function autoGuardarMaestros(payload) {
  try {
    // Guardar cliente
    if (payload.receptor?.ruc && payload.receptor?.razon_social) {
      const fd = new FormData();
      fd.append('ruc',          payload.receptor.ruc);
      fd.append('razon_social', payload.receptor.razon_social);
      fd.append('direccion',    payload.receptor.direccion  || '');
      fd.append('telefono',     payload.receptor.telefono   || '');
      fd.append('email',        payload.receptor.email      || '');
      fetch('/clientes/autoguardar', { method: 'POST', body: fd }).catch(() => {});
    }
    // Guardar productos en batch
    if (payload.items?.length) {
      fetch('/productos/autoguardar-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload.items.map(i => ({
          descripcion:     i.descripcion,
          precio_unitario: i.precio_unitario,
          iva:             i.iva,
          unidad_medida:   i.unidad_medida || 77,
          codigo:          i.codigo || '',
        }))),
      }).catch(() => {});
    }
  } catch (e) { /* silencioso — no bloquea el flujo */ }
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
    if (resp.ok) autoGuardarMaestros(payload);
  } catch (e) {
    document.getElementById('resultado').innerHTML =
      `<div class="alert alert-danger mt-3">Error de conexión: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-send me-1"></i>Emitir';
  }
}

// ── Receptor contribuyente / no contribuyente ─────────────────────────────────

function toggleContribuyente() {
  const esContrib = document.getElementById('es-contribuyente').checked;
  document.getElementById('panel-ruc').style.display      = esContrib ? '' : 'none';
  document.getElementById('panel-no-ruc').style.display   = esContrib ? 'none' : '';
  document.getElementById('col-doc-numero').style.display = esContrib ? 'none' : '';
  if (!esContrib) {
    document.getElementById('ruc').value = '';
    toggleInnominado();
  }
}

function toggleInnominado() {
  const tipo    = parseInt(document.getElementById('documento_tipo').value);
  const colNum  = document.getElementById('col-doc-numero');
  const razonEl = document.getElementById('razon_social');
  const req     = document.getElementById('razon-required');
  if (tipo === 5) {
    colNum.style.display   = 'none';
    document.getElementById('documento_numero').value = '0';
    razonEl.value    = 'Sin Nombre';
    razonEl.readOnly = true;
    if (req) req.style.display = 'none';
  } else {
    colNum.style.display = '';
    if (razonEl.value === 'Sin Nombre') razonEl.value = '';
    razonEl.readOnly = false;
    if (req) req.style.display = '';
  }
}

function getReceptorPayload() {
  const esContrib   = document.getElementById('es-contribuyente')?.checked ?? true;
  const razonSocial = (document.getElementById('razon_social')?.value  || '').trim();
  const direccion   = (document.getElementById('direccion')?.value     || '').trim() || null;
  const telefono    = (document.getElementById('telefono')?.value      || '').trim() || null;
  const email       = (document.getElementById('email')?.value         || '').trim() || null;
  if (esContrib) {
    return {
      contribuyente: true,
      ruc:          (document.getElementById('ruc')?.value || '').trim(),
      razon_social: razonSocial,
      direccion, telefono, email,
    };
  }
  const tipo = parseInt(document.getElementById('documento_tipo')?.value || '1');
  return {
    contribuyente:    false,
    documento_tipo:   tipo,
    documento_numero: tipo === 5 ? '0' : (document.getElementById('documento_numero')?.value || '').trim(),
    razon_social:     tipo === 5 ? 'Sin Nombre' : razonSocial,
    direccion, telefono, email,
  };
}

function validarReceptor() {
  const esContrib = document.getElementById('es-contribuyente')?.checked ?? true;
  if (esContrib) {
    if (!(document.getElementById('ruc')?.value || '').trim()) {
      alert('El RUC del receptor es obligatorio.');
      return false;
    }
    if (!(document.getElementById('razon_social')?.value || '').trim()) {
      alert('La razón social es obligatoria.');
      return false;
    }
  } else {
    const tipo = parseInt(document.getElementById('documento_tipo')?.value || '1');
    if (tipo !== 5 && !(document.getElementById('documento_numero')?.value || '').trim()) {
      alert('El número de documento es obligatorio.');
      return false;
    }
    if (tipo !== 5 && !(document.getElementById('razon_social')?.value || '').trim()) {
      alert('El nombre del cliente es obligatorio.');
      return false;
    }
  }
  return true;
}

function initReceptor() {
  document.addEventListener('click', function(e) {
    const item = e.target.closest('.cliente-resultado');
    if (item) {
      const esContrib = item.dataset.contribuyente !== 'false';
      const toggle = document.getElementById('es-contribuyente');
      if (toggle) { toggle.checked = esContrib; toggleContribuyente(); }

      if (esContrib) {
        const rucEl = document.getElementById('ruc');
        if (rucEl) rucEl.value = item.dataset.ruc || '';
      } else {
        const tipoEl = document.getElementById('documento_tipo');
        const numEl  = document.getElementById('documento_numero');
        if (tipoEl) tipoEl.value = item.dataset.documentoTipo || '1';
        if (numEl)  numEl.value  = item.dataset.documentoNumero || '';
        toggleInnominado();
      }
      const razon = document.getElementById('razon_social');
      if (razon && !razon.readOnly) razon.value = item.dataset.razon || '';
      const dir = document.getElementById('direccion');
      if (dir) dir.value = item.dataset.direccion || '';
      const tel = document.getElementById('telefono');
      if (tel) tel.value = item.dataset.telefono || '';
      const mail = document.getElementById('email');
      if (mail) mail.value = item.dataset.email || '';
      const buscar = document.getElementById('buscar-cliente');
      if (buscar) buscar.value = '';
      const res = document.getElementById('resultados-cliente');
      if (res) res.innerHTML = '';

      if (esContrib && typeof buscarFacturasPorRuc === 'function') {
        buscarFacturasPorRuc(item.dataset.ruc || '');
      }
      return;
    }
    if (!e.target.closest('#buscar-cliente') && !e.target.closest('#resultados-cliente')) {
      const r = document.getElementById('resultados-cliente');
      if (r) r.innerHTML = '';
    }
  });

  iniciarValidacionRuc();
}

// ── Validación de RUC en SIFEN ────────────────────────────────────────────────
function iniciarValidacionRuc() {
  const rucEl   = document.getElementById('ruc');
  const razonEl = document.getElementById('razon_social');
  if (!rucEl || !razonEl) return;

  const feedbackEl = document.createElement('div');
  feedbackEl.id = 'ruc-feedback';
  rucEl.parentNode.insertBefore(feedbackEl, rucEl.nextSibling);

  rucEl.addEventListener('blur', async function() {
    if (!document.getElementById('es-contribuyente')?.checked) return;
    const ruc = rucEl.value.trim();
    feedbackEl.innerHTML = '';
    if (!ruc || ruc.length < 3) return;

    feedbackEl.className = 'form-text mt-1 text-muted';
    feedbackEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1" style="width:.75rem;height:.75rem"></span>Validando RUC…';

    try {
      const apiKey = document.getElementById('api-key')?.value || '';
      const resp = await fetch(`/api/v1/consultas/ruc/${encodeURIComponent(ruc)}`, {
        headers: { 'X-API-Key': apiKey },
      });
      const data = await resp.json();

      if (data.encontrado) {
        feedbackEl.className = 'form-text mt-1 text-success';
        feedbackEl.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>RUC válido';
        if (data.ruc_completo) rucEl.value = data.ruc_completo;
        if (data.razon_social) razonEl.value = data.razon_social;
      } else {
        feedbackEl.className = 'form-text mt-1 text-danger';
        feedbackEl.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i>${data.mensaje || 'RUC no encontrado en SIFEN'}`;
      }
    } catch (_) {
      feedbackEl.innerHTML = '';
    }
  });

  // Limpiar feedback al empezar a editar de nuevo
  rucEl.addEventListener('focus', function() {
    feedbackEl.innerHTML = '';
  });
}

// ── Autocomplete de productos en filas de ítems ────────────────────────────────
document.addEventListener('click', function(e) {
  const item = e.target.closest('.producto-resultado');
  if (item) {
    const row = item.closest('tr.item-row');
    if (!row) return;
    row.querySelector('.item-codigo').value = item.dataset.codigo || '';
    const descEl = row.querySelector('.item-desc');
    descEl.value = item.dataset.descripcion;
    descEl.dataset.unidad = item.dataset.unidad || '77';
    const priceEl = row.querySelector('.item-price');
    if (priceEl) {
      priceEl.value = item.dataset.precio;
      const ivaEl = row.querySelector('.item-iva');
      if (ivaEl) ivaEl.value = item.dataset.iva;
      updateTotal();
    }
    row.querySelector('.producto-dropdown').innerHTML = '';
    return;
  }
  // Cerrar dropdowns de producto al hacer click fuera
  if (!e.target.closest('.item-desc') && !e.target.closest('.producto-dropdown')) {
    document.querySelectorAll('.producto-dropdown').forEach(d => d.innerHTML = '');
  }
});
