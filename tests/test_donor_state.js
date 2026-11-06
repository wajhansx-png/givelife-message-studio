const {
  extractFunction,
  extractFunctions,
  extractDeclaration,
  compact,
} = require('./helpers/source.cjs');
const fs = require('node:fs'),
  vm = require('node:vm'),
  assert = require('node:assert/strict');
const source = fs.readFileSync('donors.js', 'utf8');
const part = (...names) => extractFunctions(source, ...names);
async function main() {
  const calls = [],
    nodes = {
      donorMessagesTab: { tabIndex: 0 },
      donorSearch: { value: 'Ali' },
      donorTable: { hidden: false },
      donorMessages: { hidden: true },
      donorVolunteers: { hidden: true },
    };
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
    Map,
    Number,
    Object,
    String,
    setTimeout,
    clearTimeout,
    searchTimer: null,
    filterEpoch: 0,
    tab: 'all',
    allDonors: [
      { id: 'a', name: 'Ali', donated: false, amount: 0, important: true },
      { id: 'b', name: 'Zaid', donated: false, amount: 0, important: false },
    ],
    data: { items: [] },
    rowQueues: new Map(),
    rowVersions: new Map(),
    confirmedRows: new Map(),
    amountTimers: new Map(),
    el: (id) => nodes[id],
    page: { dataset: {}, querySelectorAll: () => [] },
    hideSent: false,
    paintHideRow() {},
    updateCounts() {},
    paintRow() {},
    notice() {},
    showMessages() {},
    draw() {},
    api: (url, body) =>
      new Promise((resolve, reject) => calls.push({ url, body, resolve, reject })),
  };
  vm.createContext(ctx);
  vm.runInContext(part('topCmp', 'applyFilters', 'paintHideRow'), ctx);
  vm.runInContext(part('selectDonorTab'), ctx);
  vm.runInContext(part('change'), ctx);
  ctx.cancelAmount = (id) => {
    clearTimeout(ctx.amountTimers.get(id));
    ctx.amountTimers.delete(id);
  };
  ctx.applyFilters();
  assert.deepEqual(
    Array.from(ctx.data.items, (d) => d.name),
    ['Ali'],
  );
  assert.equal(calls.length, 0, 'Name search must not wait for the server');
  ctx.selectDonorTab('all');
  assert.equal(nodes.donorSearch.value, '');
  assert.equal(ctx.data.items.length, 2, 'All resets the stale search');
  assert.equal(calls.length, 0);
  const baseline = { ...ctx.allDonors[0] };
  ctx.confirmedRows.set('a', baseline);
  const old = ctx.change('a', { donated: true, amount: 2000 });
  const latest = ctx.change('a', { donated: false });
  assert.equal(ctx.allDonors[0].donated, false, 'The latest selection updates immediately');
  assert.equal(ctx.allDonors[0].amount, 0);
  await new Promise(setImmediate);
  assert.equal(calls.length, 1, 'Saves for one donor are serialized');
  calls[0].resolve({ donor: { ...baseline, donated: true, amount: 2000 } });
  await new Promise(setImmediate);
  assert.equal(
    ctx.allDonors[0].donated,
    false,
    'An old response must not reverse the latest status',
  );
  assert.equal(calls.length, 2);
  calls[1].resolve({ donor: { ...baseline, donated: false, amount: 0 } });
  await Promise.all([old, latest]);
  assert.equal(ctx.allDonors[0].donated, false);
  const timer = setTimeout(() => {
    throw Error('Old amount callback was not cancelled');
  }, 10);
  ctx.amountTimers.set('a', timer);
  const save = ctx.change('a', { donated: false });
  assert.equal(ctx.amountTimers.has('a'), false);
  await new Promise(setImmediate);
  calls[2].resolve({ donor: { ...baseline, donated: false, amount: 0 } });
  await save;
  console.log(
    'Donor state passed: instant local filters, All clears search, optimistic status, ordered writes, stale-response protection and amount-timer cancellation.',
  );
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
