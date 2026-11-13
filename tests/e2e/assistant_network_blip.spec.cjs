const { test, expect } = require('@playwright/test');

/* The assistant runs on the server. A short network blip while the page waits for the answer must not
   abandon it, and must never repeat the request itself (that could send twice). Routes are mocked:
   nothing reaches WhatsApp. */
async function open(page) {
  await page.addInitScript(() =>
    localStorage.setItem('givelife-cloud-key', 'manual-fix-preview-key'),
  );
  await page.route('**/wa-status', (r) =>
    r.fulfill({ json: { results: { is_connected: true, is_logged_in: true } } }),
  );
  await page.goto('/old');
  await expect(page.locator('#leftChip')).toContainText('25,000');
}

test('a network blip while waiting for the assistant is survived without repeating the request', async ({
  page,
}) => {
  let posts = 0,
    statusCalls = 0;
  await open(page);
  await page.route('**/assistant', (r) => {
    posts++;
    return r.fulfill({ status: 202, json: { task_id: 'blip-task' } });
  });
  await page.route('**/assistant-status/blip-task', (r) => {
    statusCalls++;
    if (statusCalls <= 2) return r.abort('connectionreset');
    return r.fulfill({ json: { done: true, result: { reply: 'Answer after the blip' } } });
  });
  await page.locator('#cmd').fill('what is the balance');
  await page.locator('#cmd').press('Enter');
  await expect(page.locator('#log')).toContainText('Answer after the blip', { timeout: 15000 });
  expect(posts).toBe(1); // the question itself was sent once, never repeated
  expect(statusCalls).toBe(3);
});

test('a long outage stops waiting with a clear message and still does not repeat the request', async ({
  page,
}) => {
  let posts = 0,
    statusCalls = 0;
  await open(page);
  await page.route('**/assistant', (r) => {
    posts++;
    return r.fulfill({ status: 202, json: { task_id: 'gone-task' } });
  });
  await page.route('**/assistant-status/gone-task', (r) => {
    statusCalls++;
    return r.abort('connectionreset');
  });
  await page.locator('#cmd').fill('what is the balance');
  await page.locator('#cmd').press('Enter');
  await expect(page.locator('#log')).toContainText('will not repeat the action', {
    timeout: 20000,
  });
  expect(posts).toBe(1);
  expect(statusCalls).toBe(4); // bounded: it gives up, it does not loop forever
});
