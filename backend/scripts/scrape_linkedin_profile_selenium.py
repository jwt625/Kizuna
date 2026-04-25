from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_FIREFOX_PROFILE = str(Path.home() / "Library/Application Support/Firefox/Profiles/9ons1v9u.default-release")
DEFAULT_OUTPUT = Path("../import/linkedin_profile_probe.json")
DEFAULT_PFP_CACHE_DIR = Path("../import/linkedin_pfpcache")
SHOW_MORE_PATTERNS = ("show more", "show all", "see more", "… more", "... more")
SECTION_STOP_MARKERS = ("Profile language", "Who your viewers also viewed", "About", "Questions?", "Select language")
TOP_CARD_STOP_MARKERS = ("Highlights", "Featured", "Activity", "Experience", "About")
SKILL_FILTER_PATTERNS = (
    re.compile(r"^Skills$", re.I),
    re.compile(r"^All$", re.I),
    re.compile(r"^Industry Knowledge$", re.I),
    re.compile(r"^Tools & Technologies$", re.I),
    re.compile(r"endorsement", re.I),
    re.compile(r"^Endorsed by ", re.I),
)
DATE_LINE_RE = re.compile(
    r"((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\s+[–-]\s+((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|Present))|(\d{4}\s+[–-]\s+\d{4})"
)
MUTUAL_CONNECTIONS_RE = re.compile(r"(?:(\d[\d,]*) other mutual connections|(\d[\d,]*) mutual connections)", re.I)
INSTITUTION_RE = re.compile(r"(University|School|College|Institute|Academy|Laboratory|Lab|Center|Gymnasium)", re.I)


def build_firefox_driver(profile_path: str, headless: bool) -> webdriver.Firefox:
    firefox_options = Options()
    firefox_options.add_argument(f"--profile={profile_path}")
    firefox_options.add_argument("--width=1920")
    firefox_options.add_argument("--height=1080")

    if headless:
        firefox_options.add_argument("--headless")

    firefox_options.set_preference("dom.webdriver.enabled", False)
    firefox_options.set_preference("useAutomationExtension", False)
    firefox_options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    )
    firefox_options.set_preference("toolkit.telemetry.enabled", False)
    firefox_options.set_preference("toolkit.telemetry.unified", False)
    firefox_options.set_preference("datareporting.healthreport.uploadEnabled", False)
    firefox_options.set_preference("datareporting.policy.dataSubmissionEnabled", False)
    firefox_options.set_preference("network.http.sendRefererHeader", 2)
    firefox_options.set_preference("network.http.sendSecureXSiteReferrer", True)
    firefox_options.set_preference("media.peerconnection.enabled", False)

    return webdriver.Firefox(options=firefox_options)


def normalize_profile_url(url: str) -> str:
    return url.rstrip("/")


def slug_from_profile_url(profile_url: str) -> str:
    return profile_url.rstrip("/").split("/")[-1]


def wait_for_main(driver: webdriver.Firefox) -> None:
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "main")))


def ensure_logged_in(driver: webdriver.Firefox, requested_url: str) -> None:
    current = driver.current_url
    if any(token in current for token in ("/login", "/checkpoint", "/signup", "/uas/authwall")):
        raise RuntimeError(
            f"LinkedIn requires login for {requested_url}. Log into the same Firefox profile, close Firefox, then rerun."
        )
    if "linkedin.com" not in urlparse(current).netloc:
        raise RuntimeError(f"Unexpected redirect while opening {requested_url}: {current}")


def click_expand_buttons(driver: webdriver.Firefox) -> int:
    clicked_total = 0
    for _ in range(8):
        clicked_round = 0
        for button in driver.find_elements(By.CSS_SELECTOR, "button, a[role='button']"):
            try:
                if not button.is_displayed():
                    continue
                text = " ".join(button.text.split()).strip()
                if not text or not any(pattern in text.lower() for pattern in SHOW_MORE_PATTERNS):
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.5)
                clicked_round += 1
                clicked_total += 1
            except WebDriverException:
                continue
        if clicked_round == 0:
            break
    return clicked_total


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def trim_lines(lines: list[str], stop_markers: tuple[str, ...]) -> list[str]:
    trimmed: list[str] = []
    for line in lines:
        if any(marker.lower() in line.lower() for marker in stop_markers):
            break
        trimmed.append(line)
    return trimmed


