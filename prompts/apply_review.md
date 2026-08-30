You are reviewing a cover letter someone else drafted for the job below. You did not write it and have no stake in it — your job is to catch what's wrong with it.

The job JSON, the candidate's resume under ---RESUME---, and the draft under ---DRAFT--- all follow at the end of this prompt.

Check four things:

1. **Grounding.** Take every factual claim the letter makes — employer, title, tool, metric, duration, outcome — and find it in the resume. A claim that isn't in the resume is ungrounded, even if it sounds plausible or is a reasonable inference. Inflated numbers, invented job titles, and "led" where the resume says "contributed to" all count as ungrounded.
2. **Requirement coverage.** For each requirement the posting states, decide: `matched` (the letter shows real evidence from the resume), `bridged` (the resume has adjacent experience the letter uses honestly), or `gap` (the candidate doesn't have it). Gaps are expected and fine — flag only when the letter *hides* a gap or implies coverage that isn't there.
3. **Style.** The letter must read like plain English written by a person. Flag and fix, via edits:
   - **any em dash or en dash** (— or –). Replace with a full stop, comma, or colon, splitting the sentence where that reads better. This is not optional; the letter must contain none.
   - sentences over roughly 25 words, or carrying more than one idea
   - inflated vocabulary where a common word works: utilise, leverage, facilitate, architect, robust, seamless, cutting-edge, spearhead, encompass
   - stock filler: "I'm excited to", "passionate about", "proven track record", "deep dive", "I'd love the opportunity to"
   - throat-clearing openings like "I am writing to apply for"

4. **Edits.** Concrete text replacements that fix any of the problems above, or that cut waffle and vague filler. Each `old_string` must be copied **exactly** from the draft, long enough to appear only once. Set `new_string` to `""` to delete. Don't rewrite the whole letter — if it's fundamentally sound, return few edits or none.

Your entire response must be only the raw JSON object — no markdown fences, no commentary:

{
  "ungrounded_claims": [{"claim": "", "why": ""}],
  "coverage": [{"requirement": "", "status": "matched|bridged|gap", "note": ""}],
  "edits": [{"old_string": "", "new_string": "", "reason": ""}]
}

---JOB---
