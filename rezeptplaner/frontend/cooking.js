'use strict';

import { cooking, planState } from './state.js';
import { showToast } from './app.js';

export function openCooking(mealId) {
  const meal = planState.plan?.meals.find(m => m.id === mealId);
  if (!meal) return;
  cooking.steps = meal.recipe.steps;
  cooking.recipeName = meal.recipe.name;
  cooking.ingredients = meal.recipe.ingredients;
  cooking.portionMultiplier = meal.portion_multiplier || 1;
  cooking.stepIndex = 0;
  cooking.stepTimers = {};
  cooking.alarmStepIndex = null;
  stopAlarm();
  releaseWakeLock();
  requestWakeLock();
  document.getElementById('cooking-recipe-label').textContent = meal.recipe.name;
  document.getElementById('cooking-mode').classList.remove('hidden');
  renderCookingStep();
}

export function closeCooking() {
  stopAllTimers();
  stopAlarm();
  releaseWakeLock();
  document.getElementById('cooking-mode').classList.add('hidden');
}

function stopAllTimers() {
  if (cooking.globalTimerInterval) {
    clearInterval(cooking.globalTimerInterval);
    cooking.globalTimerInterval = null;
  }
  for (const timer of Object.values(cooking.stepTimers)) {
    timer.running = false;
  }
}

export function renderCookingStep() {
  const i = cooking.stepIndex, steps = cooking.steps, total = steps.length;
  document.getElementById('cooking-step-num').textContent = `Schritt ${i + 1} / ${total}`;
  document.getElementById('cooking-step-text').textContent = steps[i];

  const dots = document.getElementById('cooking-dots');
  dots.innerHTML = steps.map((_, idx) =>
    `<span class="cooking-dot ${idx < i ? 'done' : idx === i ? 'active' : ''}"></span>`
  ).join('');

  document.getElementById('cooking-prev').disabled = i === 0;
  document.getElementById('cooking-next').textContent = i === total - 1 ? '✓ Fertig' : 'Weiter →';

  renderIngredients();

  const secs = parseStepTime(steps[i]);
  const timerSection = document.getElementById('cooking-timer-section');
  if (secs) {
    ensureStepTimer(i, secs);
    timerSection.classList.remove('hidden');
    updateTimerDisplay();
    updateTimerButton();
  } else {
    timerSection.classList.add('hidden');
  }
}

function renderIngredients() {
  const container = document.getElementById('cooking-ingredients');
  if (!container) return;
  const mult = cooking.portionMultiplier || 1;
  const fmt = n => n === Math.floor(n) ? Math.floor(n) : n.toFixed(1).replace(/\.0$/, '');
  container.innerHTML = cooking.ingredients.map(ing => {
    const amount = ing.amount * mult;
    return `<div class="cooking-ingredient"><span>${ing.name}</span><span>${fmt(amount)} ${ing.unit}</span></div>`;
  }).join('');
}

function ensureStepTimer(stepIndex, total) {
  if (!cooking.stepTimers[stepIndex]) {
    cooking.stepTimers[stepIndex] = { total, remaining: total, running: false };
  }
}

export function cookingPrev() {
  if (cooking.stepIndex > 0) { cooking.stepIndex--; renderCookingStep(); }
}

export function cookingNext() {
  if (cooking.stepIndex < cooking.steps.length - 1) { cooking.stepIndex++; renderCookingStep(); }
  else closeCooking();
}

export function toggleCookingTimer() {
  if (cooking.alarmInterval) { stopAlarm(); return; }
  const timer = cooking.stepTimers[cooking.stepIndex];
  if (!timer) return;
  if (timer.running) pauseTimer();
  else startTimer();
}

function startTimer() {
  const timer = cooking.stepTimers[cooking.stepIndex];
  if (!timer) return;
  timer.running = true;
  ensureGlobalTimer();
  updateTimerButton();
}

