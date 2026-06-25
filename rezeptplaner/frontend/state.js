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
  skippedSlot: null,
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
  ingredients: [],
  portionMultiplier: 1,
  // Per-step timer state: { [stepIndex]: { total, remaining, running } }
  stepTimers: {},
  globalTimerInterval: null,
  alarmInterval: null,
  alarmStepIndex: null,
  wakeLock: null,
};

export const DAY_LABELS = {
  monday:'Montag', tuesday:'Dienstag', wednesday:'Mittwoch',
  thursday:'Donnerstag', friday:'Freitag', saturday:'Samstag', sunday:'Sonntag',
};
export const MEAL_LABELS = { lunch:'Mittagessen', dinner:'Abendessen' };
export const DAY_ORDER   = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
export const MEAL_SLOTS  = [
  { day: 'monday',    meal_type: 'dinner' },
  { day: 'tuesday',   meal_type: 'dinner' },
  { day: 'wednesday', meal_type: 'dinner' },
  { day: 'thursday',  meal_type: 'dinner' },
  { day: 'friday',    meal_type: 'dinner' },
  { day: 'saturday',  meal_type: 'lunch'  },
  { day: 'saturday',  meal_type: 'dinner' },
  { day: 'sunday',    meal_type: 'lunch'  },
  { day: 'sunday',    meal_type: 'dinner' },
];
export const CATEGORIES  = [
  'Gemüse & Obst', 'Fleisch & Fisch', 'Milchprodukte & Eier',
  'Getreide & Backwaren', 'Konserven & Trockenwaren', 'Gewürze & Öle', 'Sonstiges',
];
export const CAT_ICONS   = {
  'Gemüse & Obst':'🥦','Fleisch & Fisch':'🥩','Milchprodukte & Eier':'🥛',
  'Getreide & Backwaren':'🌾','Konserven & Trockenwaren':'🥫','Gewürze & Öle':'🫙','Sonstiges':'🛒',
};