def is_date_line(line: str) -> bool:
    return bool(DATE_LINE_RE.search(line))


def looks_like_institution(line: str) -> bool:
    return bool(INSTITUTION_RE.search(line))


def extract_section_text(driver: webdriver.Firefox) -> str:
    selector_candidates = [
        "main#workspace > div > div > div:first-child > div",
        "main#workspace > div > div > div:first-child",
        "main#workspace > div > div",
        "main#workspace",
        "main",
    ]
    raw_text = ""
    for selector in selector_candidates:
        try:
            raw_text = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
            if raw_text:
                break
        except WebDriverException:
            continue
    lines = trim_lines(split_lines(raw_text), SECTION_STOP_MARKERS)
    return "\n".join(lines)


def split_next_header(lines: list[str], section_name: str) -> tuple[list[str], list[str]]:
    if not lines:
        return [], []
    if section_name == "education":
        if len(lines) >= 2 and looks_like_institution(lines[-2]):
            return lines[:-2], lines[-2:]
        if looks_like_institution(lines[-1]):
            return lines[:-1], lines[-1:]
    if section_name == "experience":
        if len(lines) >= 2 and all(not is_date_line(item) for item in lines[-2:]):
            return lines[:-2], lines[-2:]
        if len(lines) >= 1 and not is_date_line(lines[-1]):
            return lines[:-1], lines[-1:]
    return lines, []


def parse_timeline_entries(section_name: str, clean_text: str) -> list[dict[str, object]]:
    lines = split_lines(clean_text)
    if lines and lines[0].lower() == section_name.lower():
        lines = lines[1:]
    date_indices = [index for index, line in enumerate(lines) if is_date_line(line)]
    if not date_indices:
        return [{"header": lines, "date_range": None, "details": []}] if lines else []

    entries: list[dict[str, object]] = []
    header = lines[: date_indices[0]]

    for position, date_index in enumerate(date_indices):
        next_date_index = date_indices[position + 1] if position + 1 < len(date_indices) else len(lines)
        trailing_lines = lines[date_index + 1 : next_date_index]
        if position + 1 < len(date_indices):
            details, next_header = split_next_header(trailing_lines, section_name)
        else:
            details, next_header = trailing_lines, []
        entries.append(
            {
                "header": header,
                "date_range": lines[date_index],
                "details": details,
            }
        )
        header = next_header

    if header:
        if entries:
            entries[-1]["details"] = [*entries[-1]["details"], *header]
        else:
            entries.append({"header": header, "date_range": None, "details": []})
    return entries


def parse_skills(clean_text: str) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    for line in split_lines(clean_text):
        if "nothing to see for now" in line.lower():
            return []
        if "skills that " in line.lower() and " will appear here" in line.lower():
            return []
        if any(pattern.search(line) for pattern in SKILL_FILTER_PATTERNS):
            continue
        if line in seen:
            continue
        seen.add(line)
        skills.append(line)
    return skills


def parse_top_card(driver: webdriver.Firefox) -> dict[str, object]:
    raw_lines = trim_lines(split_lines(driver.find_element(By.TAG_NAME, "main").text), TOP_CARD_STOP_MARKERS)
    filtered_lines = [
        line
        for line in raw_lines
        if line not in {"·", "Contact info", "Message", "More"} and not re.fullmatch(r"·\s*\d+(?:st|nd|rd|th)", line)
    ]
    name = filtered_lines[0] if filtered_lines else None
    headline = filtered_lines[1] if len(filtered_lines) > 1 else None
    location = next(
        (
            line
            for line in filtered_lines[2:]
            if "connections" not in line.lower()
            and "mutual" not in line.lower()
            and "private to you" not in line.lower()
            and line not in {"Open to", "Add section", "Enhance profile", "Resources", "Suggested for you"}
            and "http" not in line
        ),
        None,
    )
    mutual_line = next((line for line in filtered_lines if "mutual connections" in line.lower()), None)
    match = MUTUAL_CONNECTIONS_RE.search(mutual_line or "")
    mutual_count_text = match.group(1) or match.group(2) if match else None
    mutual_count = int(mutual_count_text.replace(",", "")) if mutual_count_text else None
    return {
        "top_card_lines": filtered_lines,
        "name": name,
        "headline": headline,
        "location": location,
        "mutual_connections_text": mutual_line,
        "mutual_connections_count": mutual_count,
    }


