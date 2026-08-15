from playwright.sync_api import sync_playwright

from app.tools.browser.actions.execute_js import handle_execute_js


class Manager:
    def __init__(self, page):
        self.page = page

    def get_active_page(self, session_id="default"):
        return self.page


def test_execute_js_accepts_bare_multi_statement_script():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.set_content(
            """
            <a role="menuitem" href="javascript:void(0)">工单信息管理</a>
            <script>
            window.clicked = false;
            document.querySelector('a').addEventListener('click', () => {
              window.clicked = true;
            });
            </script>
            """
        )

        result = handle_execute_js(
            Manager(page),
            """
            var items = document.querySelectorAll('a[role="menuitem"]');
            for (var i = 0; i < items.length; i++) {
              if (items[i].textContent.includes('工单信息管理')) {
                items[i].click();
                return 'clicked';
              }
            }
            return 'not found';
            """,
        )

        assert result["type"] == "string"
        assert result["result"] == "clicked"
        assert page.evaluate("window.clicked") is True

        browser.close()
