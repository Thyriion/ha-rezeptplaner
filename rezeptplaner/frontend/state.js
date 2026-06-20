'use strict';

export const state = {
  settings: null,
  allPlans: [],
  currentPlanIdx: 0,
  plan: null,
  ratings: {},
  swapMealId: null,
  swapMealName: null,
  swapReason: null,
  pendingSingleRecipe: null,
  addDay: null,
  addMealType: null,
  wizardStep: 1,
  wizardData: {
    persons: 2, diet_types: [], disliked_foods: [],
    favorite_foods: [], max_cooking_time: 30, budget: 'mittel',
  },
};

export const cooking = {
  steps: [],
  stepIndex: 0,
  recipeName: '',
  timerTotal: 0,
  timerRemaining: 0,
  timerInterval: null,
  timerRunning: false,
};

export const DAY_LABELS = {
  monday:'Montag', tuesday:'Dienstag', wednesday:'Mittwoch',
  thursday:'Donnerstag', friday:'Freitag', saturday:'Samstag', sunday:'Sonntag',
};
export const MEAL_LABELS = { lunch:'Mittagessen', dinner:'Abendessen' };
export const DAY_ORDER   = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
export const CAT_ICONS   = {
  'Gemüse & Obst':'🥦','Fleisch & Fisch':'🥩','Milchprodukte & Eier':'🥛',
  'Getreide & Backwaren':'🌾','Konserven & Trockenwaren':'🥫','Gewürze & Öle':'🫙','Sonstiges':'🛒',
};
