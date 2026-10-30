/* DubLab reviews dashboard */
const key = new URLSearchParams(location.search).get('key') || '';
let allReviews = [];
let filter = 'all';

const $ = (s) => document.querySelector(s);

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function load() {
  try {
    const r = await fetch('/admin/api/reviews?key=' + encodeURIComponent(key));
    if (!r.ok) { $('#list').innerHTML = '<p class="empty">not found</p>'; return; }
    const j = await r.json();
    allReviews = j.reviews || [];
    renderStats(j.stats || {});
    renderList();
  } catch (e) {
    $('#list').innerHTML = '<p class="empty">load failed</p>';
  }
}

function renderStats(s) {
  $('#st-total').textContent = s.total ?? 0;
  $('#st-avg').textContent = s.avg ?? '–';
  $('#st-5').textContent = (s.dist && s.dist['5']) ?? 0;
  const dist = $('#dist');
  dist.innerHTML = '';
  const max = Math.max(1, ...[1, 2, 3, 4, 5].map((i) => (s.dist && s.dist[String(i)]) || 0));
  for (let i = 5; i >= 1; i--) {
    const c = (s.dist && s.dist[String(i)]) || 0;
    const row = document.createElement('div');
    row.className = 'drow';
    row.innerHTML = `<span class="lbl">⭐${i}</span><div class="dbar"><span style="width:${(c / max) * 100}%"></span></div><span class="cnt">${c}</span>`;
    dist.appendChild(row);
  }
}

function renderList() {
  const list = $('#list');
  const rows = allReviews.filter((r) => {
    if (filter === 'all') return true;
    if (filter === 'msg') return (r.message || '').trim().length > 0;
    return r.stars === +filter;
  });
  if (!rows.length) { list.innerHTML = '<p class="empty">မရှိသေးဘူး</p>'; return; }
  list.innerHTML = '';
  rows.forEach((r) => {
    const el = document.createElement('div');
    el.className = 'rev';
    const stars = r.stars ? '⭐'.repeat(r.stars) : '<span style="color:var(--dim)">no rating</span>';
    el.innerHTML =
      `<div class="meta"><span>${esc(fmtTime(r.ts))} · ${esc(r.ip || '?')}${r.job_id ? ' · job ' + esc(r.job_id) : ''}</span>` +
      `<button class="del" title="delete">🗑️</button></div>` +
      `<div class="stars">${stars}</div>` +
      `<div class="msg">${esc(r.message || '—')}</div>`;
    el.querySelector('.del').addEventListener('click', async () => {
      if (!confirm('ဒီ review ကို ဖျက်မလား?')) return;
      try {
        const dr = await fetch('/admin/api/reviews/' + encodeURIComponent(r.id || '') +
          '?key=' + encodeURIComponent(key), { method: 'DELETE' });
        if (dr.ok) load();
      } catch (e) { /* ignore */ }
    });
    list.appendChild(el);
  });
}

$('#filters').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
  $('#filters').querySelectorAll('button').forEach((x) => x.classList.remove('on'));
  b.classList.add('on');
  filter = b.dataset.f;
  renderList();
}));
$('#refresh').addEventListener('click', load);

load();
setInterval(() => { if (!document.hidden) load(); }, 30000);
