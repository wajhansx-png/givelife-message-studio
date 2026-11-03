/* Exercise production handlers with controlled DOM/transport boundaries, never real WhatsApp. */
const fs = require('node:fs'),
  vm = require('node:vm'),
  assert = require('node:assert/strict');
const source = fs.readFileSync('app.js', 'utf8'),
  html = fs.readFileSync('index.html', 'utf8');
const part = (start, end) =>
  source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const events = [],
  nodes = new Map(),
  storage = new Map();
let phone = true;
function node(id) {
  if (!nodes.has(id))
    nodes.set(id, {
      id,
      value: '',
      style: {},
      dataset: {},
      scrollHeight: 44,
      disabled: false,
      hidden: true,
      open: false,
      attrs: {},
      classList: { toggle() {} },
      setAttribute(k, v) {
        this.attrs[k] = v;
      },
      focus() {
        events.push('focus:' + id);
      },
      blur() {
        events.push('blur:' + id);
      },
      addEventListener() {},
      showModal() {
        this.open = true;
      },
      close() {
        this.open = false;
      },
    });
  return nodes.get(id);
}
const ctx = {
  Nav: {
    go() {},
    leave() {},
    path() {
      return '';
    },
    top() {
      return '';
    },
  },
  console,
  Promise,
  JSON,
  Set,
  Map,
  Error,
  Date,
  Math,
  $: node,
  localStorage: { setItem: (k, v) => storage.set(k, v), getItem: (k) => storage.get(k) },
  document: {
    activeElement: {
      blur() {
        events.push('blur:active');
      },
    },
    documentElement: {
      style: {
        setProperty(k, v) {
          events.push(k + ':' + v);
        },
      },
    },
    body: { classList: { toggle() {} } },
    querySelectorAll() {
      return [];
    },
  },
  window: { visualViewport: { height: 480, offsetTop: 18, addEventListener() {} } },
  innerHeight: 844,
  isPhone: () => phone,
  requestAnimationFrame: (f) => {
    f();
    return 1;
  },
  cancelAnimationFrame() {},
  addEventListener() {},
  followReplies() {
    events.push('follow');
  },
  fitConversation() {},
  followChat() {
    events.push('reveal-answer');
  },
  rememberScroll() {},
  act: async (v) => events.push('act:' + v),
  say() {},
  setTimeout,
  clearTimeout,
};
ctx.visualViewport = ctx.window.visualViewport;
vm.createContext(ctx);
vm.runInContext(part('function saveChatDraft(', 'let correctionTurn='), ctx);
async function main() {
  node('histCmd').value = 'A real instruction';
  events.length = 0;
  await ctx.submitChat({ preventDefault() {} }, 'histCmd');
  assert.equal(node('histCmd').value, '');
  assert.equal(node('cmd').value, '');
  assert.equal(storage.get('givelife-chat-draft'), '');
  assert(
    events.indexOf('blur:active') < events.indexOf('act:A real instruction'),
    'Mobile must blur synchronously before the async action',
  );
  assert(!events.some((x) => x.startsWith('focus:')), 'Send must never focus an input again');
  assert(
    events.indexOf('reveal-answer') > events.indexOf('act:A real instruction'),
    'After an explicit chat request, reveal the answer even if an older turn was being read',
  );
  ctx.saveChatDraft('My unsent draft\nwith a second line');
  assert.equal(node('cmd').value, node('histCmd').value);
  assert.equal(storage.get('givelife-chat-draft'), node('cmd').value);
  node('histCmd').value = '   ';
  events.length = 0;
  await ctx.submitChat({ preventDefault() {} }, 'histCmd');
  assert.equal(node('histCmd').value, '   ');
  assert(!events.some((x) => x.startsWith('act:')), 'Blank input must not submit');
  phone = false;
  node('cmd').value = 'Desktop question';
  events.length = 0;
  await ctx.submitChat({ preventDefault() {} }, 'cmd');
  assert(!events.some((x) => x.startsWith('blur:')), 'Desktop typing focus should stay available');
  phone = true;
  assert(
    events.includes('--chat-height:480px') && events.includes('--chat-top:18px'),
    'Use the real visible viewport',
  );
  Object.assign(ctx, {
    editing: false,
    rememberScroll() {
      events.push('remember');
    },
    syncChat() {},
    drawLog() {},
    setEditing() {},
    refreshNextActions() {},
  });
  vm.runInContext(part('function openChat(', '/* ---- message preview'), ctx);
  events.length = 0;
  ctx.openChat();
  assert(node('hist').open);
  assert(events.includes('focus:histMain'));
  assert(!events.includes('focus:histCmd'), 'Opening chat must not open keyboard');
  ctx.saveChatDraft('Keep this');
  ctx.closeChat();
  assert(!node('hist').open);
  assert.equal(storage.get('givelife-chat-draft'), 'Keep this');
  assert(events.includes('focus:chatOpen'));
  // Pending locks cover the network round trip and the receipt, and are per action.
  vm.runInContext(part('const watchingJobs=', 'const requestId='), ctx);
  assert(ctx.lockSend('main', true));
  assert(!ctx.lockSend('main', true));
  assert(ctx.lockSend('community', true));
  ctx.lockSend('main', false);
  assert(ctx.lockSend('main', true));
  ctx.lockSend('main', false);
  let posts = 0,
    resolvePost,
    watches = 0;
  Object.assign(ctx, {
    editing: false,
    GN: { main: 'GiveLife' },
    setLiveNotice() {},
    busy() {},
    ensureCaption: async () => {},
    save: async () => {},
    requestId: () => String(posts),
    post: () => {
      posts++;
      return new Promise(
        (r) => (resolvePost = () => r({ ok: true, json: async () => ({ job_id: 'job-1' }) })),
      );
    },
    watchGroupJob: () => watches++,
  });
  node('group').value = 'Original *formatted* caption';
  vm.runInContext(
    'let timer=null;' +
      part('async function sendGroup(', "document.querySelectorAll('[data-group]')"),
    ctx,
  );
  const first = ctx.sendGroup('main'),
    duplicate = ctx.sendGroup('main');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(posts, 1, 'Rapid repeated taps must create one request');
  resolvePost();
  await Promise.all([first, duplicate]);
  assert.equal(watches, 1);
  assert.equal(node('group').value, 'Original *formatted* caption');
  assert(!ctx.lockSend('main', true), 'Keep locked until receipt');
  ctx.releaseJob('job-1');
  assert(ctx.lockSend('main', true));
  assert(!html.includes('id="sugg"'));
  assert(!source.includes('pollSuggestions'));
  assert(!source.includes("$('histCmd').focus()"), 'No implicit keyboard reopening');
  assert(
    html.includes('id="histMain"') && html.indexOf('id="histMain"') < html.indexOf('id="histForm"'),
    'Main has a dedicated row above composer',
  );
  assert(
    !source.includes('prepareReveal'),
    'Replies should appear immediately, without fake typing',
  );
  ctx.navigator = { onLine: true };
  node('whatsappConnection').dataset.state = 'online';
  vm.runInContext(
    "let autoOn=false,autoKnown=true,liveNotice=null,liveSnapshot=null,checkedAt=Date.now()-10000,pollError='',operationCount=0,lastAnnouncedError='';" +
      part('function setLiveNotice(', 'let autoPolling='),
    ctx,
  );
  ctx.paintStatusLine();
  assert(node('liveMeta').textContent.includes('Automatic actions off'));
  assert(node('liveDetail').textContent.includes('Synced 10s ago'));
  ctx.setLiveNotice('Confirmed sent to test group');
  assert(
    node('liveMeta').textContent.includes('Confirmed sent'),
    'Last meaningful result must remain visible',
  );
  ctx.setLiveNotice('Send was not confirmed', true);
  assert.equal(node('live').dataset.error, '1');
  assert(node('liveMeta').textContent.includes('not confirmed'));
  ctx.navigator.onLine = false;
  ctx.paintStatusLine();
  assert(
    node('liveMeta').textContent.startsWith('No internet'),
    'Connection failures must take priority over old success',
  );
  ctx.navigator.onLine = true;
  node('whatsappConnection').dataset.state = 'offline';
  ctx.paintStatusLine();
  assert(node('liveMeta').textContent.includes('WhatsApp disconnected'));
  vm.runInContext("pollError='Cannot reach cloud. Status may be old.'", ctx);
  ctx.paintStatusLine();
  assert(node('liveMeta').textContent.includes('Status may be old'));
  node('whatsappConnection').dataset.state = 'online';
  vm.runInContext(
    "pollError='';liveNotice=null;liveSnapshot={now:'Sending to GiveLife Foundation'}",
    ctx,
  );
  ctx.paintStatusLine();
  assert(
    node('liveMeta').textContent.includes('Sending to GiveLife'),
    'Cloud scheduled sends must appear even with Auto off',
  );
  vm.runInContext('autoKnown=false;liveSnapshot=null', ctx);
  ctx.paintStatusLine();
  assert(
    node('liveMeta').textContent.includes('Checking Auto status'),
    'Initial state must not falsely claim Auto is off',
  );
  assert(html.includes('id="auto" disabled'));
  const upcoming = ctx.statusView(
    { state: 'idle', next: [{ group: 'main', due_at: Date.now() / 1000 + 600 }] },
    true,
  );
  assert(upcoming.text.includes('Auto: GiveLife in'));
  assert(!upcoming.text.includes('Reading'), 'Idle must not claim an active read');
  assert.equal(
    ctx.statusView({ state: 'reading', now: 'Reading replies: GiveLife' }, true).text,
    'Reading: GiveLife',
  );
  assert(
    ctx
      .statusView(
        { state: 'sending', job: { next_send_at: Date.now() / 1000 + 45, next_target: 'main' } },
        true,
      )
      .text.includes('Next: GiveLife in'),
  );
  assert(
    ctx
      .statusView(
        { state: 'off', scheduled: { due_at: Date.now() / 1000 + 60, label: 'main' } },
        false,
      )
      .text.includes('Scheduled: GiveLife'),
  );
  assert(
    ctx
      .statusView({ state: 'idle', next: [{ group: 'main', due_at: Date.now() / 1000 - 1 }] }, true)
      .text.includes('waiting for send check'),
  );
  assert.equal(ctx.sinceLabel('malformed'), 'Not checked yet');
  vm.runInContext(
    "autoKnown=true;autoOn=true;liveNotice=null;liveSnapshot={state:'reading',now:'Reading replies: GiveLife',last_event:{text:'Confirmed sent to GiveLife',time:Date.now()/1000-45}}",
    ctx,
  );
  ctx.paintStatusLine();
  assert.equal(
    node('liveMeta').textContent,
    'Reading: GiveLife',
    'Current activity must stay above the previous result',
  );
  assert(
    node('liveDetail').textContent.startsWith('Last update: Confirmed sent to GiveLife'),
    'Highlight the real last result with an explicit past-event label',
  );
  assert(node('liveDetail').textContent.includes('45s ago'));
  vm.runInContext(
    "liveSnapshot={state:'idle',next:[{group:'main',due_at:Date.now()/1000+600}],last_event:{text:{bad:true}}}",
    ctx,
  );
  ctx.paintStatusLine();
  assert(
    node('liveMeta').textContent.startsWith('Waiting'),
    'A future timer must never look like active sending',
  );
  assert(
    !node('liveDetail').textContent.includes('[object Object]'),
    'Malformed event data must not leak into the status',
  );
  const syncFields = { group: { value: 'Saved group' }, dm: { value: 'Saved DM' } },
    syncCtx = {
      $: (id) => syncFields[id],
      JSON,
      showLeft() {},
      applyDrafts: (d) => {
        syncFields.group.value = d.group;
        syncFields.dm.value = d.dm;
      },
    };
  vm.createContext(syncCtx);
  vm.runInContext(
    "let left=25000,draftsReady=true,editing=false,pendingChats=0,operationCount=0,draftSaved=JSON.stringify({group:'Saved group',dm:'Saved DM'});" +
      part('function refreshLiveDrafts(', 'let autoPolling='),
    syncCtx,
  );
  const baseline = {
      left: 25000,
      payload: JSON.stringify({ group: 'Saved group', dm: 'Saved DM' }),
      wasSaved: true,
    },
    remote = { left: 23000, drafts: { group: 'Current group 23,000', dm: 'Current DM 23,000' } };
  assert(syncCtx.refreshLiveDrafts(remote, baseline));
  assert.equal(
    syncFields.group.value,
    remote.drafts.group,
    'Background donation should refresh the visible caption',
  );
  assert.equal(vm.runInContext('left', syncCtx), 23000);
  syncFields.group.value = 'My new unsaved edit';
  assert.equal(syncCtx.refreshLiveDrafts(remote, baseline), false);
  assert.equal(syncFields.group.value, 'My new unsaved edit');
  syncFields.group.value = 'Saved group';
  syncFields.dm.value = 'Saved DM';
  vm.runInContext('editing=true', syncCtx);
  assert.equal(syncCtx.refreshLiveDrafts(remote, baseline), false, 'Never replace an open edit');
  vm.runInContext('editing=false;left=31000', syncCtx);
  syncCtx.refreshLiveDrafts(remote, baseline);
  assert.equal(vm.runInContext('left', syncCtx), 31000, 'A late poll cannot undo a newer amount');
  assert.equal(
    syncCtx.refreshLiveDrafts(remote, { ...baseline, wasSaved: false }),
    false,
    'A draft that was unsaved when the poll began stays protected',
  );
  const preview = { style: { fontSize: '17px' }, textContent: 'Exact *caption*' },
    box = { clientHeight: 364, style: {} };
  Object.defineProperty(preview, 'scrollHeight', {
    get() {
      return 120 + 20 * parseFloat(this.style.fontSize);
    },
  });
  const fitCtx = {
    $: (id) => (id === 'chat' ? box : preview),
    view: () => 'group',
    isPhone: () => true,
    getComputedStyle: () => ({ paddingTop: '12px', paddingBottom: '12px' }),
  };
  vm.createContext(fitCtx);
  vm.runInContext('let editing=false;' + part('function fit(){', 'new ResizeObserver'), fitCtx);
  fitCtx.fit();
  assert.equal(preview.style.fontSize, '11px');
  assert.equal(box.style.overflowY, 'hidden');
  assert.equal(preview.textContent, 'Exact *caption*');
  box.clientHeight = 0;
  preview.style.fontSize = '14px';
  fitCtx.fit();
  assert.equal(preview.style.fontSize, '14px', 'A hidden preview must not shrink to minimum');
  box.clientHeight = 100;
  fitCtx.fit();
  assert.equal(preview.style.fontSize, '11px');
  assert.equal(box.style.overflowY, 'auto', 'Very long content still has a safe scroll fallback');
  fitCtx.isPhone = () => false;
  fitCtx.fit();
  assert.equal(
    preview.style.fontSize,
    '11px',
    'Desktop fitting must also shrink to the readable minimum when space is limited',
  );
  let scheduled = 0,
    campaign = { running: false, log: [] },
    campaignReads = 0;
  Object.assign(ctx, {
    setTimeout: (f, delay) => {
      scheduled = delay;
      return 1;
    },
    clearTimeout() {},
    fetch: async () => {
      campaignReads++;
      return { ok: true, json: async () => campaign };
    },
    showCamp: (t) => {
      node('camp').hidden = false;
      node('campText').textContent = t;
    },
  });
  vm.runInContext('let listT=null;' + part('let campTimer=', '/* ---- the assistant:'), ctx);
  await ctx.pollCamp();
  assert.equal(
    scheduled,
    10000,
    'Keep checking even when idle, so campaigns started in chat appear',
  );
  campaign = { running: true, sent: 3, total: 5, skipped: 0, wait: 30, current: 'Waiting' };
  await Promise.all([ctx.pollCamp(), ctx.pollCamp()]);
  assert.equal(campaignReads, 2, 'Campaign refreshes must coalesce');
  assert.equal(node('camp').hidden, false);
  assert(node('campText').textContent.includes('DMs 3/5'));
  assert.equal(scheduled, 3000);
  const campaignNotices = [];
  ctx.setLiveNotice = (t) => campaignNotices.push(t);
  let stopped = false;
  ctx.post = async (url, body) => {
    assert.equal(url, '/campaign');
    stopped = body.stop;
    campaign = { running: false, log: [] };
    return { ok: true, json: async () => ({ reply: 'DMs stopped' }) };
  };
  await node('campStop').onclick();
  assert(stopped);
  assert.equal(node('campStop').disabled, false);
  await new Promise((resolve) => setImmediate(resolve));
  assert(
    campaignNotices.at(-1).startsWith('DM list inactive'),
    'A stopped campaign cannot leave an old starting/countdown notice',
  );
  console.log(
    'UI behavior passed: blur before send, no autofocus, shared persistent draft, empty input, desktop focus, viewport, main navigation, action locks, duplicate requests, receipt unlock, unchanged caption.',
  );
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
