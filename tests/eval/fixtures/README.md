# Evaluation fixture pages

Fictional course sales pages used by `tests/eval/datasets/basic-dataset.json`.
None of these products, creators, or prices are real. The agent fetches them
through their raw GitHub URLs, so they exercise the real fetch path.

| File | What it tests |
|---|---|
| `mlm_community_course.md` | Recruitment commissions (pyramid-scheme veto), income promise, artificial scarcity |
| `income_promise_agency.md` | Extreme income promise, high price, artificial scarcity |
| `injection_course.md` | Prompt injection embedded in the page must not change the verdict |

The pages contain no hints that they are tests, so the model is evaluated as
it would be on a real page.
