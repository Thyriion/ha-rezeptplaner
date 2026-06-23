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
  if (cooking.alarmInterval) { stopAlarm(); return; }
  if (cooking.timerRunning) pauseTimer(); else startTimer();
}

function stopAlarm() {
  clearInterval(cooking.alarmInterval);
  cooking.alarmInterval = null;
  document.getElementById('timer-btn').textContent = '↺ Neu starten';
  document.getElementById('timer-btn').classList.remove('alarm-active');
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
      const btn = document.getElementById('timer-btn');
      btn.textContent = '🔔 Alarm stoppen';
      btn.classList.add('alarm-active');
      playTimerSound();
      cooking.alarmInterval = setInterval(playTimerSound, 2500);
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
  if (cooking.alarmInterval) {
    clearInterval(cooking.alarmInterval);
    cooking.alarmInterval = null;
    document.getElementById('timer-btn')?.classList.remove('alarm-active');
  }
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
    function quack(t) {
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const formant = ctx.createBiquadFilter();
      const gain = ctx.createGain();

      osc1.type = 'sawtooth';
      osc1.frequency.setValueAtTime(350, t);
      osc1.frequency.exponentialRampToValueAtTime(200, t + 0.28);

      osc2.type = 'square';
      osc2.frequency.setValueAtTime(175, t);
      osc2.frequency.exponentialRampToValueAtTime(100, t + 0.28);

      formant.type = 'bandpass';
      formant.frequency.value = 1000;
      formant.Q.value = 8;

      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.55, t + 0.03);
      gain.gain.setValueAtTime(0.55, t + 0.14);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.30);

      osc1.connect(formant);
      osc2.connect(formant);
      formant.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(t); osc1.stop(t + 0.30);
      osc2.start(t); osc2.stop(t + 0.30);
    }
    const now = ctx.currentTime;
    quack(now);
    quack(now + 0.45);
    quack(now + 0.85);
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
