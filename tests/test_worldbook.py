import json
import tempfile
import unittest
from pathlib import Path

from story_harness.world.worldbook import Worldbook


class WorldbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "worldbook.json"
        self.path.write_text(
            json.dumps(
                {
                    "package_id": "sample",
                    "version": "1.0.0",
                    "entries": [
                        {"id": "hall", "text": "大厅的窗户面向庭院", "visibility": "public", "kind": "lore", "source": "sample.docx:1"},
                        {"id": "a_goal", "text": "A 想保护钥匙", "visibility": "actor", "allowed_actors": ["A"]},
                        {"id": "truth", "text": "窗户后藏着真正的线索", "visibility": "secret"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_exact_lookup_filters_secrets_before_returning_content(self) -> None:
        book = Worldbook.load(self.path)

        self.assertEqual(book.get("hall", "B").text, "大厅的窗户面向庭院")
        self.assertEqual(book.get("hall", "B").source, "sample.docx:1")
        self.assertEqual(book.get("a_goal", "A").text, "A 想保护钥匙")
        self.assertIsNone(book.get("a_goal", "B"))
        self.assertIsNone(book.get("truth", "A"))
        self.assertEqual(book.get("truth", "A", grants={"truth"}).entry_id, "truth")
        self.assertEqual(book.get("truth", "system").entry_id, "truth")

    def test_retrieval_excludes_entries_outside_viewer_scope(self) -> None:
        book = Worldbook.load(self.path)

        self.assertEqual([entry.entry_id for entry in book.retrieve("窗户", "A")], ["hall"])
        self.assertEqual(
            [entry.entry_id for entry in book.retrieve("窗户", "A", grants={"truth"})],
            ["hall", "truth"],
        )

    def test_duplicate_entry_ids_are_rejected(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["entries"].append(payload["entries"][0])
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(ValueError):
            Worldbook.load(self.path)


if __name__ == "__main__":
    unittest.main()
