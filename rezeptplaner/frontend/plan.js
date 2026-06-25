'use strict';

import { apiGet, apiPost, apiDelete } from './api.js';
import { DAY_LABELS, DAY_ORDER, MEAL_LABELS, MEAL_SLOTS, planState, swapState, recipeState } from './state.js';
import { showToast, switchTab } from './app.js';
import { openCooking } from './cooking.js';

export async function loadAllPlans() {
  try {
    planState.allPlans = await apiGet('api/plans');
    planState.currentPlanIdx = 0;
    if (planState.allPlans.length > 0) await loadPlanById(planState.allPlans[0].id);
    updatePlanNav();
  } catch { /* silent */ }
}

export async function loadPlanById(planId) {
  try {
    const plan = await apiGet(`api/plan/${planId}`);
    if (plan) { planState.plan = plan; renderPlan(); }
  } catch { /* silent */ }
}

export async function loadRatings() {
  try { planState.ratings = await apiGet('api/recipe/ratings'); } catch { /* silent */ }
}

export function updatePlanNav() {
  const nav = document.getElementById('plan-nav');
  const label = document.getElementById('plan-nav-label');
  const prev = document.getElementById('plan-nav-prev');
  const next = document.getElementById('plan-nav-next');
  if (planState.allPlans.length === 0) { nav.classList.add('hidden'); return; }
  nav.classList.remove('hidden');
  const meta = planState.allPlans[planState.currentPlanIdx];
  const d = new Date(meta.week_start + 'T00:00:00');
  const end = new Date(d); end.setDate(d.getDate() + 6);
  const fmt = dt => dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
  label.textContent = `${fmt(d)} – ${fmt(end)}`;
  prev.disabled = planState.currentPlanIdx >= planState.allPlans.length - 1;
  next.disabled = planState.currentPlanIdx <= 0;
}

export async function navigatePlan(dir) {
  const newIdx = planState.currentPlanIdx + (-dir);
  if (newIdx < 0 || newIdx >= planState.allPlans.length) return;
  planState.currentPlanIdx = newIdx;
  await loadPlanById(planState.allPlans[newIdx].id);
  updatePlanNav();
}

