const assert = require('node:assert/strict'),
  fs = require('node:fs');
require('../format.js');
const html = globalThis.chatFormat;
const raw = 'Full reply. ' + 'Every requested detail is preserved. 💔🤲\n'.repeat(500);
const rendered = html(raw);
assert.equal(
  (rendered.match(/Every requested detail/g) || []).length,
  500,
  'A long reply is never shortened',
);
assert(rendered.includes('🤲'));
assert(html('**important**').includes('<strong>important</strong>'));
assert(html('*_amount_*').includes('<em>amount</em>'));
assert(!html('<img src=x onerror=alert(1)>').includes('<img'), 'Untrusted markup must be escaped');
const app = fs.readFileSync('app.js', 'utf8');
assert(
  app.includes("document.querySelector('dialog[open]')"),
  'Keyboard shortcuts must respect an open dialog',
);
const replyHtml = app.slice(
  app.indexOf('function replyHtml'),
  app.indexOf('function replyHtml') + 600,
);
assert(!replyHtml.includes('.slice(0,'), 'The reply renderer does not trim content to make it fit');
console.log(
  'Reply view passed: full-text retention, readable formatting, escaped markup and modal keyboard isolation.',
);
