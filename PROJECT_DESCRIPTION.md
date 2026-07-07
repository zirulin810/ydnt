# YDNT — "You Don't Need This"

### An AI Due-Diligence Agent for Online Courses

---

## The Problem

The creator economy has made "sell a course" a default business model. Beyond outright scams — anonymous "gurus," income promises, artificial urgency, recruitment pyramids — sits a harder question that applies **even to legitimate courses**:

> Is this $500 worth paying when 80% of the syllabus is already free on YouTube?

Answering honestly means reading the sales page critically, verifying the instructor, hunting down free alternatives, and weighing money against time. Almost nobody does it before clicking **"Buy."** YDNT does it for you.

---

## What We Built

YDNT is an **autonomous due-diligence agent**. Hand it a course sales-page URL (or raw text); it returns an evidence-based verdict — one of:

| Verdict | Meaning |
| --- | --- |
| `worthy` | Worth the money |
| `situational` | A judgment call for the buyer |
| `need_not` | You don't need to buy it |
| `should_not` | You should not buy it |
| `insufficient` | Not enough evidence to judge |

...along with **red flags**, **green flags**, a **money-vs-time analysis**, and concrete **free alternatives with real links**.

It's built on **Google's Agent Development Kit (ADK)** as a directed workflow graph, powered by **Gemini 2.5 Flash**. The guiding principle:

> **LLMs extract, investigate, and synthesize; deterministic Python does all the scoring and decision math.**

This keeps the final judgment auditable, reproducible, and immune to a persuasive sales page talking the model into a good grade.

---

## How It Works

A DAG alternates **deterministic nodes** and **LLM agents**:

1. **Fetch** the page (Jina Reader, with layered retries and half-rendered-page detection); unreachable pages fail honestly as `insufficient`.
2. **Parse** into a structured profile — title, creator (distinguished from the host platform), price, promised outcome, syllabus, scarcity signals, pyramid-scheme and course-page flags — hardened against prompt injection, and forbidden from inventing a creator or price.
3. **Triage** — reject non-course pages; if price or creator is missing, pause and ask the user via a resumable human-in-the-loop prompt rather than guessing.
4. **Verify the creator** with Google Search grounding, constrained to a few queries and real source URLs only — no hallucinated citations.
5. **Find free alternatives** on YouTube, estimating syllabus coverage and flagging content farms conservatively.
6. **Score** deterministically, then **deliver** an English-only verdict whose links are injected from verified tool data.

---

## The Core Insight

Rather than judging price in a vacuum, YDNT computes an **equivalent price**:

```
equivalent_price = price / (1 − coverage%)
```

If free alternatives cover 80% of a $500 course, you're really paying **$2,500 for the unique 20%** — graded harshly. A course covering material found nowhere else keeps its real price.

Content and creator credibility gate the verdict: a middling creator demotes `worthy` down to `situational`, and an unknown price never fakes precision.

---

## Why It Matters

Most AI course reviewers rubber-stamp whatever they're shown. YDNT does the unglamorous work a diligent buyer *should* do but never does — verifying the instructor against the real world, pricing the course against what's already free, and refusing to be argued out of an honest answer.

Often the most valuable thing it returns is a list of free links and one sentence:

> **You don't need this.**