export function renderPlan() {
  const plan = planState.plan;
  const container = document.getElementById('plan-content');
  if (!plan?.meals?.length && !plan?.skipped_slots?.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>Noch kein Wochenplan</p><p class="hint">Nutze den Chat oder klicke "Wochenplan generieren"!</p></div>`;
    return;
  }
  const isConfirmed = plan.meals.every(m => m.confirmed);
  const byDay = {};
  for (const meal of plan.meals) (byDay[meal.day] = byDay[meal.day] || []).push(meal);
  const skippedByDay = {};
  for (const slot of (plan.skipped_slots || [])) (skippedByDay[slot.day] = skippedByDay[slot.day] || []).push(slot);

  let html = `<div class="plan-toolbar">
    <button class="btn btn-danger btn-sm" onclick="deletePlan(${plan.id})">🗑 Woche löschen</button>
  </div>`;
  for (const day of DAY_ORDER) {
    const meals = byDay[day];
    const skipped = skippedByDay[day];
    if (!meals?.length && !skipped?.length) continue;
    html += `<div class="plan-day"><div class="plan-day-header">${DAY_LABELS[day]}</div>`;
    if (meals) for (const meal of meals) html += renderMealCard(meal, isConfirmed);
    if (skipped) for (const slot of skipped) html += renderSkippedSlotCard(slot, isConfirmed);
    html += `</div>`;
  }
  html += `<div class="plan-actions">`;
  if (isConfirmed) html += `<span class="confirmed-badge">✓ Woche bestätigt</span>`;
  else html += `<button class="btn btn-success" onclick="confirmPlan()">✓ Woche bestätigen</button>`;
  html += `</div>`;
  container.innerHTML = html;
}

export function renderMealCard(meal, isConfirmed) {
  if (meal.is_leftovers) {
    const undoBtn = isConfirmed ? '' : `<button class="btn-swap" onclick="event.stopPropagation(); undoDouble(${meal.id})">↩ Aufheben</button>`;
    return `<div class="plan-meal leftovers-meal" id="meal-${meal.id}">
      <div class="plan-meal-header">
        <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type]}</span>
        <span class="meal-name">↩ Reste</span>
        <span class="leftovers-badge">${meal.source_recipe_name}</span>
        <div class="meal-actions">${undoBtn}</div>
      </div>
    </div>`;
  }
  const r = meal.recipe, n = r.nutrition_per_serving;
  const disabled = (isConfirmed || meal.confirmed) ? 'disabled' : '';
  const canDouble = !isConfirmed && _canDoubleSlot(meal.day, meal.meal_type);
  const multiplierBadge = meal.portion_multiplier > 1 ? `<span class="multiplier-badge">×${meal.portion_multiplier}</span>` : '';
  const amt = i => `${i.amount === Math.floor(i.amount) ? Math.floor(i.amount) : i.amount} ${i.unit}`;
  const currentRating = planState.ratings[r.name] ?? 5;
  const stars = renderStars(r.name, currentRating);
  const editButtons = isConfirmed ? '' : `
    <button class="btn-swap" ${disabled} onclick="event.stopPropagation(); skipSlot('${meal.day}','${meal.meal_type}')">✕ Auslassen</button>
    <button class="btn-swap" ${disabled} ${canDouble ? '' : 'disabled'} onclick="event.stopPropagation(); doubleSlot('${meal.day}','${meal.meal_type}')">×2 Verdoppeln</button>
  `;
  return `<div class="plan-meal" id="meal-${meal.id}">
    <div class="plan-meal-header" onclick="toggleMeal(${meal.id})">
      <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type]}</span>
      <span class="meal-name">${r.name}</span>
      ${multiplierBadge}
      <span class="meal-time">⏱ ${r.cooking_time_minutes} Min</span>
      <div class="meal-actions">
        <button class="btn-cook" onclick="event.stopPropagation(); openCooking(${meal.id})">👨‍🍳 Kochen</button>
        <button class="btn-swap" ${disabled} onclick="event.stopPropagation(); openSwapModal(${meal.id},'${r.name.replace(/'/g,"\\'")}')">↔ Tauschen</button>
        ${editButtons}
      </div>
      <span class="expand-icon">▾</span>
    </div>
    <div class="rating-row" onclick="event.stopPropagation()">
      ${stars}
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

function _canDoubleSlot(day, mealType) {
  const idx = MEAL_SLOTS.findIndex(s => s.day === day && s.meal_type === mealType);
  if (idx <= 0) return false;
  const prev = MEAL_SLOTS[idx - 1];
  return planState.plan?.meals.some(m => m.day === prev.day && m.meal_type === prev.meal_type && !m.is_leftovers) ?? false;
}

export function renderSkippedSlotCard(slot, isConfirmed) {
  const swapBtn = isConfirmed ? '' : `<button class="btn-swap" onclick="openSwapSkippedSlot('${slot.day}','${slot.meal_type}')">↔ Tauschen</button>`;
  return `<div class="plan-meal skipped-meal" id="skipped-${slot.day}-${slot.meal_type}">
    <div class="plan-meal-header">
      <span class="meal-type-badge">${MEAL_LABELS[slot.meal_type]}</span>
      <span class="meal-name">✕ Ausgelassen</span>
      <div class="meal-actions">${swapBtn}</div>
    </div>
  </div>`;
}

export function renderStars(recipeName, currentScore) {
  const safe = recipeName.replace(/'/g, "\\'").replace(/"/g, '&quot;');
  let html = '<div class="stars">';
  for (let i = 1; i <= 10; i++) {
    html += `<button class="star-btn ${i <= currentScore ? 'active' : ''}" onclick="event.stopPropagation();rateMeal('${safe}',${i})" title="${i}/10">★</button>`;
  }
  html += `<span class="star-score">${currentScore}/10</span></div>`;
  return html;
}

