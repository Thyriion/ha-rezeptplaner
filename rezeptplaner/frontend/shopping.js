'use strict';

import { apiGet, apiPost } from './api.js';
import { CAT_ICONS, state } from './state.js';
import { showToast } from './app.js';
import { navigatePlan } from './plan.js';

export function updateShoppingNav() {
  const nav = document.getElementById('shopping-nav');
  if (!nav) return;
  if (state.allPlans.length === 0) { nav.classList.add('hidden'); return; }
  nav.classList.remove('hidden');
  const meta = state.allPlans[state.currentPlanIdx];
  const d = new Date(meta.week_start + 'T00:00:00');
  const end = new Date(d); end.setDate(d.getDate() + 6);
  const fmt = dt => dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
  document.getElementById('shopping-nav-label').textContent = `${fmt(d)} – ${fmt(end)}`;
  document.getElementById('shopping-nav-prev').disabled = state.currentPlanIdx >= state.allPlans.length - 1;
  document.getElementById('shopping-nav-next').disabled = state.currentPlanIdx <= 0;
}

export async function navigateShopping(dir) {
  await navigatePlan(dir);
  await loadShopping();
}

export async function loadShopping() {
  updateShoppingNav();
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
