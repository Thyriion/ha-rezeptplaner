'use strict';

import { apiGet } from './api.js';
import { openAddToPlanModal } from './chat.js';
import { showToast } from './app.js';

const PAGE_SIZE = 20;
const state = { items: [], total: 0, loaded: false, busy: false, recipes: {} };
let debounce = null;

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const euro = v => `${v.toFixed(2).replace('.', ',')} €`;
const num = v => (v === Math.floor(v) ? Math.floor(v) : v);
const TYPE_LABEL = { fleisch: '🥩 Fleisch', fisch: '🐟 Fisch', vegetarisch: '🥦 Vegetarisch' };

export function openCatalogTab() {
  if (!state.loaded) catalogSearch(true);
}

export function catalogFilterChanged() {
  clearTimeout(debounce);
  debounce = setTimeout(() => catalogSearch(true), 300);
}

function filterParams(offset) {
  const val = id => document.getElementById(id)?.value || '';
  const params = new URLSearchParams({
    q: val('catalog-q').trim(),
    sort: val('catalog-sort') || 'neu',
    respect_settings: document.getElementById('catalog-respect')?.checked ? 'true' : 'false',
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  for (const [id, key] of [['catalog-time', 'max_time'], ['catalog-price', 'max_price'], ['catalog-kind', 'kind']]) {
    if (val(id)) params.set(key, val(id));
  }
  return params;
}

export async function catalogSearch(reset = true) {
  if (state.busy) return;
  state.busy = true;
  if (reset) { state.items = []; state.total = 0; }
  try {
    const page = await apiGet(`api/catalog/browse?${filterParams(state.items.length)}`);
    state.items = state.items.concat(page.items);
    state.total = page.total;
    state.loaded = true;
    renderCatalog();
  } catch {
    document.getElementById('catalog-results').innerHTML =
      `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Fehler beim Laden.</p></div>`;
  } finally { state.busy = false; }
}

export function catalogMore() { catalogSearch(false); }

function renderCatalog() {
  const box = document.getElementById('catalog-results');
  if (!state.items.length) {
    box.innerHTML = `<div class="empty-state"><div class="empty-icon">🔎</div><p>Keine Rezepte gefunden</p>
      <p class="hint">Lockere die Filter oder importiere den Katalog in den Einstellungen.</p></div>`;
    return;
  }
  const cards = state.items.map(item => {
    const meta = [`⏱ ${item.cooking_time_minutes} Min`,
      item.price_per_serving ? `≈ ${euro(item.price_per_serving)}` : null,
      item.calories ? `${item.calories} kcal` : null].filter(Boolean).join(' · ');
    const img = item.image_url ? `<img class="catalog-thumb" src="${esc(item.image_url)}" alt="" loading="lazy">` : '';
    return `<div class="plan-meal catalog-card" id="cat-${item.id}">
      <div class="plan-meal-header" onclick="toggleCatalogRecipe(${item.id})">
        ${img}
        <div class="catalog-title"><span class="meal-name">${esc(item.name)}</span>
          <span class="catalog-meta">${TYPE_LABEL[item.protein_type] || ''} · ${meta}</span></div>
        <div class="meal-actions">
          <button class="btn-swap" onclick="event.stopPropagation(); addCatalogRecipeToPlan(${item.id})">＋ In den Plan</button>
        </div>
        <span class="expand-icon">▾</span>
      </div>
      <div class="recipe-detail" id="cat-detail-${item.id}"><span class="spinner"></span></div>
    </div>`;
  }).join('');
  const more = state.items.length < state.total
    ? `<button class="btn btn-sm catalog-more" onclick="catalogMore()">Mehr laden (${state.items.length} von ${state.total})</button>`
    : `<p class="hint catalog-count">${state.total} Rezepte</p>`;
  box.innerHTML = cards + more;
}

async function loadRecipe(id) {
  if (!state.recipes[id]) state.recipes[id] = await apiGet(`api/catalog/recipe/${id}`);
  return state.recipes[id];
}

export async function toggleCatalogRecipe(id) {
  const card = document.getElementById(`cat-${id}`);
  if (!card) return;
  card.classList.toggle('open');
  if (!card.classList.contains('open') || card.dataset.loaded) return;
  try {
    const r = await loadRecipe(id);
    const n = r.nutrition_per_serving;
    const amt = i => (i.amount ? `${num(i.amount)} ${i.unit}`.trim() : i.unit);
    document.getElementById(`cat-detail-${id}`).innerHTML = `
      ${r.image_url ? `<img class="recipe-photo" src="${esc(r.image_url)}" alt="" loading="lazy">` : ''}
      <div class="nutrition-row">
        <div class="nut-item"><span class="nut-value">${n.calories}</span><span class="nut-label">kcal</span></div>
        ${r.price_per_serving ? `<div class="nut-item"><span class="nut-value">≈ ${euro(r.price_per_serving)}</span><span class="nut-label">pro Portion</span></div>` : ''}
        <div class="nut-item"><span class="nut-value">${n.protein_g}g</span><span class="nut-label">Protein</span></div>
        <div class="nut-item"><span class="nut-value">${n.carbs_g}g</span><span class="nut-label">Kohlenhydrate</span></div>
        <div class="nut-item"><span class="nut-value">${n.fat_g}g</span><span class="nut-label">Fett</span></div>
      </div>
      <p class="section-label">Zutaten (für ${r.servings} Pers.)</p>
      <ul class="ingredients-list">${r.ingredients.map(i => `<li><span>${esc(i.name)}</span><span class="ing-amount">${esc(amt(i))}</span></li>`).join('')}</ul>
      <p class="section-label">Zubereitung</p>
      <ol class="steps-list">${r.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      ${r.source_url ? `<p class="source-link"><a href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">Originalrezept ansehen ↗</a></p>` : ''}`;
    card.dataset.loaded = '1';
  } catch { showToast('Rezept konnte nicht geladen werden.', 'error'); card.classList.remove('open'); }
}

export async function addCatalogRecipeToPlan(id) {
  try { openAddToPlanModal(await loadRecipe(id)); }
  catch { showToast('Rezept konnte nicht geladen werden.', 'error'); }
}
