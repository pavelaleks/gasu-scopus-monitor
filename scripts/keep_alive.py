"""Разбудить Streamlit Community Cloud реальным визитом в браузере.

Обычный HTTP GET получает только статическую оболочку SPA и не запускает
Python-процесс. Пустые git-коммиты засоряют историю и вызывают лишний
redeploy — Streamlit больше не считает их активностью.
"""

from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://gasu-scopus-monitor.streamlit.app"
APP_TITLE = "Мониторинг публикаций Scopus"
WAKE_NAME = re.compile(r"get this app back up", re.I)


def visit(url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(120_000)
        try:
            print(f"Opening {url}", flush=True)
            page.goto(url, wait_until="domcontentloaded")

            wake = page.get_by_role("button", name=WAKE_NAME)
            try:
                wake.first.wait_for(state="visible", timeout=8_000)
                print("App is sleeping — clicking wake button", flush=True)
                wake.first.click()
            except PlaywrightTimeout:
                print("Wake button not shown — checking if app is already running", flush=True)

            page.get_by_text(APP_TITLE).first.wait_for(timeout=120_000)
            print("App is awake", flush=True)
        except PlaywrightTimeout as exc:
            snippet = page.inner_text("body")[:800]
            raise SystemExit(f"App did not become ready.\n{snippet}") from exc
        finally:
            browser.close()


def main() -> None:
    url = os.environ.get("STREAMLIT_APP_URL", DEFAULT_URL).strip()
    if not url:
        print("STREAMLIT_APP_URL is empty; nothing to visit", flush=True)
        sys.exit(0)
    visit(url)


if __name__ == "__main__":
    main()
