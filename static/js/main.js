// ── Modal ─────────────────────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.classList.add('open'); document.body.style.overflow = 'hidden'; }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) { el.classList.remove('open'); document.body.style.overflow = ''; }
}

document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => {
      m.classList.remove('open');
      document.body.style.overflow = '';
    });
  }
});

// ── Toast ─────────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info' };
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i> ${message}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'opacity .3s, transform .3s';
    setTimeout(() => toast.remove(), 350);
  }, 3000);
}

// ── API wrapper ───────────────────────────────────────────────────────
async function apiCall(url, method = 'GET', data = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (data) opts.body = JSON.stringify(data);
    const res = await fetch(url, opts);
    return await res.json();
  } catch (err) {
    console.error('API error:', err);
    return { error: 'Network error — please try again.' };
  }
}

// ── Form helpers ──────────────────────────────────────────────────────
function showError(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('show');
  const input = el.previousElementSibling;
  if (input?.classList.contains('form-control')) {
    input.classList.add('error');
    input.addEventListener('input', () => {
      el.classList.remove('show');
      input.classList.remove('error');
    }, { once: true });
  }
}

function clearErrors(ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('show');
    el.previousElementSibling?.classList.remove('error');
  });
}

// ── Counter animation ─────────────────────────────────────────────────
function animateCounter(el) {
  const original = el.textContent.trim();
  const hasDollar  = original.startsWith('$');
  const numStr     = original.replace(/[^0-9.]/g, '');
  const target     = parseFloat(numStr);
  if (isNaN(target) || target === 0) return;

  const duration = 900;
  const start    = performance.now();

  function tick(now) {
    const elapsed  = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // ease-out cubic
    const eased    = 1 - Math.pow(1 - progress, 3);
    const current  = target * eased;

    const formatted = Number.isInteger(target)
      ? Math.round(current).toLocaleString()
      : Math.round(current).toLocaleString();

    el.textContent = (hasDollar ? '$' : '') + formatted;

    if (progress < 1) {
      requestAnimationFrame(tick);
    } else {
      el.textContent = original;
      // subtle pop on finish
      el.classList.add('pop');
      el.addEventListener('animationend', () => el.classList.remove('pop'), { once: true });
    }
  }

  requestAnimationFrame(tick);
}

// ── Staggered table row reveal ────────────────────────────────────────
function animateTableRows() {
  document.querySelectorAll('tbody tr').forEach((row, i) => {
    row.style.opacity = '0';
    row.style.transform = 'translateY(8px)';
    setTimeout(() => {
      row.style.opacity   = '';
      row.style.transform = '';
    }, 60 + i * 35);
  });
}

// ── Progress bar fill ─────────────────────────────────────────────────
function animateProgressBars() {
  document.querySelectorAll('.progress-bar').forEach(bar => {
    const targetWidth = bar.style.width;
    bar.style.width = '0%';
    // let CSS animation handle it via transform, restore width for layout
    requestAnimationFrame(() => {
      bar.style.width = targetWidth;
    });
  });
}

// ── Button ripple ─────────────────────────────────────────────────────
function addRipple(e) {
  const btn  = e.currentTarget;
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const x    = e.clientX - rect.left - size / 2;
  const y    = e.clientY - rect.top  - size / 2;

  const ripple = document.createElement('span');
  ripple.style.cssText = `
    position:absolute; border-radius:50%; pointer-events:none;
    width:${size}px; height:${size}px;
    left:${x}px; top:${y}px;
    background:rgba(255,255,255,0.12);
    transform:scale(0); animation:rippleAnim 0.5s ease-out forwards;
  `;
  btn.style.position = 'relative';
  btn.style.overflow = 'hidden';
  btn.appendChild(ripple);
  ripple.addEventListener('animationend', () => ripple.remove());
}

// ── Number format helper ──────────────────────────────────────────────
function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 0 });
}

// ── Init on page load ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Animate stat counters
  document.querySelectorAll('.stat-value').forEach(el => {
    // small delay so entrance animation plays first
    setTimeout(() => animateCounter(el), 350);
  });

  // Stagger table rows
  animateTableRows();

  // Animate progress bars
  animateProgressBars();

  // Add ripple to all primary/ghost buttons
  document.querySelectorAll('.btn-primary, .btn-ghost, .btn-success').forEach(btn => {
    btn.addEventListener('click', addRipple);
  });
});

// Inject ripple keyframe once
const rippleStyle = document.createElement('style');
rippleStyle.textContent = `
  @keyframes rippleAnim {
    to { transform: scale(2.5); opacity: 0; }
  }
`;
document.head.appendChild(rippleStyle);
