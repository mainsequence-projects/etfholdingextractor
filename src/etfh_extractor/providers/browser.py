from __future__ import annotations


def fetch_page_html_with_playwright(
    url: str,
    *,
    wait_for_text: str | None = None,
    timeout: float = 30.0,
    browser_name: str = "chromium",
    headless: bool = True,
) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install browser runtime support before using browser-backed provider fallbacks."
        ) from exc

    timeout_ms = int(timeout * 1000)
    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_name, None)
            if browser_type is None:
                raise RuntimeError(f"Unsupported Playwright browser: {browser_name!r}")
            browser = browser_type.launch(headless=headless)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_for_text:
                    page.get_by_text(wait_for_text, exact=False).first.wait_for(
                        state="visible",
                        timeout=timeout_ms,
                    )
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
                except PlaywrightTimeoutError:
                    pass
                return page.content()
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"Browser fetch timed out for {url}") from exc


def capture_response_text_with_playwright(
    page_url: str,
    *,
    response_url_substring: str,
    exclude_response_url_substring: str | None = None,
    timeout: float = 30.0,
    browser_name: str = "chromium",
    headless: bool = True,
) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install browser runtime support before using browser-backed provider fallbacks."
        ) from exc

    timeout_ms = int(timeout * 1000)
    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_name, None)
            if browser_type is None:
                raise RuntimeError(f"Unsupported Playwright browser: {browser_name!r}")
            browser = browser_type.launch(headless=headless)
            page = browser.new_page()
            try:
                with page.expect_response(
                    lambda response: (
                        response_url_substring in response.url
                        and (
                            exclude_response_url_substring is None
                            or exclude_response_url_substring not in response.url
                        )
                    ),
                    timeout=timeout_ms,
                ) as response_info:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                return response_info.value.text()
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Timed out waiting for response containing {response_url_substring!r} from {page_url}"
        ) from exc
