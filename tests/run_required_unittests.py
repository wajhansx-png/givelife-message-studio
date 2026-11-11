"""Run the Python suite and fail when a test is unexpectedly skipped."""

import sys
import unittest


suite = unittest.defaultTestLoader.discover("tests")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    print("Required tests were skipped:", file=sys.stderr)
    for test, reason in result.skipped:
        print(f"- {test}: {reason}", file=sys.stderr)
sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
