import unittest
import gc
import os
import tempfile
from datetime import datetime, timedelta
from voice_flow.storage import StorageEngine

class TestInsightsDeep(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self.temp_dir.name, "test_insights.db")
        self.storage = StorageEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_insights_empty_database(self):
        """Test get_insights returns correct zero-state values on an empty database."""
        res = self.storage.get_insights(range_filter="all")
        self.assertEqual(res["total_words"], 0)
        self.assertEqual(res["avg_wpm"], 0)
        self.assertEqual(res["dictation_count"], 0)
        self.assertEqual(res["time_saved_hours"], 0)
        self.assertEqual(res["time_saved_minutes"], 0)
        self.assertEqual(res["speed_multiplier"], 1.0)
        self.assertEqual(res["streak"], 0)
        self.assertEqual(res["words_corrected"], 0)
        self.assertEqual(res["dictionary_fixes"], 0)
        self.assertEqual(len(res["app_breakdown"]), 0)
        self.assertEqual(len(res["daily_activity"]), 28)
        self.assertTrue(all(day["words"] == 0 and day["level"] == 0 for day in res["daily_activity"]))
        self.assertEqual(res["voice_profile"]["archetype"], "Getting Started")
        self.assertFalse(res["voice_profile"]["vocabulary_unlocked"])

    def test_insights_populated_calculations(self):
        """Test get_insights calculates real metrics from stored history records."""
        # 1. Coding in VS Code
        self.storage.add_dictation(
            raw_text="function calculate sum a b return a plus b",
            polished_text="function calculateSum(a, b) { return a + b; }",
            app_name="Visual Studio Code",
            duration_sec=3.0
        )

        # 2. Communication in Slack
        self.storage.add_dictation(
            raw_text="hey team we are deploying the new release today please test",
            polished_text="Hey team, we are deploying the new release today. Please test.",
            app_name="Slack",
            duration_sec=4.0
        )

        res = self.storage.get_insights(range_filter="all")
        self.assertEqual(res["dictation_count"], 2)
        self.assertGreater(res["total_words"], 0)
        self.assertGreater(res["avg_wpm"], 0)
        self.assertGreater(res["time_saved_minutes"], 0)
        self.assertGreater(res["speed_multiplier"], 1.0)
        self.assertEqual(len(res["app_breakdown"]), 2)
        
        apps = {a["app_name"]: a for a in res["app_breakdown"]}
        self.assertIn("Visual Studio Code", apps)
        self.assertEqual(apps["Visual Studio Code"]["category"], "Coding")
        self.assertIn("Slack", apps)
        self.assertEqual(apps["Slack"]["category"], "Communication")

    def test_insights_time_range_filter(self):
        """Test 7d, 30d, and all time range filtering."""
        now = datetime.now()
        
        # Today
        self.storage.add_dictation(
            raw_text="today quick note",
            polished_text="Today quick note.",
            app_name="Notion",
            duration_sec=2.0
        )
        
        # 15 days ago
        d_15_ago = (now - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        with self.storage._get_conn() as conn:
            conn.execute(
                "INSERT INTO history (raw_text, polished_text, app_name, duration_sec, timestamp, word_count, wpm_speed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("fifteen days ago note", "Fifteen days ago note.", "Notion", 2.0, d_15_ago, 4, 120)
            )

        # 45 days ago
        d_45_ago = (now - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
        with self.storage._get_conn() as conn:
            conn.execute(
                "INSERT INTO history (raw_text, polished_text, app_name, duration_sec, timestamp, word_count, wpm_speed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("forty five days ago note", "Forty five days ago note.", "Notion", 2.0, d_45_ago, 5, 150)
            )

        res_7d = self.storage.get_insights(range_filter="7d")
        self.assertEqual(res_7d["dictation_count"], 1)

        res_30d = self.storage.get_insights(range_filter="30d")
        self.assertEqual(res_30d["dictation_count"], 2)

        res_all = self.storage.get_insights(range_filter="all")
        self.assertEqual(res_all["dictation_count"], 3)

    def test_insights_voice_archetypes(self):
        """Test voice archetype classification rules."""
        self.storage.add_dictation(
            raw_text="def async function test connection with retry loop and timeout exception handling",
            polished_text="def async function test connection with retry loop and timeout exception handling",
            app_name="Cursor",
            duration_sec=5.0
        )
        res = self.storage.get_insights(range_filter="all")
        self.assertEqual(res["voice_profile"]["archetype"], "The Code Architect")
        self.assertEqual(res["voice_profile"]["archetype_tag"], "Engineering Flow")

    def test_insights_daily_activity_levels(self):
        """Test 28-day matrix intensity levels."""
        today = datetime.now().strftime("%Y-%m-%d")
        long_text = " ".join(["word"] * 120)
        self.storage.add_dictation(
            raw_text=long_text,
            polished_text=long_text,
            app_name="Chrome",
            duration_sec=40.0
        )

        res = self.storage.get_insights(range_filter="all")
        today_activity = next((d for d in res["daily_activity"] if d["date"] == today), None)
        self.assertIsNotNone(today_activity)
        self.assertEqual(today_activity["words"], 120)
        self.assertEqual(today_activity["level"], 2)

if __name__ == "__main__":
    unittest.main()
