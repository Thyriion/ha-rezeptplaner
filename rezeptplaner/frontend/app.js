'use strict';

// ── State ────────────────────────────────────────────────────────

const state = {
  settings: null,
  plan: null,
  wizardStep: 1,
  wizardData: {
    persons: 2,
    diet_types: [],
    disliked_foods: [],
    favorite_foods: [],
    max_cooking_time: 30,
    budget: 'mittel',
  },
  swapMealId: null,
  swapMealName: null,
  swapReason: null,
  settingsData: {},
};

const DAY_LABELS = {
  monday: 'Montag', tuesday: 'Dienstag', wednesday: 'Mittwoch',
  thursday: 'Donnerstag', friday: 'Freitag', saturday: 'Samstag', sunday: 'Sonntag',
};
const MEAL_LABELS = { lunch: 'Mittagessen', dinner: 'Abendessen' };
const DAY_ORDER = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const CAT_ICONS = {
  'Gemüse & Obst': '🥦',
  'Fleisch & Fisch': '🥩',
  'Milchprodukte & Eier': '🥛',
  'Getreide & Backwaren': '🌾',
  'Konserven & Trockenwaren': '🥫',
  'Gewürze & Öle': '🫙',
  'Sonstiges': '🛒',
};

// ── API ──────────────────────────────────────────────────────────

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Init ─────────────────────────────────────────────────────────

async function init() {
  try {
    const s = await apiGet('api/settings');
    if (!s || s.persons === undefined) {
      showWizard();
    } else {
      state.settings = s;
      showApp();
      await loadPlan();
    }
  } catch (e) {
    showApp();
    appendMsg('assistant', 'Fehler beim Laden der Einstellungen. Bitte prüfe ob das Backend läuft.');
  }
}

function showApp() {
  document.getElementById('app').classList.remove('hidden');
}

// ── Tabs ─────────────────────────────────────────────────────────

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === `tab-${tab}`));
  if (tab === 'shopping') loadShopping();
}

// ── Chat ─────────────────────────────────────────────────────────

function chatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  appendMsg('user', msg);

  const typingEl = appendMsg('assistant', '…', true);
  const sendBtn = document.getElementById('btn-send');
  sendBtn.disabled = true;
  input.disabled = true;

  try {
    const res = await apiPost('api/chat', { message: msg });
    typingEl.remove();
    appendMsg('assistant', res.reply, false, res.plan);
    if (res.plan) {
      state.plan = res.plan;
      renderPlan();
    }
  } catch (e) {
    typingEl.remove();
    appendMsg('assistant', 'Fehler beim Senden. Bitte prüfe die KI-Provider-Konfiguration.');
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

function appendMsg(role, text, isTyping = false, plan = null) {
  const wrap = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = `msg ${role}${isTyping ? ' typing' : ''}`;
  el.textContent = text;

  if (plan) {
    const btn = document.createElement('button');
    btn.className = 'msg-plan-link';
    btn.textContent = '→ Zum Wochenplan';
    btn.onclick = () => switchTab('plan');
    el.appendChild(document.createElement('br'));
    el.appendChild(btn);
  }

  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
  return el;
}

// ── Plan ─────────────────────────────────────────────────────────

async function loadPlan() {
  try {
    const plan = await apiGet('api/plan');
    if (plan) {
      state.plan = plan;
      renderPlan();
    }
  } catch (_) {}
}

function renderPlan() {
  const plan = state.plan;
  const container = document.getElementById('plan-content');
  if (!plan || !plan.meals || plan.meals.length === 0) {
    container.innerHTML = `<div class="empty-state"><p>Noch kein Wochenplan.</p><p class="hint">Geh in den Chat und frag nach Rezepten!</p></div>`;
    return;
  }

  const isConfirmed = plan.meals.every(m => m.confirmed);

  // Group meals by day
  const byDay = {};
  for (const meal of plan.meals) {
    if (!byDay[meal.day]) byDay[meal.day] = [];
    byDay[meal.day].push(meal);
  }

  let html = '';
  for (const day of DAY_ORDER) {
    const meals = byDay[day];
    if (!meals) continue;
    html += `<div class="plan-day">
      <div class="plan-day-header">${DAY_LABELS[day]}</div>`;
    for (const meal of meals) {
      html += renderMealCard(meal, isConfirmed);
    }
    html += `</div>`;
  }

  html += `<div class="plan-actions">`;
  if (isConfirmed) {
    html += `<span class="confirmed-badge">✓ Woche bestätigt</span>`;
  } else {
    html += `<button class="btn btn-success" onclick="confirmPlan()">✓ Woche bestätigen</button>`;
  }
  html += `</div>`;

  container.innerHTML = html;
}

function renderMealCard(meal, isConfirmed) {
  const r = meal.recipe;
  const n = r.nutrition_per_serving;
  const swapDisabled = isConfirmed || meal.confirmed ? 'disabled' : '';

  const ingHtml = r.ingredients.map(i => {
    const amt = i.amount === Math.floor(i.amount) ? Math.floor(i.amount) : i.amount;
    return `<li><span class="item-name">${i.name}</span><span class="ing-amount">${amt} ${i.unit}</span></li>`;
  }).join('');

  const stepsHtml = r.steps.map(s => `<li>${s}</li>`).join('');

  return `
  <div class="plan-meal" id="meal-${meal.id}">
    <div class="plan-meal-header" onclick="toggleMeal(${meal.id})">
      <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type]}</span>
      <span class="meal-name">${r.name}</span>
      <span class="meal-time">⏱ ${r.cooking_time_minutes} Min</span>
      <button class="btn-swap" ${swapDisabled} onclick="event.stopPropagation(); openSwapModal(${meal.id}, '${r.name.replace(/'/g,"\\'")}')">↔ Tauschen</button>
      <span class="expand-icon">▾</span>
    </div>
    <div class="recipe-detail">
      <div class="nutrition-row">
        <div class="nut-item"><span class="nut-value">${n.calories}</span><span class="nut-label">kcal</span></div>
        <div class="nut-item"><span class="nut-value">${n.protein_g}g</span><span class="nut-label">Protein</span></div>
        <div class="nut-item"><span class="nut-value">${n.carbs_g}g</span><span class="nut-label">Kohlenhydrate</span></div>
        <div class="nut-item"><span class="nut-value">${n.fat_g}g</span><span class="nut-label">Fett</span></div>
      </div>
      <p class="section-label">Zutaten</p>
      <ul class="ingredients-list">${ingHtml}</ul>
      <p class="section-label">Zubereitung</p>
      <ol class="steps-list">${stepsHtml}</ol>
    </div>
  </div>`;
}

function toggleMeal(mealId) {
  document.getElementById(`meal-${mealId}`)?.classList.toggle('open');
}

async function confirmPlan() {
  try {
    await apiPost('api/plan/confirm', {});
    if (state.plan) state.plan.meals.forEach(m => m.confirmed = true);
    renderPlan();
    showToast('Wochenplan bestätigt! Einkaufsliste ist bereit.', 'success');
    switchTab('shopping');
  } catch (e) {
    showToast('Fehler beim Bestätigen.', 'error');
  }
}

// ── Swap ─────────────────────────────────────────────────────────

function openSwapModal(mealId, mealName) {
  state.swapMealId = mealId;
  state.swapMealName = mealName;
  state.swapReason = null;
  document.getElementById('swap-meal-name').textContent = mealName;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('swap-confirm-btn').disabled = true;
  document.getElementById('swap-modal').classList.remove('hidden');
}

function closeSwapModal() {
  document.getElementById('swap-modal').classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#swap-reasons .option-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.swapReason = btn.dataset.value;
      document.getElementById('swap-confirm-btn').disabled = false;
    });
  });
});

