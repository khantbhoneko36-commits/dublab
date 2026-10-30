const $ = (s) => document.querySelector(s);
const drop = $('#drop'), fileInput = $('#file'), preview = $('#preview');
let direction = 'en2mm', voice = 'female', pollTimer = null, lastJid = null;

function selectGrid(gridSel, attr, cb) {
  document.querySelectorAll(gridSel + ' .opt').forEach((b) => {
    b.addEventListener('click', () => {
      document.querySelectorAll(gridSel + ' .opt').forEach((x) => x.classList.remove('selected'));
      b.classList.add('selected');
      cb(b.dataset[attr]);
    });
  });
}
selectGrid('#dirgrid', 'dir', (v) => (direction = v));
selectGrid('#voicegrid', 'voice', (v) => (voice = v));

drop.addEventListener('click', () => fileInput.click());
['dragover', 'dragenter'].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', (ev) => {
  if (ev.dataTransfer.files.length) handleFile(ev.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

function handleFile(f) {
  if (!/^video\//.test(f.type) && !/\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name)) {
    alert('ဗီဒီယိုဖိုင်ပဲ တင်လို့ရတယ်'); return;
  }
  preview.src = URL.createObjectURL(f);
  preview.hidden = false;
  const meta = $('#filemeta');
  meta.hidden = false;
  meta.textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`;
  $('#card-opts').hidden = false;
  drop.querySelector('.drop-title').innerHTML = '✅ ရွေးပြီးပြီ <span class="dim">— ပြောင်းချင်ရင် နှိပ်ပါ</span>';
  $('#card-opts').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

$('#go').addEventListener('click', () => {
  const f = fileInput.files[0];
  if (!f) return;
  const btn = $('#go');
  btn.disabled = true; btn.textContent = '⏳ တင်နေတယ်…';
  const fd = new FormData();
  fd.append('video', f); fd.append('direction', direction); fd.append('voice', voice);
  // NOTE: iOS Safari's fetch() throws "The string did not match the expected
  // pattern" on FormData POST uploads (WebKit bug) — XHR works reliably.
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/jobs');
  xhr.onload = () => {
    btn.disabled = false; btn.textContent = '✨ Dub စလုပ်မယ်';
    try {
      const j = JSON.parse(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300 && j.job_id) showProgress(j.job_id);
      else showError(j.error || 'upload failed');
    } catch (e) { showError('upload failed'); }
  };
  xhr.onerror = () => { btn.disabled = false; btn.textContent = '✨ Dub စလုပ်မယ်'; showError('upload failed'); };
  xhr.send(fd);
});

function showProgress(jid) {
  ['card-upload', 'card-opts', 'card-result', 'card-error'].forEach((id) => ($('#' + id).hidden = true));
  $('#card-progress').hidden = false;
  $('#card-progress').scrollIntoView({ behavior: 'smooth' });
  const order = ['audio', 'transcribe', 'translate', 'voice', 'mux'];
  const stopLog = startLiveLog(jid);
  const stopAll = () => { clearInterval(pollTimer); stopLog(); };
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/jobs/' + jid);
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'status failed');
      $('#barfill').style.width = j.pct + '%';
      $('#stagelabel').textContent = j.label + (j.pct ? ` · ${j.pct}%` : '');
      document.querySelectorAll('#stages li').forEach((li) => {
        const s = li.dataset.s;
        li.classList.remove('active', 'done');
        if (j.stage === 'done' || order.indexOf(s) < order.indexOf(j.stage)) li.classList.add('done');
        else if (s === j.stage) li.classList.add('active');
      });
      if (j.status === 'done') { stopAll(); showResult(jid); }
      if (j.status === 'failed') { stopAll(); showError(j.error || 'အမှားရှိတယ်'); }
    } catch (e) { stopAll(); showError(e.message); }
  }, 2000);
}

// Live job logs — polls /api/jobs/<jid>/log, auto-scrolls.
function startLiveLog(jid) {
  const pre = $('#livelog');
  pre.textContent = '';
  const t = setInterval(async () => {
    try {
      const r = await fetch('/api/jobs/' + jid + '/log');
      const j = await r.json();
      if (r.ok && typeof j.log === 'string' && j.log !== pre.textContent) {
        pre.textContent = j.log;
        pre.scrollTop = pre.scrollHeight;
      }
    } catch (e) { /* keep old content */ }
  }, 2000);
  return () => clearInterval(t);
}

function showResult(jid) {
  $('#card-progress').hidden = true;
  $('#card-result').hidden = false;
  lastJid = jid;
  $('#resultvideo').src = '/r/' + jid;
  setSpeed(1);
  $('#download').href = '/r/' + jid;
  $('#card-result').scrollIntoView({ behavior: 'smooth' });
}

function showError(msg) {
  if (pollTimer) clearInterval(pollTimer);
  ['card-upload', 'card-opts', 'card-progress', 'card-result'].forEach((id) => ($('#' + id).hidden = true));
  $('#card-error').hidden = false;
  $('#errmsg').textContent = msg;
}

$('#again').addEventListener('click', () => location.reload());
$('#retry').addEventListener('click', () => location.reload());

// ---- reviews ----
function makeStars(id) {
  const el = document.getElementById(id);
  let val = 0;
  const btns = el.querySelectorAll('button');
  btns.forEach((b) => b.addEventListener('click', () => {
    val = +b.dataset.s;
    btns.forEach((x) => (x.textContent = +x.dataset.s <= val ? '⭐' : '☆'));
  }));
  return {
    get: () => val,
    reset: () => { val = 0; btns.forEach((x) => (x.textContent = '☆')); },
  };
}
const rstars = makeStars('rstars'), fstars = makeStars('fstars');

function postReview(stars, msgEl, jid, doneEl, starsObj) {
  const msg = msgEl.value.trim();
  if (!stars && !msg) { alert('star ဒါမှမဟုတ် စာတစ်ခုခု ပေးပါ'); return; }
  const xhr = new XMLHttpRequest();  // XHR, not fetch (iOS Safari FormData/POST bug)
  xhr.open('POST', '/api/reviews');
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = () => {
    let ok = false, err = '';
    try { const j = JSON.parse(xhr.responseText); ok = xhr.status < 300 && !!j.ok; err = j.error || ''; }
    catch (e) { /* ignore */ }
    if (ok) {
      doneEl.hidden = false;
      msgEl.value = ''; starsObj.reset();
      setTimeout(() => (doneEl.hidden = true), 4000);
    } else if (err) alert(err);
    else alert('ပို့မရဘူး');
  };
  xhr.onerror = () => alert('ပို့မရဘူး');
  xhr.send(JSON.stringify({ stars: stars, message: msg, job_id: jid || '' }));
}
$('#rsend').addEventListener('click', () =>
  postReview(rstars.get(), $('#rmsg'), lastJid, $('#rdone'), rstars));
$('#fsend').addEventListener('click', () =>
  postReview(fstars.get(), $('#fmsg'), null, $('#fdone'), fstars));

// ---- playback speed (review request: အနှေး/အမြန်) ----
function setSpeed(r) {
  const v = $('#resultvideo');
  if (v) v.playbackRate = r;
  const slider = $('#speedslider'), val = $('#speedval');
  if (slider) slider.value = r;
  if (val) val.textContent = r.toFixed(2) + 'x';
  document.querySelectorAll('#speedrow button').forEach((x) =>
    x.classList.toggle('on', parseFloat(x.dataset.r) === r));
}
document.querySelectorAll('#speedrow button').forEach((b) => b.addEventListener('click', () => {
  setSpeed(parseFloat(b.dataset.r));
}));
(function () {
  const slider = $('#speedslider');
  if (slider) slider.addEventListener('input', () => setSpeed(parseFloat(slider.value)));
})();

// ---- update notice box (show once per device) ----
(function () {
  const KEY = 'dublab_notice_karaoke_v1';
  const notice = $('#updatenotice');
  if (!notice) return;
  let seen = false;
  try { seen = localStorage.getItem(KEY) === '1'; } catch (e) { /* private mode */ }
  if (!seen) notice.hidden = false;
  const okBtn = $('#noticeok');
  if (okBtn) okBtn.addEventListener('click', () => {
    try { if ($('#noshowagain') && $('#noshowagain').checked) localStorage.setItem(KEY, '1'); } catch (e) {}
    notice.hidden = true;
  });
})();

// ---- tabs: Dubbing / SRT translator ----
(function () {
  const tabs = document.querySelectorAll('#tabs .tab');
  if (!tabs.length) return;
  const panels = { dub: document.getElementById('tab-dub'), srt: document.getElementById('tab-srt') };
  tabs.forEach(btn => btn.addEventListener('click', () => {
    tabs.forEach(b => b.classList.toggle('on', b === btn));
    const name = btn.dataset.tab;
    if (panels.dub) panels.dub.hidden = name !== 'dub';
    if (panels.srt) panels.srt.hidden = name !== 'srt';
  }));
})();
