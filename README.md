# 「YOU DON'T NEED THIS」— Online Course Due Diligence Agent (YDNT)

> **Kaggle 5-Day AI Agents Competition Submission**  
> **Track**: Agents for Good (Consumer Protection)  
> **Tech Stack**: Google ADK 2.0 + Agents CLI + FastMCP + Pydantic + Semgrep

---

## 1. Project Positioning & Core Value

### The Lemon Market Problem (Akerlof's Market for Lemons)
Online courses (especially high-ticket self-hosted ones on Skool / Whop / Gumroad without third-party platform vetting) are a classic information asymmetry market. Buyers cannot evaluate the quality of the content before paying, leading to a market flooded with low-quality products featuring "fake testimonials, artificial scarcity, and MLM/reseller recruiting".

### YDNT's Solution
**Avoid jumping to a "scam" verdict; answer only with verifiable evidence:**
> "Can the speaker's claimed expertise be independently verified outside of the course they are selling?"

We combine **Multi-agent collaboration** and **deterministic routing code** to verify the creator's real web footprint, GitHub development history, and compare knowledge coverage and extraction cost against free alternatives on YouTube. This delivers an "evidential (non-judgmental)" due diligence report, providing consumers with a rational balance sheet at the moment of impulse buying.

---

## 2. System Architecture: DAG Data Flow

YDNT is designed using the ADK 2.0 Workflow Graph to ensure non-deterministic LLM reasoning is clearly separated from deterministic code logic.

The system always runs the full due diligence pipeline. If page retrieval fails (`fetch_page_node` error) or if triage/information completion fails (`triage_course` identifies a non-course page or the user is unable to provide critical missing details), the system routes to `insufficient_verdict` for an early, honest termination without fabricating any scores.

```
                       START
                         │
                         ▼
                  [fetch_page_node]             @node: Fetches sales page (fetch_sales_page)
                         │
                 ┌───────┴───────┐
                 ▼(insuf.)       ▼(ok)
         [insufficient_    [parse_course]       LlmAgent: Parses page → CourseProfile
          verdict](END)          │              (prompt hygiene + extract is_pyramid_scheme)
                                 ▼
                          [triage_course]       @node (HITL): Triages non-course pages or prompts user for missing info
                                 │
                         ┌───────┴───────┐
                         ▼(insuf.)       ▼(ok)
                 [insufficient_    [creator_verify]     LlmAgent: Checks GitHub / web / YouTube footprint
                  verdict](END)          │
                                         ▼
                               [prepare_free_alt_input] @node: Injects course profile into downstream queries
                                         │
                                         ▼
                                  [free_alt_score]      LlmAgent: Searches for free alternatives on YouTube
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

---

## 3. MCP Heterogeneous Toolchain & Clever Tool Use

We designed a local FastMCP service that ingeniously wraps standard search/fetching APIs into dedicated "due diligence tools":

| Tool Name | Signature | Original Purpose → YDNT Clever Reuse |
|------|------|----------------------|
| `fetch_sales_page` | `(url_or_case: str) -> str` | Web Scraping → **Raw Page Ingestion** (ingests untrusted page data for safe sanitization & fact extraction) |
| `search_youtube` | `(query: str) -> list` | Video Search → **Free Alternative Search Engine** |
| `get_youtube_transcript` | `(video_id: str) -> str` | Transcript Retrieval → **Content Quality X-Ray** (calculates knowledge coverage and content farm metrics) |
| `get_channel_stats` | `(channel_id: str) -> dict` | Channel Stats → **Creator Authenticity & Activity Signals** |
| `verify_github_user` | `(handle: str) -> dict` | Repo Query → **Creator Expertise Polygraph** (checks for authentic open-source contributions) |
| `web_search` | `(query: str) -> list` | Web Search → **Credential/Institutional Value Verification** |

---

## 4. Project Directory Structure

```
ydnt/
├─ README.md                      # This description file
├─ GEMINI.md                      # Project guidelines
├─ config.py                      # Centralized configuration for models & thresholds
├─ app/
│  ├─ agent.py                    # ADK 2.0 Workflow DAG definition
│  ├─ agent_runtime_app.py        # ADK 2.0 App execution entrypoint
│  ├─ schemas.py                  # Pydantic data contracts (I/O validation)
│  ├─ nodes.py                    # @node Deterministic nodes (routing, security, and triage)
│  ├─ scoring.py                  # 6+1 axes rubric scoring logic
│  ├─ agents_llm.py               # 4 LlmAgent definitions (Programmatic McpToolset)
│  └─ mcp_server.py               # FastMCP server (containing 6 tools)
├─ .agents/
│  ├─ AGENTS.md                   # Persistent rules (security, dependency, Conventional Commit)
│  ├─ hooks.json                  # PreToolUse interception configurations
│  ├─ scripts/
│  │  ├─ validate_tool_call.py    # Hook: Intercepts dangerous commands & invalid commits
│  │  └─ validate_file_write.py   # Hook: Prevents circular imports & hardcoded API Keys
│  └─ skills/
│     ├─ course-rubric/           # Level 4 skill: Deterministic scoring
│     │  ├─ SKILL.md
│     │  └─ scripts/score.py      # 6+1 axes scoring implementation
│     ├─ git-workflow/            # Level 3 skill
│     │  └─ SKILL.md
│     ├─ code-standards/          # Level 2 skill
│     │  └─ SKILL.md
│     └─ testing-strategy/        # Level 2 skill
│        └─ SKILL.md
├─ cache/                         # Mock cache data for 5 demo cases
├─ tests/
│  └─ eval/
│     └─ datasets/
│        └─ basic-dataset.json    # Evaluation dataset with 5 test cases
├─ .semgrep/
│  └─ rules.yaml                  # Semgrep rules for detecting hardcoded keys
├─ .pre-commit-config.yaml        # Runs Semgrep checks pre-commit
```

---

## 5. Security Protection & Development Governance

The YDNT project features a rigorous security mesh to completely prevent API key leaks:
1. **Semgrep Scanning**: `.semgrep/rules.yaml` blocks commits containing keys matching formats like `AIzaSy*`.
2. **Pre-commit Hook**: Automatically triggers Semgrep checks during every `git commit`.
3. **PreToolUse Hooks**: Tailored `.agents/hooks.json` intercepts `write_file` commands from the AI assistant to verify:
   - No hardcoded API keys are introduced.
   - No circular imports occur (e.g., schemas depending on nodes).
   - No direct `os.getenv` calls are used outside of whitelisted files.

### Injection Mitigation & Architectural Defense
* **Architectural Defense**: The final evaluation verdict is determined deterministically by Python code based on multi-axis scores and Veto rules. The LLM never makes the final purchase decision, ensuring malicious injections cannot hijack the final verdict.
* **Prompt Hygiene & Semantic Extraction**: The `parse_course` node explicitly instructs the LLM that the sales page is untrusted data and it should only extract facts and ignore any embedded instructions. Potential MLM/pyramid schemes are extracted by the LLM as the `is_pyramid_scheme` boolean fact, acting as a Veto red flag in the deterministic scoring node, achieving robust and precise defense.