function pauseTimer() {
  const timer = cooking.stepTimers[cooking.stepIndex];
  if (!timer) return;
  timer.running = false;
  updateTimerButton();
}

export function stopAlarm() {
  clearInterval(cooking.alarmInterval);
  cooking.alarmInterval = null;
  cooking.alarmStepIndex = null;
  updateTimerButton();
  updateAlarmButtonVisibility();
  document.getElementById('timer-btn')?.classList.remove('alarm-active');
}

export function stopCookingAlarm() {
  stopAlarm();
}

function updateAlarmButtonVisibility() {
  const btn = document.getElementById('cooking-stop-alarm');
  if (!btn) return;
  if (cooking.alarmInterval) {
    btn.classList.remove('hidden');
  } else {
    btn.classList.add('hidden');
  }
}

function ensureGlobalTimer() {
  if (cooking.globalTimerInterval) return;
  cooking.globalTimerInterval = setInterval(() => {
    let anyRunning = false;
    for (const [idx, timer] of Object.entries(cooking.stepTimers)) {
      if (!timer.running) continue;
      anyRunning = true;
      timer.remaining = Math.max(0, timer.remaining - 1);
      if (timer.remaining <= 0) {
        timer.running = false;
        triggerAlarm(parseInt(idx));
      }
    }
    if (cooking.stepIndex in cooking.stepTimers) {
      updateTimerDisplay();
      updateTimerButton();
    }
    if (!anyRunning && !cooking.alarmInterval) {
      clearInterval(cooking.globalTimerInterval);
      cooking.globalTimerInterval = null;
    }
  }, 1000);
}

function triggerAlarm(stepIndex) {
  stopAlarm();
  cooking.alarmStepIndex = stepIndex;
  const btn = document.getElementById('timer-btn');
  if (cooking.stepIndex === stepIndex) {
    btn.textContent = '🔔 Alarm stoppen';
    btn.classList.add('alarm-active');
  }
  updateAlarmButtonVisibility();
  playTimerSound();
  cooking.alarmInterval = setInterval(playTimerSound, 2500);
}

function updateTimerButton() {
  const btn = document.getElementById('timer-btn');
  const timer = cooking.stepTimers[cooking.stepIndex];
  if (!timer) return;
  if (cooking.alarmInterval && cooking.alarmStepIndex === cooking.stepIndex) {
    btn.textContent = '🔔 Alarm stoppen';
    btn.classList.add('alarm-active');
  } else if (timer.remaining <= 0) {
    btn.textContent = '↺ Neu starten';
    btn.classList.remove('alarm-active');
  } else if (timer.running) {
    btn.textContent = '⏸ Pausieren';
    btn.classList.remove('alarm-active');
  } else {
    btn.textContent = timer.remaining < timer.total ? '▶ Weiter' : '▶ Timer starten';
    btn.classList.remove('alarm-active');
  }
}

function updateTimerDisplay() {
  const timer = cooking.stepTimers[cooking.stepIndex];
  if (!timer) return;
  const r = timer.remaining;
  const m = Math.floor(r / 60), s = r % 60;
  document.getElementById('timer-digits').textContent = `${m}:${s.toString().padStart(2, '0')}`;
  const circumference = 276.46;
  const progress = timer.total > 0 ? r / timer.total : 0;
  document.getElementById('timer-circle').style.strokeDashoffset = circumference * (1 - progress);
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

let _duckAudio = null;
function playTimerSound() {
  try {
    if (!_duckAudio) _duckAudio = new Audio('duck.mp3');
    _duckAudio.currentTime = 0;
    _duckAudio.play();
  } catch { /* Audio nicht verfügbar */ }
}

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      cooking.wakeLock = await navigator.wakeLock.request('screen');
    }
  } catch { /* Wake Lock nicht verfügbar */ }
}

function releaseWakeLock() {
  if (cooking.wakeLock) {
    try { cooking.wakeLock.release(); } catch { /* ignore */ }
    cooking.wakeLock = null;
  }
}
