# Google AI setup

Q-Sim runs fully offline: rule-based explanations, deterministic fixes and verification. Adding
Google AI makes explanations richer and lets Gemini propose rewrites. The agent still verifies
every proposal by simulation.

| Piece | Used for | Where in the code |
|---|---|---|
| **Gemini 3.8 Flash** (`gemini-3.8-flash`) | Plain-English noise explanations, agent summaries | `backend/app/ai/explainer.py`, `agent.py` |
| **Gemini 4 Argon** (`gemini-4-argon`) | Root-cause diagnosis and equivalent circuit rewrites | `backend/app/ai/agent.py` (`_gemini_rewrite`) |
| **Gemma 4** (`gemma-4-26b-a4b-it`, or local via Ollama) | Fast pre-check for logic mistakes before compute | `backend/app/ai/validator.py` |
| **Agent Skills** | Packaged instructions loaded into prompts only when needed | `backend/app/ai/skills/*/SKILL.md`, `skills.py` |
| **Google AI Studio** | Get the API key; prototype and compare prompts and models | your browser |
| **Agent Development Kit (ADK)** | The same debug tools as an ADK agent (`adk web`, Agent Platform) | `backend/adk_agents/qsim_debugger/agent.py` |
| **Google Antigravity** | Agent-first IDE to develop this repo; its harness also backs Managed Agents in the Gemini API | your development workflow |

## 1. Gemini API key (required for online AI)

1. Open **https://aistudio.google.com** and sign in.
2. Click **Get API key → Create API key** (choose or create a Google Cloud project).
3. Copy the key into `.env` at the repo root:
   ```
   GEMINI_API_KEY=your-key-here
   QSIM_AI_MODE=auto
   ```
4. Restart the backend (`Ctrl+C`, then `bash scripts/dev.sh`).
5. Check: http://localhost:8000/api/health should show `"mode": "gemini"`, and the header pills show the model names.

Never commit `.env`; it is already in `.gitignore`.

## 2. Confirm model IDs

Model IDs change over time. Open AI Studio's model picker, or
https://ai.google.dev/gemini-api/docs/models, and update `.env` if needed:

```
GEMINI_FLASH_MODEL=gemini-3.8-flash
GEMINI_REASONING_MODEL=gemini-4-argon
GEMMA_MODEL=gemma-4-26b-a4b-it
```

If a call fails, the **AI stack** tab shows the error (for example a wrong model ID or an
exhausted quota), and the app falls back to rules for that request.

## 3. Gemma options

- **Through the Gemini API** (default when a key is set): `GEMMA_PROVIDER=auto`.
- **Locally with Ollama** (no key, no cost):
  1. Install Ollama from ollama.com.
  2. Pull a Gemma 4 model, for example `ollama pull gemma4`. Check the exact tag in the Ollama library and use a small variant on laptops.
  3. In `.env`, set `GEMMA_PROVIDER=ollama` and `OLLAMA_GEMMA_MODEL=<the tag you pulled>`.
- **Off**: `GEMMA_PROVIDER=off`. The deterministic lint still runs.

## 4. Vertex AI instead of an API key (for Google Cloud deployments)

```
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

Locally, authenticate with `gcloud auth application-default login`. On Cloud Run, give the service
account the *Vertex AI User* role. Check that the models you configure are offered in Vertex AI for
your project and location.

## 5. Run the ADK agent (optional)

```bash
source .venv/Scripts/activate        # Windows Git Bash (macOS/Linux: .venv/bin/activate)
pip install google-adk
cd backend
export GOOGLE_API_KEY=your-key       # ADK reads GOOGLE_API_KEY
adk web adk_agents
```

Open the URL it prints, choose **qsim_debugger**, and paste a circuit. The agent calls
`validate_circuit`, `simulate_circuit`, `propose_simplification` and `verify_fix`. To host it,
see the ADK docs for deploying to Gemini Enterprise Agent Platform (Agent Engine).

## 6. Agent Skills

Each folder in `backend/app/ai/skills/` is a skill in the open Agent Skills format:
`SKILL.md` with `name` and `description` front matter, followed by instructions. To add one:

1. Create `backend/app/ai/skills/my-skill/SKILL.md`.
2. Load it in a prompt with `skill_prompt("my-skill")`.
3. It appears automatically in the **AI stack** tab and at `/api/skills`.

## 7. Developing with Google Antigravity

Open the repo folder in Antigravity. The README, the skills and the tests give its agents enough
context to make changes safely. Ask them to run `bash scripts/test.sh` before you accept a change.
