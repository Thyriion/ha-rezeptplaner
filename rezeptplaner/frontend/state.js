'use strict';

export const planState = {
  settings: null,
  allPlans: [],
  currentPlanIdx: 0,
  plan: null,
  ratings: {},
};

export const swapState = {
  mealId: null,
  mealName: null,
  reason: null,
  mode: null,
  recipeId: null,
};

export const wizardState = {
  step: 1,
  data: {
    persons: 2, diet_types: [], disliked_foods: [],
    favorite_foods: [], max_cooking_time: 30, budget: 'mittel',
    likes_spicy: false,
  },
};

export const recipeState = {
  userRecipes: [],
  pending: null,
  addDay: null,
  addMealType: null,
};

export const cooking = {
  steps: [],
  stepIndex: 0,
  recipeName: '',
  timerTotal: 0,
  timerRemaining: 0,
  timerInterval: null,
  timerRunning: false,
  alarmInterval: null,
};

export const DAY_LABELS = {
  monday:'Montag', tuesday:'Dienstag', wednesday:'Mittwoch',
  thursday:'Donnerstag', friday:'Freitag', saturday:'Samstag', sunday:'Sonntag',
};
export const MEAL_LABELS = { lunch:'Mittagessen', dinner:'Abendessen' };
export const DAY_ORDER   = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
export const CATEGORIES  = [
  'Gemüse & Obst', 'Fleisch & Fisch', 'Milchprodukte & Eier',
  'Getreide & Backwaren', 'Konserven & Trockenwaren', 'Gewürze & Öle', 'Sonstiges',
];
export const CAT_ICONS   = {
  'Gemüse & Obst':'🥦','Fleisch & Fisch':'🥩','Milchprodukte & Eier':'🥛',
  'Getreide & Backwaren':'🌾','Konserven & Trockenwaren':'🥫','Gewürze & Öle':'🫙','Sonstiges':'🛒',
};
