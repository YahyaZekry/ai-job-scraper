# Stack

> Part of job-hunter-agent/.project-knowledge/ | Last updated: 2026-08-27

## Tech Stack

| Category | Details |
|----------|---------|
| Language | Python 3.10+ |
| Runtime | CPython, single process |
| Framework | FastAPI (server.py) + uvicorn |
| Database | None — flat JSON files in `output/` |
| ORM / Query | N/A |
| Auth | None (local-only tool) |
| Styling | Tailwind (CDN, no build step) |
| State Mgmt | Vanilla JS, in-memory (`allJobs` array in `ui/index.html`) |
| Testing | pytest + httpx (FastAPI TestClient) |
| Key Libraries | `firecrawl-py` (search + scrape), `exa-py` (fallback extraction), `python-dotenv`. Stdlib `csv` backs the application tracker |
| AI | Any command-line AI tool, invoked as a subprocess. `LLM_CLI` / `LLM_ARGS` select it; defaults to `claude`. Not an SDK, and no provider library is imported |
| Deployment | None — local dev tool, run via `python server.py` |

## Dev Commands

| Command | What It Does |
|---------|-------------|
| `python -m venv .venv && .venv/bin/pip install -r requirements.txt` | Install deps (needed on externally-managed Python distros, e.g. Arch — plain `pip install` fails there) |
| `python server.py` | Start FastAPI dashboard at http://127.0.0.1:8000 |
| `python agent.py` | Run the 5-step pipeline headless (no UI) |
| `pytest` | Run `test_pipeline.py` + `test_server.py` — 84 tests, everything external mocked (the AI CLI, Firecrawl, Exa, typst, pdftotext) |
| `typst compile templates/cv.typ` | Render the CV template standalone to check styling changes |

## Environment Variables

| Variable | Used In | What It Enables |
|----------|---------|----------------|
| `FIRECRAWL_API_KEY` | `agent.py` (`scrape_jobs`) | Firecrawl search + scrape calls |
| `EXA_API_KEY` | `agent.py` (`scrape_jobs`, `_extract_via_exa`) | Optional. Fallback structured extraction for pages Firecrawl can't scrape (LinkedIn, Reddit respond "Website Not Supported"). Pipeline works without it — falls straight to the search snippet instead |

## CV Toolchain (for the apply stage — Typst chosen 2026-08-16)

| Tool | Where | Purpose |
|------|-------|---------|
| `typst` (v0.15.1) | `~/.local/bin/typst` | **The** CV compiler (approved 2026-08-16) — single binary, ~0.27 s compiles, deterministic, clean ATS text layer. Template: `templates/cv.typ` |
| ~~Portable TinyTeX (LaTeX)~~ | `~/.TinyTeX/bin/x86_64-linux/lualatex` | ~~Fallback CV compiler~~ — dropped in favor of Typst; needed `tlmgr` package installs (`fontawesome5`, `luatexbase`), ~0.8 s compiles, icon glyphs leaked as noise into the ATS text layer. Still installed on this machine, unused by the project |
| Font Awesome 5 OTFs | `~/.local/share/fonts` | Section icons in the CV (referenced by codepoint via `str.from-unicode()`, no built-in `icon()` in Typst 0.15) |
| `pdftotext` (poppler-utils) | PATH | ATS text-layer verification of compiled CVs (email/phone literal, reading order, keyword coverage) |

Scratch renders from the test-drive were in `/tmp/opencode/cv-demo/` (volatile); the surviving artifact is `templates/cv.typ`.

## External Prerequisites (not env vars)

- A command-line AI tool must be installed and authenticated on PATH. `agent.py` shells out to it via `subprocess.run` in `run_llm()`. `LLM_CLI` picks the binary (default `claude`) and `LLM_ARGS` templates its argv, with `{prompt}` replaced by the prompt text. No provider API key is used directly.
- `resume.md` in project root — gitignored, user-supplied, required for the pipeline to run at all (`run_pipeline` raises `RuntimeError` if missing).
