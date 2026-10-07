import unittest
from app.social.inline_charts import attach_reply_resources


class InlineChartLayoutTests(unittest.TestCase):
    def test_static_image_beats_its_spec_and_stays_on_the_referenced_turn(self):
        spec = {"file_id": "s1", "visual_id": "v1", "resource_key": "chart-spec", "interactive": False}
        image = {"file_id": "i1", "visual_id": "v1", "mime_type": "image/png"}
        for resources in ([spec, image], [image, spec]):
            history = [{"type": "final", "content": "[[chart:v1]]"}, {"type": "final", "content": "下一轮"}]
            attach_reply_resources(history, resources)
            self.assertEqual(history[0]["attachments"], [image])
            self.assertEqual(history[1]["attachments"], [])

    def test_interactive_spec_beats_its_image_rendition(self):
        spec = {"file_id": "s1", "visual_id": "v1", "resource_key": "chart-spec", "interactive": True}
        image = {"file_id": "i1", "visual_id": "v1", "mime_type": "image/png"}
        history = [{"type": "final", "content": "[[chart:v1]]"}]
        attach_reply_resources(history, [spec, image])
        self.assertEqual(history[0]["attachments"], [spec])

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
        self.assertEqual([r["file_id"] for r in history[1]["attachments"]], ["r1"])

    def test_missing_reference_does_not_replace_text(self):
        history = [{"type": "final", "content": "[[chart:missing]]"}]
        attach_reply_resources(history, [])
        self.assertEqual(history[0]["content"], "[[chart:missing]]")

    def test_run_resources_go_to_their_own_reply_not_the_latest(self):
        history = [{"type": "user"}, {"type": "tool_result", "data": {"run_id": "run1"}},
                   {"type": "final", "content": "第一轮"}, {"type": "user"},
                   {"type": "final", "data": {"run_id": "run2"}, "content": "第二轮"}]
        resources = [{"file_id": "f1", "run_id": "run1"}, {"file_id": "f2", "run_id": "run2"}, {"file_id": "unknown"}]
        attach_reply_resources(history, resources)
        self.assertEqual(history[2]["attachments"], [resources[0]])
        self.assertEqual(history[4]["attachments"], [resources[1]])

    def test_tool_messages_with_assistant_role_do_not_claim_final_resources(self):
        history = [{"type": "tool_result", "role": "assistant", "data": {"run_id": "r1"}}, {"type": "final"}]
        attach_reply_resources(history, [{"file_id": "document", "run_id": "r1"}])
        self.assertNotIn("attachments", history[0])
        self.assertEqual(history[1]["attachments"][0]["file_id"], "document")
