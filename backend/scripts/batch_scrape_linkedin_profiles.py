from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from selenium.common.exceptions import TimeoutException, WebDriverException

from app.db.session import SessionLocal
from app.models import ExternalProfile, Person
from scripts.scrape_linkedin_profile_selenium import (
    DEFAULT_FIREFOX_PROFILE,
    build_firefox_driver,
    normalize_profile_url,
    scrape_profile_with_driver,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = ROOT_DIR / "import" / "linkedin_batch_scrape"
DEFAULT_RESULTS_JSONL = DEFAULT_RUN_DIR / "results.jsonl"
DEFAULT_PROGRESS_JSON = DEFAULT_RUN_DIR / "progress.json"
DEFAULT_TARGET_ORDER_JSON = DEFAULT_RUN_DIR / "target_order.json"
DEFAULT_PROFILE_OUTPUT_DIR = DEFAULT_RUN_DIR / "profiles"
DEFAULT_PFP_CACHE_DIR = ROOT_DIR / "import" / "linkedin_pfpcache"


@dataclass(frozen=True)
class ProfileTarget:
    person_id: str
    display_name: str
    external_profile_id: str
    profile_url: str


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug or "profile"


def build_target_statement() -> Select[tuple[ExternalProfile]]:
    return (
        select(ExternalProfile)
        .options(joinedload(ExternalProfile.person))
        .join(Person, ExternalProfile.person_id == Person.id)
        .where(
            ExternalProfile.platform == "LinkedIn",
            ExternalProfile.person_id.is_not(None),
            Person.deleted_at.is_(None),
        )
        .order_by(Person.display_name.asc(), ExternalProfile.created_at.asc(), ExternalProfile.id.asc())
    )


def load_targets() -> list[ProfileTarget]:
    session = SessionLocal()
    try:
        statement = build_target_statement()
        profiles = session.scalars(statement).all()
    finally:
        session.close()

    targets: list[ProfileTarget] = []
    seen_urls: set[str] = set()
    for profile in profiles:
        if profile.person is None:
            continue
        profile_url = normalize_profile_url(profile.url_or_handle)
        if profile_url in seen_urls:
            continue
        seen_urls.add(profile_url)
        targets.append(
            ProfileTarget(
                person_id=str(profile.person.id),
                display_name=profile.person.display_name,
                external_profile_id=str(profile.id),
                profile_url=profile_url,
            )
        )
    return targets


def load_latest_attempts(results_jsonl_path: Path) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    if not results_jsonl_path.exists():
        return latest
    with results_jsonl_path.open() as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            entry = json.loads(line)
            profile_url = entry.get("profile_url")
            if isinstance(profile_url, str):
                latest[profile_url] = entry
    return latest


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def build_randomized_target_order(
    *,
    targets: list[ProfileTarget],
    latest_attempts: dict[str, dict[str, object]],
    order_path: Path,
) -> list[ProfileTarget]:
    target_by_url = {target.profile_url: target for target in targets}
    completed_urls = {
        profile_url
        for profile_url, attempt in latest_attempts.items()
        if attempt.get("status") == "success"
    }
    existing_payload = read_json(order_path)
    ordered_urls: list[str] = []
    is_global_queue = (
        bool(existing_payload)
        and existing_payload.get("order_mode") == "global_random"
        and existing_payload.get("total_available_target_count") == len(targets)
    )

    if is_global_queue and isinstance(existing_payload.get("ordered_profile_urls"), list):
        for url in existing_payload["ordered_profile_urls"]:
            if isinstance(url, str) and url in target_by_url and url not in completed_urls:
                ordered_urls.append(url)

    remaining_urls = [
        target.profile_url
        for target in targets
        if target.profile_url not in completed_urls and target.profile_url not in ordered_urls
    ]
    random.shuffle(remaining_urls)
    ordered_urls.extend(remaining_urls)

    write_json(
        order_path,
        {
            "generated_at": utc_now_iso(),
            "order_mode": "global_random",
            "total_available_target_count": len(targets),
            "completed_profile_urls_excluded_at_generation": sorted(completed_urls),
            "ordered_profile_urls": ordered_urls,
        },
    )
    return [target_by_url[url] for url in ordered_urls]


def select_targets_for_limit(ordered_targets: list[ProfileTarget], limit: int | None) -> list[ProfileTarget]:
    if limit is None:
        return ordered_targets
    return ordered_targets[:limit]


def select_runnable_targets(
    ordered_targets: list[ProfileTarget],
    latest_attempts: dict[str, dict[str, object]],
    *,
    limit: int | None,
    retry_errors: bool,
) -> list[ProfileTarget]:
    completed_urls = {
        profile_url
        for profile_url, attempt in latest_attempts.items()
        if attempt.get("status") == "success"
    }
    error_urls = {
        profile_url
        for profile_url, attempt in latest_attempts.items()
        if attempt.get("status") == "error"
    }

    runnable_targets = [target for target in ordered_targets if target.profile_url not in completed_urls]
    if not retry_errors:
        runnable_targets = [target for target in runnable_targets if target.profile_url not in error_urls]

    if limit is None:
        return runnable_targets
    return runnable_targets[:limit]


def build_progress_snapshot(
    *,
    selected_targets: list[ProfileTarget],
    all_targets: list[ProfileTarget],
    ordered_targets: list[ProfileTarget],
    latest_attempts: dict[str, dict[str, object]],
    started_at: str,
    args: argparse.Namespace,
    interrupted: bool,
) -> dict[str, object]:
    completed_urls = {
        profile_url
        for profile_url, attempt in latest_attempts.items()
        if attempt.get("status") == "success"
    }
    error_urls = {
        profile_url
        for profile_url, attempt in latest_attempts.items()
        if attempt.get("status") == "error"
    }
    pending_targets = selected_targets
    return {
        "started_at": started_at,
        "updated_at": utc_now_iso(),
        "interrupted": interrupted,
        "run_dir": str(args.run_dir),
        "results_jsonl_path": str(args.results_jsonl),
        "target_order_json_path": str(args.target_order_json),
        "profile_output_dir": str(args.profile_output_dir),
        "pfp_cache_dir": str(args.pfp_cache_dir),
        "query_limit": args.limit,
        "batch_size": args.batch_size,
        "min_delay_seconds": args.min_delay_seconds,
        "max_delay_seconds": args.max_delay_seconds,
        "restart_browser_every": args.restart_browser_every,
        "retry_errors": args.retry_errors,
        "dry_run": args.dry_run,
        "headless": args.headless,
        "selected_target_count": len(selected_targets),
        "global_target_pool_count": len(all_targets),
        "ordered_target_pool_count": len(ordered_targets),
        "completed_count": len(completed_urls),
        "error_count": len(error_urls),
        "pending_count": len(pending_targets),
        "pending_profile_urls": [target.profile_url for target in pending_targets[:25]],
    }


def ensure_driver(driver, firefox_profile_path: str, headless: bool):
    if driver is not None:
        return driver
    return build_firefox_driver(firefox_profile_path, headless=headless)


def close_driver(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def sleep_between_profiles(min_delay_seconds: float, max_delay_seconds: float) -> float:
    delay_seconds = random.uniform(min_delay_seconds, max_delay_seconds)
    time.sleep(delay_seconds)
    return delay_seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch scrape LinkedIn profiles from Kizuna's backend database with append-only progress tracking."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=DEFAULT_RUN_DIR,
        help="Base directory for the batch run's progress and output files.",
    )
    parser.add_argument(
        "--results-jsonl",
        type=Path,
        default=DEFAULT_RESULTS_JSONL,
        help="Append-only JSONL file with one record per scrape attempt.",
    )
    parser.add_argument(
        "--progress-json",
        type=Path,
        default=DEFAULT_PROGRESS_JSON,
        help="Progress snapshot updated after each processed profile.",
    )
    parser.add_argument(
        "--target-order-json",
        type=Path,
        default=DEFAULT_TARGET_ORDER_JSON,
        help="Persisted randomized target order reused across runs.",
    )
    parser.add_argument(
        "--profile-output-dir",
        type=Path,
        default=DEFAULT_PROFILE_OUTPUT_DIR,
        help="Directory to store one pretty-printed JSON file per successful profile scrape.",
    )
    parser.add_argument(
        "--firefox-profile-path",
        default=DEFAULT_FIREFOX_PROFILE,
        help="Firefox profile directory to reuse for the logged-in LinkedIn session.",
    )
    parser.add_argument(
        "--pfp-cache-dir",
        type=Path,
        default=DEFAULT_PFP_CACHE_DIR,
        help="Directory for cached profile photos.",
    )
    parser.add_argument("--limit", type=int, help="Only consider the first N LinkedIn profiles from the database.")
    parser.add_argument("--batch-size", type=int, default=25, help="Process targets in chunks of this size.")
    parser.add_argument(
        "--restart-browser-every",
        type=int,
        default=25,
        help="Restart Firefox after this many processed profiles to reduce session drift.",
    )
    parser.add_argument(
        "--min-delay-seconds",
        type=float,
        default=10.0,
        help="Minimum delay between profiles.",
    )
    parser.add_argument(
        "--max-delay-seconds",
        type=float,
        default=30.0,
        help="Maximum delay between profiles.",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry profiles whose latest JSONL record is an error.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only load targets and write the progress snapshot without opening Firefox.",
    )
    parser.add_argument("--headless", action="store_true", help="Run headless instead of opening Firefox.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be greater than 0.")
    if args.restart_browser_every <= 0:
        raise SystemExit("--restart-browser-every must be greater than 0.")
    if args.min_delay_seconds < 0 or args.max_delay_seconds < 0:
        raise SystemExit("Delay values must be non-negative.")
    if args.min_delay_seconds > args.max_delay_seconds:
        raise SystemExit("--min-delay-seconds cannot be greater than --max-delay-seconds.")

    all_targets = load_targets()
    latest_attempts = load_latest_attempts(args.results_jsonl)
    ordered_targets = build_randomized_target_order(
        targets=all_targets,
        latest_attempts=latest_attempts,
        order_path=args.target_order_json,
    )
    selected_targets = select_runnable_targets(
        ordered_targets,
        latest_attempts,
        limit=args.limit,
        retry_errors=args.retry_errors,
    )
    started_at = utc_now_iso()
    interrupted = False

    progress_snapshot = build_progress_snapshot(
        selected_targets=selected_targets,
        all_targets=all_targets,
        ordered_targets=ordered_targets,
        latest_attempts=latest_attempts,
        started_at=started_at,
        args=args,
        interrupted=interrupted,
    )
    write_json(args.progress_json, progress_snapshot)

    if args.dry_run:
        print(json.dumps(progress_snapshot, ensure_ascii=False, indent=2))
        return

    pending_targets = selected_targets

    driver = None
    processed_since_restart = 0

    try:
        for batch_start in range(0, len(pending_targets), args.batch_size):
            batch = pending_targets[batch_start : batch_start + args.batch_size]
            for batch_index, target in enumerate(batch):
                try:
                    if processed_since_restart >= args.restart_browser_every:
                        close_driver(driver)
                        driver = None
                        processed_since_restart = 0

                    driver = ensure_driver(driver, args.firefox_profile_path, args.headless)
                    scrape_started_at = utc_now_iso()
                    result = scrape_profile_with_driver(
                        driver=driver,
                        profile_url=target.profile_url,
                        pfp_cache_dir=args.pfp_cache_dir,
                    )
                    result_payload = {
                        "status": "success",
                        "scraped_at": utc_now_iso(),
                        "started_at": scrape_started_at,
                        "person_id": target.person_id,
                        "display_name": target.display_name,
                        "external_profile_id": target.external_profile_id,
                        "profile_url": target.profile_url,
                        "result": result,
                    }
                    append_jsonl(args.results_jsonl, result_payload)
                    latest_attempts[target.profile_url] = result_payload

                    args.profile_output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = args.profile_output_dir / f"{slugify_filename(target.display_name)}__{target.person_id}.json"
                    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                    processed_since_restart += 1
                except KeyboardInterrupt:
                    interrupted = True
                    append_jsonl(
                        args.results_jsonl,
                        {
                            "status": "interrupted",
                            "interrupted_at": utc_now_iso(),
                            "person_id": target.person_id,
                            "display_name": target.display_name,
                            "external_profile_id": target.external_profile_id,
                            "profile_url": target.profile_url,
                        },
                    )
                    raise
                except (RuntimeError, TimeoutException, WebDriverException) as exc:
                    append_jsonl(
                        args.results_jsonl,
                        {
                            "status": "error",
                            "failed_at": utc_now_iso(),
                            "person_id": target.person_id,
                            "display_name": target.display_name,
                            "external_profile_id": target.external_profile_id,
                            "profile_url": target.profile_url,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        },
                    )
                    latest_attempts[target.profile_url] = {
                        "status": "error",
                        "profile_url": target.profile_url,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                    close_driver(driver)
                    driver = None
                    processed_since_restart = 0

                progress_snapshot = build_progress_snapshot(
                    selected_targets=selected_targets,
                    all_targets=all_targets,
                    ordered_targets=ordered_targets,
                    latest_attempts=latest_attempts,
                    started_at=started_at,
                    args=args,
                    interrupted=interrupted,
                )
                write_json(args.progress_json, progress_snapshot)

                is_last_profile = batch_start + batch_index + 1 >= len(pending_targets)
                if not is_last_profile:
                    delay_seconds = sleep_between_profiles(args.min_delay_seconds, args.max_delay_seconds)
                    progress_snapshot["last_delay_seconds"] = delay_seconds
                    write_json(args.progress_json, progress_snapshot)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        close_driver(driver)
        progress_snapshot = build_progress_snapshot(
            selected_targets=selected_targets,
            all_targets=all_targets,
            ordered_targets=ordered_targets,
            latest_attempts=latest_attempts,
            started_at=started_at,
            args=args,
            interrupted=interrupted,
        )
        write_json(args.progress_json, progress_snapshot)

    summary = build_progress_snapshot(
        selected_targets=selected_targets,
        all_targets=all_targets,
        ordered_targets=ordered_targets,
        latest_attempts=latest_attempts,
        started_at=started_at,
        args=args,
        interrupted=interrupted,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