def choose_profile_photo(driver: webdriver.Firefox) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for image in driver.find_elements(By.CSS_SELECTOR, "main img"):
        try:
            current_src = driver.execute_script("return arguments[0].currentSrc || arguments[0].src || null;", image)
            natural_width = int(driver.execute_script("return arguments[0].naturalWidth || 0;", image))
            natural_height = int(driver.execute_script("return arguments[0].naturalHeight || 0;", image))
            if not current_src or "profile-displayphoto" not in current_src:
                continue
            candidates.append(
                {
                    "src": image.get_attribute("src"),
                    "current_src": current_src,
                    "srcset": image.get_attribute("srcset"),
                    "natural_width": natural_width,
                    "natural_height": natural_height,
                }
            )
        except WebDriverException:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate["natural_width"], candidate["natural_height"]))


def download_profile_photo(photo_url: str, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(photo_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        output_path.write_bytes(response.read())
    return str(output_path)


def scrape_section(driver: webdriver.Firefox, profile_url: str, section_slug: str, section_name: str) -> dict[str, object]:
    section_url = f"{profile_url}/details/{section_slug}/"
    driver.get(section_url)
    wait_for_main(driver)
    time.sleep(2)
    clicks = click_expand_buttons(driver)
    clean_text = extract_section_text(driver)
    result: dict[str, object] = {
        "url": section_url,
        "title": driver.title,
        "expanded_clicks": clicks,
        "clean_text": clean_text,
    }
    if section_name == "skills":
        result["items"] = parse_skills(clean_text)
    else:
        result["items"] = parse_timeline_entries(section_name, clean_text)
    return result


def scrape_profile_with_driver(
    driver: webdriver.Firefox,
    profile_url: str,
    pfp_cache_dir: Path,
) -> dict[str, object]:
    profile_url = normalize_profile_url(profile_url)
    driver.get(profile_url)
    wait_for_main(driver)
    time.sleep(2)
    ensure_logged_in(driver, profile_url)

    top_card = parse_top_card(driver)
    profile_photo = choose_profile_photo(driver)
    cached_photo_path = None
    if profile_photo and profile_photo["current_src"]:
        cached_photo_path = download_profile_photo(
            profile_photo["current_src"],
            pfp_cache_dir / f"{slug_from_profile_url(profile_url)}.jpg",
        )

    return {
        "profile_url": profile_url,
        "page_title": driver.title,
        "top_card": top_card,
        "profile_photo": {
            **profile_photo,
            "cached_path": cached_photo_path,
        }
        if profile_photo
        else None,
        "experience": scrape_section(driver, profile_url, "experience", "experience"),
        "education": scrape_section(driver, profile_url, "education", "education"),
        "skills": scrape_section(driver, profile_url, "skills", "skills"),
    }


def scrape_profile(
    profile_url: str,
    firefox_profile_path: str,
    output_path: Path | None,
    pfp_cache_dir: Path,
    headless: bool,
) -> dict[str, object]:
    driver = build_firefox_driver(firefox_profile_path, headless=headless)
    try:
        result = scrape_profile_with_driver(
            driver=driver,
            profile_url=profile_url,
            pfp_cache_dir=pfp_cache_dir,
        )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    finally:
        driver.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LinkedIn profile details using the same Selenium + Firefox profile approach as the existing script."
    )
    parser.add_argument("profile_url", help="LinkedIn profile URL to inspect.")
    parser.add_argument(
        "--firefox-profile-path", default=DEFAULT_FIREFOX_PROFILE, help="Firefox profile directory to reuse."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Optional JSON output path.")
    parser.add_argument("--pfp-cache-dir", type=Path, default=DEFAULT_PFP_CACHE_DIR, help="Directory for cached profile photos.")
    parser.add_argument("--headless", action="store_true", help="Run headless instead of opening Firefox.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = scrape_profile(
            profile_url=args.profile_url,
            firefox_profile_path=args.firefox_profile_path,
            output_path=args.output,
            pfp_cache_dir=args.pfp_cache_dir,
            headless=args.headless,
        )
    except TimeoutException as exc:
        raise SystemExit(f"Timed out while loading LinkedIn profile: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
