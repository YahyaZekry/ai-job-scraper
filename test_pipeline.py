import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest


def test_discover_pages_interleaves_results_across_queries():
    import agent
    results = {
        "q1": [SimpleNamespace(url=f"https://a.com/{i}", title="", description="") for i in range(3)],
        "q2": [SimpleNamespace(url=f"https://b.com/{i}", title="", description="") for i in range(2)],
        "q3": [],
    }
    fake_app = SimpleNamespace(search=lambda q, limit: SimpleNamespace(web=results[q]))

    pages = agent.discover_pages(fake_app, ["q1", "q2", "q3"])

    assert [p["url"] for p in pages] == [
        "https://a.com/0",
        "https://b.com/0",
        "https://a.com/1",
        "https://b.com/1",
        "https://a.com/2",
    ]


def test_discover_pages_dedupes_regional_subdomains():
    import agent
    results = {
        "q1": [SimpleNamespace(url="https://www.indeed.com/viewjob?jk=abc", title="", description="")],
        "q2": [
            SimpleNamespace(url="https://in.indeed.com/viewjob?jk=abc", title="", description=""),
            SimpleNamespace(url="https://uk.linkedin.com/jobs/view/123", title="", description=""),
        ],
        "q3": [SimpleNamespace(url="https://www.linkedin.com/jobs/view/123", title="", description="")],
    }
    fake_app = SimpleNamespace(search=lambda q, limit: SimpleNamespace(web=results[q]))

    pages = agent.discover_pages(fake_app, ["q1", "q2", "q3"])

    assert [p["url"] for p in pages] == [
        "https://www.indeed.com/viewjob?jk=abc",
        "https://uk.linkedin.com/jobs/view/123",
    ]


def test_canonical_host_leaves_regular_domains_alone():
    import agent
    assert agent._canonical_host("www.indeed.com") == "indeed.com"
    assert agent._canonical_host("ng.indeed.com") == "indeed.com"
    assert agent._canonical_host("ph.jobstreet.com") == "jobstreet.com"
    assert agent._canonical_host("onlinejobs.ph") == "onlinejobs.ph"
    assert agent._canonical_host("glassdoor.co.uk") == "glassdoor.co.uk"
    assert agent._canonical_host("reddit.com") == "reddit.com"


