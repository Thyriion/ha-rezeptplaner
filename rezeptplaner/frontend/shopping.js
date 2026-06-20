'use strict';

import { apiGet, apiPost } from './api.js';
import { CAT_ICONS, state } from './state.js';
import { showToast } from './app.js';

export async function loadShopping() {
  const container = document.getElementById('shopping-content');
  const planId = state.plan?.id;
  try {
    const url = planId ? `api/shopping-list?plan_id=${planId}` : 'api/shopping-list';
    renderShopping(await apiGet(url), container);
  } catch {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Fehler beim Laden.</p></div>`;
  }
}

export function renderShopping(list, container) {
  const cats = list.items_by_category || {};
  if (!Object.keys(cats).length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">🛒</div><p>Noch keine Einkaufsliste</p><p class="hint">Bestätige zuerst deinen Wochenplan.</p></div>`;
    return;
  }
  let html = `<div class="shopping-actions">
    <button class="btn btn-primary btn-sm" onclick="pushToHA()">→ Zur HA Einkaufsliste</button>
  </div>`;
  for (const [cat, items] of Object.entries(cats)) {
    const icon = CAT_ICONS[cat] || '🛒';
    html += `<div class="shopping-category"><div class="shopping-cat-header">${icon} ${cat}</div>`;
    for (const item of items) {
      const n = item.amount === Math.floor(item.amount) ? Math.floor(item.amount) : item.amount;
      html += `<label class="shopping-item">
        <input type="checkbox" onchange="toggleCheck(this.closest('.shopping-item'))">
        <span class="item-name">${item.name}</span>
        <span class="item-amount">${n} ${item.unit}</span>
      </label>`;
    }
    html += `</div>`;
  }
  container.innerHTML = html;
}

export function toggleCheck(el) {
  el.classList.toggle('checked');
  const cb = el.querySelector('input[type="checkbox"]');
  if (cb) cb.checked = el.classList.contains('checked');
}

export async function pushToHA() {
  const planId = state.plan?.id;
  try {
    const url = planId ? `api/shopping-list/push-to-ha?plan_id=${planId}` : 'api/shopping-list/push-to-ha';
    const res = await apiPost(url, {});
    res.ok
      ? showToast(`${res.pushed} Artikel zur HA Einkaufsliste hinzugefügt!`, 'success')
      : showToast(res.error || 'Fehler beim Pushen.', 'error');
  } catch { showToast('Verbindung zu Home Assistant fehlgeschlagen.', 'error'); }
}
