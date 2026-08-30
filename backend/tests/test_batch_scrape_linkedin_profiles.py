from argparse import Namespace
from pathlib import Path

from scripts.batch_scrape_linkedin_profiles import ProfileTarget, build_progress_snapshot


def make_args(tmp_path: Path) -> Namespace:
    return Namespace(
        run_dir=tmp_path,
        results_jsonl=tmp_path / "results.jsonl",
        target_order_json=tmp_path / "target_order.json",
        profile_output_dir=tmp_path / "profiles",
        pfp_cache_dir=tmp_path / "pfp",
        limit=50,
        batch_size=25,
        min_delay_seconds=10.0,
        max_delay_seconds=30.0,
        restart_browser_every=25,
        retry_errors=False,
        dry_run=False,
        headless=True,
    )


def test_progress_only_reports_unattempted_selected_targets_as_pending(tmp_path: Path) -> None:
    targets = [
        ProfileTarget("person-1", "Success", "profile-1", "https://linkedin.test/1"),
        ProfileTarget("person-2", "Error", "profile-2", "https://linkedin.test/2"),
        ProfileTarget("person-3", "Pending", "profile-3", "https://linkedin.test/3"),
    ]
    latest_attempts: dict[str, dict[str, object]] = {
        targets[0].profile_url: {"status": "success"},
        targets[1].profile_url: {"status": "error"},
    }

    snapshot = build_progress_snapshot(
        selected_targets=targets,
        all_targets=targets,
        ordered_targets=targets,
        latest_attempts=latest_attempts,
        started_at="2026-08-29T00:00:00+00:00",
        args=make_args(tmp_path),
        interrupted=False,
    )

    assert snapshot["pending_count"] == 1
    assert snapshot["pending_profile_urls"] == [targets[2].profile_url]
