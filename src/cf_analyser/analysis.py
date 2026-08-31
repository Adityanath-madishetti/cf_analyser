"""Pure aggregation/analysis functions over raw Codeforces API data.

No network calls here -- everything takes already-fetched data (submissions,
problems, rating history) and returns small, summarized results. Keeping this
separate from cf_client.py makes it unit-testable without hitting the network,
and keeps the MCP tools from ever handing Claude a raw, unfiltered payload.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

SECONDS_PER_DAY = 86400


def _problem_key(problem: dict[str, Any]) -> str:
    contest_id = problem.get("contestId", problem.get("problemsetName", "?"))
    return f"{contest_id}{problem.get('index', '?')}"


def filter_recent(submissions: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = time.time() - days * SECONDS_PER_DAY
    return [s for s in submissions if s.get("creationTimeSeconds", 0) >= cutoff]


def solved_problem_keys(submissions: list[dict[str, Any]]) -> set[str]:
    return {
        _problem_key(s["problem"])
        for s in submissions
        if s.get("verdict") == "OK"
    }


def activity_summary(submissions: list[dict[str, Any]], days: int) -> dict[str, Any]:
    recent = filter_recent(submissions, days)

    verdict_counts: dict[str, int] = defaultdict(int)
    tag_counts: dict[str, int] = defaultdict(int)
    ratings_solved: list[int] = []
    attempted_keys: set[str] = set()
    solved_keys: set[str] = set()

    for sub in recent:
        verdict = sub.get("verdict", "UNKNOWN")
        verdict_counts[verdict] += 1

        problem = sub["problem"]
        key = _problem_key(problem)
        attempted_keys.add(key)

        if verdict == "OK":
            if key not in solved_keys:
                solved_keys.add(key)
                for tag in problem.get("tags", []):
                    tag_counts[tag] += 1
                if "rating" in problem:
                    ratings_solved.append(problem["rating"])

    return {
        "days": days,
        "problems_attempted": len(attempted_keys),
        "problems_solved": len(solved_keys),
        "verdict_breakdown": dict(sorted(verdict_counts.items(), key=lambda kv: -kv[1])),
        "top_tags_practiced": dict(
            sorted(tag_counts.items(), key=lambda kv: -kv[1])[:10]
        ),
        "avg_rating_solved": round(sum(ratings_solved) / len(ratings_solved), 1)
        if ratings_solved
        else None,
        "min_rating_solved": min(ratings_solved) if ratings_solved else None,
        "max_rating_solved": max(ratings_solved) if ratings_solved else None,
    }


def weak_topics(submissions: list[dict[str, Any]], min_attempts: int = 3) -> list[dict[str, Any]]:
    tag_attempts: dict[str, set[str]] = defaultdict(set)
    tag_solves: dict[str, set[str]] = defaultdict(set)

    for sub in submissions:
        problem = sub["problem"]
        key = _problem_key(problem)
        for tag in problem.get("tags", []):
            tag_attempts[tag].add(key)
            if sub.get("verdict") == "OK":
                tag_solves[tag].add(key)

    rows = []
    for tag, attempted in tag_attempts.items():
        if len(attempted) < min_attempts:
            continue
        solved = len(tag_solves.get(tag, set()))
        rows.append(
            {
                "tag": tag,
                "attempted": len(attempted),
                "solved": solved,
                "solve_rate": round(solved / len(attempted), 2),
            }
        )

    rows.sort(key=lambda r: (r["solve_rate"], -r["attempted"]))
    return rows


def recommend_problems(
    problems: list[dict[str, Any]],
    already_solved: set[str],
    target_rating: int,
    count: int,
    rating_window: int = 100,
) -> list[dict[str, Any]]:
    low, high = target_rating - rating_window, target_rating + rating_window
    candidates = [
        p
        for p in problems
        if _problem_key(p) not in already_solved
        and low <= p.get("rating", -1) <= high
    ]
    candidates.sort(key=lambda p: abs(p.get("rating", target_rating) - target_rating))

    picks = []
    for p in candidates[: count * 3]:
        picks.append(
            {
                "name": p.get("name"),
                "contestId": p.get("contestId"),
                "index": p.get("index"),
                "rating": p.get("rating"),
                "tags": p.get("tags", []),
                "url": f"https://codeforces.com/problemset/problem/{p.get('contestId')}/{p.get('index')}"
                if p.get("contestId")
                else None,
            }
        )
        if len(picks) >= count:
            break
    return picks


def compare_users(
    handle1: str,
    info1: dict[str, Any],
    submissions1: list[dict[str, Any]],
    handle2: str,
    info2: dict[str, Any],
    submissions2: list[dict[str, Any]],
) -> dict[str, Any]:
    solved1 = solved_problem_keys(submissions1)
    solved2 = solved_problem_keys(submissions2)

    def tag_strength(submissions: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        seen: set[str] = set()
        for sub in submissions:
            if sub.get("verdict") != "OK":
                continue
            key = _problem_key(sub["problem"])
            if key in seen:
                continue
            seen.add(key)
            for tag in sub["problem"].get("tags", []):
                counts[tag] += 1
        return dict(counts)

    strength1 = tag_strength(submissions1)
    strength2 = tag_strength(submissions2)
    all_tags = set(strength1) | set(strength2)
    tag_comparison = {
        tag: {"handle1": strength1.get(tag, 0), "handle2": strength2.get(tag, 0)}
        for tag in sorted(all_tags, key=lambda t: -(strength1.get(t, 0) + strength2.get(t, 0)))[:10]
    }

    return {
        "handle1": {
            "handle": handle1,
            "rating": info1.get("rating"),
            "maxRating": info1.get("maxRating"),
            "rank": info1.get("rank"),
            "problems_solved": len(solved1),
        },
        "handle2": {
            "handle": handle2,
            "rating": info2.get("rating"),
            "maxRating": info2.get("maxRating"),
            "rank": info2.get("rank"),
            "problems_solved": len(solved2),
        },
        "shared_solved_count": len(solved1 & solved2),
        "top_tag_comparison": tag_comparison,
    }


def solve_streak(submissions: list[dict[str, Any]]) -> dict[str, Any]:
    solve_days: set[int] = set()
    for sub in submissions:
        if sub.get("verdict") != "OK":
            continue
        ts = sub.get("creationTimeSeconds")
        if ts is not None:
            solve_days.add(ts // SECONDS_PER_DAY)

    if not solve_days:
        return {"current_streak": 0, "longest_streak": 0, "active_days": 0}

    sorted_days = sorted(solve_days)
    longest = current = 1
    for prev, cur in zip(sorted_days, sorted_days[1:]):
        if cur == prev + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    today = int(time.time()) // SECONDS_PER_DAY
    if today not in solve_days and today - 1 not in solve_days:
        current_streak = 0
    else:
        current_streak = 1
        day = today if today in solve_days else today - 1
        while (day - 1) in solve_days:
            current_streak += 1
            day -= 1

    return {
        "current_streak": current_streak,
        "longest_streak": longest,
        "active_days": len(solve_days),
    }


def rating_progress(rating_changes: list[dict[str, Any]]) -> dict[str, Any]:
    if not rating_changes:
        return {
            "contests_rated": 0,
            "current_rating": None,
            "best_contest": None,
            "worst_contest": None,
            "recent_plateau": False,
        }

    history = [
        {
            "contestId": rc.get("contestId"),
            "contestName": rc.get("contestName"),
            "rank": rc.get("rank"),
            "oldRating": rc.get("oldRating"),
            "newRating": rc.get("newRating"),
            "delta": rc.get("newRating", 0) - rc.get("oldRating", 0),
        }
        for rc in rating_changes
    ]

    best = max(history, key=lambda h: h["delta"])
    worst = min(history, key=lambda h: h["delta"])
    last5 = history[-5:]
    plateau = len(last5) == 5 and sum(h["delta"] for h in last5) <= 0

    return {
        "contests_rated": len(history),
        "current_rating": history[-1]["newRating"],
        "best_contest": {"name": best["contestName"], "delta": best["delta"]},
        "worst_contest": {"name": worst["contestName"], "delta": worst["delta"]},
        "recent_plateau": plateau,
        "last_5_deltas": [h["delta"] for h in last5],
    }
