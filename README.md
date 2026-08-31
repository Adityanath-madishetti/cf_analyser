# cf-analyser

A local MCP server for analysing Codeforces activity: weekly practice summaries, problem
recommendations, user comparisons, weak-topic detection, contest tracking, and rating
progress. Backed by the public [Codeforces API](https://codeforces.com/apiHelp), with every
request signed and authenticated for higher rate limits and reliability.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Codeforces API key and secret — generate one at https://codeforces.com/settings/api

## Setup

1. Clone the repo and install dependencies:
   ```
   git clone <this-repo-url>
   cd cf_analyser
   uv sync
   ```
2. Copy `.env.example` to `.env` and fill in your API key/secret:
   ```
   cp .env.example .env
   ```
   (`.env` isn't loaded automatically — it's just there as a reference for the values you'll
   put into your MCP client config in the next step.)

## Adding to Claude Desktop / Claude Code

Add an MCP server entry pointing at this project. Find the absolute path to `uv` with
`which uv`, and use the absolute path to wherever you cloned this repo — Claude launches MCP
servers without your shell's `PATH`, so a bare `"uv"` command may fail to resolve.

Claude Desktop: edit `claude_desktop_config.json` (on macOS,
`~/Library/Application Support/Claude/claude_desktop_config.json`). Claude Code: use
`claude mcp add` or edit its MCP config the same way.

```json
{
  "mcpServers": {
    "cf-analyser": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "--directory", "/absolute/path/to/cf_analyser", "cf-analyser"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/cf_analyser/src",
        "CF_API_KEY": "your-api-key",
        "CF_API_SECRET": "your-api-secret"
      }
    }
  }
}
```

Restart Claude Desktop/Code afterwards so it picks up the new server.

## Running standalone (for testing)

```
CF_API_KEY=... CF_API_SECRET=... PYTHONPATH=src uv run cf-analyser
```

Or use the MCP inspector to poke at tools interactively in the browser:

```
CF_API_KEY=... CF_API_SECRET=... PYTHONPATH=src uv run mcp dev src/cf_analyser/server.py
```

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

Once connected, just ask Claude things like *"analyse my Codeforces week"*, *"recommend some
problems for me"*, or *"compare me with tourist"* — it'll call the right tool automatically.

## Troubleshooting

- **Server doesn't show up in Claude**: double-check the `command` path is absolute and
  correct (`which uv`), and that `--directory` points at this repo.
- **"CF_API_KEY and CF_API_SECRET must be set"**: the `env` block in your MCP config is
  missing or has empty values.
- **Tool calls fail with a Codeforces error message**: usually an invalid handle, or an
  invalid/expired API key or secret — regenerate one at
  https://codeforces.com/settings/api if needed.

## License

I never understood what this actually is 
