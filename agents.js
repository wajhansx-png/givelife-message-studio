(() => {
  const $ = (id) => document.getElementById(id);
  const C = { Active: '#10a37f', Working: '#e8b04a', Idle: '#8f8f8f', Error: '#ef6b6b' };
  let key = localStorage.getItem('givelife-cloud-key') || '',
    data = null,
    pick = localStorage.getItem('givelife-agent') || 'manager',
    fixing = null;

  const CHIPS = {
    manager: [
      'Ask all agents for their progress',
      'Ask Writer to draft a group appeal',
      'Ask Checker to verify latest message',
      'Tell Volunteer Guide to check volunteers',
      'Recover and retry failed tasks',
    ],
    writer: [
      'Draft a sincere group appeal',
      'Write a warm DM to an existing donor',
      'Write a volunteer poster ask',
      'Improve tone to be softer and more compassionate',
    ],
    checker: [
      'Audit all saved group versions',
      'Check message: Please help if you can danger Rs 5000',
      'Audit current case facts and math',
    ],
    auto: [
      'What is the next group scheduled?',
      'Check posting intervals and group rules',
    ],
    volunteers: [
      'Check pending volunteer outreach',
      'How many volunteers are ready to share?',
    ],
    plan: [
      'Switch to slow mode',
      'Switch to normal mode',
      'What is the remaining case balance?',
    ],
  };

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  function formatText(text) {
    if (!text) return '';
    // Format basic markdown: code blocks, inline code, bold, italic
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    html = html.replace(/\*([^*]+)\*/g, '<i>$1</i>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

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

  function getChatHistory(agentId) {
    try {
      return JSON.parse(localStorage.getItem('givelife-chat-' + agentId) || '[]');
    } catch {
      return [];
    }
  }

  function saveChatHistory(agentId, list) {
    try {
      localStorage.setItem('givelife-chat-' + agentId, JSON.stringify(list.slice(-30)));
    } catch {}
  }

  function renderChat() {
    const history = getChatHistory(pick);
    const container = $('chatThread');
    container.innerHTML = '';

    if (!history.length) {
      const welcome = el('div', 'bubble bot');
      if (pick === 'manager') {
        welcome.innerHTML =
          '<b>GiveLife AI Manager</b><br>I supervise and coordinate all 7 agents. You can talk to me directly, give instructions to any agent, or ask: <i>"Ask all agents for their progress"</i>.';
      } else if (pick === 'writer') {
        welcome.innerHTML =
          '<b>Conversational Writer</b><br>I write and refine honest, respectful fundraising messages following your exact taste and verified case facts.';
      } else if (pick === 'checker') {
        welcome.innerHTML =
          '<b>Quality Checker</b><br>I detect wrong amounts, invented medical details, panic urgency, and formatting errors.';
      } else {
        welcome.innerHTML = `Connected to <b>${pick.toUpperCase()}</b>. How can I help?`;
      }
      container.append(welcome);
    } else {
      for (const m of history) {
        const b = el('div', 'bubble ' + (m.role === 'user' ? 'user' : 'bot'));
        b.innerHTML = formatText(m.text);
        container.append(b);
      }
    }

    // Render chips
    const chipsContainer = $('chips');
    chipsContainer.innerHTML = '';
    const suggestions = CHIPS[pick] || CHIPS['manager'];
    for (const s of suggestions) {
      const btn = el('button', 'chip', s);
      btn.type = 'button';
      btn.onclick = () => {
        $('inp').value = s;
        sendMessage(s);
      };
      chipsContainer.append(btn);
    }
  }

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
        t.append(el('small', '', x.status + ' · ' + (x.now || 'Ready')));
        b.append(t);
        b.onclick = () => {
          pick = x.id;
          localStorage.setItem('givelife-agent', pick);
          render();
        };
        return b;
      }),
    );

    const on = data.auto === true;
    $('modeManual').setAttribute('aria-pressed', String(!on));
    $('modeAuto').setAttribute('aria-pressed', String(on));
    $('modeText').textContent = on
      ? 'Auto: the agents post, read and reply on their own.'
      : 'Manual: nothing runs by itself. You send from the main page.';

    $('name').textContent = a.name;
    $('pill').textContent = a.status;
    $('pill').style.background = C[a.status] || '#10a37f';
    $('now').textContent = a.now || '';
    $('role').textContent = a.role;

    const p = a.progress || {};
    $('pLabel').textContent = p.label || '';
    $('pText').textContent = p.max ? `${p.value} / ${p.max}` : String(p.value ?? '');
    $('pBar').style.width =
      (p.max ? Math.min(100, (100 * p.value) / p.max) : p.value ? 100 : 0) + '%';
    $('pBar').style.background = C[a.status] || '#10a37f';

    $('facts').replaceChildren(...(a.facts || []).map((f) => el('li', '', f)));

    $('errors').replaceChildren(
      ...(a.errors || []).map((e) => {
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
        if (r.kind === 'note')
          li.append(el('small', 'muted', ' · AI note only, not enforced by the timers'));
        const x = el('button', 'x', '✕');
        x.setAttribute('aria-label', 'Remove rule: ' + r.text);
        x.onclick = () => act({ action: 'delete_rule', id: r.id });
        li.append(x);
        return li;
      }),
    );

    $('feed').replaceChildren(
      ...((a.feed && a.feed.length)
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
        : [el('div', 'empty', 'No recent activity.')]),
    );

    $('inp').placeholder =
      pick === 'manager'
        ? 'Ask Manager anything, or: "Ask Writer to...", "Tell Volunteer Guide to..."'
        : `Talk directly to ${a.name}…`;

    $('live').textContent = 'Updated ' + clock(data.updated);

    renderChat();
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

  document.querySelectorAll('[data-mode]').forEach((b) => {
    b.onclick = async () => {
      const want = b.dataset.mode === 'auto';
      if (!data || data.auto === want) return;
      document.querySelectorAll('[data-mode]').forEach((x) => (x.disabled = true));
      await act({ action: want ? 'auto_on' : 'auto_off' });
      document.querySelectorAll('[data-mode]').forEach((x) => (x.disabled = false));
    };
  });

  async function sendMessage(text) {
    text = (text || '').trim();
    if (!text) return;

    const hist = getChatHistory(pick);
    hist.push({ role: 'user', text });
    saveChatHistory(pick, hist);
    renderChat();

    // Show temporary thinking bubble
    const container = $('chatThread');
    const thinking = el('div', 'bubble bot', 'Thinking…');
    container.append(thinking);
    thinking.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    $('inp').value = '';
    say('');

    try {
      const res = await call('POST', {
        action: 'chat',
        agent: pick,
        text,
        history: hist.slice(-8),
      });

      thinking.remove();
      data = res;
      hist.push({ role: 'bot', text: res.reply || 'Done.' });
      saveChatHistory(pick, hist);
      renderChat();

      const lastBubble = container.lastElementChild;
      if (lastBubble) lastBubble.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      thinking.textContent = '⚠️ ' + err.message;
    }
  }

  $('ask').onsubmit = (e) => {
    e.preventDefault();
    sendMessage($('inp').value);
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