def test_run_pipeline_emits_all_step_events(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    mock_resume_info = {"target_roles": ["Frontend Developer"], "key_skills": ["React"]}
    mock_config = {"search_queries": ["frontend dev remote"]}
    mock_raw_jobs = [{"title": "Dev", "company": "Co", "location": "Remote",
                      "url": "https://example.com", "description": "",
                      "posted_date": "", "source": "example.com"}]
    mock_analyzed = [{"title": "Dev", "company": "Co", "url": "https://example.com",
                      "score": 85, "verdict": "apply", "match_reasons": [],
                      "red_flags": [], "suggested_angle": ""}]

    events = []

    with patch.object(agent, "analyze_resume", return_value=mock_resume_info), \
         patch.object(agent, "build_search_config", return_value=mock_config), \
         patch.object(agent, "scrape_jobs", return_value=mock_raw_jobs), \
         patch.object(agent, "analyze_jobs", return_value=mock_analyzed), \
         patch.object(agent, "generate_cvs"):
        result = agent.run_pipeline(on_progress=lambda s, l, st: events.append((s, st)))

    step_statuses = {(s, st) for s, st in events}
    assert (1, "running") in step_statuses
    assert (1, "done") in step_statuses
    assert (2, "running") in step_statuses
    assert (2, "done") in step_statuses
    assert (3, "running") in step_statuses
    assert (3, "done") in step_statuses
    assert (4, "running") in step_statuses
    assert (4, "done") in step_statuses
    assert result["total"] == 1 and result["above_threshold"] == 1
    assert result["excluded"] == 0


def test_run_pipeline_raises_when_resume_missing(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Missing resume.md"):
        agent.run_pipeline()


def test_run_pipeline_works_without_callback(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    mock_resume_info = {"target_roles": ["Frontend Developer"], "key_skills": ["React"]}
    mock_config = {"search_queries": ["q"]}
    mock_raw_jobs = [{"title": "Dev", "company": "Co", "location": "Remote",
                      "url": "https://example.com", "description": "",
                      "posted_date": "", "source": "example.com"}]
    mock_analyzed = [{"title": "Dev", "url": "https://example.com", "score": 50,
                      "verdict": "skip", "match_reasons": [], "red_flags": [],
                      "suggested_angle": ""}]

    with patch.object(agent, "analyze_resume", return_value=mock_resume_info), \
         patch.object(agent, "build_search_config", return_value=mock_config), \
         patch.object(agent, "scrape_jobs", return_value=mock_raw_jobs), \
         patch.object(agent, "analyze_jobs", return_value=mock_analyzed), \
         patch.object(agent, "generate_cvs"):
        result = agent.run_pipeline()

    assert result["total"] == 1
    assert result["above_threshold"] == 0


def test_analyze_resume_extracts_roles_and_skills():
    import agent
    mock_result = {"target_roles": ["Frontend Developer"], "key_skills": ["React"]}
    with patch.object(agent, "run_llm_json", return_value=mock_result) as mock_call:
        result = agent.analyze_resume()
    assert result == mock_result
    assert mock_call.call_args[0][0] == "prompts/analyze_resume.md"


def test_build_search_config_passes_roles_skills_and_preferences(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    captured = {}

    def fake_run_llm_json(prompt_file, context=""):
        captured["prompt_file"] = prompt_file
        captured["context"] = context
        return {"search_queries": ["q1"]}

    with patch.object(agent, "run_llm_json", side_effect=fake_run_llm_json):
        config = agent.build_search_config(["Frontend Developer"], ["React"], "Egypt, USD, part-time")

    assert captured["prompt_file"] == "prompts/build_queries.md"
    assert "Frontend Developer" in captured["context"]
    assert "React" in captured["context"]
    assert "Egypt, USD, part-time" in captured["context"]
    assert config["target_roles"] == ["Frontend Developer"]
    assert config["key_skills"] == ["React"]
    saved = json.loads((tmp_path / "output" / "search_config.json").read_text())
    assert saved["target_roles"] == ["Frontend Developer"]


def test_build_search_config_omits_preferences_line_when_not_given(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    captured = {}

    def fake_run_llm_json(prompt_file, context=""):
        captured["context"] = context
        return {"search_queries": []}

    with patch.object(agent, "run_llm_json", side_effect=fake_run_llm_json):
        agent.build_search_config(["Frontend Developer"], ["React"])

    assert "Run preferences" not in captured["context"]


def test_run_pipeline_uses_given_resume_info_and_skips_analyze_resume(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    resume_info = {"target_roles": ["Frontend Developer"], "key_skills": ["React"]}
    mock_raw_jobs = [{"title": "Dev", "company": "Co", "location": "Remote",
                      "url": "https://example.com", "description": "",
                      "posted_date": "", "source": "example.com"}]
    mock_analyzed = [{"title": "Dev", "url": "https://example.com", "score": 90,
                      "verdict": "apply", "match_reasons": [], "red_flags": [],
                      "suggested_angle": ""}]
    captured = {}

    def fake_build_search_config(roles, skills, preferences=""):
        captured["roles"] = roles
        captured["skills"] = skills
        captured["preferences"] = preferences
        return {"search_queries": ["q"]}

    def _boom():
        raise AssertionError("analyze_resume should not be called when resume_info is given")

    with patch.object(agent, "analyze_resume", side_effect=_boom), \
         patch.object(agent, "build_search_config", side_effect=fake_build_search_config), \
         patch.object(agent, "scrape_jobs", return_value=mock_raw_jobs), \
         patch.object(agent, "analyze_jobs", return_value=mock_analyzed), \
         patch.object(agent, "generate_cvs"):
        agent.run_pipeline(resume_info=resume_info, preferences="Egypt, USD, part-time")

    assert captured == {"roles": ["Frontend Developer"], "skills": ["React"], "preferences": "Egypt, USD, part-time"}


def test_run_llm_json_strips_markdown_fences():
    import agent
    fenced = '```json\n{"target_roles": ["Virtual Assistant"]}\n```'
    with patch.object(agent, "run_llm", return_value=fenced):
        assert agent.run_llm_json("prompts/x.md") == {"target_roles": ["Virtual Assistant"]}


def test_run_llm_json_passes_plain_json_through():
    import agent
    with patch.object(agent, "run_llm", return_value='[{"score": 88}]'):
        assert agent.run_llm_json("prompts/x.md") == [{"score": 88}]


def test_run_llm_json_extracts_json_from_surrounding_prose():
    import agent
    chatty = (
        "I don't have write permission for `output/jobs.json`. Per the task "
        'instructions, here is the raw JSON array:\n\n[{"title": "Support Rep", '
        '"score": 72}]\n\nLet me know if you need anything else.'
    )
    with patch.object(agent, "run_llm", return_value=chatty):
        assert agent.run_llm_json("prompts/x.md") == [{"title": "Support Rep", "score": 72}]


def test_run_llm_json_still_fails_loudly_on_no_json():
    import agent
    with patch.object(agent, "run_llm", return_value="Sorry, I cannot do that."):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            agent.run_llm_json("prompts/x.md")


def test_load_config_returns_defaults_without_file(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    cfg = agent.load_config()
    assert "linkedin.com/jobs" in cfg["job_boards"]
    assert any(g["name"] == "Community" for g in cfg["reddit_groups"])


def test_load_config_overrides_from_file(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({"job_boards": ["remoteok.com"]}))
    cfg = agent.load_config()
    assert cfg["job_boards"] == ["remoteok.com"]
    assert cfg["reddit_groups"] == agent.DEFAULT_CONFIG["reddit_groups"]


def test_sources_context_lists_boards_and_groups():
    import agent
    ctx = agent._sources_context({
        "job_boards": ["remoteok.com", "weworkremotely.com"],
        "reddit_groups": [
            {"name": "Dev", "subreddits": ["webdev", "cscareers"], "extra_terms": "hiring"},
            {"name": "Gigs", "subreddits": ["freelance"]},
        ],
    })
    assert "- remoteok.com" in ctx
    assert "- weworkremotely.com" in ctx
    assert "Dev: r/webdev, r/cscareers" in ctx
    assert '"hiring"' in ctx
    assert "Gigs: r/freelance" in ctx


def test_run_llm_raises_when_cli_missing(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("hello")
    with patch.object(agent.shutil, "which", return_value=None):
        with pytest.raises(RuntimeError, match="not found on PATH"):
            agent.run_llm("prompt.md")


def test_run_llm_raises_runtime_error_when_exec_fails(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("hello")

    def _boom(*a, **k):
        raise OSError(8, "Exec format error")

    with patch.object(agent.shutil, "which", return_value="/home/user/.npm-global/bin/claude"), \
         patch.object(agent.subprocess, "run", side_effect=_boom):
        with pytest.raises(RuntimeError, match="failed to run"):
            agent.run_llm("prompt.md")


def test_run_llm_uses_resolved_executable(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("hello")
    fake_result = SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
    with patch.object(agent.shutil, "which", return_value="/usr/local/bin/claude"), \
         patch.object(agent.subprocess, "run", return_value=fake_result) as mock_run:
        out = agent.run_llm("prompt.md")
    assert out == "ok"
    assert mock_run.call_args[0][0][0] == "/usr/local/bin/claude"


def test_extract_postings_uses_firecrawl_when_it_succeeds():
    import agent
    page = {"url": "https://indeed.com/job/1", "title": "snippet title", "description": "snippet desc"}
    fake_app = SimpleNamespace(scrape=lambda *a, **k: SimpleNamespace(
        json={"jobs": [{"title": "Dev", "company": "Co", "url": "/job/1"}]}
    ))

    postings = agent.extract_postings(fake_app, exa=None, page=page)

    assert postings == [{
        "title": "Dev", "company": "Co", "location": "Remote",
        "url": "https://indeed.com/job/1", "description": "", "posted_date": "",
        "source": "indeed.com",
    }]


def test_extract_postings_falls_back_to_exa_when_firecrawl_fails():
    import agent

    def _boom(*a, **k):
        raise RuntimeError("Website Not Supported")

    fake_app = SimpleNamespace(scrape=_boom)
    fake_exa = SimpleNamespace(get_contents=lambda urls, summary: SimpleNamespace(
        results=[SimpleNamespace(summary=json.dumps({"jobs": [{"title": "Dev", "company": "Co"}]}))]
    ))
    page = {"url": "https://www.linkedin.com/jobs/view/1", "title": "t", "description": "d"}

    postings = agent.extract_postings(fake_app, exa=fake_exa, page=page)

    assert postings[0]["title"] == "Dev"
    assert postings[0]["source"] == "linkedin.com"


def test_extract_postings_falls_back_to_snippet_when_exa_also_fails():
    import agent

    def _boom(*a, **k):
        raise RuntimeError("Website Not Supported")

    fake_app = SimpleNamespace(scrape=_boom)
    fake_exa = SimpleNamespace(get_contents=_boom)
    page = {"url": "https://www.linkedin.com/jobs/view/1", "title": "snippet title", "description": "d"}

    postings = agent.extract_postings(fake_app, exa=fake_exa, page=page)

    assert postings == [{
        "title": "snippet title", "company": "", "location": "Remote",
        "url": "https://www.linkedin.com/jobs/view/1", "description": "d",
        "posted_date": "", "source": "linkedin.com",
    }]


def test_extract_postings_skips_exa_when_not_configured():
    import agent

    def _boom(*a, **k):
        raise RuntimeError("Website Not Supported")

    fake_app = SimpleNamespace(scrape=_boom)
    page = {"url": "https://www.linkedin.com/jobs/view/1", "title": "snippet title", "description": "d"}

    postings = agent.extract_postings(fake_app, exa=None, page=page)

    assert postings[0]["title"] == "snippet title"


def test_analyze_jobs_writes_jobs_json(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    analyzed = [{"title": "Dev", "score": 85, "verdict": "apply"}]
    with patch.object(agent, "run_llm", return_value=json.dumps(analyzed)):
        result = agent.analyze_jobs()

    assert result == analyzed
    assert json.loads((tmp_path / "output" / "jobs.json").read_text()) == analyzed


def test_analyze_jobs_includes_preferences_in_context(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    captured = {}

    def fake_run_llm(prompt_file, context=""):
        captured["context"] = context
        return "[]"

    with patch.object(agent, "run_llm", side_effect=fake_run_llm):
        agent.analyze_jobs(preferences="Egypt, USD, part-time")

    assert "Egypt, USD, part-time" in captured["context"]


def test_generate_cvs_writes_source_and_compiles(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    job = {"company": "Tech Co", "title": "Backend Engineer"}

    compiled = []
    with patch.object(agent, "run_llm", return_value="#set page()\n= CV"), \
         patch.object(agent, "_compile_cv", side_effect=lambda p: compiled.append(p) or p), \
         patch.object(agent, "_verify_cv", return_value=[]):
        agent.generate_cvs([job])

    source = (tmp_path / "output" / "cvs" / "tech-co__backend-engineer.typ").read_text()
    assert source == "#set page()\n= CV"
    assert compiled == [Path("output/cvs/tech-co__backend-engineer.typ")]


def test_generate_cvs_strips_markdown_fences(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)

    with patch.object(agent, "run_llm", return_value="```typst\n#set page()\n```"), \
         patch.object(agent, "_compile_cv"), patch.object(agent, "_verify_cv", return_value=[]):
        agent.generate_cvs([{"company": "Co", "title": "Dev"}])

    assert (tmp_path / "output" / "cvs" / "co__dev.typ").read_text() == "#set page()"


def test_generate_cvs_survives_a_failing_job(tmp_path, monkeypatch, capsys):
    import agent
    monkeypatch.chdir(tmp_path)

    with patch.object(agent, "run_llm", return_value="#set page()"), \
         patch.object(agent, "_compile_cv", side_effect=RuntimeError("typst compile failed")), \
         patch.object(agent, "_verify_cv", return_value=[]):
        agent.generate_cvs([{"company": "Co", "title": "Dev"}])

    assert "typst compile failed" in capsys.readouterr().out


def test_verify_cv_flags_missing_email_and_extra_pages(tmp_path, monkeypatch):
    import agent
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF")
    text = " ".join(["word"] * 60) + "\f" + "second page\f"

    with patch.object(agent.shutil, "which", return_value="/usr/bin/pdftotext"), \
         patch.object(agent.subprocess, "run",
                      return_value=SimpleNamespace(returncode=0, stdout=text)):
        warnings = agent._verify_cv(pdf)

    assert any("email" in w for w in warnings)
    assert any("pages" in w for w in warnings)


def test_verify_cv_passes_a_clean_one_pager(tmp_path):
    import agent
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF")
    text = "me@example.com " + " ".join(["word"] * 60)

    with patch.object(agent.shutil, "which", return_value="/usr/bin/pdftotext"), \
         patch.object(agent.subprocess, "run",
                      return_value=SimpleNamespace(returncode=0, stdout=text)):
        assert agent._verify_cv(pdf) == []


def test_verify_cv_skipped_when_pdftotext_missing(tmp_path):
    import agent
    with patch.object(agent.shutil, "which", return_value=None):
        assert agent._verify_cv(tmp_path / "cv.pdf") == []


def test_apply_edits_replaces_exact_matches():
    import agent
    text = "I led the migration. I mentored engineers."
    edits = [{"old_string": "led the migration", "new_string": "worked on the migration"}]

    revised, skipped = agent._apply_edits(text, edits)

    assert revised == "I worked on the migration. I mentored engineers."
    assert skipped == []


def test_apply_edits_deletes_on_empty_new_string():
    import agent
    revised, skipped = agent._apply_edits("Keep this. Cut this.", [{"old_string": " Cut this.", "new_string": ""}])
    assert revised == "Keep this."
    assert skipped == []


def test_apply_edits_skips_unmatched_and_ambiguous_edits():
    import agent
    text = "the same phrase and the same phrase again"
    edits = [
        {"old_string": "never appears", "new_string": "x"},
        {"old_string": "the same phrase", "new_string": "y"},
    ]

    revised, skipped = agent._apply_edits(text, edits)

    assert revised == text
    assert len(skipped) == 2
    assert any("no match" in s for s in skipped)
    assert any("2 matches" in s for s in skipped)


def test_apply_to_job_writes_posting_draft_review_and_letter(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    job = {"company": "Tech Co", "title": "Backend Engineer", "url": "https://example.com/j/1",
           "description": "We need Python.", "score": 88}
    review = {"ungrounded_claims": [], "coverage": [],
              "edits": [{"old_string": "eight", "new_string": "5"}]}

    with patch.object(agent, "run_llm", return_value="I have eight years of Python."), \
         patch.object(agent, "run_llm_json", return_value=review):
        result = agent.apply_to_job(job)

    out = tmp_path / "output" / "applications" / "tech-co__backend-engineer"
    assert "We need Python." in (out / "job_posting.md").read_text()
    assert (out / "cover_letter_draft.md").read_text() == "I have eight years of Python."
    assert (out / "cover_letter.md").read_text() == "I have 5 years of Python."
    assert json.loads((out / "review.json").read_text()) == review
    assert result["revised"] == "I have 5 years of Python."
    assert result["skipped_edits"] == []


def test_apply_to_job_reviews_the_exact_draft_it_wrote(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    captured = {}

    with patch.object(agent, "run_llm", return_value="The drafted letter."), \
         patch.object(agent, "run_llm_json",
                      side_effect=lambda f, context="": captured.update(context=context) or {"edits": []}):
        agent.apply_to_job({"company": "Co", "title": "Dev", "url": "u"})

    assert "---DRAFT---\nThe drafted letter." in captured["context"]


def test_apply_to_job_emits_progress_labels(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    labels = []

    with patch.object(agent, "run_llm", return_value="draft"), \
         patch.object(agent, "run_llm_json", return_value={"edits": []}):
        agent.apply_to_job({"company": "Co", "title": "Dev", "url": "u"}, on_progress=labels.append)

    assert labels == ["Drafting", "Reviewing", "Revising"]


def test_record_application_writes_a_row(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    agent.record_application({"company": "Co", "title": "Dev", "url": "https://x/1", "score": 91})

    rows = list(csv.DictReader((tmp_path / "output" / "applications.csv").open()))
    assert len(rows) == 1
    assert rows[0]["company"] == "Co"
    assert rows[0]["fit_score"] == "91"
    assert rows[0]["status"] == "drafted"


def test_record_application_updates_instead_of_duplicating(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    agent.record_application({"company": "Co", "title": "Dev", "url": "https://x/1"})
    agent.record_application({"company": "Co", "title": "Dev", "url": "https://x/1"}, cv_file="cv.pdf")

    rows = list(csv.DictReader((tmp_path / "output" / "applications.csv").open()))
    assert len(rows) == 1
    assert rows[0]["cv_file"] == "cv.pdf"


def test_set_application_status_updates_a_tracked_row(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    agent.record_application({"company": "Co", "title": "Dev", "url": "https://x/1"})

    agent.set_application_status("https://x/1", "applied")

    rows = list(csv.DictReader((tmp_path / "output" / "applications.csv").open()))
    assert rows[0]["status"] == "applied"


def test_set_application_status_ignores_untracked_jobs(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    agent.record_application({"company": "Co", "title": "Dev", "url": "https://x/1"})

    agent.set_application_status("https://never-drafted", "applied")

    rows = list(csv.DictReader((tmp_path / "output" / "applications.csv").open()))
    assert len(rows) == 1
    assert rows[0]["status"] == "drafted"


def test_set_application_status_without_a_csv_is_a_noop(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    agent.set_application_status("https://x/1", "applied")
    assert not (tmp_path / "output" / "applications.csv").exists()


def test_missing_keywords_reports_only_terms_the_resume_can_back_up(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("Skills: Notion, Airtable, QuickBooks")
    job = {"title": "Airtable Specialist",
           "description": "Notion and Airtable required. QuickBooks a plus. Kubernetes a bonus."}

    missing = agent._missing_keywords(job, "I use Notion daily and manage invoices.")

    assert "airtable" in missing
    assert "quickbooks" in missing
    assert "notion" not in missing        # already on the CV
    assert "kubernetes" not in missing    # a real gap — must not be suggested


def test_missing_keywords_ignores_filler_words(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("I have experience with the team")
    missing = agent._missing_keywords({"title": "", "description": "You must have experience with the team"}, "")
    assert missing == []


def test_missing_keywords_is_skipped_without_a_resume(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    assert agent._missing_keywords({"title": "Airtable", "description": "Airtable"}, "") == []


def test_generate_cvs_retries_once_when_over_one_page(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    contexts = []

    def fake_run_llm(prompt_file, context=""):
        contexts.append(context)
        return "#set page()"

    verdicts = iter([["CV is 2 pages — should be one"], []])
    with patch.object(agent, "run_llm", side_effect=fake_run_llm), \
         patch.object(agent, "_compile_cv"), \
         patch.object(agent, "_verify_cv", side_effect=lambda p, j=None: next(verdicts)):
        agent.generate_cvs([{"company": "Co", "title": "Dev"}])

    assert len(contexts) == 2
    assert "overflowed onto a second page" in contexts[1]


def test_generate_cvs_does_not_retry_a_clean_one_pager(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    calls = []

    with patch.object(agent, "run_llm", side_effect=lambda f, context="": calls.append(1) or "#set page()"), \
         patch.object(agent, "_compile_cv"), patch.object(agent, "_verify_cv", return_value=[]):
        agent.generate_cvs([{"company": "Co", "title": "Dev"}])

    assert len(calls) == 1


def test_scraped_description_recovers_posting_text_dropped_by_analyze(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "raw_jobs.json").write_text(json.dumps(
        [{"url": "https://www.indeed.com/viewjob?jk=1", "description": "We need Airtable."}]))

    # analyze.md returns a regional mirror of the same URL and no description
    assert agent._scraped_description("https://in.indeed.com/viewjob?jk=1") == "We need Airtable."


def test_scraped_description_returns_empty_when_unavailable(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    assert agent._scraped_description("https://x/1") == ""
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "raw_jobs.json").write_text("not json")
    assert agent._scraped_description("https://x/1") == ""


def test_apply_to_job_archives_the_scraped_posting_text(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "raw_jobs.json").write_text(json.dumps(
        [{"url": "https://x/1", "description": "Verbatim posting text."}]))

    with patch.object(agent, "run_llm", return_value="draft"), \
         patch.object(agent, "run_llm_json", return_value={"edits": []}):
        agent.apply_to_job({"company": "Co", "title": "Dev", "url": "https://x/1"})

    archived = (tmp_path / "output" / "applications" / "co__dev" / "job_posting.md").read_text()
    assert "Verbatim posting text." in archived


def test_run_pipeline_restores_descriptions_before_writing_copy(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    scraped = [{"title": "Dev", "company": "Co", "location": "Remote", "url": "https://x/1",
                "description": "Airtable required.", "posted_date": "", "source": "x"}]
    analyzed = [{"title": "Dev", "company": "Co", "url": "https://x/1", "score": 85,
                 "verdict": "apply", "match_reasons": [], "red_flags": [], "suggested_angle": ""}]
    seen = {}

    with patch.object(agent, "analyze_resume", return_value={"target_roles": [], "key_skills": []}), \
         patch.object(agent, "build_search_config", return_value={"search_queries": ["q"]}), \
         patch.object(agent, "scrape_jobs", return_value=scraped), \
         patch.object(agent, "analyze_jobs", return_value=analyzed), \
         patch.object(agent, "generate_cvs", side_effect=lambda jobs: seen.update(cv=jobs)):
        agent.run_pipeline()

    assert seen["cv"][0]["description"] == "Airtable required."


def _page(url):
    return {"url": url, "title": "", "description": ""}


def test_pick_batch_caps_pages_per_domain():
    import agent
    pages = [_page(f"https://flood.com/{i}") for i in range(10)] + [
        _page("https://other.com/1"), _page("https://third.com/1")]

    batch = agent._pick_batch(pages, set(), limit=20)

    assert sum(1 for p in batch if "flood.com" in p["url"]) == agent.MAX_PAGES_PER_DOMAIN
    assert "https://other.com/1" in [p["url"] for p in batch]
    assert "https://third.com/1" in [p["url"] for p in batch]


def test_pick_batch_treats_regional_mirrors_as_one_domain():
    import agent
    pages = [_page("https://in.indeed.com/1"), _page("https://www.indeed.com/2"),
             _page("https://uk.indeed.com/3"), _page("https://indeed.com/4")]

    batch = agent._pick_batch(pages, set(), limit=20)

    assert len(batch) == agent.MAX_PAGES_PER_DOMAIN


def test_pick_batch_skips_pages_already_scraped():
    import agent
    pages = [_page("https://a.com/1"), _page("https://b.com/2")]

    batch = agent._pick_batch(pages, {agent._dedup_key("https://a.com/1")}, limit=20)

    assert [p["url"] for p in batch] == ["https://b.com/2"]


def test_scrape_jobs_saves_every_discovered_page_not_just_the_scraped_ones(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    pages = [_page(f"https://site{i}.com/j") for i in range(30)]

    with patch.object(agent, "FirecrawlApp"), patch.object(agent, "discover_pages", return_value=pages), \
         patch.object(agent, "_scrape_batch", return_value=[]):
        agent.scrape_jobs(["q"])

    queue = json.loads((tmp_path / "output" / "page_queue.json").read_text())
    assert len(queue["pages"]) == 30                       # everything found is kept
    assert len(queue["scraped"]) == agent.MAX_PAGES_TO_SCRAPE  # only a batch was paid for


def test_scrape_more_takes_the_next_batch_and_never_repeats(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    pages = [_page(f"https://site{i}.com/j") for i in range(30)]
    first = [agent._dedup_key(p["url"]) for p in pages[:20]]
    agent.QUEUE_FILE.write_text(json.dumps({"pages": pages, "scraped": first}))

    scraped = []
    with patch.object(agent, "_scrape_batch", side_effect=lambda b: scraped.extend(b) or []):
        agent.scrape_more()

    assert [p["url"] for p in scraped] == [p["url"] for p in pages[20:]]
    assert len(json.loads(agent.QUEUE_FILE.read_text())["scraped"]) == 30


def test_scrape_more_refuses_when_the_queue_is_exhausted(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    pages = [_page("https://a.com/1")]
    agent.QUEUE_FILE.write_text(json.dumps(
        {"pages": pages, "scraped": [agent._dedup_key("https://a.com/1")]}))

    with pytest.raises(RuntimeError, match="No pages left"):
        agent.scrape_more()


def test_scrape_more_refuses_before_any_search(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Nothing discovered yet"):
        agent.scrape_more()


def test_find_more_run_merges_new_postings_and_skips_the_search(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()
    existing = [{"title": "Old", "url": "https://x/1", "description": "d"}]
    (tmp_path / "output" / "raw_jobs.json").write_text(json.dumps(existing))
    found = [{"title": "Old", "url": "https://x/1", "description": "d"},
             {"title": "New", "url": "https://x/2", "description": "d"}]

    with patch.object(agent, "build_search_config") as build, \
         patch.object(agent, "scrape_jobs") as search_scrape, \
         patch.object(agent, "scrape_more", return_value=found), \
         patch.object(agent, "analyze_jobs", return_value=[]), \
         patch.object(agent, "generate_cvs"):
        agent.run_pipeline(find_more=True)

    build.assert_not_called()
    search_scrape.assert_not_called()
    merged = json.loads((tmp_path / "output" / "raw_jobs.json").read_text())
    assert [j["url"] for j in merged] == ["https://x/1", "https://x/2"]


def test_generate_cvs_skips_ones_already_compiled(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "cvs").mkdir(parents=True)
    (tmp_path / "output" / "cvs" / "co__dev.pdf").write_bytes(b"%PDF")

    with patch.object(agent, "run_llm") as claude:
        agent.generate_cvs([{"company": "Co", "title": "Dev"}])

    claude.assert_not_called()


def test_apply_to_job_strips_dashes_the_model_left_behind(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    draft = "I build agents — mostly in Python — and I ship them."

    with patch.object(agent, "run_llm", return_value=draft), \
         patch.object(agent, "run_llm_json", return_value={"edits": []}):
        result = agent.apply_to_job({"company": "Co", "title": "Dev", "url": "u"})

    assert "—" not in result["revised"]
    assert result["revised"] == "I build agents, mostly in Python, and I ship them."
    # the draft is kept verbatim so the modal can show what was changed
    assert "—" in result["draft"]


def _fake_run(captured):
    def run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    return run


def test_run_llm_substitutes_the_prompt_into_configured_args(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("PROMPT BODY")
    monkeypatch.setattr(agent, "LLM_ARGS", "--flag {prompt} --after")
    captured = {}

    with patch.object(agent.shutil, "which", return_value="/bin/tool"), \
         patch.object(agent.subprocess, "run", side_effect=_fake_run(captured)):
        agent.run_llm("prompt.md")

    # everything but {prompt} passes through untouched, in order
    assert captured["argv"][0] == "/bin/tool"
    assert captured["argv"][1] == "--flag"
    assert "PROMPT BODY" in captured["argv"][2]
    assert captured["argv"][3] == "--after"


def test_run_llm_works_with_a_non_default_cli(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("hello")
    monkeypatch.setattr(agent, "LLM_CLI", "codex")
    monkeypatch.setattr(agent, "LLM_ARGS", "exec {prompt}")
    captured = {}

    with patch.object(agent.shutil, "which", return_value="/bin/codex") as which, \
         patch.object(agent.subprocess, "run", side_effect=_fake_run(captured)):
        assert agent.run_llm("prompt.md") == "ok"

    which.assert_called_once_with("codex")
    assert captured["argv"][:2] == ["/bin/codex", "exec"]


def test_run_llm_names_the_configured_cli_when_it_is_missing(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("hello")
    monkeypatch.setattr(agent, "LLM_CLI", "codex")

    with patch.object(agent.shutil, "which", return_value=None):
        with pytest.raises(RuntimeError, match="codex"):
            agent.run_llm("prompt.md")


def test_run_llm_prepends_the_shared_preamble(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "_context.md").write_text("SHARED RULES")
    (tmp_path / "prompts" / "step.md").write_text("STEP BODY")
    monkeypatch.setattr(agent, "LLM_ARGS", "{prompt}")
    captured = {}

    with patch.object(agent.shutil, "which", return_value="/bin/tool"), \
         patch.object(agent.subprocess, "run", side_effect=_fake_run(captured)):
        agent.run_llm("prompts/step.md")

    sent = captured["argv"][1]
    assert sent.index("SHARED RULES") < sent.index("STEP BODY")


def test_run_llm_runs_fine_without_a_preamble(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "step.md").write_text("STEP BODY")
    monkeypatch.setattr(agent, "LLM_ARGS", "{prompt}")
    captured = {}

    with patch.object(agent.shutil, "which", return_value="/bin/tool"), \
         patch.object(agent.subprocess, "run", side_effect=_fake_run(captured)):
        agent.run_llm("step.md")

    assert captured["argv"][1].strip() == "STEP BODY"


def test_attach_inlines_files_under_labelled_markers(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("MY RESUME")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "cv.typ").write_text("THE TEMPLATE")

    out = agent._attach("resume.md", "templates/cv.typ")

    assert "---RESUME---\nMY RESUME" in out
    assert "---CV---\nTHE TEMPLATE" in out


def test_attach_skips_files_that_do_not_exist(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    assert agent._attach("nope.md") == ""


def test_analyze_resume_sends_the_resume_contents_not_a_filename(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("SECRET RESUME TEXT")
    captured = {}

    with patch.object(agent, "run_llm_json",
                      side_effect=lambda f, context="": captured.update(context=context) or {}):
        agent.analyze_resume()

    # the model can no longer be relied on to open files, so the bytes must travel
    assert "SECRET RESUME TEXT" in captured["context"]


def test_drop_excluded_matches_whole_words_only():
    import agent
    jobs = [
        {"title": "Java Developer", "description": ""},
        {"title": "Frontend Engineer", "description": "You will write JavaScript daily."},
    ]

    kept, counts = agent.drop_excluded(jobs, ["java"])

    # "java" must not swallow "JavaScript"
    assert [j["title"] for j in kept] == ["Frontend Engineer"]
    assert counts == {"java": 1}


def test_drop_excluded_handles_hyphenated_and_multiword_terms():
    import agent
    jobs = [
        {"title": "Designer", "description": "This role is on-site in Berlin."},
        {"title": "Analyst", "description": "Fully remote."},
        {"title": "Intern", "description": "This is an unpaid internship."},
    ]

    kept, counts = agent.drop_excluded(jobs, ["on-site", "unpaid internship"])

    assert [j["title"] for j in kept] == ["Analyst"]
    assert counts == {"on-site": 1, "unpaid internship": 1}


def test_drop_excluded_is_case_insensitive_and_counts_per_term():
    import agent
    jobs = [{"title": "PHP Dev", "description": ""}, {"title": "Senior php engineer", "description": ""},
            {"title": "Python Dev", "description": ""}]

    kept, counts = agent.drop_excluded(jobs, ["PHP"])

    assert len(kept) == 1
    assert counts == {"php": 2}


def test_drop_excluded_without_terms_changes_nothing():
    import agent
    jobs = [{"title": "Anything", "description": "on-site unpaid php"}]
    kept, counts = agent.drop_excluded(jobs, [])
    assert kept == jobs and counts == {}


def test_run_pipeline_filters_before_scoring_and_reports_what_it_dropped(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    scraped = [
        {"title": "Remote Python Dev", "company": "A", "url": "https://x/1", "description": "remote", "source": "x"},
        {"title": "PHP Dev", "company": "B", "url": "https://x/2", "description": "php shop", "source": "x"},
    ]
    scored = {}

    with patch.object(agent, "build_search_config", return_value={"search_queries": ["q"]}), \
         patch.object(agent, "analyze_resume", return_value={"target_roles": [], "key_skills": []}), \
         patch.object(agent, "scrape_jobs", return_value=scraped), \
         patch.object(agent, "analyze_jobs", side_effect=lambda p="": scored.update(
             seen=json.loads((tmp_path / "output" / "raw_jobs.json").read_text())) or []), \
         patch.object(agent, "generate_cvs"):
        result = agent.run_pipeline(exclude=["php"])

    # the excluded posting never reaches the scorer, so it costs no tokens
    assert [j["title"] for j in scored["seen"]] == ["Remote Python Dev"]
    assert result["excluded"] == 1
    assert result["excluded_terms"] == {"php": 1}


def test_run_pipeline_says_so_when_exclusions_remove_everything(tmp_path, monkeypatch):
    import agent
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume.md").write_text("# Resume")
    (tmp_path / "output").mkdir()

    with patch.object(agent, "build_search_config", return_value={"search_queries": ["q"]}), \
         patch.object(agent, "analyze_resume", return_value={"target_roles": [], "key_skills": []}), \
         patch.object(agent, "scrape_jobs",
                      return_value=[{"title": "PHP Dev", "url": "https://x/1", "description": ""}]), \
         patch.object(agent, "analyze_jobs") as scorer, \
         patch.object(agent, "generate_cvs"):
        with pytest.raises(RuntimeError, match="Loosen the exclusions"):
            agent.run_pipeline(exclude=["php"])

    scorer.assert_not_called()
