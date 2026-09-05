# Phase 4 validation - a claim fetched instead of remembered

**Capability under test:** search and a real browser, and the difference they
make to the failure Phase 3 ended on - a researcher citing a URL that does not
exist.

## How it was run

Against `gpt-oss:20b`, with Playwright's Chromium installed
(`uv sync --extra browser && uv run playwright install chromium`).

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
export KAI_WORKSPACE_DIR=/tmp/research
uv run kai run-task --employee researcher \
  "Find out what SQLite's WAL mode changes about concurrent reads and writes. Search for it, open the official documentation page, and quote what it actually says. Save your answer to wal.md."
```

## Result - passed, 2026-09-05

Seven steps: `web.search` (keyless, ten results), `browser.open` on
`https://sqlite.org/wal.html`, `browser.extract` (30,757 characters of page
text, truncated to 20,000 for the model), then `fs.write` of `wal.md`.
Cost $0.00.

The quotes in `wal.md` are verbatim from the page - checked afterwards against
`curl https://sqlite.org/wal.html`:

> WAL provides more concurrency as readers do not block writers and a writer
> does not block readers. Reading and writing can proceed concurrently.

> Writers merely append new content to the end of the WAL file. [...] since
> there is only one WAL file, there can only be one writer at a time.

This is the Phase 3 failure closed: the same question, answered from the page
rather than from the model's memory.

## What this run changed in the code

The first two attempts failed at the step limit, and both were the tool layer's
fault rather than the model's:

1. The model called `browser.open` with `{"id": ...}` instead of `{"url": ...}`
   and could not find its way back from "Unknown argument: id". Failure messages
   now carry the call shape: `Call browser.open like this: {"url": <string>}`.
   It recovered on the next step.
2. The model garnished correct calls with keys from some other harness -
   `{"url": ..., "cursor": 0, "loc": 200}` - and the whole call was being thrown
   away over them. Six of twelve steps went on that. Unknown arguments are now
   dropped and reported back in the result (`ignored_arguments`) instead of
   refusing a call whose required arguments were all correct.

Both are recorded as tests in `tests/unit/test_web_tools.py`, with the
observation that produced them.

## What this does not prove

**Search is scraped, not bought.** `DuckDuckGoSearch` reads the HTML endpoint,
which needs no key and no account - and can change without warning. The
`SearchEngine` protocol is what everything else depends on, so replacing it with
a paid API is one adapter and one line in the container.

**The model still decorates its citations.** `wal.md` carries markers like
`【1†L1-L4】`, an artifact of this model's training rather than anything the
tools produced. The quotes behind them are real; the markers are noise.

**One page, opened deliberately.** This scenario says "open the official
documentation"; it does not test a browsing session that has to navigate,
follow links or fill in a form. That is what Phase 5 is for.
