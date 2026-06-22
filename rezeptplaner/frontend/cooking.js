'use strict';

import { cooking, state } from './state.js';
import { showToast } from './app.js';

export function openCooking(mealId) {
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

export function closeCooking() {
  stopTimer();
  document.getElementById('cooking-mode').classList.add('hidden');
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

export function cookingPrev() {
  if (cooking.stepIndex > 0) { cooking.stepIndex--; renderCookingStep(); }
}

export function cookingNext() {
  if (cooking.stepIndex < cooking.steps.length - 1) { cooking.stepIndex++; renderCookingStep(); }
  else closeCooking();
}

export function toggleCookingTimer() {
  if (cooking.timerRunning) pauseTimer(); else startTimer();
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
      playTimerSound();
      showToast('Timer abgelaufen!', 'success');
    }
  }, 1000);
}

function pauseTimer() {
  cooking.timerRunning = false;
  clearInterval(cooking.timerInterval);
  document.getElementById('timer-btn').textContent = '▶ Weiter';
}

export function stopTimer() {
  cooking.timerRunning = false;
  clearInterval(cooking.timerInterval);
  cooking.timerInterval = null;
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

function playTimerSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [[880, 0, 0.15], [880, 0.2, 0.15], [1320, 0.4, 0.6]].forEach(([freq, start, dur]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0.4, ctx.currentTime + start);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
      osc.start(ctx.currentTime + start);
      osc.stop(ctx.currentTime + start + dur);
    });
  } catch { /* Audio nicht verfügbar */ }
}

function updateTimerDisplay() {
  const r = cooking.timerRemaining;
  const m = Math.floor(r / 60), s = r % 60;
  document.getElementById('timer-digits').textContent = `${m}:${s.toString().padStart(2, '0')}`;
  const circumference = 276.46;
  const progress = cooking.timerTotal > 0 ? r / cooking.timerTotal : 0;
  document.getElementById('timer-circle').style.strokeDashoffset = circumference * (1 - progress);
}