async function confirmSwap() {
  if (!state.swapMealId || !state.swapReason) return;
  const btn = document.getElementById('swap-confirm-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Wird getauscht…';

  try {
    const updatedMeal = await apiPost('api/plan/swap', { meal_id: state.swapMealId, reason: state.swapReason });
    if (state.plan) {
      const idx = state.plan.meals.findIndex(m => m.id === state.swapMealId);
      if (idx !== -1) state.plan.meals[idx] = updatedMeal;
    }
    closeSwapModal();
    renderPlan();
    showToast('Rezept wurde ausgetauscht!', 'success');
  } catch (e) {
    showToast('Fehler beim Tauschen.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Tauschen';
  }
}

// ── Shopping ─────────────────────────────────────────────────────

async function loadShopping() {
  const container = document.getElementById('shopping-content');
  try {
    const list = await apiGet('api/shopping-list');
    renderShopping(list, container);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><p>Fehler beim Laden.</p></div>`;
  }
}

function renderShopping(list, container) {
  const cats = list.items_by_category || {};
  if (Object.keys(cats).length === 0) {
    container.innerHTML = `<div class="empty-state"><p>Noch keine Einkaufsliste.</p><p class="hint">Bestätige zuerst deinen Wochenplan.</p></div>`;
    return;
  }

  let html = `<div class="shopping-actions">
    <button class="btn btn-primary btn-sm" onclick="pushToHA()">→ Zur HA Einkaufsliste</button>
  </div>`;

  for (const [cat, items] of Object.entries(cats)) {
    const icon = CAT_ICONS[cat] || '🛒';
    html += `<div class="shopping-category">
      <div class="shopping-cat-header">${icon} ${cat}</div>`;
    for (const item of items) {
      const amt = item.amount === Math.floor(item.amount) ? Math.floor(item.amount) : item.amount;
      html += `<label class="shopping-item" onclick="toggleCheck(this)">
        <input type="checkbox" onclick="event.stopPropagation(); toggleCheck(this.closest('.shopping-item'))">
        <span class="item-name">${item.name}</span>
        <span class="item-amount">${amt} ${item.unit}</span>
      </label>`;
    }
    html += `</div>`;
  }

  container.innerHTML = html;
}

function toggleCheck(el) {
  el.classList.toggle('checked');
  const cb = el.querySelector('input[type="checkbox"]');
  if (cb) cb.checked = el.classList.contains('checked');
}

async function pushToHA() {
  try {
    const res = await apiPost('api/shopping-list/push-to-ha', {});
    if (res.ok) {
      showToast(`${res.pushed} Artikel zur HA Einkaufsliste hinzugefügt!`, 'success');
    } else {
      showToast(res.error || 'Fehler beim Pushen zur HA Einkaufsliste.', 'error');
    }
  } catch (e) {
    showToast('Verbindung zu Home Assistant fehlgeschlagen.', 'error');
  }
}

// ── Wizard ───────────────────────────────────────────────────────

function showWizard() {
  updateWizardStep(1);
  document.getElementById('wizard').classList.remove('hidden');
}

function updateWizardStep(step) {
  state.wizardStep = step;
  document.querySelectorAll('.wizard-step').forEach(el => {
    el.classList.toggle('hidden', parseInt(el.dataset.step) !== step);
  });
  document.getElementById('wizard-step-label').textContent = `Schritt ${step} von 6`;
  document.getElementById('wizard-bar').style.width = `${(step / 6) * 100}%`;
  document.getElementById('wizard-back').style.visibility = step > 1 ? 'visible' : 'hidden';
  document.getElementById('wizard-next').textContent = step === 6 ? 'Fertig' : 'Weiter';
}

function wizardBack() { if (state.wizardStep > 1) updateWizardStep(state.wizardStep - 1); }

async function wizardNext() {
  collectWizardStep(state.wizardStep);
  if (state.wizardStep < 6) {
    updateWizardStep(state.wizardStep + 1);
  } else {
    await finishWizard();
  }
}

function collectWizardStep(step) {
  if (step === 1) {
    state.wizardData.persons = parseInt(document.getElementById('persons-display').textContent);
  } else if (step === 2) {
    state.wizardData.diet_types = [...document.querySelectorAll('#diet-chips .chip.active')].map(c => c.dataset.value);
  } else if (step === 3) {
    // tags collected live
  } else if (step === 4) {
    // tags collected live
  } else if (step === 5) {
    const active = document.querySelector('#time-options .option-btn.active');
    state.wizardData.max_cooking_time = active ? parseInt(active.dataset.value) : 30;
  } else if (step === 6) {
    const active = document.querySelector('#budget-options .option-btn.active');
    state.wizardData.budget = active ? active.dataset.value : 'mittel';
  }
}

async function finishWizard() {
  const btn = document.getElementById('wizard-next');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Speichern…';

  try {
    await apiPost('api/settings', state.wizardData);
    state.settings = state.wizardData;
    document.getElementById('wizard').classList.add('hidden');
    showApp();
    appendMsg('assistant', `Alles klar! Ich kenne jetzt eure Vorlieben und bin bereit.\n\nSchreib einfach "Gib mir Rezepte für diese Woche" um loszulegen! 🍽`);
  } catch (e) {
    showToast('Fehler beim Speichern der Einstellungen.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Fertig';
  }
}

function adjustPersons(delta) {
  const el = document.getElementById('persons-display');
  const val = Math.max(1, Math.min(10, parseInt(el.textContent) + delta));
  el.textContent = val;
  state.wizardData.persons = val;
}

// ── Settings ─────────────────────────────────────────────────────

function openSettings() {
  const s = state.settings || {};
  state.settingsData = JSON.parse(JSON.stringify(s));

  // Persons
  document.getElementById('settings-persons-display').textContent = s.persons || 2;

  // Diet chips
  document.querySelectorAll('#settings-diet-chips .chip').forEach(c => {
    c.classList.toggle('active', (s.diet_types || []).includes(c.dataset.value));
  });

  // Tags
  renderTagList('settings-disliked', s.disliked_foods || []);
  renderTagList('settings-favorite', s.favorite_foods || []);

  // Time
  document.querySelectorAll('#settings-time-options .option-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.value) === (s.max_cooking_time || 30));
  });

  // Budget
  document.querySelectorAll('#settings-budget-options .option-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.value === (s.budget || 'mittel'));
  });

  document.getElementById('settings-modal').classList.remove('hidden');
}

function closeSettings() {
  document.getElementById('settings-modal').classList.add('hidden');
}

async function saveSettings() {
  const persons = parseInt(document.getElementById('settings-persons-display').textContent);
  const diet_types = [...document.querySelectorAll('#settings-diet-chips .chip.active')].map(c => c.dataset.value);
  const disliked_foods = getTagValues('settings-disliked');
  const favorite_foods = getTagValues('settings-favorite');
  const max_cooking_time = parseInt(document.querySelector('#settings-time-options .option-btn.active')?.dataset.value || 30);
  const budget = document.querySelector('#settings-budget-options .option-btn.active')?.dataset.value || 'mittel';

  try {
    const saved = await apiPost('api/settings', { persons, diet_types, disliked_foods, favorite_foods, max_cooking_time, budget });
    state.settings = saved;
    closeSettings();
    showToast('Einstellungen gespeichert!', 'success');
  } catch (e) {
    showToast('Fehler beim Speichern.', 'error');
  }
}

function adjustSettingsPersons(delta) {
  const el = document.getElementById('settings-persons-display');
  el.textContent = Math.max(1, Math.min(10, parseInt(el.textContent) + delta));
}

// ── Tags ─────────────────────────────────────────────────────────

const tagValues = {};

function addTag(prefix) {
  const input = document.getElementById(`${prefix}-input`);
  const val = input.value.trim();
  if (!val) return;
  if (!tagValues[prefix]) tagValues[prefix] = [];
  if (!tagValues[prefix].includes(val)) {
    tagValues[prefix].push(val);
    // sync wizard state
    if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
    if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
    renderTagList(prefix, tagValues[prefix]);
  }
  input.value = '';
}

function removeTag(prefix, val) {
  if (!tagValues[prefix]) return;
  tagValues[prefix] = tagValues[prefix].filter(v => v !== val);
  if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
  if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
  renderTagList(prefix, tagValues[prefix]);
}

function renderTagList(prefix, values) {
  tagValues[prefix] = [...values];
  const container = document.getElementById(`${prefix}-tags`);
  if (!container) return;
  container.innerHTML = values.map(v =>
    `<span class="tag">${v}<button onclick="removeTag('${prefix}','${v.replace(/'/g,"\\'")}')">×</button></span>`
  ).join('');
}

function getTagValues(prefix) {
  return tagValues[prefix] || [];
}

function tagKeydown(e, prefix) {
  if (e.key === 'Enter') { e.preventDefault(); addTag(prefix); }
}

// ── Option Group Clicks ───────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Single-select option groups
  ['time-options', 'budget-options', 'settings-time-options', 'settings-budget-options'].forEach(id => {
    const group = document.getElementById(id);
    if (!group) return;
    group.querySelectorAll('.option-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        group.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  });

  // Multi-select chip groups
  ['diet-chips', 'settings-diet-chips'].forEach(id => {
    const group = document.getElementById(id);
    if (!group) return;
    group.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => chip.classList.toggle('active'));
    });
  });

  init();
});

// ── Toast ─────────────────────────────────────────────────────────

function showToast(msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}
