'use strict';

import { apiPost } from './api.js';
import { planState, recipeState } from './state.js';
import { showToast, switchTab } from './app.js';
import { loadAllPlans, renderPlan, updatePlanNav } from './plan.js';

// ── Helpers ───────────────────────────────────────────────────────

function _extractError(e) {
  try {
    const data = JSON.parse(e.message);
    return data.detail ?? e.message;
  } catch {
    return e.message;
  }
}

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

// ── Plan Generation ────────────────────────────────────────────

export async function quickGeneratePlan() {
  await _doGeneratePlan();
}

async function _doGeneratePlan() {
  const btn = document.getElementById('btn-gen-plan');
  btn.disabled = true;
  appendMsg('user', 'Wochenplan generieren');
  const typing = appendMsg('assistant', '', true);
  try {
    const res = await apiPost('api/plan/generate', {});
    typing.remove();
    appendMsg('assistant', res.reply, false, res.plan);
    if (res.plan) await _onNewPlan(res.plan);
  } catch(e) {
    typing.remove();
    appendMsg('assistant', `Fehler beim Generieren: ${_extractError(e)}`);
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
    recipeState.pending = recipe;
    appendSingleRecipeMsg(recipe);
  } catch(e) {
    typing.remove();
    appendMsg('assistant', `Fehler beim Generieren: ${_extractError(e)}`);
  } finally { btn.disabled = false; }
}

function appendSingleRecipeMsg(recipe) {
  const wrap = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = 'msg assistant';
  const n = recipe.nutrition_per_serving;
  el.innerHTML = `<strong>${recipe.name}</strong><br>
<span style="color:var(--text-dim);font-size:0.85em">⏱ ${recipe.cooking_time_minutes} Min · ${n.calories} kcal · ${n.protein_g}g Protein</span>`;
  if (planState.allPlans.length > 0) {
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
  } catch(e) {
    typing.remove();
    appendMsg('assistant', `Fehler beim Senden: ${_extractError(e)}`);
  } finally { btn.disabled = false; input.disabled = false; input.focus(); }
}

async function _onNewPlan() {
  await loadAllPlans();
  if (planState.allPlans.length > 0) {
    const { apiGet } = await import('./api.js');
    planState.plan = await apiGet(`api/plan/${planState.allPlans[0].id}`);
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
  recipeState.pending = recipe;
  recipeState.addDay = null;
  recipeState.addMealType = null;
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
  document.getElementById('add-to-plan-confirm-btn').disabled = !(recipeState.addDay && recipeState.addMealType);
}

export async function confirmAddToPlan() {
  if (!recipeState.pending || !recipeState.addDay || !recipeState.addMealType) return;
  const planId = planState.allPlans[planState.currentPlanIdx]?.id;
  if (!planId) { showToast('Kein aktiver Plan vorhanden.', 'error'); return; }
  const btn = document.getElementById('add-to-plan-confirm-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const meal = await apiPost('api/plan/add-recipe', {
      recipe: recipeState.pending,
      plan_id: planId,
      day: recipeState.addDay,
      meal_type: recipeState.addMealType,
    });
    if (planState.plan) planState.plan.meals.push(meal);
    closeAddToPlanModal();
    renderPlan();
    showToast('Rezept zum Plan hinzugefügt!', 'success');
    switchTab('plan');
  } catch { showToast('Fehler beim Hinzufügen.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Hinzufügen'; }
}
