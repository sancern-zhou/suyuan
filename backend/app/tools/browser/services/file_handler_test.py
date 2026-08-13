import os

import pytest
from playwright.sync_api import sync_playwright

from app.tools.browser.services.file_handler import FileHandler


class FakeDownload:
    suggested_filename = "report.csv"

    def save_as(self, path):
        with open(path, "wb") as output:
            output.write(b"id,value\n1,ok\n")


class FakeDownloadContext:
    def __init__(self, page):
        self.page = page
        self.value = FakeDownload()

    def __enter__(self):
        self.page.expect_download_entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.page.expect_download_exited = True


class FakePage:
    def __init__(self):
        self.clicked_selector = None
        self.expect_download_entered = False
        self.expect_download_exited = False
        self.expect_download_timeout = None

    def expect_download(self, timeout):
        self.expect_download_timeout = timeout
        return FakeDownloadContext(self)

    def click(self, selector):
        assert self.expect_download_entered
        self.clicked_selector = selector


def test_wait_for_download_wraps_click_in_expect_download(tmp_path):
    page = FakePage()
    handler = FileHandler(download_dir=str(tmp_path))

    result = handler.wait_for_download(page, selector="#export", timeout=1234)

    assert page.clicked_selector == "#export"
    assert page.expect_download_timeout == 1234
    assert page.expect_download_exited
    assert result["filename"] == "report.csv"
    assert result["size_kb"] > 0
    assert os.path.exists(result["download_path"])


@pytest.mark.browser
def test_wait_for_download_saves_real_playwright_download(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        try:
            page = context.new_page()
            page.set_content(
                """
                <a id="export"
                   download="browser-report.csv"
                   href="data:text/csv;charset=utf-8,id%2Cvalue%0A1%2Cok%0A">
                   Export
                </a>
                """
            )

            handler = FileHandler(download_dir=str(tmp_path))
            result = handler.wait_for_download(page, selector="#export", timeout=5000)

            assert result["filename"] == "browser-report.csv"
            assert os.path.exists(result["download_path"])
            with open(result["download_path"], encoding="utf-8") as downloaded:
                assert downloaded.read() == "id,value\n1,ok\n"
        finally:
            context.close()
            browser.close()
