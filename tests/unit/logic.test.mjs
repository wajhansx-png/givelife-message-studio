import { test, expect } from 'vitest';
import fc from 'fast-check';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const py = (body) =>
  JSON.parse(
    execFileSync('python', ['tests/logic_bridge.py'], {
      input: JSON.stringify(body),
      encoding: 'utf8',
    }),
  );
test('donation totals match exact integer-paisa sums', () => {
  fc.assert(
    fc.property(
      fc.array(fc.integer({ min: 0, max: 1000000 }), { minLength: 1, maxLength: 12 }),
      (cents) => {
        expect(py({ op: 'total', cents })).toBe(cents.reduce((a, b) => a + b, 0) / 100);
      },
    ),
    { numRuns: 40, seed: 2801026 },
  );
});
test('phone normalization is idempotent across accepted Pakistan formats', () => {
  fc.assert(
    fc.property(fc.integer({ min: 1000000, max: 9999999 }), (tail) => {
      const expected = '92300' + tail;
      for (const value of ['0300 ' + tail, '+92 300 ' + tail, '0092300' + tail])
        expect(py({ op: 'phone', value })).toBe(expected);
    }),
    { numRuns: 20, seed: 2801026 },
  );
});
test('duplicate contact imports preserve one record per normalized number and hide numbers', () => {
  fc.assert(
    fc.property(
      fc.array(fc.integer({ min: 1, max: 8 }), { minLength: 1, maxLength: 20 }),
      (ids) => {
        const phones = ids.map((i) => '1555' + String(1230000 + i));
        const r = py({ op: 'duplicates', phones });
        expect(r.count).toBe(new Set(phones).size);
        expect(JSON.stringify(r.public)).not.toContain('1555');
      },
    ),
    { numRuns: 25, seed: 2801026 },
  );
});
test('assistant formatting cannot inject HTML for arbitrary text', () => {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(readFileSync('format.js', 'utf8'), context);
  fc.assert(
    fc.property(fc.string({ maxLength: 400 }), (text) => {
      const html = context.window.chatFormat('<img onerror=alert(1)>' + text);
      expect(html).not.toContain('<img');
      expect(html).not.toContain('<script');
    }),
    { numRuns: 200, seed: 2801026 },
  );
});
