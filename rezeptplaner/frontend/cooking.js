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
  cooking.alarmKeys = [];
  stopAlarm();
  releaseWakeLock();
  requestWakeLock();
  document.getElementById('cooking-recipe-label').textContent = meal.recipe.name;
  document.getElementById('cooking-mode').classList.remove('hidden');
  renderCookingStep();
  renderTimerSidebar();
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
  for (const timers of Object.values(cooking.stepTimers)) {
    for (const t of timers) t.running = false;
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

  renderStepIngredients();
  renderStepTimers();
}

function renderStepIngredients() {
  const container = document.getElementById('cooking-ingredients');
  if (!container) return;
  const mult = cooking.portionMultiplier || 1;
  const fmt = n => n === Math.floor(n) ? Math.floor(n) : n.toFixed(1).replace(/\.0$/, '');
  const stepText = cooking.steps[cooking.stepIndex] || '';
  const relevant = getRelevantIngredients(stepText, cooking.ingredients);
  container.innerHTML = relevant.map(ing => {
    const amount = ing.amount * mult;
    return `<div class="cooking-ingredient"><span>${escapeHtml(ing.name)}</span><span>${fmt(amount)} ${escapeHtml(ing.unit)}</span></div>`;
  }).join('');
}

const STOP_WORDS = new Set(['und', 'oder', 'mit', 'in', 'aus', 'von', 'zum', 'zur', 'ca', 'etwa', 'ungefähr', 'ggf', 'nach', 'geschmack', 'z', 'b', 'beispiel']);

function getRelevantIngredients(stepText, allIngredients) {
  if (!stepText || !allIngredients?.length) return [];
  const lowerStep = stepText.toLowerCase();
  const relevant = allIngredients.filter(ing => isIngredientInText(ing.name, lowerStep));
  return relevant.length > 0 ? relevant : allIngredients;
}

function isIngredientInText(ingredientName, lowerStepText) {
  const cleaned = normalizeIngredientName(ingredientName);
  if (!cleaned) return false;

  // 1. Ganze bereinigte Zutat als Phrase mit Wortgrenzen suchen
  try {
    if (new RegExp(`\\b${escapeRegex(cleaned)}\\b`, 'i').test(lowerStepText)) return true;
  } catch { /* ignore */ }

  // 2. Einzelne signifikante Wörter prüfen (erlaubt Plural/Stammform)
  const words = cleaned.split(/\s+/).filter(w => w.length > 3 && !STOP_WORDS.has(w));
  for (const word of words) {
    try {
      if (new RegExp(`\\b${escapeRegex(word)}\\b`, 'i').test(lowerStepText)) return true;
      // Für längere Wörter: Wortanfang im Text akzeptieren (Zwiebel -> Zwiebeln, Zwiebeln,)
      if (word.length >= 5 && new RegExp(`\\b${escapeRegex(word)}`, 'i').test(lowerStepText)) return true;
    } catch { /* ignore */ }
  }
  return false;
}

function normalizeIngredientName(name) {
  return name
    .toLowerCase()
    .replace(/\(.*?\)/g, ' ')
    .replace(/\[.*?\]/g, ' ')
    .replace(/,.*/g, ' ')
    .replace(/\b(ca\.?|etwa|ungefähr|ggf\.?|nach geschmack|z\.b\.?|zum beispiel)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str ?? '');
  return div.innerHTML;
}

function renderStepTimers() {
  const section = document.getElementById('cooking-timer-section');
  const timers = getStepTimers(cooking.stepIndex);
  if (!timers.length) {
    section.classList.add('hidden');
    section.innerHTML = '';
    return;
  }
  section.classList.remove('hidden');
  section.innerHTML = timers.map((t, ti) => {
    const isAlarm = isAlarmKey(cooking.stepIndex, ti);
    const time = formatTime(t.remaining);
    const pct = t.total > 0 ? (t.remaining / t.total) * 100 : 0;
    let btnText, btnClass;
    if (isAlarm) { btnText = '🔔 Alarm stoppen'; btnClass = 'btn-danger alarm-active'; }
    else if (t.remaining <= 0) { btnText = '↺ Neu starten'; btnClass = 'btn-primary'; }
    else if (t.running) { btnText = '⏸ Pausieren'; btnClass = 'btn-primary'; }
    else { btnText = t.remaining < t.total ? '▶ Weiter' : '▶ Timer starten'; btnClass = 'btn-primary'; }
    return `
      <div class="timer-card ${isAlarm ? 'alarm' : ''}" data-step="${cooking.stepIndex}" data-timer="${ti}">
        <div class="timer-card-header">
          <span class="timer-card-label">${escapeHtml(t.label)}</span>
          <span class="timer-card-time">${time}</span>
        </div>
        <div class="timer-card-bar"><div class="timer-card-progress" style="width:${pct}%"></div></div>
        <button class="btn ${btnClass} btn-sm" onclick="toggleCookingTimer(${cooking.stepIndex}, ${ti})">${btnText}</button>
      </div>
    `;
  }).join('');
}

