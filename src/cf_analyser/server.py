"""Codeforces Analyser MCP server.

Exposes tools for analysing a Codeforces user's activity, recommending
practice problems, comparing users, and tracking contest/rating progress.
Every Codeforces API call is authenticated (see cf_client.py) and every
tool returns a small, pre-aggregated result -- never a raw dump of
submissions or the full problem archive.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

import analysis
from cf_analyser.cf_client import CFClient

mcp = MCPServer("cf-analyser")

_client: CFClient | None = None


def get_client() -> CFClient:
    global _client
    if _client is None:
        _client = CFClient()
    return _client


@mcp.tool()
async def get_user_profile(handle: str) -> dict:
    """Get a Codeforces user's profile: rank, rating, max rating, contribution, and rating trend."""
    client = get_client()
    info = (await client.user_info([handle]))[0]
    rating_changes = await client.user_rating(handle)
    progress = analysis.rating_progress(rating_changes)

    return {
        "handle": info.get("handle"),
        "rank": info.get("rank"),
        "rating": info.get("rating"),
        "maxRank": info.get("maxRank"),
        "maxRating": info.get("maxRating"),
        "contribution": info.get("contribution"),
        "contests_rated": progress["contests_rated"],
        "recent_plateau": progress["recent_plateau"],
    }


@mcp.tool()
async def analyse_activity(handle: str, days: int = 7) -> dict:
    """Analyse a user's practice activity over the trailing N days: problems solved/attempted,
    verdict breakdown, tags practiced, and difficulty range solved."""
    client = get_client()
    submissions = await client.user_status(handle)
    return analysis.activity_summary(submissions, days)


@mcp.tool()
async def recommend_problems(
    handle: str,
    count: int = 5,
    target_rating: int | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Recommend unsolved practice problems for a user, near their current rating (or a
    given target_rating), optionally restricted to specific tags/topics."""
    client = get_client()
    info = (await client.user_info([handle]))[0]
    submissions = await client.user_status(handle)
    already_solved = analysis.solved_problem_keys(submissions)

    if target_rating is None:
        base = info.get("rating", 1200)
        target_rating = base + 150

    result = await client.problemset_problems(tags=tags)
    picks = analysis.recommend_problems(
        result["problems"], already_solved, target_rating, count
    )
    return {"handle": handle, "target_rating": target_rating, "recommendations": picks}


@mcp.tool()
async def compare_users(handle1: str, handle2: str) -> dict:
    """Compare two Codeforces users: rating, solved-problem counts, shared solved problems,
    and relative strength across their most common tags."""
    client = get_client()
    infos = await client.user_info([handle1, handle2])
    submissions1 = await client.user_status(handle1)
    submissions2 = await client.user_status(handle2)
    return analysis.compare_users(
        handle1, infos[0], submissions1, handle2, infos[1], submissions2
    )


@mcp.tool()
async def weak_topics(handle: str, min_attempts: int = 3) -> dict:
    """Find a user's weakest topics/tags: the ones with the lowest solve rate among tags
    they've attempted at least min_attempts times."""
    client = get_client()
    submissions = await client.user_status(handle)
    return {"handle": handle, "weak_topics": analysis.weak_topics(submissions, min_attempts)}


@mcp.tool()
async def upcoming_contests(count: int = 5) -> dict:
    """List the next upcoming Codeforces contests, soonest first."""
    client = get_client()
    contests = await client.contest_list()
    upcoming = [c for c in contests if c.get("phase") == "BEFORE"]
    upcoming.sort(key=lambda c: c.get("startTimeSeconds", float("inf")))
    return {
        "upcoming_contests": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "startTimeSeconds": c.get("startTimeSeconds"),
                "durationSeconds": c.get("durationSeconds"),
            }
            for c in upcoming[:count]
        ]
    }


@mcp.tool()
async def contest_performance(handle: str, contest_id: int) -> dict:
    """Get a user's performance in a specific contest: rank, problems solved, penalty,
    and the resulting rating change."""
    client = get_client()
    standings = await client.contest_standings(contest_id, [handle])
    rating_changes = await client.user_rating(handle)

    rows = standings.get("rows", [])
    row = rows[0] if rows else None
    delta = next(
        (
            rc.get("newRating", 0) - rc.get("oldRating", 0)
            for rc in rating_changes
            if rc.get("contestId") == contest_id
        ),
        None,
    )

    if row is None:
        return {"handle": handle, "contest_id": contest_id, "found": False}

    solved = sum(1 for r in row.get("problemResults", []) if r.get("points", 0) > 0 or r.get("bestSubmissionTimeSeconds"))
    return {
        "handle": handle,
        "contest_id": contest_id,
        "contest_name": standings.get("contest", {}).get("name"),
        "rank": row.get("rank"),
        "points": row.get("points"),
        "penalty": row.get("penalty"),
        "problems_solved": solved,
        "rating_delta": delta,
    }


@mcp.tool()
async def solve_streak(handle: str) -> dict:
    """Get a user's current and longest daily problem-solving streak."""
    client = get_client()
    submissions = await client.user_status(handle)
    return {"handle": handle, **analysis.solve_streak(submissions)}


@mcp.tool()
async def rating_progress(handle: str) -> dict:
    """Get a user's rating history summary: current rating, best/worst contest, recent trend,
    and whether they're in a rating plateau."""
    client = get_client()
    rating_changes = await client.user_rating(handle)
    return {"handle": handle, **analysis.rating_progress(rating_changes)}


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
