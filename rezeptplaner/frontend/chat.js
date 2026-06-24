'use strict';

import { apiPost } from './api.js';
import { state, DAY_LABELS, MEAL_LABELS } from './state.js';
import { showToast, switchTab } from './app.js';
import { loadAllPlans, renderPlan, updatePlanNav } from './plan.js';

// ── Chat ──────────────────────────────────────────────────────────

export function chatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
}

export async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  appendMsg('user', msg);
  await _doChat({ message: msg });
}

// ── Slot Config Modal ──────────────────────────────────────────

const _ALL_SLOTS = [
  { day: 'monday',    meal_type: 'dinner' },
  { day: 'tuesday',   meal_type: 'dinner' },
  { day: 'wednesday', meal_type: 'dinner' },
  { day: 'thursday',  meal_type: 'dinner' },
  { day: 'friday',    meal_type: 'dinner' },
  { day: 'saturday',  meal_type: 'lunch'  },
  { day: 'saturday',  meal_type: 'dinner' },
  { day: 'sunday',    meal_type: 'lunch'  },
  { day: 'sunday',    meal_type: 'dinner' },
];
const _slotModes = {};

export function openSlotModal() {
  _ALL_SLOTS.forEach(s => { _slotModes[`${s.day}:${s.meal_type}`] = 'normal'; });
  _renderSlotList();
  document.getElementById('slot-modal').classList.remove('hidden');
}

export function closeSlotModal() {
  document.getElementById('slot-modal').classList.add('hidden');
}

export function setSlotMode(day, mealType, mode) {
  _slotModes[`${day}:${mealType}`] = mode;
  _renderSlotList();
}

function _renderSlotList() {
  const list = document.getElementById('slot-list');
  list.innerHTML = _ALL_SLOTS.map((s, idx) => {
    const key = `${s.day}:${s.meal_type}`;
    const mode = _slotModes[key] || 'normal';
    const hasPrev = _ALL_SLOTS.slice(0, idx).some(p => (_slotModes[`${p.day}:${p.meal_type}`] || 'normal') === 'normal');
    const btn = (m, label) =>
      `<button class="slot-mode-btn ${mode === m ? 'active' : ''}" onclick="setSlotMode('${s.day}','${s.meal_type}','${m}')">${label}</button>`;
    const leftoverBtn = hasPrev
      ? btn('leftovers', '↩ Reste')
      : `<button class="slot-mode-btn" disabled>↩ Reste</button>`;
    return `<div class="slot-row">
      <span class="slot-label">${DAY_LABELS[s.day]}, ${MEAL_LABELS[s.meal_type]}</span>
      <div class="slot-mode-btns">
        ${btn('normal', '✓ Normal')}
        ${btn('skip', '✕ Auslassen')}
        ${leftoverBtn}
      </div>
    </div>`;
  }).join('');
}

export async function confirmSlotConfig() {
  closeSlotModal();
  const slots = _ALL_SLOTS.map(s => ({
    day: s.day,
    meal_type: s.meal_type,
    mode: _slotModes[`${s.day}:${s.meal_type}`] || 'normal',
  }));
  await _doGeneratePlan(slots);
}

export async function quickGeneratePlan() {
  openSlotModal();
}

async function _doGeneratePlan(slots) {
  const btn = document.getElementById('btn-gen-plan');
  btn.disabled = true;
  appendMsg('user', 'Wochenplan generieren');
  const typing = appendMsg('assistant', '', true);
  try {
    const res = await apiPost('api/plan/generate', { slots });
    typing.remove();
    appendMsg('assistant', res.reply, false, res.plan);
    if (res.plan) await _onNewPlan(res.plan);
  } catch {
    typing.remove();
    appendMsg('assistant', 'Fehler beim Generieren. Bitte prüfe die KI-Konfiguration.');
  } finally { btn.disabled = false; }
}

