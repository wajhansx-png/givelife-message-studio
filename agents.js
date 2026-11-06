(() => {
  const $ = (id) => document.getElementById(id);
  const COLOR = { Active: '#10a37f', Working: '#e8b04a', Idle: '#6b6b6b', Error: '#ef6b6b' };
  const ROSTER = [
    ['manager', 'Manager'],
    ['writer', 'Writer'],
    ['checker', 'Checker'],
    ['auto', 'Group Poster'],
    ['dms', 'DM Guard'],
    ['replies', 'Reply Reader'],
    ['volunteers', 'Volunteer Guide'],
    ['plan', 'Case Plan'],
  ];
  const NAMES = Object.fromEntries(ROSTER);
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let key = localStorage.getItem('givelife-cloud-key') || '',
    pick = localStorage.getItem('givelife-agent') || 'manager',
    data = null,
    shown = '',
    typing = false;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  // Agent replies use Markdown (**bold**); drafts use WhatsApp (*bold*). Both render, nothing shows as symbols.
  const md = (t) =>
    String(t || '')
      .replace(/^#{1,6}\s+(.+)$/gm, '*$1*')
      .replace(/\*\*([^*\n]+)\*\*/g, '*$1*')
      .replace(/__([^_\n]+)__/g, '_$1_')
      .replace(/^(\s*)[-•]\s+/gm, '$1* ');
  const rich = (node, text) => {
    node.innerHTML = window.waFormat ? window.waFormat(md(text)) : '';
    if (!window.waFormat) node.textContent = text;
  };
  const say = (t, bad) => {
    $('msg').textContent = t || '';
    $('msg').className = 'msg' + (bad ? ' bad' : '');
  };
  async function call(method, body) {
    const r = await fetch('/api/agents', {
      method,
      headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(method === 'GET' ? 20000 : 150000),
    }).catch((e) => {
      throw new Error(
        e.name === 'TimeoutError'
          ? 'The server is slow. Retrying…'
          : 'Cannot reach the server. Retrying…',
      );
    });
    if (r.status === 401) {
      $('accessDialog').showModal();
      throw new Error('Enter your access key.');
    }
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Something went wrong.');
    return d;
  }
  function chips() {
    const states = Object.fromEntries((data?.agents || []).map((a) => [a.id, a.state]));
    $('list').replaceChildren(
      ...ROSTER.map(([id, name]) => {
        const b = el('button', 'agent');
        b.type = 'button';
        b.setAttribute('aria-current', String(id === pick));
        const dot = el('span', 'dot');
        dot.style.background = COLOR[states[id]] || '#6b6b6b';
        b.append(dot, el('span', '', name));
        b.onclick = () => {
          if (pick === id) return;
          pick = id;
          shown = '';
          localStorage.setItem('givelife-agent', pick);
          render();
          b.scrollIntoView({ block: 'nearest', inline: 'center' });
        };
        return b;
      }),
    );
  }
  // The draft exactly as it will look in WhatsApp, sized to fit the screen so it never needs scrolling.
  const fit = (card) => {
    const block = card.closest('.draft');
    if (!block) return;
    // Everything the owner must see at once: the card and its buttons, between the top bar and the input.
    const room = () =>
      $('ask').getBoundingClientRect().top -
      document.querySelector('.top').getBoundingClientRect().bottom -
      28;
    let size = 17;
    card.style.fontSize = size + 'px';
    card.style.lineHeight = '1.45';
    while (size > 10 && block.getBoundingClientRect().height > room()) {
      size -= 0.5;
      card.style.fontSize = size + 'px';
      if (size <= 12) card.style.lineHeight = '1.3';
    }
  };
  function draftCard(d, pendingId) {
    const wrap = el('div', 'draft');
    const wall = el('div', 'wa-wall');
    const card = el('div', 'wa-bubble');
    const text = el('div', 'wa-text');
    text.innerHTML = window.waFormat ? window.waFormat(d.text) : '';
    if (!window.waFormat) text.textContent = d.text;
    card.append(text, el('div', 'wa-time', (d.kind === 'dm' ? 'DM' : 'Group') + ' · preview  ✓✓'));
    wall.append(card);
    wrap.append(wall);
    if (d.saved) {
      wrap.append(
        el('div', 'saved', '✓ Saved as your ' + (d.saved === 'dm' ? 'DM' : 'Group') + ' message'),
      );
    } else if (d.id === pendingId) {
      const row = el('div', 'choices');
      for (const [label, say, cls] of [
        ['Approve ✓', 'Approved', 'yes'],
        ['Next option →', 'Next option', ''],
      ]) {
        const b = el('button', cls, label);
        b.type = 'button';
        b.onclick = () => {
          if ($('inp').disabled) return;
          $('inp').value = say;
          $('ask').requestSubmit();
        };
        row.append(b);
      }
      wrap.append(row);
    }
    requestAnimationFrame(() => fit(card));
    return wrap;
  }
  function bubble(m, pendingId) {
    const me = m.who === 'you',
      row = el('div', 'bubble ' + (me ? 'me' : 'them'));
    if (!me && m.who !== pick) row.append(el('b', 'who', NAMES[m.who] || m.who));
    if (m.text || me) {
      const body = el('div', 'txt');
      me ? (body.textContent = m.text) : rich(body, m.text);
      row.append(body);
    }
    if (m.draft) {
      row.classList.add('has-draft');
      row.append(draftCard(m.draft, pendingId));
    }
    return row;
  }
  function render() {
    chips();
    $('name').textContent = NAMES[pick];
    $('inp').placeholder = 'Message ' + NAMES[pick];
    if (!data) return;
    const a = data.agents.find((x) => x.id === pick) || data.agents[0];
    $('modeAuto').setAttribute('aria-checked', String(!!data.auto));
    // Only what needs attention: problems with a fix, and Manager's issues. Everything else lives in chat.
    const notes = [
      ...(a.errors || []).map((e) => ({ text: e.text, action: e.action })),
      ...(a.id === 'manager'
        ? (a.facts || []).filter((f) => !/^Writer: \d/.test(f)).map((t) => ({ text: t }))
        : []),
    ];
    $('notes').replaceChildren(
      ...notes.map((n) => {
        const box = el('div', 'note');
        box.append(el('span', '', n.text));
        if (n.action) {
          const b = el('button', '', n.action === 'open_home' ? 'Open' : 'Fix');
          b.type = 'button';
          b.onclick = () =>
            n.action === 'open_home'
              ? (location.href = '/')
              : act({ action: 'fix', fix: n.action });
          box.append(b);
        }
        return box;
      }),
    );
    const rules = a.rules || [];
    $('rules').hidden = !rules.length;
    $('rules').replaceChildren(
      ...rules.map((r) => {
        const c = el('span', 'rule', r.text);
        const x = el('button', 'x', '✕');
        x.type = 'button';
        x.setAttribute('aria-label', 'Remove rule: ' + r.text);
        x.onclick = () => act({ action: 'rule_delete', id: r.id });
        c.append(x);
        return c;
      }),
    );
    if (typing) return; // never redraw the conversation while a reply is being typed out
    const lines = (data.chat || []).filter((m) => pick === 'manager' || m.agent === pick);
    const sig =
      pick +
      ':' +
      lines.length +
      ':' +
      (lines.at(-1)?.id || '') +
      ':' +
      data.pending +
      ':' +
      (lines.at(-1)?.draft?.saved || '');
    if (sig === shown) return;
    shown = sig;
    $('thread').replaceChildren(
      ...(lines.length
        ? lines.map((m) => bubble(m, data.pending))
        : [el('p', 'empty', 'Ask ' + NAMES[pick] + ' anything.')]),
    );
    const card = $('thread').querySelector('.bubble.has-draft:last-child .draft');
    card ? card.scrollIntoView({ block: 'start' }) : end();
  }
  const end = () => requestAnimationFrame(() => ($('scroll').scrollTop = $('scroll').scrollHeight));
  // Claude-style reply: a typing indicator while waiting, then the text writes itself out.
  async function typeOut(node, text) {
    if (calm) return rich(node, text);
    const words = String(text).split(/(\s+)/);
    let out = '';
    for (let i = 0; i < words.length; i += 3) {
      out += words.slice(i, i + 3).join('');
      rich(node, out);
      end();
      await new Promise((r) => setTimeout(r, 18));
    }
    rich(node, text);
  }
  async function load() {
    if (!key) return $('accessDialog').showModal();
    try {
      data = await call('GET');
      render();
      if (!typing) say('');
    } catch (e) {
      say(e.message, true);
    }
  }
  async function act(body) {
    try {
      data = await call('POST', body);
      render();
      say(data.reply && body.action !== 'say' ? data.reply : '');
      return true;
    } catch (e) {
      say(e.message, true);
      return false;
    }
  }
  async function send(text) {
    typing = true;
    if ($('thread').querySelector('.empty')) $('thread').replaceChildren();
    $('thread').append(bubble({ who: 'you', text }));
    const wait = el('div', 'bubble them');
    wait.append(el('div', 'dots'));
    wait.firstChild.append(el('i'), el('i'), el('i'));
    $('thread').append(wait);
    end();
    try {
      const d = await call('POST', { action: 'say', text, agent: pick });
      data = d;
      wait.remove();
      for (const m of (d.messages || []).filter((x) => x.who !== 'you')) {
        const row = bubble({ ...m, text: m.text ? ' ' : '', draft: null });
        $('thread').append(row);
        if (m.text) await typeOut(row.querySelector('.txt'), m.text);
      }
      return true;
    } catch (e) {
      wait.remove();
      say(e.message, true);
      return false;
    } finally {
      typing = false;
      shown = '';
      render();
    }
  }
  const grow = () => {
    const t = $('inp');
    t.style.height = 'auto';
    t.style.height = Math.min(t.scrollHeight, 160) + 'px';
    $('ask').querySelector('.send').disabled = !t.value.trim() || t.disabled;
  };
  $('inp').addEventListener('input', grow);
  $('inp').onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('ask').requestSubmit();
    }
  };
  $('ask').onsubmit = async (e) => {
    e.preventDefault();
    const text = $('inp').value.trim();
    if (!text || $('inp').disabled) return;
    $('inp').value = '';
    $('inp').disabled = true;
    grow();
    say('');
    if (!(await send(text))) $('inp').value = text;
    $('inp').disabled = false;
    grow();
    $('inp').focus();
  };
  $('modeAuto').onclick = () => data && act({ action: 'auto', on: !data.auto });
  $('accessForm').onsubmit = (e) => {
    e.preventDefault();
    key = $('accessKey').value.trim();
    localStorage.setItem('givelife-cloud-key', key);
    $('accessDialog').close();
    load();
  };
  addEventListener('resize', () => document.querySelectorAll('.wa-bubble').forEach(fit));
  render();
  load();
  setInterval(() => document.hidden || typing || load(), 8000);
})();