export function toggleCookingTimer(stepIndex, timerIndex) {
  if (typeof stepIndex !== 'number') stepIndex = cooking.stepIndex;
  if (typeof timerIndex !== 'number') timerIndex = 0;
  if (isAlarmKey(stepIndex, timerIndex)) {
    clearAlarmKey(stepIndex, timerIndex);
    return;
  }
  const timer = getTimer(stepIndex, timerIndex);
  if (!timer) return;
  if (timer.running) pauseTimer(stepIndex, timerIndex);
  else startTimer(stepIndex, timerIndex);
}

function getStepTimers(stepIndex) {
  if (!cooking.stepTimers[stepIndex]) {
    const parsed = parseStepTimes(cooking.steps[stepIndex] || '');
    cooking.stepTimers[stepIndex] = parsed.map((p, i) => ({
      id: i,
      label: p.label,
      total: p.seconds,
      remaining: p.seconds,
      running: false,
    }));
  }
  return cooking.stepTimers[stepIndex];
}

function getTimer(stepIndex, timerIndex) {
  return getStepTimers(stepIndex)[timerIndex];
}

function startTimer(stepIndex, timerIndex) {
  const timer = getTimer(stepIndex, timerIndex);
  if (!timer) return;
  if (timer.remaining <= 0) timer.remaining = timer.total;
  timer.running = true;
  ensureGlobalTimer();
  renderStepTimers();
  renderTimerSidebar();
}

function pauseTimer(stepIndex, timerIndex) {
  const timer = getTimer(stepIndex, timerIndex);
  if (!timer) return;
  timer.running = false;
  renderStepTimers();
  renderTimerSidebar();
}

function ensureGlobalTimer() {
  if (cooking.globalTimerInterval) return;
  cooking.globalTimerInterval = setInterval(() => {
    let anyRunning = false;
    for (const [stepIdx, timers] of Object.entries(cooking.stepTimers)) {
      for (const [timerIdx, timer] of timers.entries()) {
        if (!timer.running) continue;
        anyRunning = true;
        timer.remaining = Math.max(0, timer.remaining - 1);
        if (timer.remaining <= 0) {
          timer.running = false;
          triggerAlarm(parseInt(stepIdx), parseInt(timerIdx));
        }
      }
    }
    renderStepTimers();
    renderTimerSidebar();
    if (!anyRunning && !cooking.alarmKeys.length) {
      clearInterval(cooking.globalTimerInterval);
      cooking.globalTimerInterval = null;
    }
  }, 1000);
}

function triggerAlarm(stepIndex, timerIndex) {
  addAlarmKey(stepIndex, timerIndex);
  playTimerSound();
  if (!cooking.alarmInterval) {
    cooking.alarmInterval = setInterval(playTimerSound, 2500);
  }
  renderStepTimers();
  renderTimerSidebar();
}

function addAlarmKey(stepIndex, timerIndex) {
  if (!isAlarmKey(stepIndex, timerIndex)) {
    cooking.alarmKeys.push({ stepIndex, timerIndex });
  }
}

function clearAlarmKey(stepIndex, timerIndex) {
  cooking.alarmKeys = cooking.alarmKeys.filter(
    k => k.stepIndex !== stepIndex || k.timerIndex !== timerIndex
  );
  if (!cooking.alarmKeys.length) stopAlarm();
  else { renderStepTimers(); renderTimerSidebar(); }
}

function isAlarmKey(stepIndex, timerIndex) {
  return cooking.alarmKeys.some(k => k.stepIndex === stepIndex && k.timerIndex === timerIndex);
}

export function stopAlarm() {
  clearInterval(cooking.alarmInterval);
  cooking.alarmInterval = null;
  cooking.alarmKeys = [];
  stopAlarmSound();
  renderStepTimers();
  renderTimerSidebar();
}

export function stopCookingAlarm() {
  stopAlarm();
}

