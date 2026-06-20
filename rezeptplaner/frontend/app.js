'use strict';

// ── State ─────────────────────────────────────────────────────────

const state = {
  settings: null,
  plan: null,
  wizardStep: 1,
  wizardData: { persons: 2, diet_types: [], disliked_foods: [], favorite_foods: [], max_cooking_time: 30, budget: 'mittel' },
  swapMealId: null,
  swapMealName: null,
  swapReason: null,
};

const cooking = {
  steps: [],
  stepIndex: 0,
  recipeName: '',
  timerTotal: 0,
  timerRemaining: 0,
  timerInterval: null,
  timerRunning: false,
};

const DAY_LABELS = {
  monday:'Montag', tuesday:'Dienstag', wednesday:'Mittwoch',
  thursday:'Donnerstag', friday:'Freitag', saturday:'Samstag', sunday:'Sonntag',
};
const MEAL_LABELS = { lunch:'Mittagessen', dinner:'Abendessen' };
const DAY_ORDER   = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const CAT_ICONS   = {
  'Gemüse & Obst':'🥦','Fleisch & Fisch':'🥩','Milchprodukte & Eier':'🥛',
  'Getreide & Backwaren':'🌾','Konserven & Trockenwaren':'🥫','Gewürze & Öle':'🫙','Sonstiges':'🛒',
};

// ── API ───────────────────────────────────────────────────────────

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiPost(path, body) {
  const res = await fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiDelete(path) {
  const res = await fetch(path, { method:'DELETE' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  try {
    const s = await apiGet('api/settings');
    if (!s || s.persons === undefined) { showWizard(); return; }
    state.settings = s;
    showApp();
    await loadPlan();
  } catch {
    showApp();
    appendMsg('assistant', 'Fehler beim Laden. Bitte prüfe ob das Backend läuft.');
  }
}
function showApp() { document.getElementById('app').classList.remove('hidden'); }

// ── Tabs ──────────────────────────────────────────────────────────

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === `tab-${tab}`));
  if (tab === 'shopping') loadShopping();
}

// ── Chat ──────────────────────────────────────────────────────────

