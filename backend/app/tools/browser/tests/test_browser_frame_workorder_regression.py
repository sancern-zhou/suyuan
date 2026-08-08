from pathlib import Path

from playwright.sync_api import sync_playwright

from app.tools.browser.snapshot.generator import SnapshotGenerator
from app.tools.browser.actions.interaction import handle_act
from app.tools.browser.refs.ref_resolver import set_global_refs


class _Manager:
    def __init__(self, page):
        self.page = page

    def get_active_page(self, session_id="default"):
        return self.page


def test_snapshot_exposes_working_order_code_inside_iframe(tmp_path: Path):
    child = tmp_path / "child.html"
    child.write_text(
        "<label>工单号：</label>"
        "<input id='WorkingOrderCode' name='WorkingOrderCode'>"
        "<input id='btnSearchSubmit' type='submit' value='查询'>",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.html"
    parent.write_text(f"<iframe src='{child.as_uri()}'></iframe>", encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(parent.as_uri())
        result = SnapshotGenerator().generate(page, include_frames=True, max_refs=20)
        browser.close()

        assert "Frame 1" in result["snapshot"]
        assert "WorkingOrderCode" in str(result["refs"])
        assert any(ref.startswith("f1:") for ref in result["refs"])


def test_fill_fields_can_target_frame_prefixed_refs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.set_content("""
            <iframe name="workorder" srcdoc="
                <input id='WorkingOrderCode' name='WorkingOrderCode' placeholder='工单号'>
            "></iframe>
        """)
        frame = page.frame(name="workorder")
        frame.wait_for_selector("#WorkingOrderCode")

        result = SnapshotGenerator().generate(page, include_frames=True, max_refs=20)
        set_global_refs(result["refs"])
        work_order_ref = next(ref for ref, data in result["refs"].items()
                              if data.get("html_attrs", {}).get("id") == "WorkingOrderCode")

        handle_act(
            _Manager(page),
            fill_fields=[{"ref": work_order_ref, "type": "text", "value": "CH2605271779891926742"}],
        )

        assert frame.locator("#WorkingOrderCode").input_value() == "CH2605271779891926742"
        browser.close()
