# cf-analyser

A local MCP server for analysing Codeforces activity: weekly practice summaries, problem
recommendations, user comparisons, weak-topic detection, contest tracking, and rating
progress. Backed by the public [Codeforces API](https://codeforces.com/apiHelp), with every
request signed and authenticated.

## Project structure

```
src/cf_analyser/
  main.py         # standalone entrypoint: `python main.py`
  __init__.py     # defines main(), the package's real entrypoint
  server.py       # the MCP server itself: tool definitions + startup
  cf_client.py    # signed HTTP client for the Codeforces API
  analysis.py     # pure aggregation logic (no network calls)
```

**`main.py`** — a thin runnable script. Lets you (or an IDE "Run" button) execute
`python main.py` directly. It just imports and calls `main()` from `__init__.py`.

**`__init__.py`** — defines the package's `main()` function, which is also what the
`cf-analyser` console-script command (registered in `pyproject.toml`) points at. It does one
thing: calls `run()` from `server.py`.

**`server.py`** — where the MCP server actually lives. Creates the `MCPServer` instance,
registers all 9 tools with `@mcp.tool()`, and `run()` starts `mcp.run()`, which opens a
stdio JSON-RPC loop and blocks, waiting for a client (Claude) to send requests. Each tool
function is a thin orchestrator: it calls `cf_client.py` to fetch raw data, hands that to
`analysis.py` to crunch into a summary, and returns the summary.

**`cf_client.py`** — the only file that talks to `codeforces.com/api`. Holds the `CFClient`
class, which reads `CF_API_KEY`/`CF_API_SECRET` from the environment, signs every outgoing
request per Codeforces' `apiSig` scheme, makes the HTTP call, and raises `CFApiError` on
failure. Tool code in `server.py` never builds a request or touches signing itself — it just
calls methods like `client.user_status(handle)`.

**`analysis.py`** — pure functions, zero network calls. Takes raw data already fetched by
`cf_client.py` (a list of submissions, the problem archive, rating history) and turns it into
the small, summarized shape a tool actually returns — tag-frequency counts, solve rates,
streaks, top picks. Kept separate from `cf_client.py` so this logic is testable without
hitting the network.

### Request flow

Walking through what happens when Claude calls, say, `analyse_activity(handle="tourist")`:

1. Claude Desktop/Code sends a `tools/call` JSON-RPC request over stdio to the running
   `cf-analyser` process (the one launched by your MCP config).
2. The `mcp` library routes it to the matching `@mcp.tool()` function in `server.py`.
3. That function calls `client.user_status(handle)` on the shared `CFClient` (from
   `cf_client.py`).
4. `cf_client.py` builds the request params, signs them (`apiKey` + `time` + `apiSig`), and
   makes an authenticated `GET` to `codeforces.com/api/user.status`.
5. Codeforces returns the user's full submission history as JSON. `cf_client.py` checks
   `status == "OK"` and returns just the `result` payload (raising `CFApiError` if it failed).
6. `server.py` hands that raw submission list to `analysis.activity_summary()` in
   `analysis.py`, which computes verdict counts, tag frequency, solved/attempted totals, etc.
7. `server.py` returns that small summary dict as the tool result.
8. The `mcp` library serializes it back over stdio to Claude, which uses it to answer you.

Every other tool follows the same shape: `server.py` orchestrates, `cf_client.py` fetches +
authenticates, `analysis.py` crunches — nothing but the final summary ever leaves the server.

## Setup

1. Generate an API key/secret pair at https://codeforces.com/settings/api.
2. Install dependencies:
   ```
   uv sync
   ```
3. Set `CF_API_KEY` and `CF_API_SECRET` in the environment the server runs in (see below).

## Running standalone (for testing)

```
CF_API_KEY=... CF_API_SECRET=... PYTHONPATH=src uv run cf-analyser
```

Or use the MCP inspector:

```
CF_API_KEY=... CF_API_SECRET=... PYTHONPATH=src uv run mcp dev src/cf_analyser/server.py
```

## Adding to Claude Code / Claude Desktop

Add an MCP server entry pointing at this project, with the API credentials in `env`. Use the
**absolute path to `uv`** for `command` — Claude launches this without your shell's `PATH`, so
a bare `"uv"` will fail to resolve. Find yours with `which uv` (or, for this project,
`uv` lives at `/Users/adityanath/Desktop/AI/MCPs/.env/bin/uv`):

```json
{
  "mcpServers": {
    "cf-analyser": {
      "command": "/Users/adityanath/Desktop/AI/MCPs/.env/bin/uv",
      "args": ["run", "--directory", "/Users/adityanath/Desktop/AI/MCPs/cf_analyser", "cf-analyser"],
      "env": {
        "PYTHONPATH": "/Users/adityanath/Desktop/AI/MCPs/cf_analyser/src",
        "CF_API_KEY": "your-api-key",
        "CF_API_SECRET": "your-api-secret"
      }
    }
  }
}
```

Note: `PYTHONPATH` is set explicitly above because this environment's editable-install
(`.pth`-based) resolution was observed to be unreliable under Python 3.14.0 / uv 0.12.7 —
setting `PYTHONPATH` sidesteps it and is what was used for all testing during development.

## Tools

- `get_user_profile(handle)` — rank, rating, max rating, contribution, rating trend.
- `analyse_activity(handle, days=7)` — problems solved/attempted, verdict breakdown, tags practiced, difficulty range.
- `recommend_problems(handle, count=5, target_rating=None, tags=None)` — unsolved problems near the user's level.
- `compare_users(handle1, handle2)` — side-by-side rating, solved counts, shared solves, tag strength.
- `weak_topics(handle, min_attempts=3)` — tags with the lowest solve rate.
- `upcoming_contests(count=5)` — next contests, soonest first.
- `contest_performance(handle, contest_id)` — rank, points, penalty, and rating delta for one contest.
- `solve_streak(handle)` — current and longest daily solve streak.
- `rating_progress(handle)` — rating history summary, best/worst contest, plateau detection.

All CF API calls are made with a signed, authenticated request (`apiKey`/`time`/`apiSig`),
and every tool returns a small, pre-aggregated result rather than raw API payloads.
