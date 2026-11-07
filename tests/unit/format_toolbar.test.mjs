import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { toggle, lineBounds } = require('../../format.js') && require('../../format-toolbar.js');
const render = require('../../format.js');

const pick = (value, text, mark) => {
  const start = value.indexOf(text);
  return toggle(value, start, start + text.length, mark);
};

describe('toggle: bold and italic that WhatsApp really renders', () => {
  it('wraps a selected word', () => {
    expect(pick('Please help Yousuf today', 'Yousuf', '*').value).toBe(
      'Please help *Yousuf* today',
    );
    expect(pick('Please help Yousuf today', 'Yousuf', '_').value).toBe(
      'Please help _Yousuf_ today',
    );
  });

  it('keeps spaces outside the markers (markers must touch the text)', () => {
    const r = pick('say  hello there ', '  hello ', '*');
    expect(r.value).toBe('say  *hello* there ');
  });

  it('takes the whole word when the selection starts or ends inside one', () => {
    const v = 'Donation received';
    const r = toggle(v, 3, 7, '*'); // "ation" -> whole word "Donation"
    expect(r.value).toBe('*Donation* received');
    expect(render(r.value)).toContain('<strong>Donation</strong>');
  });

  it('toggles off when the selection includes the markers', () => {
    const r = pick('Help *Yousuf* now', '*Yousuf*', '*');
    expect(r.value).toBe('Help Yousuf now');
  });

  it('toggles off when only the inside of an already-bold word is selected', () => {
    const r = pick('Help *Yousuf* now', 'Yousuf', '*');
    expect(r.value).toBe('Help Yousuf now');
    expect(r.start).toBe(5);
    expect(r.end).toBe(11);
  });

  it('never produces broken nesting when part of the selection is already bold', () => {
    const r = pick('Need *Rs. 5,000* more today', 'Need *Rs. 5,000* more', '*');
    expect(r.value).toBe('*Need Rs. 5,000 more* today');
    expect(render(r.value)).toContain('<strong>Need Rs. 5,000 more</strong>');
  });

  it('italic inside bold and bold inside italic both render', () => {
    const bold = pick('Help Yousuf now', 'Help Yousuf now', '*').value;
    const both = pick(bold, 'Yousuf', '_').value;
    expect(both).toBe('*Help _Yousuf_ now*');
    expect(render(both)).toBe('<strong>Help <em>Yousuf</em> now</strong>');
  });

  it('wraps each line of a multi-line selection (WhatsApp styling stops at a line break)', () => {
    const v = 'First line\n\nSecond line';
    const r = toggle(v, 0, v.length, '*');
    expect(r.value).toBe('*First line*\n\n*Second line*');
    expect(toggle(r.value, 0, r.value.length, '*').value).toBe(v); // and back
  });

  it('does nothing for an empty or whitespace-only selection', () => {
    expect(toggle('abc def', 3, 3, '*').changed).toBe(false);
    expect(toggle('abc   def', 3, 6, '*').changed).toBe(false);
    expect(toggle('abc', 0, 3, '~').changed).toBe(false);
  });

  it('handles Urdu and emoji next to the selection', () => {
    const v = 'یوسف کی مدد کریں 💔';
    const r = pick(v, 'یوسف', '*');
    expect(r.value).toBe('*یوسف* کی مدد کریں 💔');
    const e = toggle('Pray 🤲 now', 5, 7, '*');
    expect(e.value).toBe('Pray *🤲* now');
  });

  it('keeps selection and replace range consistent with the result', () => {
    const v = 'A *B* and C word here';
    for (const [sel, mark] of [
      ['word', '*'],
      ['C word', '_'],
      ['*B*', '*'],
    ]) {
      const r = pick(v, sel, mark);
      expect(r.value).toBe(v.slice(0, r.from) + r.text + v.slice(r.to));
      expect(r.start).toBeGreaterThanOrEqual(0);
      expect(r.end).toBeLessThanOrEqual(r.value.length);
      expect(r.start).toBeLessThan(r.end);
    }
  });

  it('is its own inverse for a plain selection', () => {
    for (const mark of ['*', '_']) {
      const v = 'Plain text with several words';
      const on = pick(v, 'several words', mark);
      const off = toggle(on.value, on.start, on.end, mark);
      expect(off.value).toBe(v);
    }
  });

  it('always renders back as the styled text it was given (property check)', () => {
    const words = ['Yousuf', 'help', 'Rs.', '5,000', 'today', 'دعا', '💔', 'now'];
    let seed = 7;
    const rnd = (n) => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) % n;
    for (let i = 0; i < 300; i++) {
      const text = Array.from({ length: 2 + rnd(6) }, () => words[rnd(words.length)]).join(' ');
      const a = rnd(text.length),
        z = a + 1 + rnd(text.length - a);
      const r = toggle(text, a, z, rnd(2) ? '*' : '_');
      if (!r.changed) continue;
      expect(r.value).toBe(text.slice(0, r.from) + r.text + text.slice(r.to));
      // The styled block must not leave stray markers behind.
      const tag = r.text.includes('*') ? 'strong' : 'em';
      expect(render(r.value)).toContain('<' + tag + '>');
    }
  });
});

describe('lineBounds', () => {
  it('returns the line around the cursor', () => {
    expect(lineBounds('one\ntwo\nthree', 5)).toEqual([4, 7]);
    expect(lineBounds('one', 1)).toEqual([0, 3]);
  });
});
