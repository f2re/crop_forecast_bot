from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

GateState = Literal["ready", "pending", "blocked", "absent"]
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class GateDecision:
    state: GateState
    reason: str

    @property
    def deployable(self) -> bool:
        return self.state in {"ready", "absent"}


def evaluate_workflow_runs(
    payload: dict[str, Any],
    *,
    sha: str,
    workflow_label: str,
    required: bool,
) -> GateDecision:
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return GateDecision("blocked", f"{workflow_label}: invalid GitHub response")

    exact_runs = [run for run in runs if str(run.get("head_sha", "")) == sha]
    if not exact_runs:
        if required:
            return GateDecision(
                "pending",
                f"{workflow_label}: no push run is registered for {sha[:12]}",
            )
        return GateDecision(
            "absent",
            f"{workflow_label}: no run is required for this commit",
        )

    run = max(
        exact_runs,
        key=lambda item: (
            int(item.get("run_number") or 0),
            int(item.get("id") or 0),
        ),
    )
    status = str(run.get("status") or "unknown")
    conclusion = str(run.get("conclusion") or "")
    if status != "completed":
        return GateDecision(
            "pending",
            f"{workflow_label}: workflow status is {status}",
        )
    if conclusion == "success":
        return GateDecision(
            "ready",
            f"{workflow_label}: completed successfully",
        )
    return GateDecision(
        "blocked",
        f"{workflow_label}: completed with conclusion {conclusion or 'unknown'}",
    )


def _workflow_url(
    *,
    api_url: str,
    repository: str,
    workflow: str,
    branch: str,
    sha: str,
) -> str:
    query = urlencode(
        {
            "branch": branch,
            "event": "push",
            "head_sha": sha,
            "per_page": 10,
        }
    )
    encoded_workflow = quote(workflow, safe="")
    return (
        f"{api_url.rstrip('/')}/repos/{repository}/actions/workflows/"
        f"{encoded_workflow}/runs?{query}"
    )


def _fetch_json(url: str, *, token: str | None, timeout: float) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "crop-forecast-bot-release-gate",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed API URL
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub API returned a non-object JSON payload")
    return payload


def check_release(
    *,
    repository: str,
    sha: str,
    branch: str,
    api_url: str = "https://api.github.com",
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[GateDecision, ...]:
    if not _REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must use owner/name format")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("sha must be a full 40-character Git commit SHA")
    if not branch or any(character.isspace() for character in branch):
        raise ValueError("branch is invalid")

    workflows = (
        ("ci.yml", "CI", True),
        ("provider-smoke.yml", "Live provider smoke", False),
        (
            "ensemble-provider-smoke.yml",
            "Ensemble provider smoke",
            False,
        ),
    )
    decisions: list[GateDecision] = []
    for workflow, label, required in workflows:
        payload = _fetch_json(
            _workflow_url(
                api_url=api_url,
                repository=repository,
                workflow=workflow,
                branch=branch,
                sha=sha,
            ),
            token=token,
            timeout=timeout,
        )
        decisions.append(
            evaluate_workflow_runs(
                payload,
                sha=sha,
                workflow_label=label,
                required=required,
            )
        )
    return tuple(decisions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed GitHub Actions gate for pull-based deployment"
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--api-url",
        default=os.getenv("GITHUB_API_URL", "https://api.github.com"),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    token = (
        os.getenv("GITHUB_TOKEN", "").strip()
        or os.getenv("GITHUB_API_TOKEN", "").strip()
        or None
    )
    try:
        decisions = check_release(
            repository=args.repository,
            sha=args.sha.lower(),
            branch=args.branch,
            api_url=args.api_url,
            token=token,
            timeout=args.timeout,
        )
    except (ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"release gate unavailable: {exc}", file=sys.stderr)
        return 3

    for decision in decisions:
        print(f"{decision.state}: {decision.reason}")
    return 0 if all(decision.deployable for decision in decisions) else 3


if __name__ == "__main__":
    raise SystemExit(main())
