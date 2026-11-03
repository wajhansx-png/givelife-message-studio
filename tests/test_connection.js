const {
  extractFunction,
  extractFunctions,
  extractDeclaration,
  compact,
} = require('./helpers/source.cjs');
const fs = require('node:fs'),
  vm = require('node:vm'),
  assert = require('node:assert/strict');
const source = fs.readFileSync('connection.js', 'utf8');
const body = extractFunction(source, 'checkStatus');
let finish,
  requests = 0,
  online = false;
const nodes = new Map();
const ctx = {
  Promise,
  console,
  request: () => {
    requests++;
    return new Promise(
      (r) =>
        (finish = () =>
          r({
            status: 200,
            ok: true,
            json: async () => ({ results: { is_connected: true, is_logged_in: true } }),
          })),
    );
  },
  paint: (s) => {
    online = s === 'online';
  },
  el: (id) => {
    if (!nodes.has(id))
      nodes.set(id, {
        disabled: false,
        hidden: false,
        textContent: '',
        classList: { toggle() {} },
      });
    return nodes.get(id);
  },
};
vm.createContext(ctx);
vm.runInContext(
  "let key='test',statusPending=null,checking=false,connected=false;" +
    body +
    ';this.check=checkStatus;',
  ctx,
);
(async () => {
  const a = ctx.check(),
    b = ctx.check();
  assert.equal(requests, 1);
  assert.equal(a, b);
  assert.equal(online, false);
  finish();
  await Promise.all([a, b]);
  assert.equal(online, true);
  assert.equal(nodes.get('waCloudRefresh').disabled, false);
  console.log('Connection refresh race passed: concurrent sends await one shared status check.');
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

const pollCtx = { document: { hidden: false }, count: 0 };
vm.createContext(pollCtx);
vm.runInContext(
  "let key='test';function checkStatus(){count++;}" + extractFunction(source, 'pollConnection'),
  pollCtx,
);
pollCtx.pollConnection();
assert.equal(pollCtx.count, 1);
pollCtx.document.hidden = true;
pollCtx.pollConnection();
assert.equal(pollCtx.count, 1);
pollCtx.document.hidden = false;
vm.runInContext("key='';", pollCtx);
pollCtx.pollConnection();
assert.equal(pollCtx.count, 1);
