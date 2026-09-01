# Job Hunter Agent

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support%20this%20project-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/YahyaZekry)

Reads your resume, finds remote jobs worth applying to, and writes the application for you. Each match gets a CV rebuilt for that specific posting, and a cover letter whenever you ask for one.

Then it checks its own work. A second, independent pass reads every letter with fresh context and removes anything it cannot find in your resume.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/dashboard-dark.png">
  <img alt="The dashboard, showing scored job matches with a cover letter and tailored CV button on each card" src="docs/dashboard-light.png">
</picture>

Works for any profession. Developer, designer, virtual assistant, writer, accountant. Your roles, search queries, scoring and copy all come from your `resume.md`, and nothing about your field is hardcoded.

## Why the fact-check matters

Language models embellish. On real runs this one caught:

- **"four years"** when the resume said 2021 to present, which is five
- **"available full-time"** when the current role was listed as part-time
- **a tool claimed as a core skill** that appeared in the skills list with no project behind it

Every one of those falls apart in an interview. The checker only sees three things: the job posting, your resume, and the letter. It never saw the letter being written, so it has no reason to defend it.

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env     # add FIRECRAWL_API_KEY
```

Put your resume at `resume.md`. It is gitignored and never leaves your machine. Then:

```bash
.venv/bin/python server.py    # → http://127.0.0.1:8000
```

**You need:** Python 3.10+, a command-line AI tool signed in, and a [Firecrawl](https://firecrawl.dev) key. The default is [Claude Code](https://claude.com/claude-code); see below for using something else.

**Optional:** [`typst`](https://github.com/typst/typst) for CVs, `pdftotext` from poppler for the ATS check, and an [Exa](https://exa.ai) key for pages Firecrawl cannot reach.

## Using a different AI tool

The pipeline shells out to a command-line AI tool. Claude Code is the default because that is what it was built against, but nothing depends on it. Two variables in `.env` point it at anything else:

```bash
LLM_CLI=codex
LLM_ARGS=exec {prompt}
```

```bash
LLM_CLI=gemini
LLM_ARGS=-p {prompt}
```

`{prompt}` is replaced with the full prompt text. Everything else is passed through exactly as written, so any tool that takes a prompt and prints an answer to stdout will work.

The model is never asked to open a file. Python inlines whatever each prompt needs, which means no tool needs filesystem permissions, and the shared rules in `prompts/_context.md` reach every provider identically.

## How a run works

| Step | What happens |
|------|--------------|
| **0. Find roles** | The model reads your resume and suggests target roles and key skills. You pick which ones this run covers. |
| **1. Build queries** | Your roles, skills and preferences become search queries, one per source. |
| **2. Discover and scrape** | Firecrawl searches, then scrapes a batch of result pages into individual job postings. |
| **3. Score** | Every posting is scored 0 to 100 against your profile: skills, seniority, remote signals, freshness, location, language and red flags. |
| **4. CVs** | Every job scoring 70 or above gets its own CV, compiled to PDF and checked the way an ATS would read it. |

Cover letters are not written in bulk. You ask for one job at a time, and it gets fact-checked before you ever see it.

## What each button does

### Cover letter

If a letter already exists for that job, it opens. If not, you get a short explanation and a **Write it** button.

The model drafts the letter from your resume. A second, separate run then reads it, checks every claim against your resume, and removes what it cannot find. That second run never saw the first one happen, so it has no reason to defend the text. You end up with the finished letter, a Copy button, and a collapsed section called "what was checked" holding:

- the claims that were removed, and why
- what the job asked for against what you actually have, marked as *you have it*, *close enough, said honestly*, or *you do not have it*
- the original draft, so you can see exactly what changed

Gaps are fine. The checker only objects when a letter hides one.

Everything is saved to `output/applications/<company>__<role>/` and tracked in `output/applications.csv`.

### Tailored CV

Every job scoring 70 or above gets its own CV, rebuilt from `resume.md` for that posting. Same facts, different shape. The experience and skills the posting asks for move to the front, and the rest is trimmed.

From one real run on the same resume:

| Job | The CV led with |
|-----|-----------------|
| AI evaluation role | Agentic AI: multi-agent systems, tool orchestration, agent evaluation |
| React Native role | Mobile and Web: React Native, Expo, iOS/Android |

Nothing is invented. Tailoring means choosing and ordering, never adding. If a CV runs onto a second page it is rewritten once, told to cut the least relevant material.

`templates/cv.typ` controls the styling. Edit it and preview with `typst compile templates/cv.typ`.

### Find more

A search finds far more pages than one run scrapes. In practice 46 to 168 found, 20 scraped. The rest are not thrown away, they sit in a queue.

This button scrapes the next batch. No repeated search, no page scraped twice, and any letter or CV already written is skipped. That makes a second look cheaper than starting over. No single site gets more than 3 pages per batch, so one careers page cannot eat the whole budget.

### New search

Starts over: new queries, fresh discovery, fresh scraping. This replaces the queue, so anything left over from the last search is discarded. Use **Find more** instead if you just want more results from the search you already paid for.

## Preferences

Before a search you can edit everything the model pulled out of your resume, and add your own.

**Roles and skills** arrive as chips read from `resume.md`. Uncheck one to leave it out of this run, click the × to delete it, or type your own and press Enter. Your edits are remembered, so re-reading the resume after you change it will not quietly undo them.

**Exclude** drops any posting that mentions a term you list, before anything is scored. That means it costs no tokens and the model never gets a chance to talk itself round. Terms match as whole words against the title and description, so excluding "java" will not drop JavaScript roles, and "on-site" will not fire on "onsite". The run summary tells you how many postings each term removed, so a filter can never quietly shrink your results.

Employment type, pay and currency, and location feed into both the search queries and the scoring.

"Worldwide Remote" and a specific country are mutually exclusive, so they cannot combine into "worldwide or Egypt" and quietly widen your search. Note that typing a country searches *for* that country. There is no way to exclude one.

## How the writing sounds

The letter prompt bans em dashes, stock phrases like "passionate about" and "proven track record", and inflated words like "leverage" and "seamlessly". Sentences are capped at around 25 words. The checker flags anything that slips through, and a final pass strips any dash that survives both.

The goal is a letter that reads like a person emailing a stranger about a job.

## Where things are saved

Everything lands in `output/`, which is gitignored:

| Path | What is in it |
|------|---------------|
| `jobs.json` | Scored jobs |
| `raw_jobs.json` | Everything scraped |
| `page_queue.json` | Pages found, and which have been scraped |
| `cvs/` | Tailored `.typ` sources and compiled `.pdf` files |
| `applications/<slug>/` | The saved posting, first draft, review, and final letter |
| `applications.csv` | The tracker: date, company, role, status, score, file paths |

## Configuration

`config.json` sets where the agent searches. `job_boards` gets one query each, and `reddit_groups` are searched as groups with optional extra terms. The defaults are remote-first worldwide with no region-specific boards.

Add your own if your field has dedicated boards. One thing to know: `job_boards` are searched every run no matter what location you set, so a board tied to one region keeps surfacing that region regardless.

## Development

```bash
.venv/bin/python -m pytest       # 84 tests, everything external mocked
.venv/bin/python agent.py        # headless, no UI
```

```
agent.py          # the whole pipeline plus the letter flow
server.py         # FastAPI, server-sent events for progress
ui/index.html     # single-file dashboard, no build step
prompts/          # _context.md is shared, then one prompt per step
templates/cv.typ  # CV layout
```

`.project-knowledge/` holds the living docs: architecture, data shapes, past decisions and a roadmap of known limits.

## Known limits

- Listing pages often give short teaser descriptions, because the full text is not on the page to scrape
- LinkedIn returns nothing usable through either Firecrawl or Exa
- `posted_date` arrives as free text like "11 months ago" and feeds the freshness rule without being normalised
- Nothing in the UI shows what was tailored in a CV, so the work stays invisible unless you compare two of them

## Support

Built while job hunting, and it runs on an AI CLI subscription you already have plus Firecrawl's free tier for exactly that reason. If it saved you hours of scrolling or helped you land an interview:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/YahyaZekry)

## Credits and license

MIT. Originally created by [Kurt De Austria](https://github.com/Kurt-Chan) as [ai-job-scraper](https://github.com/Kurt-Chan/ai-job-scraper). The pipeline shape is his. Substantially extended since then with CV generation, the fact-checked letter flow, the application tracker, and the rework of how discovery and scraping relate.

Both copyright notices are kept in [`LICENSE`](LICENSE), as MIT requires.

Stars, issues and pull requests are all appreciated.

---

<details>
<summary>🧠 AI Context</summary>

This project uses the [project-knowledge](https://github.com/YahyaZekry/project-knowledge-skill) skill to maintain a `.project-knowledge/` folder, a living, AI-readable map of the codebase. Every AI session loads only the files relevant to the current task instead of scanning from scratch.

Built by [Yahya Zekry](https://github.com/YahyaZekry/project-knowledge-skill).

</details>
