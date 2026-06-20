'use strict';

import { apiGet } from './api.js';
import { state } from './state.js';
import { loadAllPlans, loadRatings, updatePlanNav, navigatePlan, renderPlan,
         toggleMeal, confirmPlan, deletePlan,
         openSwapModal, closeSwapModal, confirmSwap,
         rateMeal } from './plan.js';
import { openCooking, closeCooking, cookingPrev, cookingNext,
         toggleCookingTimer } from './cooking.js';
import { loadShopping, toggleCheck, pushToHA } from './shopping.js';
import { sendChat, chatKeydown, quickGeneratePlan, quickSingleRecipe,
         appendMsg, openAddToPlanModal, closeAddToPlanModal,
         confirmAddToPlan, checkAddToPlanReady } from './chat.js';
import { showWizard, updateWizardStep, wizardBack, wizardNext, adjustPersons,
         openSettings, closeSettings, saveSettings, adjustSettingsPersons,
         addTag, removeTag, tagKeydown } from './settings.js';

// ── Toast ─────────────────────────────────────────────────────────

export function showToast(msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

// ── Tabs ──────────────────────────────────────────────────────────

export function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab)
  );
  document.querySelectorAll('.tab-content').forEach(s =>
    s.classList.toggle('active', s.id === `tab-${tab}`)
  );
  if (tab === 'shopping') loadShopping();
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  try {
    const s = await apiGet('api/settings');
    if (!s || s.persons === undefined) { showWizard(); return; }
    state.settings = s;
    document.getElementById('app').classList.remove('hidden');
    await Promise.all([loadAllPlans(), loadRatings()]);
  } catch {
    document.getElementById('app').classList.remove('hidden');
    appendMsg('assistant', 'Fehler beim Laden. Bitte prüfe ob das Backend läuft.');
  }
}

// ── Expose to HTML inline handlers ────────────────────────────────

Object.assign(window, {
  // tabs
  switchTab,
  // plan
  navigatePlan, toggleMeal, confirmPlan, deletePlan,
  openSwapModal, closeSwapModal, confirmSwap, rateMeal,
  // cooking
  openCooking, closeCooking, cookingPrev, cookingNext, toggleCookingTimer,
  // shopping
  toggleCheck, pushToHA,
  // chat
  sendChat, chatKeydown, quickGeneratePlan, quickSingleRecipe,
  openAddToPlanModal, closeAddToPlanModal, confirmAddToPlan,
  // settings
  showWizard, wizardBack, wizardNext, adjustPersons,
  openSettings, closeSettings, saveSettings, adjustSettingsPersons,
  addTag, removeTag, tagKeydown,
});

// ── DOM Wiring ────────────────────────────────────────────────────

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

  // Add-to-plan day selection
  document.querySelectorAll('#add-day-options .option-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('#add-day-options .option-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.addDay = btn.dataset.value;
      checkAddToPlanReady();
    })
  );

  // Add-to-plan meal type selection
  document.querySelectorAll('#add-meal-type-options .option-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('#add-meal-type-options .option-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.addMealType = btn.dataset.value;
      checkAddToPlanReady();
    })
  );

  init();
});
