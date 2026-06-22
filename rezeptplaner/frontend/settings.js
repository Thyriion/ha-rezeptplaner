'use strict';

import { apiPost } from './api.js';
import { state } from './state.js';
import { showToast } from './app.js';

// ── Wizard ────────────────────────────────────────────────────────

export function showWizard() {
  updateWizardStep(1);
  document.getElementById('wizard').classList.remove('hidden');
}

export function updateWizardStep(step) {
  state.wizardStep = step;
  document.querySelectorAll('.wizard-step').forEach(el =>
    el.classList.toggle('hidden', parseInt(el.dataset.step) !== step)
  );
  document.getElementById('wizard-step-label').textContent = `Schritt ${step} von 7`;
  document.getElementById('wizard-bar').style.width = `${(step / 7) * 100}%`;
  document.getElementById('wizard-back').style.visibility = step > 1 ? 'visible' : 'hidden';
  document.getElementById('wizard-next').textContent = step === 7 ? 'Fertig' : 'Weiter';
}

export function wizardBack() {
  if (state.wizardStep > 1) updateWizardStep(state.wizardStep - 1);
}

export async function wizardNext() {
  collectWizardStep(state.wizardStep);
  if (state.wizardStep < 7) { updateWizardStep(state.wizardStep + 1); return; }
  const btn = document.getElementById('wizard-next');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Speichern…';
  try {
    await apiPost('api/settings', state.wizardData);
    state.settings = state.wizardData;
    document.getElementById('wizard').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    const { appendMsg } = await import('./chat.js');
    appendMsg('assistant', 'Alles klar! Ich kenne jetzt eure Vorlieben.\n\nKlicke "Wochenplan generieren" oder schreib mir einfach was du dir vorstellst! 🍽');
  } catch { showToast('Fehler beim Speichern.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Fertig'; }
}

export function collectWizardStep(step) {
  if (step === 1) state.wizardData.persons = parseInt(document.getElementById('persons-display').textContent);
  else if (step === 2) state.wizardData.diet_types = [...document.querySelectorAll('#diet-chips .chip.active')].map(c => c.dataset.value);
  else if (step === 5) state.wizardData.max_cooking_time = parseInt(document.querySelector('#time-options .option-btn.active')?.dataset.value || 30);
  else if (step === 6) state.wizardData.budget = document.querySelector('#budget-options .option-btn.active')?.dataset.value || 'mittel';
  else if (step === 7) state.wizardData.likes_spicy = document.querySelector('#spicy-options .option-btn.active')?.dataset.value === 'true';
}

export function adjustPersons(d) {
  const el = document.getElementById('persons-display');
  el.textContent = Math.max(1, Math.min(10, parseInt(el.textContent) + d));
  state.wizardData.persons = parseInt(el.textContent);
}

// ── Settings Modal ────────────────────────────────────────────────

export function openSettings() {
  const s = state.settings || {};
  document.getElementById('settings-persons-display').textContent = s.persons || 2;
  document.querySelectorAll('#settings-diet-chips .chip').forEach(c =>
    c.classList.toggle('active', (s.diet_types || []).includes(c.dataset.value))
  );
  renderTagList('settings-disliked', s.disliked_foods || []);
  renderTagList('settings-favorite', s.favorite_foods || []);
  document.querySelectorAll('#settings-time-options .option-btn').forEach(b =>
    b.classList.toggle('active', parseInt(b.dataset.value) === (s.max_cooking_time || 30))
  );
  document.querySelectorAll('#settings-budget-options .option-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.value === (s.budget || 'mittel'))
  );
  document.querySelectorAll('#settings-spicy-options .option-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.value === String(s.likes_spicy ?? false))
  );
  document.getElementById('settings-modal').classList.remove('hidden');
}

export function closeSettings() { document.getElementById('settings-modal').classList.add('hidden'); }

export function adjustSettingsPersons(d) {
  const el = document.getElementById('settings-persons-display');
  el.textContent = Math.max(1, Math.min(10, parseInt(el.textContent) + d));
}

export async function saveSettings() {
  const saved = await apiPost('api/settings', {
    persons: parseInt(document.getElementById('settings-persons-display').textContent),
    diet_types: [...document.querySelectorAll('#settings-diet-chips .chip.active')].map(c => c.dataset.value),
    disliked_foods: getTagValues('settings-disliked'),
    favorite_foods: getTagValues('settings-favorite'),
    max_cooking_time: parseInt(document.querySelector('#settings-time-options .option-btn.active')?.dataset.value || 30),
    budget: document.querySelector('#settings-budget-options .option-btn.active')?.dataset.value || 'mittel',
    likes_spicy: document.querySelector('#settings-spicy-options .option-btn.active')?.dataset.value === 'true',
  }).catch(() => null);
  if (saved) { state.settings = saved; closeSettings(); showToast('Einstellungen gespeichert!', 'success'); }
  else showToast('Fehler beim Speichern.', 'error');
}

// ── Tags (case-insensitive) ───────────────────────────────────────

const tagValues = {};

export function addTag(prefix) {
  const input = document.getElementById(`${prefix}-input`);
  const raw = input.value.trim();
  if (!raw) return;
  if (!tagValues[prefix]) tagValues[prefix] = [];
  if (!tagValues[prefix].some(v => v.toLowerCase() === raw.toLowerCase())) {
    tagValues[prefix].push(raw);
    if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
    if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
    renderTagList(prefix, tagValues[prefix]);
  }
  input.value = '';
}

export function removeTag(prefix, val) {
  tagValues[prefix] = (tagValues[prefix] || []).filter(v => v !== val);
  if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
  if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
  renderTagList(prefix, tagValues[prefix]);
}

export function renderTagList(prefix, values) {
  tagValues[prefix] = [...values];
  const el = document.getElementById(`${prefix}-tags`);
  if (!el) return;
  el.innerHTML = values.map(v =>
    `<span class="tag">${v}<button onclick="removeTag('${prefix}','${v.replace(/'/g, "\\'")}')">×</button></span>`
  ).join('');
}

export function getTagValues(prefix) { return tagValues[prefix] || []; }

export function tagKeydown(e, prefix) {
  if (e.key === 'Enter') { e.preventDefault(); addTag(prefix); }
}
