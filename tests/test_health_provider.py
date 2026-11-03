"""/health reports which AI model is configured, for the footer and Settings badge."""

import os, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app


class HealthProvider(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        os.environ.pop("DEEPSEEK_API_KEY", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)

    def body(self):
        h = app.Handler.__new__(app.Handler)
        out = []
        h.reply = lambda b: out.append(b) or b
        h.path = "/health"
        h.do_GET()
        return out[-1]

    def test_not_connected_when_no_key(self):
        self.assertEqual(self.body()["ai_provider"], "Not connected")

    def test_deepseek_when_key_set(self):
        os.environ["DEEPSEEK_API_KEY"] = "d-key"
        self.assertIn("DeepSeek", self.body()["ai_provider"])


if __name__ == "__main__":
    unittest.main()
