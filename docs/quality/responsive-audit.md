# Responsive layout contract

References reviewed for this app:

- [GitHub Primer React](https://github.com/primer/react), especially [PageLayout](https://github.com/primer/react/tree/main/packages/react/src/PageLayout): bounded flexible panes, shared spacing, responsive arrangements and named scrolling regions.
- [Primer layout foundations](https://primer.style/product/getting-started/foundations/layout/): narrow/regular/wide layouts, with finer adjustments when content needs them.
- [Adobe Spectrum layout](https://react-spectrum.adobe.com/v3/layout.html): flex/grid arrangements that adapt to available space and preserve functionality.
- [WCAG reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) and [target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html). The AA minimum is 24 CSS px with documented exceptions; this app aims for 44px primary phone controls.

These are references for the existing vanilla JS/CSS app, not claims about any product's private implementation or a certification of accessibility.

## Contracts

1. Every rendered element stays within the horizontal viewport or an intentional scroll container.
2. Every rendered enabled control can be reached after scrolling; another layer must not completely cover it.
3. Labels wrap legibly. Explicit two-line donor name truncation preserves the full name in its management form.
4. Main donor actions, star, row menu, DM and status controls have 44px phone targets. Icon controls retain accessible names.
5. The bottom dock reserves space for its controls. On short screens, status details scroll independently while primary actions remain visible.
6. Modal dialogs scroll internally, stay within the viewport, and retain reachable exits.
7. Editors retain readable text and scroll when content exceeds available space. Keyboard-sized windows must preserve an editable surface.
8. Expanding, hiding and scheduled states are checked separately. No UI navigation or measurement activates a send.

## Repeatable audit

`tests/e2e/responsive-elements.spec.cjs` opens 27 named states including menus, dialogs, editors, Notes and research forms. `element-audit.cjs` inspects every rendered element for horizontal clipping and records every visible control's geometry, label, target size, and reachability.

The full matrix includes 320, 390, 768, 1280 and 1920px widths, phone landscape, and 640×400 / 320×256 CSS viewports to exercise 200% / 400% reflow-equivalent space. These are local Chromium simulations, not physical device or OS keyboard tests. Focused tests additionally cover long names, donor counts, 44px targets, Hide/resume overlap, text editing, and keyboard-sized windows.

Run against the isolated fake transport:

```sh
corepack pnpm exec playwright test tests/e2e/responsive-elements.spec.cjs
ELEMENT_AUDIT_SMOKE=1 corepack pnpm exec playwright test tests/e2e/responsive-elements.spec.cjs
corepack pnpm exec playwright test tests/e2e/donors-mobile.spec.cjs
```

JSON reports are written to `test-results/element-audit/` and attached to the Playwright results. Reports enumerate actual checked controls and failures, rather than treating a screenshot alone as proof. Hidden conditional states, assistive technology behavior, and physical devices require additional checks; passing this audit is not a blanket compliance claim.

## Formatter baseline

The existing Prettier gate also flags legacy sections of `comfort.css`, `donors.js` and `tests/e2e/donors-mobile.spec.cjs` at base commit `18f5cb8`. Newly added audit files and the changed formatted helper files pass Prettier. The recorded browser and unit results are independent of that existing repository-wide formatting debt.
