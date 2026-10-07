import unittest
from app.social.inline_charts import attach_reply_resources


class InlineChartLayoutTests(unittest.TestCase):
    def test_history_restores_each_chart_on_its_own_turn(self):
        history = [{"type": "final", "content": "结论一\n[[chart:v1]]"},
                   {"role": "assistant", "content": "结论二\n[[chart:r2]]"}]
        resources = [{"file_id": "r1", "visual_id": "v1"}, {"file_id": "r2", "visual_id": "v2"}]
        attach_reply_resources(history, resources)
        self.assertEqual(history[0]["attachments"], [resources[0]])
        self.assertEqual(history[1]["attachments"], [resources[1]])

    def test_duplicate_references_and_existing_files_are_preserved(self):
        resource = {"file_id": "r1", "visual_id": "v1"}
        history = [{"type": "user", "content": "[[chart:v1]]"},
                   {"type": "final", "content": "[[chart:v1]] [[chart:v1]]", "attachments": [resource]}]
        attach_reply_resources(history, [resource, {"file_id": "document"}])
        self.assertNotIn("attachments", history[0])
        self.assertEqual([r["file_id"] for r in history[1]["attachments"]], ["r1", "document"])

    def test_missing_reference_does_not_replace_text(self):
        history = [{"type": "final", "content": "[[chart:missing]]"}]
        attach_reply_resources(history, [])
        self.assertEqual(history[0]["content"], "[[chart:missing]]")
