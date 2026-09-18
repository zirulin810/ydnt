# 「YOU DON'T NEED THIS」: Online Course Due Diligence Agent (YDNT)

> **Kaggle 5-Day AI Agents Competition Submission**  
> **Track**: Agents for Good (Consumer Protection)  
> **Tech Stack**: Google ADK 2.0 + Agents CLI + Gemini 2.5 Flash + Pydantic + Vertex AI Agent Runtime + Cloud Run  
> **Live demo**: https://ydnt-dashboard-4dtupehtda-ue.a.run.app

---

## 1. Project Positioning & Core Value

### The Lemon Market Problem (Akerlof's Market for Lemons)
Online courses (especially high-ticket self-hosted ones on Skool / Whop / Gumroad without third-party platform vetting) are a classic information asymmetry market. Buyers cannot evaluate the quality of the content before paying, leading to a market flooded with low-quality products featuring "fake testimonials, artificial scarcity, and MLM/reseller recruiting".

### YDNT's Solution
**Avoid jumping to a "scam" verdict; answer only with verifiable evidence:**
> "Can the speaker's claimed expertise be independently verified outside of the course they are selling?"

We combine **multi-agent collaboration** and **deterministic routing code** to verify the creator's real web footprint and to compare knowledge coverage and extraction cost against free alternatives on YouTube, checking the best alternative against its actual video content. This delivers an "evidential (non-judgmental)" due diligence report, providing consumers with a rational balance sheet at the moment of impulse buying.

---

## 2. System Architecture: DAG Data Flow

YDNT is designed using the ADK 2.0 Workflow Graph to ensure non-deterministic LLM reasoning is clearly separated from deterministic code logic.

The system always runs the full due diligence pipeline. If page retrieval fails (`fetch_page_node` error) or if triage fails (`triage_course` identifies a non-course page or the user cannot provide critical missing details), the system routes to `insufficient_verdict` for an early, honest termination without fabricating any scores.

```
                       START
                         │
                         ▼
                  [fetch_page_node]             @node: Fetches sales page via Jina Reader
                         │
                 ┌───────┴───────┐
                 ▼(insuf.)       ▼(ok)
         [insufficient_    [parse_course]       LlmAgent: Parses page → CourseProfile
          verdict](END)          │              (prompt hygiene + extract is_pyramid_scheme)
                                 ▼
                          [triage_course]       @node (HITL): Rejects non-course pages; pauses to ask the user for a missing price or creator
                                 │
                         ┌───────┴───────┐
                         ▼(insuf.)       ▼(ok)
                 [insufficient_    [creator_verify]     LlmAgent: Checks the creator's web footprint with Google Search grounding
                  verdict](END)          │
                                         ▼
                               [prepare_free_alt_input] @node: Injects course profile into downstream queries
                                         │
                                         ▼
                                  [free_alt_score]      LlmAgent: Searches YouTube; estimates coverage from titles/descriptions
                                         │
                                         ▼
                                 [verify_coverage]      @node: Re-checks the top video against its actual content
                                         │
                                         ▼
                                [rubric_scoring_node]   @node: Pure function 1-5 scoring + decision matrix (deterministic verdict)
                                         │
                                         ▼
                                   [verdict_agent]      LlmAgent: Synthesizes rubric scores into an evidential report
                                         │
                                         ▼
                                 [finalize_verdict]     @node: Deterministically populates verified free alternative links (END)
```

### Human in the Loop
`triage_course` uses ADK `RequestInput` with a resumable app (`ResumabilityConfig`). When the sales page hides the price or creator, the run pauses, the dashboard shows an intervention card, and the run resumes from the same point with the user's answer. Answering `unknown` ends the run as `insufficient` instead of guessing.

### Content-Based Coverage Check
`free_alt_score` can only see titles and descriptions. `verify_coverage` takes the highest-coverage non-content-farm YouTube video and re-judges its coverage, trying in order:

1. **Video sample**: Gemini watches one minute from the middle of the video (skipping intros) directly from its YouTube URL. Google fetches the video, so this is not affected by YouTube blocking datacenter IPs.
2. **Transcript**: `youtube-transcript-api`, judged by Gemini as text.
3. **Metadata**: keep the title/description estimate.

Every alternative in the report states which basis its coverage figure came from, and the verdict says so when coverage is only an estimate.

---

## 3. Tools

The tools are plain Python functions in `app/mcp_server.py`, which also exposes them as a FastMCP server. The agents import them directly rather than over the MCP protocol, avoiding process startup overhead.

