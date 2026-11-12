/* A private fake-WhatsApp preview for specs that change saved messages or start DM batches, so they cannot
   disturb the shared server the other specs use. Nothing here can reach real WhatsApp. */
const { spawn } = require('node:child_process');
const path = require('node:path');
const KEY = 'manual-fix-preview-key';
async function startOwnServer(port) {
  const proc = spawn(
    'python',
    [
      path.join(__dirname, '..', 'preview_fake.py'),
      '--donors',
      '--test-api',
      '--fake-ai',
      '--port',
      String(port),
    ],
    { cwd: path.join(__dirname, '..', '..'), stdio: 'ignore' },
  );
  const end = Date.now() + 40000;
  while (Date.now() < end) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) return proc;
    } catch (e) {}
    await new Promise((r) => setTimeout(r, 250));
  }
  proc.kill();
  throw new Error('private preview server did not start');
}
const api = async (port, route, body) => {
  const r = await fetch(`http://127.0.0.1:${port}${route}`, {
    method: body ? 'POST' : 'GET',
    headers: { Authorization: 'Bearer ' + KEY, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
};
module.exports = { startOwnServer, api, KEY };
