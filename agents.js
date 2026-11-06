(() => {
  const $ = (id) => document.getElementById(id);
  const COLOR = { Active: '#10a37f', Working: '#e8b04a', Idle: '#8f8f8f', Error: '#ef6b6b' };
  let key = localStorage.getItem('givelife-cloud-key') || '',
    pick = localStorage.getItem('givelife-agent') || 'manager',
    data = null,
    shown = '';
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const clock = (t) =>
    t ? new Date(t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
  const say = (t, bad) => {
    $('msg').textContent = t || '';
    $('msg').className = 'msg' + (bad ? ' bad' : '');
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
  function render() {
    if (!data) return;
    const a = data.agents.find((x) => x.id === pick) || data.agents[0];
    pick = a.id;
    const names = Object.fromEntries(data.agents.map((x) => [x.id, x.name]));
    $('list').replaceChildren(
      ...data.agents.map((x) => {
        const b = el('button', 'agent');
        b.type = 'button';
        b.setAttribute('aria-current', String(x.id === a.id));
        b.append(
          el('span', 'dot'),
          el('span', 'nm', x.name),
          el('small', '', x.state + ' · ' + x.now),
        );
        b.firstChild.style.background = COLOR[x.state];
        b.onclick = () => {
          pick = x.id;
          localStorage.setItem('givelife-agent', pick);
          render();
        };
        return b;
      }),
    );
    $('modeManual').setAttribute('aria-pressed', String(!data.auto));
    $('modeAuto').setAttribute('aria-pressed', String(data.auto));
    $('modeText').textContent = data.auto
      ? 'Auto: agents post, read and reply on their own.'
      : 'Manual: nothing runs by itself.';
    $('name').textContent = a.name;
    $('pill').textContent = a.state;
    $('pill').style.background = COLOR[a.state];
    $('now').textContent = a.now;
    $('role').textContent = a.role;
    const p = a.progress || {};
    $('pLabel').textContent = p.label || '';
    $('pText').textContent = p.max ? p.value + ' / ' + p.max : String(p.value ?? '');
    $('pBar').style.width =
      (p.max ? Math.min(100, (100 * p.value) / p.max) : p.value ? 100 : 0) + '%';
    $('pBar').style.background = COLOR[a.state];
    $('facts').replaceChildren(...(a.facts || []).map((f) => el('li', '', f)));
    $('errors').replaceChildren(
      ...(a.errors || []).map((e) => {
        const box = el('div', 'err');
        box.append(el('b', '', e.text), el('span', '', e.fix));
        if (e.action) {
          const b = el('button', '', e.action === 'open_home' ? 'Open main page' : 'Fix now');
          b.type = 'button';
          b.onclick = () =>
            e.action === 'open_home'
              ? (location.href = '/')
              : act({ action: 'fix', fix: e.action });
          box.append(b);
        }
        return box;
      }),
    );
    const rules = a.rules || [];
    $('rules').hidden = !rules.length;
    $('ruleList').replaceChildren(
      ...rules.map((r) => {
        const li = el('li', '', r.text);
        const x = el('button', 'x', '✕');
        x.type = 'button';
        x.setAttribute('aria-label', 'Remove rule: ' + r.text);
        x.onclick = () => act({ action: 'rule_delete', id: r.id });
        li.append(x);
        return li;
      }),
    );
    const lines = (data.chat || []).filter((m) => a.id === 'manager' || m.agent === a.id);
    $('thread').replaceChildren(
      ...(lines.length
        ? lines.map((m) => {
            const row = el('div', 'bubble ' + (m.who === 'you' ? 'me' : 'them'));
            row.append(
              el('b', '', m.who === 'you' ? 'You' : names[m.who] || m.who),
              el('div', 'txt', m.text),
            );
            return row;
          })
        : [
            el(
              'p',
              'muted',
              a.id === 'manager'
                ? 'Ask me anything, or say "ask all agents for their progress".'
                : 'Ask ' + a.name + ' something.',
            ),
          ]),
    );
    if (shown !== a.id + lines.length) {
      shown = a.id + lines.length;
      $('thread').lastElementChild?.scrollIntoView({ block: 'nearest' });
    }
    $('feed').replaceChildren(
      ...((a.feed || []).length
        ? a.feed
            .slice()
            .reverse()
            .map((f) => {
              const r = el('div', 'ev');
              r.append(el('time', '', clock(f.time)), el('span', '', f.text));
              return r;
            })
        : [el('p', 'muted', 'No activity yet.')]),
    );
    $('inp').placeholder =
      a.id === 'manager'
        ? 'Message Manager, e.g. ask Writer to improve the group message'
        : 'Message ' + a.name;
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
      data = await call('POST', body);
      render();
      say(data.reply || '');
      return true;
    } catch (e) {
      say(e.message, true);
      return false;
    }
  }
  $('modeManual').onclick = () => data?.auto && act({ action: 'auto', on: false });
  $('modeAuto').onclick = () => data && !data.auto && act({ action: 'auto', on: true });
  $('ask').onsubmit = async (e) => {
    e.preventDefault();
    const text = $('inp').value.trim();
    if (!text || $('inp').disabled) return;
    $('inp').disabled = true;
    say((data?.agents.find((x) => x.id === pick)?.name || 'Manager') + ' is working…');
    if (await act({ action: 'say', text, agent: pick })) $('inp').value = '';
    $('inp').disabled = false;
    $('inp').focus();
  };
  $('inp').onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      $('ask').requestSubmit();
    }
  };
  $('accessForm').onsubmit = (e) => {
    e.preventDefault();
    key = $('accessKey').value.trim();
    localStorage.setItem('givelife-cloud-key', key);
    $('accessDialog').close();
    load();
  };
  load();
  setInterval(() => document.hidden || $('inp').disabled || load(), 5000);
})();
