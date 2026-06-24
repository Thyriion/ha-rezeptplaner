'use strict';

import { apiGet, apiPost, apiDelete } from './api.js';
import { DAY_LABELS, DAY_ORDER, MEAL_LABELS, state } from './state.js';
import { showToast, switchTab } from './app.js';
import { openCooking } from './cooking.js';

export async function loadAllPlans() {
  try {
    state.allPlans = await apiGet('api/plans');
    state.currentPlanIdx = 0;
    if (state.allPlans.length > 0) await loadPlanById(state.allPlans[0].id);
    updatePlanNav();
  } catch { /* silent */ }
}

export async function loadPlanById(planId) {
  try {
    const plan = await apiGet(`api/plan/${planId}`);
    if (plan) { state.plan = plan; renderPlan(); }
  } catch { /* silent */ }
}

export async function loadRatings() {
  try { state.ratings = await apiGet('api/recipe/ratings'); } catch { /* silent */ }
}

export function updatePlanNav() {
  const nav = document.getElementById('plan-nav');
  const label = document.getElementById('plan-nav-label');
  const prev = document.getElementById('plan-nav-prev');
  const next = document.getElementById('plan-nav-next');
  if (state.allPlans.length === 0) { nav.classList.add('hidden'); return; }
  nav.classList.remove('hidden');
  const meta = state.allPlans[state.currentPlanIdx];
  const d = new Date(meta.week_start + 'T00:00:00');
  const end = new Date(d); end.setDate(d.getDate() + 6);
  const fmt = dt => dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
  label.textContent = `${fmt(d)} – ${fmt(end)}`;
  prev.disabled = state.currentPlanIdx >= state.allPlans.length - 1;
  next.disabled = state.currentPlanIdx <= 0;
}

export async function navigatePlan(dir) {
  const newIdx = state.currentPlanIdx + (-dir);
  if (newIdx < 0 || newIdx >= state.allPlans.length) return;
  state.currentPlanIdx = newIdx;
  await loadPlanById(state.allPlans[newIdx].id);
  updatePlanNav();
}

export function renderPlan() {
  const plan = state.plan;
  const container = document.getElementById('plan-content');
  if (!plan?.meals?.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>Noch kein Wochenplan</p><p class="hint">Nutze den Chat oder klicke "Wochenplan generieren"!</p></div>`;
    return;
  }
  const isConfirmed = plan.meals.every(m => m.confirmed);
  const byDay = {};
  for (const meal of plan.meals) (byDay[meal.day] = byDay[meal.day] || []).push(meal);

  let html = `<div class="plan-toolbar">
    <button class="btn btn-danger btn-sm" onclick="deletePlan(${plan.id})">🗑 Woche löschen</button>
  </div>`;
  for (const day of DAY_ORDER) {
    const meals = byDay[day];
    if (!meals) continue;
    html += `<div class="plan-day"><div class="plan-day-header">${DAY_LABELS[day]}</div>`;
    for (const meal of meals) html += renderMealCard(meal, isConfirmed);
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
    return `<div class="plan-meal leftovers-meal" id="meal-${meal.id}">
      <div class="plan-meal-header">
        <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type]}</span>
        <span class="meal-name">↩ Reste</span>
        <span class="leftovers-badge">${meal.source_recipe_name}</span>
      </div>
    </div>`;
  }
  const r = meal.recipe, n = r.nutrition_per_serving;
  const disabled = (isConfirmed || meal.confirmed) ? 'disabled' : '';
  const amt = i => `${i.amount === Math.floor(i.amount) ? Math.floor(i.amount) : i.amount} ${i.unit}`;
  const currentRating = state.ratings[r.name] ?? 5;
  const stars = renderStars(r.name, currentRating);
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
    state.ratings[recipeName] = score;
    renderPlan();
    showToast(`Bewertet: ${score}/10`, 'success');
  } catch { showToast('Fehler beim Bewerten.', 'error'); }
}

export function toggleMeal(id) { document.getElementById(`meal-${id}`)?.classList.toggle('open'); }

export async function confirmPlan() {
  try {
    await apiPost('api/plan/confirm', {});
    if (state.plan) state.plan.meals.forEach(m => m.confirmed = true);
    renderPlan();
    showToast('Wochenplan bestätigt! Einkaufsliste ist bereit.', 'success');
    switchTab('shopping');
  } catch { showToast('Fehler beim Bestätigen.', 'error'); }
}

export async function deletePlan(planId) {
  if (!confirm('Diese Woche wirklich löschen? Deine Vorlieben und der Tausch-Verlauf bleiben erhalten.')) return;
  try {
    await apiDelete(`api/plan/${planId}`);
    state.plan = null;
    await loadAllPlans();
    showToast('Wochenplan gelöscht.', 'success');
    if (state.allPlans.length === 0) {
      document.getElementById('plan-content').innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>Noch kein Wochenplan</p><p class="hint">Nutze den Chat oder klicke "Wochenplan generieren"!</p></div>`;
    }
  } catch { showToast('Fehler beim Löschen.', 'error'); }
}

