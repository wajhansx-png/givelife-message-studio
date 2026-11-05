'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  let key = localStorage.getItem('givelife-cloud-key') || '',
    data = null,
    timer = null;
  const say = (text, bad) => {
    const f = $('feedback');
    f.textContent = text || '';
    f.classList.toggle('error', !!bad);
  };
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  async function call(method, body) {
    const r = await fetch('/api/case-plan', {
      method,
      cache: 'no-store',
      headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = await r.json().catch(() => ({}));
    if (r.status === 401) {
      askKey();
      throw new Error('Enter your access key.');
    }
    if (!r.ok) throw new Error(j.error || 'Something went wrong. Nothing was changed.');
    return j;
  }
  function askKey() {
    const d = $('accessDialog');
    if (!d.open) d.showModal();
  }
  const STATE = {
    draft: [
      'Waiting for your approval',
      'Read both messages below. Nothing is sent until you approve.',
    ],
    ready: ['Approved', 'Starting the right message now.'],
    normal: ['Running: Normal message', ''],
    slow: [
      'Running: Slow message',
      'Urdu hook and hadith. GiveLife every 15 min, freelance every 30 min.',
    ],
    done: ['Done', 'Nothing is left to collect.'],
    stopped: ['Stopped', ''],
  };
  function render(d) {
    data = d;
    const p = d.plan;
    const st = p ? p.state : 'none';
    const [title, note] = STATE[st] || ['No case plan yet', 'Type the case facts to start.'];
    $('planState').textContent = title;
    const bits = [];
    if (p && p.state === 'stopped' && p.reason) bits.push(p.reason);
    else if (note) bits.push(note);
    bits.push('Rs. ' + d.left.toLocaleString('en-US') + ' left');
    if (p && ['ready', 'normal', 'slow'].includes(p.state)) {
      bits.push(
        d.in_work_hours
          ? 'Sending hours: open now'
          : 'Outside sending hours (' + d.work_hours + ')',
      );
      if (!d.auto_on) bits.push('Auto is OFF: turn it on in the studio to send');
    }
    if (d.team_alerts) bits.push(d.team_alerts + ' team member(s) get alerts');
    $('planDetail').textContent = bits.join(' · ');
    $('factsForm').hidden = !(st === 'none' || st === 'done' || st === 'stopped');
    $('approve').hidden = st !== 'draft';
    $('resume').hidden = st !== 'stopped';
    $('stop').hidden = !['ready', 'normal', 'slow'].includes(st);
    $('clear').hidden = !['draft', 'stopped', 'done'].includes(st);
    $('actions').hidden =
      $('approve').hidden && $('resume').hidden && $('stop').hidden && $('clear').hidden;
    const box = $('messages');
    box.textContent = '';
    for (const mode of ['normal', 'slow']) {
      const c = d.checks[mode];
      if (!c) continue;
      const card = el('article', undefined, 'msg');
      card.append(el('h2', mode === 'normal' ? 'Normal message' : 'Slow-donations message'));
      if (p.state === mode) card.append(el('p', 'Sending this one now', 'now'));
      card.append(el('pre', c.text));
      if (c.problems.length) {
        const ul = el('ul');
        c.problems.forEach((t) => ul.append(el('li', t)));
        card.append(ul);
      } else card.append(el('p', '✓ Passes every PDF check', 'ok'));
      box.append(card);
    }
    $('preview').hidden = !box.children.length;
    $('planNote').textContent = d.rounding || '';
    $('planNote').hidden = !d.rounding || !box.children.length;
    $('approve').disabled = !!(
      p &&
      p.state === 'draft' &&
      Object.values(d.checks).some((c) => c.problems.length)
    );
  }
  async function load() {
    if (!key) return askKey();
    try {
      render(await call('GET'));
      say('');
    } catch (e) {
      say(e.message, true);
    }
  }
  async function act(action, extra) {
    const buttons = document.querySelectorAll('button');
    buttons.forEach((b) => (b.disabled = true));
    try {
      render(await call('POST', { action, ...extra }));
      say(
        {
          create: 'Messages made. Read them, then approve.',
          approve: 'Approved. The app now follows the plan.',
          stop: 'Stopped. Nothing more will be sent from this plan.',
          resume: 'Resumed.',
          clear: 'Ready for a new case.',
        }[action],
      );
    } catch (e) {
      say(e.message, true);
    } finally {
      buttons.forEach((b) => (b.disabled = false));
      if (data) render(data);
    }
  }
  $('factsForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    act('create', { facts: f });
  });
  $('approve').onclick = () => act('approve');
  $('stop').onclick = () => confirm('Stop sending for this case?') && act('stop');
  $('resume').onclick = () => act('resume');
  $('clear').onclick = () => act('clear');
  $('accessForm').addEventListener('submit', (e) => {
    e.preventDefault();
    key = $('accessKey').value.trim();
    localStorage.setItem('givelife-cloud-key', key);
    $('accessDialog').close();
    load();
  });
  load();
  timer = setInterval(() => {
    if (!document.hidden && !document.querySelector('#factsForm :focus')) load();
  }, 30000);
})();
