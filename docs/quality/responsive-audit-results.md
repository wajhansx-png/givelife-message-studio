# Responsive verification — 2026-11-04

Result: 27 UI states across eight viewport/theme combinations (216 state checks). All recorded checks passed using the isolated fake transport and local Chromium.

| CSS viewport | Theme | States | Control checks | Rendered element checks | Failures |
| --- | --- | ---: | ---: | ---: | ---: |
| 320 × 256 | dark | 27 | 368 | 1187 | 0 |
| 320 × 568 | light | 27 | 368 | 1187 | 0 |
| 390 × 844 | dark | 27 | 387 | 1219 | 0 |
| 640 × 400 | light | 27 | 386 | 1209 | 0 |
| 740 × 360 | dark | 27 | 387 | 1210 | 0 |
| 768 × 1024 | light | 27 | 387 | 1219 | 0 |
| 1280 × 800 | dark | 27 | 393 | 1244 | 0 |
| 1920 × 1080 | light | 27 | 395 | 1247 | 0 |

Totals: 3,071 control checks and 9,722 rendered element checks. Counts include repeated elements across states and sizes.

Focused browser verification also passed: 13 Donors tests, two focused-message editor tests, two DM editor tests, three Notes tests, and seven sending-panel layout tests. Combined with the eight matrix tests, that is 35 passing browser tests. Eight donor recovery / volunteer timing unit tests passed. Changed production JavaScript and audit helpers passed syntax checks.

The final focused run passed 15/15; the earlier unaffected DM, Notes and sending-panel runs contributed the other 12 passing focused checks. Volunteer timing tests now extract functions using the existing AST helper, so source formatting cannot truncate a tested function.

The fixes cover donor header/filter stacking, long names, 44px primary row controls, the expanded/folded Resume/Hide dock, modal scroll insets, preview tool labels, Notes toolbar width, and volunteer/research controls. On very short screens, oversized sticky tools enter document flow so fields remain reachable.

See [the audit contract](responsive-audit.md) for references, commands and limits. The 640 × 400 and 320 × 256 cases simulate reduced CSS viewport space at 200% and 400% zoom; physical devices, real keyboards and assistive technology remain separate verification. CI stores complete per-control JSON reports, screenshots and failure traces.