function renderTimerSidebar() {
  const container = document.getElementById('cooking-timer-list');
  if (!container) return;
  const items = [];
  for (const [stepIdx, timers] of Object.entries(cooking.stepTimers)) {
    for (const [timerIdx, timer] of timers.entries()) {
      const si = parseInt(stepIdx), ti = parseInt(timerIdx);
      const wasStarted = timer.running || timer.remaining < timer.total || isAlarmKey(si, ti);
      if (!wasStarted) continue;
      const isAlarm = isAlarmKey(si, ti);
      items.push({ stepIndex: si, timerIndex: ti, timer, isAlarm });
    }
  }
  if (!items.length) {
    container.innerHTML = '<p class="timer-list-empty">Noch keine Timer gestartet</p>';
    return;
  }
  container.innerHTML = items.map(({stepIndex, timerIndex, timer, isAlarm}) => {
    const time = formatTime(timer.remaining);
    const label = timer.label || `Timer ${timerIndex + 1}`;
    const stepLabel = stepIndex === cooking.stepIndex ? 'Aktuell' : `Schritt ${stepIndex + 1}`;
    const btn = isAlarm
      ? `<button class="btn btn-danger btn-xs" onclick="toggleCookingTimer(${stepIndex}, ${timerIndex})">🔔 Stop</button>`
      : timer.running
      ? `<button class="btn btn-ghost btn-xs" onclick="toggleCookingTimer(${stepIndex}, ${timerIndex})">⏸ Pause</button>`
      : timer.remaining <= 0
      ? `<button class="btn btn-primary btn-xs" onclick="toggleCookingTimer(${stepIndex}, ${timerIndex})">↺ Neu</button>`
      : `<button class="btn btn-primary btn-xs" onclick="toggleCookingTimer(${stepIndex}, ${timerIndex})">▶ Weiter</button>`;
    return `
      <div class="timer-list-item ${isAlarm ? 'alarm' : timer.running ? 'running' : ''}">
        <div class="timer-list-meta">
          <span class="timer-list-step">${stepLabel}</span>
          <span class="timer-list-label">${escapeHtml(label)}</span>
        </div>
        <div class="timer-list-row">
          <span class="timer-list-time">${time}</span>
          ${btn}
        </div>
      </div>
    `;
  }).join('');
}

function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60), remS = s % 60;
  const h = Math.floor(m / 60), remM = m % 60;
  if (h > 0) return `${h}:${remM.toString().padStart(2, '0')}:${remS.toString().padStart(2, '0')}`;
  return `${m}:${remS.toString().padStart(2, '0')}`;
}

function parseStepTimes(text) {
  const times = [];
  const regex = /(\d+)\s*(Stunden?|Std|Minuten?|Min|Sekunden?|Sek)/gi;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const n = parseInt(match[1]);
    const unit = match[2].toLowerCase();
    let seconds;
    if (unit.startsWith('st')) seconds = n * 3600;
    else if (unit.startsWith('sek') || unit === 's') seconds = n;
    else seconds = n * 60;
    const before = text.slice(0, match.index);
    const label = extractLabel(before);
    times.push({ label, seconds });
  }
  return times;
}

function extractLabel(before) {
  let label = '';
  const sentenceParts = before.split(/[.!?;]/);
  label = sentenceParts[sentenceParts.length - 1].trim();
  if (!label || label.length > 60) {
    const commaParts = before.split(/,/);
    label = commaParts[commaParts.length - 1].trim();
  }
  label = label.replace(/^[,;\s]+/, '');
  if (!label) return 'Timer';
  return label.length > 42 ? label.slice(0, 42) + '…' : label;
}

export function cookingPrev() {
  if (cooking.stepIndex > 0) {
    cooking.stepIndex--;
    renderCookingStep();
    renderTimerSidebar();
  }
}

export function cookingNext() {
  if (cooking.stepIndex < cooking.steps.length - 1) {
    cooking.stepIndex++;
    renderCookingStep();
    renderTimerSidebar();
  } else {
    closeCooking();
  }
}

let _duckAudio = null;
function playTimerSound() {
  try {
    if (!_duckAudio) _duckAudio = new Audio('duck.mp3');
    _duckAudio.currentTime = 0;
    _duckAudio.play();
  } catch { /* Audio nicht verfügbar */ }
}

function stopAlarmSound() {
  if (!_duckAudio) return;
  try {
    _duckAudio.pause();
    _duckAudio.currentTime = 0;
  } catch { /* ignore */ }
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