export function openSwapModal(mealId, mealName) {
  state.swapMealId = mealId;
  state.swapMealName = mealName;
  state.swapReason = null;
  state.swapMode = null;
  state.swapRecipeId = null;
  document.getElementById('swap-meal-name').textContent = mealName;
  document.getElementById('swap-mode-section').classList.remove('hidden');
  document.getElementById('swap-ai-section').classList.add('hidden');
  document.getElementById('swap-recipe-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = 'none';
  document.getElementById('swap-confirm-btn').disabled = true;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('swap-modal').classList.remove('hidden');
}

export function closeSwapModal() { document.getElementById('swap-modal').classList.add('hidden'); }

export function selectSwapMode(mode) {
  state.swapMode = mode;
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
  const recipes = state.userRecipes || [];
  if (!recipes.length) {
    list.innerHTML = '<p class="hint" style="text-align:center;padding:16px 0">Keine eigenen Rezepte vorhanden.<br>Füge zuerst Rezepte unter "📖 Rezepte" hinzu.</p>';
    return;
  }
  list.innerHTML = `<div class="option-group vertical">${recipes.map(ur =>
    `<button class="option-btn" onclick="selectSwapRecipe(${ur.id}, this)">${ur.recipe.name}</button>`
  ).join('')}</div>`;
}

export function selectSwapRecipe(recipeId, btn) {
  state.swapRecipeId = recipeId;
  document.querySelectorAll('#swap-recipe-list .option-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('swap-confirm-btn').disabled = false;
}

export function swapGoBack() {
  state.swapMode = null;
  state.swapReason = null;
  state.swapRecipeId = null;
  document.getElementById('swap-mode-section').classList.remove('hidden');
  document.getElementById('swap-ai-section').classList.add('hidden');
  document.getElementById('swap-recipe-section').classList.add('hidden');
  document.getElementById('swap-back-btn').style.display = 'none';
  document.getElementById('swap-confirm-btn').disabled = true;
  document.querySelectorAll('#swap-reasons .option-btn').forEach(b => b.classList.remove('active'));
}

export async function confirmSwap() {
  if (!state.swapMealId || !state.swapMode) return;
  if (state.swapMode === 'ai' && !state.swapReason) return;
  if (state.swapMode === 'recipe' && !state.swapRecipeId) return;
  const btn = document.getElementById('swap-confirm-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Wird getauscht…';
  try {
    let updated;
    if (state.swapMode === 'ai') {
      updated = await apiPost('api/plan/swap', { meal_id: state.swapMealId, reason: state.swapReason });
    } else {
      updated = await apiPost('api/plan/swap-with-recipe', { meal_id: state.swapMealId, recipe_id: state.swapRecipeId });
    }
    if (state.plan) {
      const idx = state.plan.meals.findIndex(m => m.id === state.swapMealId);
      if (idx !== -1) state.plan.meals[idx] = updated;
    }
    closeSwapModal();
    renderPlan();
    showToast('Rezept wurde ausgetauscht!', 'success');
  } catch { showToast('Fehler beim Tauschen.', 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Tauschen'; }
}