export async function rateMeal(recipeName, score) {
  try {
    await apiPost('api/recipe/rate', { recipe_name: recipeName, score });
    planState.ratings[recipeName] = score;
    renderPlan();
    showToast(`Bewertet: ${score}/10`, 'success');
  } catch { showToast('Fehler beim Bewerten.', 'error'); }
}

export function toggleMeal(id) { document.getElementById(`meal-${id}`)?.classList.toggle('open'); }

export async function confirmPlan() {
  try {
    await apiPost('api/plan/confirm', {});
    if (planState.plan) planState.plan.meals.forEach(m => m.confirmed = true);
    renderPlan();
    showToast('Wochenplan bestätigt! Einkaufsliste ist bereit.', 'success');
    switchTab('shopping');
  } catch { showToast('Fehler beim Bestätigen.', 'error'); }
}

export async function deletePlan(planId) {
  if (!confirm('Diese Woche wirklich löschen? Deine Vorlieben und der Tausch-Verlauf bleiben erhalten.')) return;
  try {
    await apiDelete(`api/plan/${planId}`);
    planState.plan = null;
    await loadAllPlans();
    showToast('Wochenplan gelöscht.', 'success');
    if (planState.allPlans.length === 0) {
      document.getElementById('plan-content').innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>Noch kein Wochenplan</p><p class="hint">Nutze den Chat oder klicke "Wochenplan generieren"!</p></div>`;
    }
  } catch { showToast('Fehler beim Löschen.', 'error'); }
}

export function openSwapModal(mealId, mealName) {
  swapState.mealId = mealId;
  swapState.mealName = mealName;
  swapState.reason = null;
  swapState.mode = null;
  swapState.recipeId = null;
  swapState.skippedSlot = null;
  document.getElementById('swap-meal-name').textContent = mealName;
  document.getElementById('swap-mode-section').classList.remove('hidden');
  document.getElementById('swap-ai-section').classList.add('hidden');
  document.getElementById('swap-recipe-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = 'none';
  document.getElementById('swap-confirm-btn').disabled = true;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('swap-modal').classList.remove('hidden');
}

export function closeSwapModal() {
  document.getElementById('swap-modal').classList.add('hidden');
  swapState.skippedSlot = null;
}

export function selectSwapMode(mode) {
  swapState.mode = mode;
  document.getElementById('swap-mode-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = '';
  if (mode === 'ai') {
    document.getElementById('swap-ai-section').classList.remove('hidden');
  } else {
    document.getElementById('swap-recipe-section').classList.remove('hidden');
    renderSwapRecipeList();
  }
  document.getElementById('swap-confirm-btn').disabled = true;
}

function renderSwapRecipeList() {
  const list = document.getElementById('swap-recipe-list');
  const recipes = recipeState.userRecipes || [];
  if (!recipes.length) {
    list.innerHTML = '<p class="hint" style="text-align:center;padding:16px 0">Keine eigenen Rezepte vorhanden.<br>Füge zuerst Rezepte unter "📖 Rezepte" hinzu.</p>';
    return;
  }
  list.innerHTML = `<div class="option-group vertical">${recipes.map(ur =>
    `<button class="option-btn" onclick="selectSwapRecipe(${ur.id}, this)">${ur.recipe.name}</button>`
  ).join('')}</div>`;
}

export function selectSwapRecipe(recipeId, btn) {
  swapState.recipeId = recipeId;
  document.querySelectorAll('#swap-recipe-list .option-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('swap-confirm-btn').disabled = false;
}

export function swapGoBack() {
  swapState.mode = null;
  swapState.reason = null;
  swapState.recipeId = null;
  swapState.skippedSlot = null;
  document.getElementById('swap-mode-section').classList.remove('hidden');
  document.getElementById('swap-ai-section').classList.add('hidden');
  document.getElementById('swap-recipe-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = 'none';
  document.getElementById('swap-confirm-btn').disabled = true;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
}

export async function confirmSwap() {
  const isSkipped = !!swapState.skippedSlot;
  if (isSkipped) {
    if (!swapState.mode) return;
  } else {
    if (!swapState.mealId || !swapState.mode) return;
  }
  if (swapState.mode === 'ai' && !swapState.reason) return;
  if (swapState.mode === 'recipe' && !swapState.recipeId) return;

  const btn = document.getElementById('swap-confirm-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Wird getauscht…';
  try {
    if (isSkipped) {
      const req = { plan_id: planState.plan.id, day: swapState.skippedSlot.day, meal_type: swapState.skippedSlot.meal_type };
      if (swapState.mode === 'ai') req.reason = swapState.reason;
      else if (swapState.mode === 'recipe') req.recipe_id = swapState.recipeId;
      await apiPost('api/plan/fill-skipped-slot', req);
      closeSwapModal();
      await _reloadPlan();
      showToast('Slot wurde befüllt!', 'success');
      return;
    }

    let updated;
    if (swapState.mode === 'ai') {
      updated = await apiPost('api/plan/swap', { meal_id: swapState.mealId, reason: swapState.reason });
    } else {
      updated = await apiPost('api/plan/swap-with-recipe', { meal_id: swapState.mealId, recipe_id: swapState.recipeId });
    }
    if (planState.plan) {
      const idx = planState.plan.meals.findIndex(m => m.id === swapState.mealId);
      if (idx !== -1) planState.plan.meals[idx] = updated;
    }
    closeSwapModal();
    renderPlan();
    showToast('Rezept wurde ausgetauscht!', 'success');
  } catch { showToast('Fehler beim Tauschen.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Tauschen'; }
}

async function _reloadPlan() {
  if (!planState.plan?.id) return;
  const plan = await apiGet(`api/plan/${planState.plan.id}`);
  if (plan) { planState.plan = plan; renderPlan(); }
}

export async function skipSlot(day, mealType) {
  if (!planState.plan?.id) return;
  try {
    await apiPost('api/plan/skip-slot', { plan_id: planState.plan.id, day, meal_type: mealType });
    await _reloadPlan();
    showToast('Slot ausgelassen.', 'success');
  } catch { showToast('Fehler beim Auslassen.', 'error'); }
}

export async function doubleSlot(day, mealType) {
  if (!planState.plan?.id) return;
  try {
    await apiPost('api/plan/double-slot', { plan_id: planState.plan.id, day, meal_type: mealType });
    await _reloadPlan();
    showToast('Slot verdoppelt.', 'success');
  } catch { showToast('Fehler beim Verdoppeln.', 'error'); }
}

export async function undoDouble(leftoversMealId) {
  try {
    await apiPost('api/plan/undo-double', { leftovers_meal_id: leftoversMealId });
    await _reloadPlan();
    showToast('Verdoppeln aufgehoben.', 'success');
  } catch { showToast('Fehler beim Aufheben.', 'error'); }
}

export function openSwapSkippedSlot(day, mealType) {
  // Re-use the swap modal flow by generating a temporary AI swap for the skipped slot.
  // We create the meal first with the same recipe via AI suggestion, then remove the skipped marker.
  swapState.mealId = null;
  swapState.skippedSlot = { day, meal_type: mealType };
  document.getElementById('swap-meal-name').textContent = `${DAY_LABELS[day]}, ${MEAL_LABELS[mealType]}`;
  document.getElementById('swap-mode-section').classList.remove('hidden');
  document.getElementById('swap-ai-section').classList.add('hidden');
  document.getElementById('swap-recipe-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = 'none';
  document.getElementById('swap-confirm-btn').disabled = true;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('swap-modal').classList.remove('hidden');
}
