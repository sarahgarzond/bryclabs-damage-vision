# Live multi-model API on Vercel (no GPU)

The API runs as one Vercel serverless function (`api/index.py` → `app/api.py`). With model keys set, it runs the
**orchestrator**: each photo goes to several vision models in parallel (subagents), their findings are merged by
cross-model agreement, and a Claude judge checks every finding against the photo and lists what is still needed.

```
photo ─► Claude Opus 5.5 ┐
      ─► GPT (OpenAI)    ├─► merge (agreement) ─► Claude judge ─► rules, confidence, readiness ─► JSON / CSV
      ─► Gemini          ┘
      ─► Qwen-VL (vLLM, optional)
```

## Deploy (about 5 minutes)

1. vercel.com → **Add New → Project** → import `sarahgarzond/bryclabs-damage-vision`. Leave framework as "Other".
   `vercel.json` already routes everything to the API.
2. **Settings → Environment Variables** (Production), only on Vercel, never in the repo:

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | Claude extractor and judge (recommended minimum) |
| `OPENAI_API_KEY` | GPT subagent (optional) |
| `GEMINI_API_KEY` | Gemini subagent (optional) |
| `DV_CORS_ORIGINS` | `https://sarahgarzond.github.io` so only the site can call it |

   Optional: `DV_OPENAI_MODEL` (default `gpt-5.1`), `DV_GEMINI_MODEL` (default `gemini-2.5-pro`),
   `DV_CLAUDE_MODEL` (default `claude-opus-5-5`), `DV_EXTRACT_EFFORT` (`low`), `DV_JUDGE_EFFORT` (`medium`),
   `DV_AGENTS` (e.g. `claude,gemini`), `DV_JUDGE=0` to skip the judge. Set the OpenAI and Gemini model names to the
   newest vision models your keys can use.
3. **Redeploy**, then open `https://<project>.vercel.app/health`. It lists the active agents and the judge.
4. GitHub → repo **Settings → Secrets and variables → Actions → Variables** → `DAMAGE_API_URL` =
   `https://<project>.vercel.app`, then rerun the "Deploy demo site" workflow. The site connects automatically.

## Notes
- Each agent that fails (bad key, timeout, refusal) is reported in `meta.agents` and the caveats. The request still
  succeeds with the remaining models. If every model fails, the result has `status: "error"`, never invented findings.
- Function limit is 60 s (`vercel.json`). Extractors run in parallel, the judge runs after them. If requests time
  out, lower `DV_JUDGE_EFFORT` to `low` or remove a slow agent with `DV_AGENTS`.
- The endpoint spends money per photo. Keep `DV_CORS_ORIGINS` set and consider Vercel's firewall rate limiting
  before sharing the link widely.
- Local run of the same API: `pip install -r requirements-dev.txt`, export the keys, `uvicorn app.api:app --port 8080`.
