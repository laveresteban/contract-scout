"""Selenium UI checks for cross-source de-duplication.

Headless Chrome (driver resolved by Selenium Manager). The app under test is the
running frontend dev server; set APP_URL to point elsewhere.
"""

import os
import sys

from getgauge.python import after_suite, before_suite, step
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(__file__))  # make sibling modules importable
from dedup_key import dedup_key

APP_URL = os.getenv("APP_URL", "http://localhost:5173")
_driver = None


def _wait():
    return WebDriverWait(_driver, 20)


@before_suite
def start_browser():
    global _driver
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1600")
    _driver = webdriver.Chrome(options=options)


@after_suite
def stop_browser():
    if _driver is not None:
        _driver.quit()


def _card_fields(card):
    def _text(css):
        found = card.find_elements(By.CSS_SELECTOR, css)
        return found[0].text.strip() if found else ""

    return {
        "title": _text(".job-title-button"),
        "company": _text(".company"),
        "location": _text(".location"),
    }


def _visible_cards():
    # Exclude loading skeletons (they share .job-card but carry no posting text).
    return _driver.find_elements(
        By.CSS_SELECTOR, "article.job-card:not(.skeleton-card)"
    )


@step("Open the Contract Scout app")
def open_app():
    _driver.get(APP_URL)
    _wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, "#search-query")))


@step("Search the UI for <query>")
def search_for(query):
    # Type to use the app's debounced incremental search (lists stored jobs; no
    # live scrape) so the E2E is deterministic against the seeded dataset.
    box = _wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#search-query")))
    box.clear()
    box.send_keys(query)
    # Wait past the skeleton state for a real, populated result card.
    _wait().until(
        lambda d: any(
            c.find_elements(By.CSS_SELECTOR, ".job-title-button")
            and c.find_element(By.CSS_SELECTOR, ".job-title-button").text.strip()
            for c in _visible_cards()
        )
    )


@step("No two visible job cards are duplicates")
def assert_cards_unique():
    seen = {}
    for card in _visible_cards():
        fields = _card_fields(card)
        key = dedup_key(**fields)
        assert key not in seen, (
            f"Duplicate cards render for the same posting: "
            f"{fields} vs {seen[key]}"
        )
        seen[key] = fields


@step("The role <title> appears exactly once")
def assert_role_once(title):
    matches = [
        c for c in _visible_cards()
        if title.lower() in _card_fields(c)["title"].lower()
    ]
    assert len(matches) == 1, (
        f"Expected exactly one card for '{title}', found {len(matches)}: "
        f"{[_card_fields(c) for c in matches]}"
    )


# --- short-list guardrail --------------------------------------------------
_count_before_reveal = 0


@step("The guardrail offers to reveal hidden matches")
def assert_guardrail_offers():
    global _count_before_reveal
    banner = _wait().until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-testid=guardrail-banner]"))
    )
    assert "hidden" in banner.text.lower(), f"Unexpected guardrail text: {banner.text!r}"
    _count_before_reveal = len(_visible_cards())


@step("Revealing hidden matches shows more results")
def reveal_hidden():
    _driver.find_element(By.CSS_SELECTOR, "[data-testid=guardrail-toggle]").click()
    _wait().until(lambda d: len(_visible_cards()) > _count_before_reveal)
    banner = _driver.find_element(By.CSS_SELECTOR, "[data-testid=guardrail-banner]")
    assert "hide them" in banner.text.lower(), (
        f"Banner should switch to a restore action, got: {banner.text!r}"
    )
