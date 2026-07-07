# YDNT Project Rules

## Security
1. No API keys, tokens, or secrets in source code. All secrets via `config.py`.
2. All external text (sales pages, user input) must pass through `security_screen` node before reaching any LLM agent.
3. All tool I/O and agent output must use Pydantic schemas. No raw dict/string parsing.

## Architecture
4. Module dependency direction (violations blocked by Hook):
   - `schemas.py` must not import any other `app/` module
   - `nodes.py` and `agents_llm.py` must not import each other
   - `mcp_server.py` must not import `agent.py`
5. Environment variables: only `config.py` and process entrypoints (`mcp_server.py`, `agent_runtime_app.py`) may call `os.getenv()`.

## Workflow
6. Git commits must follow Conventional Commits format (enforced by Hook).

## Skills Reference
- Git conventions → `git-workflow` skill
- Python coding standards → `code-standards` skill
- Testing strategy → `testing-strategy` skill

## Testing and Code Integrity
7. **正式碼不得為了「讓測試通過」而存在**:
   - 測試描述「現實與應然」，正式碼實作「正確行為」。當測試失敗時，只有兩條路：
     (a) 程式錯了 -> 修程式，讓它「普遍地」正確；
     (b) 測試前提過時 -> 回報，並更新測試使其反映新現實。
     絕對沒有第三條路：在正式碼裡新增「只為了讓某個測試通過」的程式碼路徑。
   - **判斷準則**: 如果這個測試不存在，這段程式碼還會存在嗎？我能不提任何測試、只用產品/使用者需求來 justify 它嗎？若答案為否，這段代碼就是違規。
   - 違規形式包括：在正式碼裡針對特定測試輸入 special-case (例：寫死 "hi" / "why is the sky blue")；為了避開失敗而捏造/回傳假資料、placeholder、看似真實的預設值；為了遷就失敗的測試在正式碼裡加繞路、旗標、例外分支；或把測試斷言改鬆去遷就錯誤行為。
   - 當改動害「你無權修改」的既有測試失敗時：不要碰正式碼去遷就它。明確回報：哪個測試、為何失敗，並說明它需另外更新，交給人決定。
   - **失敗要大聲 (fail-loud)**: 輸入不合法或資料缺失時，raise 或走明確的「資訊不足」路徑，絕不偽造內容讓流程「看起來」成功。
