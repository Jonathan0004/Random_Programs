const state = {
  mode: 'standard',
  current: '0',
  previous: null,
  operator: null,
  justCalculated: false
};

const expressionEl = document.getElementById('expression');
const mainValueEl = document.getElementById('main-value');
const modeLabel = document.getElementById('mode-label');
const modeToggle = document.querySelector('.mode-toggle');
const modeMenu = document.getElementById('mode-menu');
const modeOptions = modeMenu.querySelectorAll('.mode-option');
const calcPanel = document.querySelector('[data-mode-view="standard"]');
const percentPanel = document.querySelector('[data-mode-view="percent"]');
const baseInput = document.getElementById('base-input');
const rateInput = document.getElementById('rate-input');
const percentResult = document.getElementById('percent-result');

const updateDisplay = () => {
  mainValueEl.textContent = state.current;
  const opSymbol = { add: '+', subtract: '−', multiply: '×', divide: '÷' }[state.operator] || '';
  const prevText = state.previous !== null ? `${state.previous} ${opSymbol}` : state.current;
  expressionEl.textContent = prevText || '0';
  modeLabel.textContent = state.mode === 'standard' ? 'Standard' : 'Percent';
  document.body.setAttribute('data-mode', state.mode);
};

const resetCalc = () => {
  state.current = '0';
  state.previous = null;
  state.operator = null;
  state.justCalculated = false;
};

const handleDigit = (digit) => {
  if (state.justCalculated && digit !== '.') {
    state.current = '0';
    state.justCalculated = false;
  }
  if (digit === '.' && state.current.includes('.')) return;
  if (state.current === '0' && digit !== '.') {
    state.current = digit;
  } else {
    state.current += digit;
  }
};

const applyOperator = (op) => {
  if (state.operator && !state.justCalculated) {
    compute();
  }
  state.previous = state.current;
  state.operator = op;
  state.justCalculated = false;
  state.current = '0';
};

const compute = () => {
  if (!state.operator || state.previous === null) return;
  const a = parseFloat(state.previous);
  const b = parseFloat(state.current);
  let result = b;

  switch (state.operator) {
    case 'add':
      result = a + b;
      break;
    case 'subtract':
      result = a - b;
      break;
    case 'multiply':
      result = a * b;
      break;
    case 'divide':
      result = b === 0 ? '∞' : a / b;
      break;
    default:
      break;
  }

  state.current = String(result);
  state.previous = null;
  state.operator = null;
  state.justCalculated = true;
};

const invert = () => {
  if (state.current === '0') return;
  state.current = String(parseFloat(state.current) * -1);
};

const quickPercent = () => {
  state.current = String(parseFloat(state.current || '0') / 100);
};

const toggleMenu = () => {
  const open = modeMenu.classList.toggle('open');
  modeToggle.setAttribute('aria-expanded', open);
};

const setMode = (mode) => {
  state.mode = mode;
  if (mode === 'standard') {
    calcPanel.hidden = false;
    percentPanel.hidden = true;
  } else {
    calcPanel.hidden = true;
    percentPanel.hidden = false;
    baseInput.focus();
  }
  modeMenu.classList.remove('open');
  modeToggle.setAttribute('aria-expanded', 'false');
  updateDisplay();
};

const computePercentResult = () => {
  const base = parseFloat(baseInput.value || '0');
  const rate = parseFloat(rateInput.value || '0');
  const output = (base * rate) / 100;
  percentResult.textContent = `${rate.toFixed(2)}% of ${base.toFixed(2)} = ${output.toFixed(2)}`;
};

document.querySelectorAll('[data-digit]').forEach((btn) => {
  btn.addEventListener('click', () => {
    handleDigit(btn.dataset.digit);
    updateDisplay();
  });
});

document.querySelectorAll('[data-operator]').forEach((btn) => {
  btn.addEventListener('click', () => {
    applyOperator(btn.dataset.operator);
    updateDisplay();
  });
});

document.querySelectorAll('[data-action]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if (action === 'clear') resetCalc();
    if (action === 'invert') invert();
    if (action === 'percent') quickPercent();
    if (action === 'equals') compute();
    updateDisplay();
  });
});

modeToggle.addEventListener('click', toggleMenu);
modeOptions.forEach((option) => {
  option.addEventListener('click', () => setMode(option.dataset.mode));
});

document.addEventListener('click', (event) => {
  if (!modeMenu.contains(event.target) && !modeToggle.contains(event.target)) {
    modeMenu.classList.remove('open');
    modeToggle.setAttribute('aria-expanded', 'false');
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    modeMenu.classList.remove('open');
    modeToggle.setAttribute('aria-expanded', 'false');
  }
});

document.getElementById('compute-percent').addEventListener('click', () => {
  computePercentResult();
});

baseInput.addEventListener('input', computePercentResult);
rateInput.addEventListener('input', computePercentResult);

updateDisplay();
