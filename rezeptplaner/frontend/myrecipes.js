'use strict';

import { apiGet, apiPost, apiDelete } from './api.js';
import { state, CATEGORIES } from './state.js';
import { showToast } from './app.js';

export async function loadUserRecipes() {
  try {
    state.userRecipes = await apiGet('api/user-recipes');
    renderUserRecipes();
  } catch { /* silent */ }
}

export function renderUserRecipes() {
  const container = document.getElementById('myrecipes-content');
  if (!state.userRecipes?.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📖</div><p>Noch keine eigenen Rezepte</p><p class="hint">Füge deine Lieblingsrezepte hinzu!</p></div>`;
    return;
  }
  container.innerHTML = state.userRecipes.map(ur => renderUserRecipeCard(ur)).join('');
}

function renderUserRecipeCard(ur) {
  const r = ur.recipe;
  const n = r.nutrition_per_serving;
  const amt = i => `${i.amount === Math.floor(i.amount) ? Math.floor(i.amount) : i.amount} ${i.unit}`;
  return `<div class="plan-day">
    <div class="plan-meal" id="ur-${ur.id}">
      <div class="plan-meal-header" onclick="toggleUserRecipe(${ur.id})">
        <span class="meal-name">${r.name}</span>
        <span class="meal-time">⏱ ${r.cooking_time_minutes} Min · ${r.servings} Port.</span>
        <div class="meal-actions">
          <button class="btn-swap" onclick="event.stopPropagation(); deleteUserRecipeById(${ur.id})">🗑 Löschen</button>
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
    </div>
  </div>`;
}

export function toggleUserRecipe(id) {
  document.getElementById(`ur-${id}`)?.classList.toggle('open');
}

export function openRecipeForm() {
  document.getElementById('rf-name').value = '';
  document.getElementById('rf-time').value = '30';
  document.getElementById('rf-servings').value = '2';
  document.getElementById('rf-ingredients-list').innerHTML = '';
  document.getElementById('rf-steps-list').innerHTML = '';
  document.getElementById('rf-cal').value = '';
  document.getElementById('rf-protein').value = '';
  document.getElementById('rf-carbs').value = '';
  document.getElementById('rf-fat').value = '';
  addIngredientRow();
  addStepRow();
  document.getElementById('recipe-form-modal').classList.remove('hidden');
}

export function closeRecipeForm() {
  document.getElementById('recipe-form-modal').classList.add('hidden');
}

export function addIngredientRow() {
  const list = document.getElementById('rf-ingredients-list');
  const catOptions = CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('');
  const row = document.createElement('div');
  row.className = 'ingredient-row';
  row.innerHTML = `
    <input type="text" class="text-input ing-name" placeholder="Zutat">
    <input type="number" class="text-input ing-amount" placeholder="Menge" min="0" step="0.1">
    <input type="text" class="text-input ing-unit" placeholder="Einheit">
    <select class="text-input ing-cat">${catOptions}</select>
    <button type="button" class="remove-btn" onclick="this.closest('.ingredient-row').remove()">×</button>
  `;
  list.appendChild(row);
}

export function addStepRow() {
  const list = document.getElementById('rf-steps-list');
  const num = list.children.length + 1;
  const row = document.createElement('div');
  row.className = 'step-row';
  row.innerHTML = `
    <textarea class="text-input step-text" rows="2" placeholder="Schritt ${num}…"></textarea>
    <button type="button" class="remove-btn" onclick="this.closest('.step-row').remove()">×</button>
  `;
  list.appendChild(row);
}

export async function saveUserRecipe() {
  const name = document.getElementById('rf-name').value.trim();
  if (!name) { showToast('Bitte Rezeptname eingeben.', 'error'); return; }

  const ingredients = [...document.querySelectorAll('#rf-ingredients-list .ingredient-row')].map(row => ({
    name: row.querySelector('.ing-name').value.trim(),
    amount: parseFloat(row.querySelector('.ing-amount').value) || 0,
    unit: row.querySelector('.ing-unit').value.trim() || 'Stück',
    category: row.querySelector('.ing-cat').value,
  })).filter(i => i.name);

  if (!ingredients.length) { showToast('Bitte mindestens eine Zutat angeben.', 'error'); return; }

  const steps = [...document.querySelectorAll('#rf-steps-list .step-text')]
    .map(t => t.value.trim()).filter(Boolean);
  if (!steps.length) { showToast('Bitte mindestens einen Schritt angeben.', 'error'); return; }

  const recipe = {
    name,
    cooking_time_minutes: parseInt(document.getElementById('rf-time').value) || 30,
    servings: parseInt(document.getElementById('rf-servings').value) || 2,
    ingredients,
    steps,
    nutrition_per_serving: {
      calories: parseInt(document.getElementById('rf-cal').value) || 0,
      protein_g: parseFloat(document.getElementById('rf-protein').value) || 0,
      carbs_g: parseFloat(document.getElementById('rf-carbs').value) || 0,
      fat_g: parseFloat(document.getElementById('rf-fat').value) || 0,
    },
  };

  try {
    const saved = await apiPost('api/user-recipes', recipe);
    state.userRecipes = [saved, ...(state.userRecipes || [])];
    renderUserRecipes();
    closeRecipeForm();
    showToast('Rezept gespeichert!', 'success');
  } catch { showToast('Fehler beim Speichern.', 'error'); }
}

export async function deleteUserRecipeById(id) {
  if (!confirm('Rezept wirklich löschen?')) return;
  try {
    await apiDelete(`api/user-recipes/${id}`);
    state.userRecipes = state.userRecipes.filter(r => r.id !== id);
    renderUserRecipes();
    showToast('Rezept gelöscht.', 'success');
  } catch { showToast('Fehler beim Löschen.', 'error'); }
}