| Tool | Used by | Original Purpose → YDNT Reuse |
|------|------|----------------------|
| `fetch_sales_page(url)` | `fetch_page_node` | Web Scraping → **Raw Page Ingestion** (untrusted page text for fact extraction; retries half-rendered pages) |
| `search_youtube(query)` | `free_alt_score` | Video Search → **Free Alternative Search Engine** |
| `get_channel_stats(channel_id)` | `free_alt_score` | Channel Stats → **Content Farm Signals** |
| `get_youtube_transcript(video_id)` | `verify_coverage` | Transcript Retrieval → **Coverage Check fallback** |
| Google Search (ADK `GoogleSearchAgentTool`) | `creator_verify` | Web Search → **Creator Credential Verification** with real source URLs |

---

## 4. Deterministic Scoring

The LLM never decides the recommendation. `app/scoring.py` scores content, creator, and free alternatives on 1-5 axes, then applies a decision matrix. The core idea is an **equivalent price**:

```
equivalent_price = price / (1 − coverage%)
```

If free alternatives cover 80% of a $500 course, you are really paying $2,500 for the unique 20%.

---

## 5. Project Directory Structure

```
ydnt/
├─ README.md                      # This description file
├─ PROJECT_DESCRIPTION.md         # Competition write-up
├─ GEMINI.md                      # Project guidelines
├─ app/                           # The agent (deployed to Vertex AI Agent Runtime)
│  ├─ agent.py                    # ADK 2.0 Workflow DAG definition
│  ├─ agent_runtime_app.py        # Agent Runtime entrypoint
│  ├─ config.py                   # Centralized configuration (keys, models, Gemini endpoint)
│  ├─ schemas.py                  # Pydantic data contracts (I/O validation)
│  ├─ nodes.py                    # @node deterministic nodes (fetch, triage/HITL, coverage check, scoring, finalize)
│  ├─ coverage.py                 # Video / transcript / metadata coverage check
│  ├─ scoring.py                  # Rubric scoring and decision matrix
│  ├─ agents_llm.py               # 4 LlmAgent definitions
│  └─ mcp_server.py               # Tool implementations (also a FastMCP server)
├─ submission_frontend/           # Dashboard (deployed to Cloud Run)
│  ├─ main.py                     # FastAPI app calling the Agent Runtime
│  └─ templates/index.html        # Progress timeline, HITL intervention card, report
├─ deploy/DEPLOY.md               # Deployment guide
├─ tests/
│  ├─ unit/                       # pytest, network calls stubbed
│  ├─ integration/                # Agent Runtime app wrapper
│  └─ eval/                       # agents-cli eval config and dataset
├─ .agents/
│  ├─ AGENTS.md                   # Persistent rules (security, dependency, Conventional Commit)
│  ├─ hooks.json                  # PreToolUse interception configurations
│  ├─ scripts/                    # Hook scripts (dangerous commands, hardcoded keys, circular imports)
│  └─ skills/                     # course-rubric, git-workflow, code-standards, testing-strategy
├─ .semgrep/rules.yaml            # Semgrep rules for detecting hardcoded keys
└─ .pre-commit-config.yaml        # Runs Semgrep before each commit
```

---

## 6. Security Protection & Development Governance

1. **Semgrep Scanning**: `.semgrep/rules.yaml` flags keys matching formats like `AIzaSy*`.
2. **Pre-commit Hook**: `.pre-commit-config.yaml` runs Semgrep on every `git commit` once enabled with `pre-commit install`.
3. **PreToolUse Hooks**: `.agents/hooks.json` intercepts file writes from the AI coding assistant to verify:
   - No hardcoded API keys are introduced.
   - No circular imports occur (e.g., schemas depending on nodes).
   - No direct `os.getenv` calls are used outside of whitelisted files.
4. **Keys stay out of logs**: the YouTube API key is sent as an `X-Goog-Api-Key` header, never in request URLs.

### Injection Mitigation & Architectural Defense
* **Architectural Defense**: The final recommendation is determined deterministically by Python code based on multi-axis scores and veto rules. The LLM never makes the final purchase decision, so malicious injections cannot hijack the verdict.
* **Prompt Hygiene & Semantic Extraction**: `parse_course` and the coverage check treat page text, transcripts, and video content as untrusted data and only extract facts. Potential MLM/pyramid schemes are extracted as the `is_pyramid_scheme` boolean fact, acting as a veto red flag in the deterministic scoring node.

---

## 7. Running and Testing

```bash
uv sync
uv run pytest tests/unit tests/integration
agents-cli playground
```

`agents-cli playground` runs the full agent locally and calls live APIs (Gemini, YouTube, Jina), so it spends quota. Configure keys in `.env` (see `.env.example`). Deployment steps are in [deploy/DEPLOY.md](deploy/DEPLOY.md).
