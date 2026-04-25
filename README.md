# neurospect-api

FastAPI backend for the Neurospect trade journal and AI coaching application.

## Development

```bash
# Install dependencies
poetry install

# Run locally
uvicorn app.main:app --reload

# Run migrations
alembic upgrade head
```

Requires a `.env` file — copy `.env.example` and fill in the values.

## Prompt Files

The AI coach system prompt and strategy library are bundled at `app/coach/prompts/`:

- `system-prompt-template.md` — Claude system prompt (wiki source: `neurospect-wiki/concepts/ai-coach/system-prompt-template.md`)
- `strategies.json` — ICT strategy definitions (wiki source: `neurospect-wiki/concepts/ai-coach/strategies.json`)

**Sync rule:** The wiki is the canonical source for editing these files. When the wiki versions change, manually re-copy them to `app/coach/prompts/` and commit. The bundled copies exist solely so Render has them at deploy time — the wiki path is not available on the server.

On local dev you can override the prompt directory via `.env`:

```
AI_COACH_PROMPT_DIR=C:/Users/PaulRussell/repos/neurospect-wiki/concepts/ai-coach
```

## Deployment

Deployed to Render via `render.yaml`. See the deployment tracker in `neurospect-wiki` for the full runbook.