function chatKeydown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  appendMsg('user', msg);
  const typing = appendMsg('assistant', '…', true);
  const btn = document.getElementById('btn-send');
  btn.disabled = true; input.disabled = true;
  try {
    const res = await apiPost('api/chat', { message: msg });
    typing.remove();
    appendMsg('assistant', res.reply, false, res.plan);
    if (res.plan) { state.plan = res.plan; renderPlan(); }
  } catch {
    typing.remove();
    appendMsg('assistant', 'Fehler beim Senden. Bitte prüfe die KI-Konfiguration.');
  } finally {
    btn.disabled = false; input.disabled = false; input.focus();
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

// ── Plan ──────────────────────────────────────────────────────────

async function loadPlan() {
  try {
    const plan = await apiGet('api/plan');
    if (plan) { state.plan = plan; renderPlan(); }
  } catch { /* silent */ }
}

function renderPlan() {
  const plan = state.plan;
  const container = document.getElementById('plan-content');
  if (!plan?.meals?.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>Noch kein Wochenplan</p><p class="hint">Geh in den Chat und frag nach Rezepten!</p></div>`;
    return;
  }

  const isConfirmed = plan.meals.every(m => m.confirmed);
  const byDay = {};
  for (const meal of plan.meals) (byDay[meal.day] = byDay[meal.day] || []).push(meal);

  let html = `<div class="plan-toolbar">
    <button class="btn btn-danger btn-sm" onclick="deletePlan()">🗑 Plan löschen</button>
  </div>`;

  for (const day of DAY_ORDER) {
    const meals = byDay[day];
    if (!meals) continue;
    html += `<div class="plan-day"><div class="plan-day-header">${DAY_LABELS[day]}</div>`;
    for (const meal of meals) html += renderMealCard(meal, isConfirmed);
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
  const r = meal.recipe, n = r.nutrition_per_serving;
  const disabled = (isConfirmed || meal.confirmed) ? 'disabled' : '';
  const amt = i => `${i.amount === Math.floor(i.amount) ? Math.floor(i.amount) : i.amount} ${i.unit}`;

  return `<div class="plan-meal" id="meal-${meal.id}">
    <div class="plan-meal-header" onclick="toggleMeal(${meal.id})">
      <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type]}</span>
      <span class="meal-name">${r.name}</span>
      <span class="meal-time">⏱ ${r.cooking_time_minutes} Min</span>
      <div class="meal-actions">
        <button class="btn-cook" onclick="event.stopPropagation(); openCooking(${meal.id})">👨‍🍳 Kochen</button>
        <button class="btn-swap" ${disabled} onclick="event.stopPropagation(); openSwapModal(${meal.id},'${r.name.replace(/'/g,"\\'")}')">↔ Tauschen</button>
      </div>
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
      <ul class="ingredients-list">${r.ingredients.map(i => `<li><span>${i.name}</span><span class="ing-amount">${amt(i)}</span></li>`).join('')}</ul>
      <p class="section-label">Zubereitung</p>
      <ol class="steps-list">${r.steps.map(s => `<li>${s}</li>`).join('')}</ol>
    </div>
  </div>`;
}

function toggleMeal(id) { document.getElementById(`meal-${id}`)?.classList.toggle('open'); }

async function confirmPlan() {
  try {
    await apiPost('api/plan/confirm', {});
    if (state.plan) state.plan.meals.forEach(m => m.confirmed = true);
    renderPlan();
    showToast('Wochenplan bestätigt! Einkaufsliste ist bereit.', 'success');
    switchTab('shopping');
  } catch { showToast('Fehler beim Bestätigen.', 'error'); }
}

async function deletePlan() {
  if (!confirm('Wochenplan wirklich löschen? Deine Vorlieben und der Tausch-Verlauf bleiben erhalten.')) return;
  try {
    await apiDelete('api/plan');
    state.plan = null;
    renderPlan();
    showToast('Wochenplan gelöscht.', 'success');
  } catch { showToast('Fehler beim Löschen.', 'error'); }
}

// ── Swap ──────────────────────────────────────────────────────────

function openSwapModal(mealId, mealName) {
  state.swapMealId = mealId; state.swapMealName = mealName; state.swapReason = null;
  document.getElementById('swap-meal-name').textContent = mealName;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('swap-confirm-btn').disabled = true;
  document.getElementById('swap-modal').classList.remove('hidden');
}
function closeSwapModal() { document.getElementById('swap-modal').classList.add('hidden'); }

async function confirmSwap() {
  if (!state.swapMealId || !state.swapReason) return;
  const btn = document.getElementById('swap-confirm-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Wird getauscht…';
  try {
    const updated = await apiPost('api/plan/swap', { meal_id: state.swapMealId, reason: state.swapReason });
    if (state.plan) {
      const idx = state.plan.meals.findIndex(m => m.id === state.swapMealId);
      if (idx !== -1) state.plan.meals[idx] = updated;
    }
    closeSwapModal();
    renderPlan();
    showToast('Rezept wurde ausgetauscht!', 'success');
  } catch {
    showToast('Fehler beim Tauschen.', 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Tauschen';
  }
}

// ── Cooking Mode ──────────────────────────────────────────────────

function openCooking(mealId) {
  const meal = state.plan?.meals.find(m => m.id === mealId);
  if (!meal) return;
  cooking.steps = meal.recipe.steps;
  cooking.recipeName = meal.recipe.name;
  cooking.stepIndex = 0;
  stopTimer();
  document.getElementById('cooking-recipe-label').textContent = meal.recipe.name;
  document.getElementById('cooking-mode').classList.remove('hidden');
  renderCookingStep();
}

function closeCooking() {
  stopTimer();
  document.getElementById('cooking-mode').classList.add('hidden');
}

function renderCookingStep() {
  const i = cooking.stepIndex, steps = cooking.steps, total = steps.length;
  document.getElementById('cooking-step-num').textContent = `Schritt ${i + 1} / ${total}`;
  document.getElementById('cooking-step-text').textContent = steps[i];

  // Dots
  const dots = document.getElementById('cooking-dots');
  dots.innerHTML = steps.map((_, idx) =>
    `<span class="cooking-dot ${idx < i ? 'done' : idx === i ? 'active' : ''}"></span>`
  ).join('');

  // Nav buttons
  document.getElementById('cooking-prev').disabled = i === 0;
  const nextBtn = document.getElementById('cooking-next');
  nextBtn.textContent = i === total - 1 ? '✓ Fertig' : 'Weiter →';

  // Timer
  stopTimer();
  const secs = parseStepTime(steps[i]);
  const timerSection = document.getElementById('cooking-timer-section');
  if (secs) {
    cooking.timerTotal = secs;
    cooking.timerRemaining = secs;
    cooking.timerRunning = false;
    timerSection.classList.remove('hidden');
    document.getElementById('timer-btn').textContent = '▶ Timer starten';
    updateTimerDisplay();
  } else {
    timerSection.classList.add('hidden');
  }
}

function cookingPrev() {
  if (cooking.stepIndex > 0) { cooking.stepIndex--; renderCookingStep(); }
}
function cookingNext() {
  if (cooking.stepIndex < cooking.steps.length - 1) { cooking.stepIndex++; renderCookingStep(); }
  else closeCooking();
}

function parseStepTime(text) {
  const m = text.match(/(\d+)\s*(Stunden?|Std|Minuten?|Min|Sekunden?|Sek)/i);
  if (!m) return null;
  const n = parseInt(m[1]);
  const unit = m[2].toLowerCase();
  if (unit.startsWith('st')) return n * 3600;
  if (unit.startsWith('sek') || unit === 's') return n;
  return n * 60;
}

function toggleCookingTimer() {
  if (cooking.timerRunning) pauseTimer();
  else startTimer();
}

function startTimer() {
  if (cooking.timerRemaining <= 0) cooking.timerRemaining = cooking.timerTotal;
  cooking.timerRunning = true;
  document.getElementById('timer-btn').textContent = '⏸ Pausieren';
  cooking.timerInterval = setInterval(() => {
    cooking.timerRemaining--;
    updateTimerDisplay();
    if (cooking.timerRemaining <= 0) {
      stopTimer();
      document.getElementById('timer-btn').textContent = '↺ Neu starten';
      showToast('Timer abgelaufen!', 'success');
    }
  }, 1000);
}

function pauseTimer() {
  cooking.timerRunning = false;
  clearInterval(cooking.timerInterval);
  document.getElementById('timer-btn').textContent = '▶ Weiter';
}

function stopTimer() {
  cooking.timerRunning = false;
  clearInterval(cooking.timerInterval);
  cooking.timerInterval = null;
}

function updateTimerDisplay() {
  const r = cooking.timerRemaining;
  const m = Math.floor(r / 60), s = r % 60;
  document.getElementById('timer-digits').textContent = `${m}:${s.toString().padStart(2, '0')}`;
  const circumference = 276.46;
  const progress = cooking.timerTotal > 0 ? r / cooking.timerTotal : 0;
  document.getElementById('timer-circle').style.strokeDashoffset = circumference * (1 - progress);
}

// ── Shopping ──────────────────────────────────────────────────────

async function loadShopping() {
  const container = document.getElementById('shopping-content');
  try {
    const list = await apiGet('api/shopping-list');
    renderShopping(list, container);
  } catch {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Fehler beim Laden.</p></div>`;
  }
}

