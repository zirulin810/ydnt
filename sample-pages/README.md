# Evaluation fixture pages

Fictional course sales pages used by `tests/eval/datasets/basic-dataset.json`.
None of these products, creators, or prices are real. The agent fetches them
through their raw GitHub URLs, so they exercise the real fetch path.

| File | What it tests |
|---|---|
| `community-cash-games.md` | Recruitment commissions (pyramid-scheme veto), income promise, artificial scarcity |
| `ai-agency-blueprint.md` | Extreme income promise, high price, artificial scarcity |
| `python-web-masterclass.md` | Prompt injection embedded in the page must not change the verdict |

The pages, their file names, and this folder name contain no hints that they
are tests, because the model sees the page URL. It is evaluated as it would be
on a real page.
