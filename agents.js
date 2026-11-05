(() => {
  const $ = (id) => document.getElementById(id);
  const C = { Active: '#10a37f', Working: '#e8b04a', Idle: '#8f8f8f', Error: '#ef6b6b' };
  let key = localStorage.getItem('givelife-cloud-key') || '',
    data = null,
    pick = localStorage.getItem('givelife-agent') || 'auto',
    fixing = null;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  async function call(method, body) {
    const r = await fetch('/api/agents', {
      method,
      headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401) {
      $('accessDialog').showModal();
      throw new Error('Enter your access key.');
    }
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Something went wrong.');
    return d;
  }
  const say = (t, bad) => {
    $('msg').textContent = t || '';
    $('msg').className = 'msg' + (bad ? ' bad' : '');
  };
  const clock = (t) =>
    t ? new Date(t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
  function render() {
    if (!data) return;
    const a = data.agents.find((x) => x.id === pick) || data.agents[0];
    pick = a.id;
    $('list').replaceChildren(
      ...data.agents.map((x) => {
        const b = el('button', 'agent');
        b.type = 'button';
        b.setAttribute('aria-current', String(x.id === a.id));
        b.append(el('span', 'dot ' + x.status));
        const t = el('span', '', x.name);
        t.append(el('small', '', x.status + ' · ' + x.now));
        b.append(t);
        b.onclick = () => {
          pick = x.id;
          localStorage.setItem('givelife-agent', pick);
          render();
        };
        return b;
      }),
    );
    $('name').textContent = a.name;
    $('pill').textContent = a.status;
    $('pill').style.background = C[a.status];
    $('now').textContent = a.now;
    $('role').textContent = a.role;
    const p = a.progress || {};
    $('pLabel').textContent = p.label || '';
    $('pText').textContent = p.max ? `${p.value} / ${p.max}` : String(p.value ?? '');
    $('pBar').style.width =
      (p.max ? Math.min(100, (100 * p.value) / p.max) : p.value ? 100 : 0) + '%';
    $('pBar').style.background = C[a.status];
    $('facts').replaceChildren(...a.facts.map((f) => el('li', '', f)));
    $('errors').replaceChildren(
      ...a.errors.map((e) => {
        const box = el('div', e.info ? 'err info' : 'err');
        box.append(el('b', '', e.text), el('span', '', e.fix));
        if (e.action) {
          const b = el(
            'button',
            '',
            e.action === 'open_home' ? 'Open main page' : e.info ? 'Turn on' : 'Fix now',
          );
          b.type = 'button';
          b.onclick = () =>
            e.action === 'open_home' ? (location.href = '/') : act({ action: e.action });
          box.append(b);
        }
        return box;
      }),
    );
    const own = a.id === 'auto' ? data.rules : [];
    $('rules').hidden = !own.length;
    $('ruleList').replaceChildren(
      ...own.map((r) => {
        const li = el('li', '', r.text);
        const x = el('button', 'x', '✕');
        x.setAttribute('aria-label', 'Remove rule: ' + r.text);
        x.onclick = () => act({ action: 'delete_rule', id: r.id });
        li.append(x);
        return li;
      }),
    );
    $('feed').replaceChildren(
      ...(a.feed.length
        ? a.feed
            .slice()
            .reverse()
            .map((f) => {
              const b = el('button', 'ev');
              b.type = 'button';
              b.append(el('time', '', clock(f.time)), el('span', '', f.text));
              b.onclick = () => {
                fixing = { agent: a.name, decision: f.text };
                $('fixWhat').textContent = f.text;
                $('fixText').value = '';
                $('fixMem').checked = false;
                $('fix').showModal();
              };
              return b;
            })
        : [el('div', 'empty', 'No activity yet this session.')]),
    );
    $('inp').placeholder =
      'Give ' + a.name + ' a standing rule, e.g. never post in fiverr at night';
    $('live').textContent = 'Updated ' + clock(data.updated);
  }
  async function load() {
    if (!key) return $('accessDialog').showModal();
    try {
      data = await call('GET');
      render();
    } catch (e) {
      say(e.message, true);
    }
  }
  async function act(body) {
    try {
      const d = await call('POST', body);
      data = d;
      render();
      say(d.reply);
      return true;
    } catch (e) {
      say(e.message, true);
      return false;
    }
  }
  $('ask').onsubmit = async (e) => {
    e.preventDefault();
    const text = $('inp').value.trim();
    if (text && (await act({ action: 'instruct', agent: pick, text }))) $('inp').value = '';
  };
  $('fix').addEventListener('close', () => {
    if ($('fix').returnValue === 'ok' && fixing)
      act({
        action: 'correct',
        ...fixing,
        text: $('fixText').value,
        remember: $('fixMem').checked,
      });
  });
  $('accessForm').onsubmit = (e) => {
    e.preventDefault();
    key = $('accessKey').value.trim();
    localStorage.setItem('givelife-cloud-key', key);
    $('accessDialog').close();
    load();
  };
  load();
  setInterval(() => document.hidden || load(), 5000);
})();
