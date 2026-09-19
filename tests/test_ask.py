"""Natural-language ask command tests."""

import unittest
from tiltlock.ask import interpret


class TestAsk(unittest.TestCase):
    def test_intents(self):
        self.assertEqual(interpret("why did I get locked?"), "review")
        self.assertEqual(interpret("run the demo"), "demo")
        self.assertEqual(interpret("show status"), "status")
        self.assertEqual(interpret("unlock please"), "unlock")
        self.assertEqual(interpret("hello"), "help")


if __name__ == "__main__":
    unittest.main()
