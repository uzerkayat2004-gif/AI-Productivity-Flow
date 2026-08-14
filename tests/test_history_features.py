import unittest
import gc
from voice_flow.storage import StorageEngine
import os
import tempfile

class TestHistoryFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self.temp_dir.name, "test_voice_flow.db")
        self.storage = StorageEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_add_and_pin_dictation(self):
        rec = self.storage.add_dictation(
            raw_text="hello world",
            polished_text="Hello world.",
            app_name="Visual Studio Code",
            duration_sec=3.5,
            style_mode="formal"
        )
        self.assertIsNotNone(rec.id)

        history = self.storage.get_recent_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["is_pinned"], 0)

        # Pin
        pin_res = self.storage.toggle_history_pin(rec.id)
        self.assertTrue(pin_res.get("success", False))
        self.assertTrue(pin_res.get("is_pinned", False))

        history_pinned = self.storage.get_recent_history()
        self.assertEqual(history_pinned[0]["is_pinned"], 1)

        # Unpin
        unpin_res = self.storage.toggle_history_pin(rec.id)
        self.assertTrue(unpin_res.get("success", False))
        self.assertFalse(unpin_res.get("is_pinned", True))

    def test_pinned_records_sort_first(self):
        rec1 = self.storage.add_dictation("first", "First.", "Chrome", 2.0)
        rec2 = self.storage.add_dictation("second", "Second.", "Notion", 2.0)
        rec3 = self.storage.add_dictation("third", "Third.", "Slack", 2.0)

        # Pin first record
        self.storage.toggle_history_pin(rec1.id)

        history = self.storage.get_recent_history()
        # Pinned rec1 should be at index 0, followed by rec3, rec2
        self.assertEqual(history[0]["id"], rec1.id)
        self.assertEqual(history[0]["is_pinned"], 1)
        self.assertEqual(history[1]["id"], rec3.id)
        self.assertEqual(history[2]["id"], rec2.id)

    def test_delete_history_record(self):
        rec = self.storage.add_dictation("temp", "Temp.", "Terminal", 1.0)
        self.assertEqual(len(self.storage.get_recent_history()), 1)

        del_res = self.storage.delete_history_record(rec.id)
        self.assertIsNotNone(del_res)
        self.assertEqual(del_res["id"], rec.id)
        self.assertEqual(len(self.storage.get_recent_history()), 0)

    def test_insights_metrics_dynamic(self):
        self.storage.add_dictation("one two three", "One two three.", "Visual Studio Code", 3.0)
        self.storage.add_dictation("four five six seven", "Four five six seven.", "Google Chrome", 4.0)

        insights = self.storage.get_insights()
        self.assertEqual(insights["total_words"], 7)
        self.assertGreater(insights["avg_wpm"], 0)
        self.assertIn("app_breakdown", insights)
        app_names = [a["app_name"] for a in insights["app_breakdown"]]
        self.assertTrue(any("Visual Studio Code" in name or "VS Code" in name for name in app_names))

if __name__ == "__main__":
    unittest.main()