export async function quickSingleRecipe() {
  const btn = document.getElementById('btn-gen-recipe');
  btn.disabled = true;
  appendMsg('user', 'Einzelnes Rezept vorschlagen');
  const typing = appendMsg('assistant', '', true);
  try {
    const recipe = await apiPost('api/recipe/single', {});
    typing.remove();
    state.pendingSingleRecipe = recipe;
    appendSingleRecipeMsg(recipe);
  } catch {
    typing.remove();
    appendMsg('assistant', 'Fehler beim Generieren. Bitte prüfe die KI-Konfiguration.');
  } finally { btn.disabled = false; }
}

function appendSingleRecipeMsg(recipe) {
  const wrap = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = 'msg assistant';
  const n = recipe.nutrition_per_serving;
  el.innerHTML = `<strong>${recipe.name}</strong><br>
<span style="color:var(--text-dim);font-size:0.85em">⏱ ${recipe.cooking_time_minutes} Min · ${n.calories} kcal · ${n.protein_g}g Protein</span>`;
  if (state.allPlans.length > 0) {
    const btn = document.createElement('button');
    btn.className = 'msg-plan-link';
    btn.textContent = '+ Zum Plan hinzufügen';
    btn.onclick = () => openAddToPlanModal(recipe);
    el.appendChild(document.createElement('br'));
    el.appendChild(btn);
  }
  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
}

async function _doChat(body) {
  const typing = appendMsg('assistant', '', true);
  const btn = document.getElementById('btn-send');
  const input = document.getElementById('chat-input');
  btn.disabled = true; input.disabled = true;
  try {
    const res = await apiPost('api/chat', body);
    typing.remove();
    appendMsg('assistant', res.reply, false, res.plan);
    if (res.plan) await _onNewPlan(res.plan);
  } catch {
    typing.remove();
    appendMsg('assistant', 'Fehler beim Senden. Bitte prüfe die KI-Konfiguration.');
  } finally { btn.disabled = false; input.disabled = false; input.focus(); }
}

async function _onNewPlan() {
  await loadAllPlans();
  if (state.allPlans.length > 0) {
    const { apiGet } = await import('./api.js');
    state.plan = await apiGet(`api/plan/${state.allPlans[0].id}`);
    renderPlan();
    updatePlanNav();
  }
}

export function appendMsg(role, text, isTyping = false, plan = null) {
  const wrap = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = `msg ${role}${isTyping ? ' typing' : ''}`;
  if (isTyping) {
    el.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  } else {
    el.textContent = text;
  }
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

// ── Add-to-Plan Modal ─────────────────────────────────────────────

export function openAddToPlanModal(recipe) {
  state.pendingSingleRecipe = recipe;
  state.addDay = null;
  state.addMealType = null;
  document.getElementById('add-to-plan-recipe-name').textContent = recipe.name;
  document.querySelectorAll('#add-day-options .option-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('#add-meal-type-options .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('add-to-plan-confirm-btn').disabled = true;
  document.getElementById('add-to-plan-modal').classList.remove('hidden');
}

export function closeAddToPlanModal() {
  document.getElementById('add-to-plan-modal').classList.add('hidden');
}

export function checkAddToPlanReady() {
  document.getElementById('add-to-plan-confirm-btn').disabled = !(state.addDay && state.addMealType);
}

export async function confirmAddToPlan() {
  if (!state.pendingSingleRecipe || !state.addDay || !state.addMealType) return;
  const planId = state.allPlans[state.currentPlanIdx]?.id;
  if (!planId) { showToast('Kein aktiver Plan vorhanden.', 'error'); return; }
  const btn = document.getElementById('add-to-plan-confirm-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const meal = await apiPost('api/plan/add-recipe', {
      recipe: state.pendingSingleRecipe,
      plan_id: planId,
      day: state.addDay,
      meal_type: state.addMealType,
    });
    if (state.plan) state.plan.meals.push(meal);
    closeAddToPlanModal();
    renderPlan();
    showToast('Rezept zum Plan hinzugefügt!', 'success');
    switchTab('plan');
  } catch { showToast('Fehler beim Hinzufügen.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Hinzufügen'; }
}