function renderShopping(list, container) {
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
      html += `<label class="shopping-item" onclick="toggleCheck(this)">
        <input type="checkbox" onclick="event.stopPropagation();toggleCheck(this.closest('.shopping-item'))">
        <span class="item-name">${item.name}</span>
        <span class="item-amount">${n} ${item.unit}</span>
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
    res.ok
      ? showToast(`${res.pushed} Artikel zur HA Einkaufsliste hinzugefügt!`, 'success')
      : showToast(res.error || 'Fehler beim Pushen.', 'error');
  } catch { showToast('Verbindung zu Home Assistant fehlgeschlagen.', 'error'); }
}

// ── Wizard ────────────────────────────────────────────────────────

function showWizard() { updateWizardStep(1); document.getElementById('wizard').classList.remove('hidden'); }

function updateWizardStep(step) {
  state.wizardStep = step;
  document.querySelectorAll('.wizard-step').forEach(el => el.classList.toggle('hidden', parseInt(el.dataset.step) !== step));
  document.getElementById('wizard-step-label').textContent = `Schritt ${step} von 6`;
  document.getElementById('wizard-bar').style.width = `${(step / 6) * 100}%`;
  document.getElementById('wizard-back').style.visibility = step > 1 ? 'visible' : 'hidden';
  document.getElementById('wizard-next').textContent = step === 6 ? 'Fertig' : 'Weiter';
}

function wizardBack() { if (state.wizardStep > 1) updateWizardStep(state.wizardStep - 1); }

async function wizardNext() {
  collectWizardStep(state.wizardStep);
  if (state.wizardStep < 6) { updateWizardStep(state.wizardStep + 1); return; }
  const btn = document.getElementById('wizard-next');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Speichern…';
  try {
    await apiPost('api/settings', state.wizardData);
    state.settings = state.wizardData;
    document.getElementById('wizard').classList.add('hidden');
    showApp();
    appendMsg('assistant', 'Alles klar! Ich kenne jetzt eure Vorlieben.\n\nSchreib einfach „Gib mir Rezepte für diese Woche" um loszulegen! 🍽');
  } catch { showToast('Fehler beim Speichern.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Fertig'; }
}

function collectWizardStep(step) {
  if (step === 1) state.wizardData.persons = parseInt(document.getElementById('persons-display').textContent);
  else if (step === 2) state.wizardData.diet_types = [...document.querySelectorAll('#diet-chips .chip.active')].map(c => c.dataset.value);
  else if (step === 5) state.wizardData.max_cooking_time = parseInt(document.querySelector('#time-options .option-btn.active')?.dataset.value || 30);
  else if (step === 6) state.wizardData.budget = document.querySelector('#budget-options .option-btn.active')?.dataset.value || 'mittel';
}

function adjustPersons(d) {
  const el = document.getElementById('persons-display');
  el.textContent = Math.max(1, Math.min(10, parseInt(el.textContent) + d));
  state.wizardData.persons = parseInt(el.textContent);
}

// ── Settings ──────────────────────────────────────────────────────

function openSettings() {
  const s = state.settings || {};
  document.getElementById('settings-persons-display').textContent = s.persons || 2;
  document.querySelectorAll('#settings-diet-chips .chip').forEach(c => c.classList.toggle('active', (s.diet_types||[]).includes(c.dataset.value)));
  renderTagList('settings-disliked', s.disliked_foods || []);
  renderTagList('settings-favorite', s.favorite_foods || []);
  document.querySelectorAll('#settings-time-options .option-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.value) === (s.max_cooking_time||30)));
  document.querySelectorAll('#settings-budget-options .option-btn').forEach(b => b.classList.toggle('active', b.dataset.value === (s.budget||'mittel')));
  document.getElementById('settings-modal').classList.remove('hidden');
}
function closeSettings() { document.getElementById('settings-modal').classList.add('hidden'); }

async function saveSettings() {
  const saved = await apiPost('api/settings', {
    persons: parseInt(document.getElementById('settings-persons-display').textContent),
    diet_types: [...document.querySelectorAll('#settings-diet-chips .chip.active')].map(c => c.dataset.value),
    disliked_foods: getTagValues('settings-disliked'),
    favorite_foods: getTagValues('settings-favorite'),
    max_cooking_time: parseInt(document.querySelector('#settings-time-options .option-btn.active')?.dataset.value||30),
    budget: document.querySelector('#settings-budget-options .option-btn.active')?.dataset.value||'mittel',
  }).catch(() => null);
  if (saved) { state.settings = saved; closeSettings(); showToast('Einstellungen gespeichert!', 'success'); }
  else showToast('Fehler beim Speichern.', 'error');
}

function adjustSettingsPersons(d) {
  const el = document.getElementById('settings-persons-display');
  el.textContent = Math.max(1, Math.min(10, parseInt(el.textContent) + d));
}

// ── Tags ──────────────────────────────────────────────────────────

const tagValues = {};
function addTag(prefix) {
  const input = document.getElementById(`${prefix}-input`);
  const val = input.value.trim();
  if (!val) return;
  if (!tagValues[prefix]) tagValues[prefix] = [];
  if (!tagValues[prefix].includes(val)) {
    tagValues[prefix].push(val);
    if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
    if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
    renderTagList(prefix, tagValues[prefix]);
  }
  input.value = '';
}
function removeTag(prefix, val) {
  tagValues[prefix] = (tagValues[prefix]||[]).filter(v => v !== val);
  if (prefix === 'disliked') state.wizardData.disliked_foods = tagValues[prefix];
  if (prefix === 'favorite') state.wizardData.favorite_foods = tagValues[prefix];
  renderTagList(prefix, tagValues[prefix]);
}
function renderTagList(prefix, values) {
  tagValues[prefix] = [...values];
  const el = document.getElementById(`${prefix}-tags`);
  if (!el) return;
  el.innerHTML = values.map(v => `<span class="tag">${v}<button onclick="removeTag('${prefix}','${v.replace(/'/g,"\\'")}')">×</button></span>`).join('');
}
function getTagValues(prefix) { return tagValues[prefix] || []; }
function tagKeydown(e, prefix) { if (e.key === 'Enter') { e.preventDefault(); addTag(prefix); } }

// ── Toast ─────────────────────────────────────────────────────────

function showToast(msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

// ── DOM Event Wiring ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Single-select option groups
  ['time-options','budget-options','settings-time-options','settings-budget-options'].forEach(id => {
    document.getElementById(id)?.querySelectorAll('.option-btn').forEach(btn =>
      btn.addEventListener('click', () => {
        btn.closest('.option-group').querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      })
    );
  });

  // Multi-select chip groups
  ['diet-chips','settings-diet-chips'].forEach(id => {
    document.getElementById(id)?.querySelectorAll('.chip').forEach(c =>
      c.addEventListener('click', () => c.classList.toggle('active'))
    );
  });

  // Swap reason selection
  document.querySelectorAll('#swap-reasons .option-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.swapReason = btn.dataset.value;
      document.getElementById('swap-confirm-btn').disabled = false;
    })
  );

  init();
});
