# Changing How Setbacks Feel: Appraisal-Aware AI Feedback After Lifestyle Setbacks

The web app for a graduate class project in CSE 6130 Affective Computing (Northeastern University). It is a class project, not published research. It has three parts:

> **Data retention: all study data (the database, every exported CSV, and `sim/output/`) must be deleted at the end of the course.** Use **Delete all data** on `/admin` (see section 4).

- **Study 2 (main experiment).** A one-session, within-subject survey. Participants write about a real setback, answer appraisal questions, then read and rate four AI feedback messages (NEUTRAL, STRICT, GENERIC_ENCOURAGING, APPRAISAL_TAILORED). The messages are shown as Message A–D, and the order is counterbalanced with a 4×4 balanced Latin square.
- **Study 3 (persona simulation).** LLM personas go through the same flow, using the same backend code.
- **Study 3a (appraisal probe).** Tests whether a plain LLM coach responds to appraisals or only to the emotion.

```
docs/survey_items.md        source of truth for every item (codes, wording, scales, (R), branching)
backend/config/survey.json  generated from the markdown; the frontend renders every page from it
backend/prompts/*.txt       coach prompts (one per condition), shared rules, safety classifier
backend/app/                FastAPI app: flow (study.py), scoring, LLM providers, exports
frontend/                   React + Vite + Tailwind participant UI and /admin
sim/                        run_personas.py (Study 3), appraisal_probe.py (Study 3a), their prompts
tests/                      pytest suite
```

## 1. Setup

You need Python 3.11+ and Node 18+.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then set ANTHROPIC_API_KEY (or OPENAI_API_KEY) and ADMIN_PASSWORD
cd frontend && npm install && npm run build && cd ..
```

### `.env` settings

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `anthropic`, `openai`, or `mock`. `mock` is an offline fake used by tests and the seed script; never use it for real data. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Provider key. Keys are never hardcoded. |
| `COACH_MODEL` | Writes the four messages (default `claude-opus-5-5`). |
| `PERSONA_MODEL` | Plays the Study 3 participants (default `claude-sonnet-5-5`). Keep it different from the coach. |
| `COACH_TEMPERATURE` / `PERSONA_TEMPERATURE` | 0.7 / 0.9. These apply to **OpenAI only**: the current Anthropic API rejects `temperature` on every Claude model. On Anthropic, reasoning effort is the control instead (`COACH_EFFORT`, `PERSONA_EFFORT`). The temperature actually used is stored per message in `messages.temperature_applied` (empty means provider default). |
| `ADMIN_PASSWORD` | Password for `/admin`. If unset, the admin page is disabled. |
| `DATABASE_URL` | Default `sqlite:///data/study.db`. |

**Sampling settings differ by provider.** On OpenAI, the coach runs at temperature 0.7 and personas at 0.9. On Anthropic, both use the provider's default sampling (the API doesn't accept `temperature`), and only reasoning effort is configurable. Each message stores the temperature that was actually applied (`messages.temperature_applied`, empty = provider default) along with the model that answered. Report the provider when you describe the method, and don't pool data collected under different providers without noting it.

## 2. Editing the survey

1. Edit `docs/survey_items.md`.
2. Run `python -m backend.config.parse_survey`, which regenerates `backend/config/survey.json`.
3. Run `pytest`. `tests/test_parser.py` fails if the JSON is out of sync with the markdown.

Participant-facing text that the markdown doesn't contain lives in `survey.json → texts` and is **kept when you regenerate**. This covers:
- the consent body;
- the support-resources page;
- the screen-out and decline pages;
- optional page titles and instructions.

**Before launch, replace `[team contact email]`.** It is the only placeholder, and it appears in two places:
- `backend/config/survey.json` → `texts.consent_body` (end of the consent text);
- `docs/survey_items.md` → the Debrief paragraph (last line). Then re-run the parser so it reaches `survey.json` → `texts.debrief`.

The support-resources text (`texts.support_resources`) appears on three pages: the P_SCR3 = Yes page, the safety-flag page, and below the debrief.

The parser derives everything else from the markdown:
- reverse-scored items (`(R)`, scored as 8 − raw);
- scale membership (STAB, CTRL, BLAME, COPE, GLOB, SHAME, GUILT, MOT, SE, SC, QUIT, AI);
- F↔M change-score pairs (same suffix);
- the attention-check rules;
- the screening branches;
- the M_ATTN placement between M_CTRL2 and M_BLAME1.

## 3. Running the app

```bash
uvicorn backend.app.main:app --reload            # http://localhost:8000
```

For frontend hot-reload, also run `cd frontend && npm run dev` and open http://localhost:5173 (it proxies `/api` to port 8000).

Participant link: `https://<host>/?pid={{PROLIFIC_PID}}&source=prolific`. Both `pid` and `source` are stored. A participant who reloads the page resumes where they left off. There is no going back: the server only accepts answers for the current page. To start a fresh session in the same browser (for testing), add `&new=1`.

### Participant flow
1. Consent → Section P pages. Consent "No" ends the study. A screening failure goes to a polite end page. P_SCR3 = Yes goes to the support-resources page.
2. Section M. Once it's submitted, an LLM safety classifier checks M_TEXT. If it's flagged, feedback is skipped, the support page is shown, and a `safety` flag is recorded. Otherwise all four messages are generated in parallel behind a loading screen. Each call is retried twice; if it still fails, an error page with "Try again" is shown.
   **Counterbalancing happens here.** Once all four messages exist, the participant gets the next round-robin number within their source. That number sets the Latin-square row, which sets the order, and the messages are stored as A–D in that order. Screened-out, declined, safety-stopped, abandoned and failed-generation sessions never use up a row (their `participant_number`, `latin_row` and `condition_order` stay empty). Humans and personas have separate counters.
3. Section F, once per message. The message stays pinned above the questions.
4. Section Z. All four messages side by side, drag-to-rank, then the remaining Z items and the debrief, followed by the support-resources text.

### Feedback generation
- Every prompt receives P_GOALTEXT and M_TEXT. The tailored prompt also receives the M-section scale scores (STAB, CTRL, BLAME, COPE, GLOB, SHAME, GUILT) and the **1–2 most maladaptive appraisals**. These are picked deterministically in code (`scoring.maladaptive_targets`): the largest distance past the scale midpoint (4) in the unhelpful direction. They're stored in `messages.tailoring_targets`.
- Every message is word-counted. If it falls outside 80–120 words it is regenerated once. If it's still out of range, the version closest to range is kept and a `length_out_of_range_<CONDITION>` flag is recorded.
- The prompt version is `<file>@<hash of prompt + shared rules>`, so any edit to a prompt shows up in the data.

## 4. Admin and exports

Open `/admin` and enter `ADMIN_PASSWORD`. It shows counts by source and status, completes per Latin-square row, message-length stats per condition, and all flags. The downloads can be filtered by source and by completed-only:

| Export | Shape |
|---|---|
| `long.csv` | One row per participant × condition. All P and M items (and Z items) repeat on each row. F items, F scale means and F − M change scores are columns, plus `condition`, `display_label`, `order_position`, `Z_RANK`, `Z_BEST_this` and the `flag_*` columns. Use this for mixed-effects models. |
| `wide.csv` | One row per participant. Per-condition columns are named `CONDITION__F_MOT1`, etc. |
| `scores.csv` | Scale means after reverse-scoring, plus `CHG_<item>` and `CHG_<DIMENSION>` (F − M, computed on matched items only, e.g. SHAME uses SHAME1–2). |
| `flags.csv` | `attention_fail` (M_ATTN ≠ 3), `attention_mismatch` (Z_ATTN2 ≠ P_GOALTYPE), `speeder` (human, total < 5 min), `safety`, `self_reported_inattention` (Z_HONEST = No), `screened_support`, `generation_error`, `length_out_of_range_*`. |
| `messages.csv` | Every generated message, with model, prompt version and word count. |

Every export has a `source` column (`human` or `persona`). `recruit_source` holds the `?source=` URL parameter. The same files are available from the command line:

```bash
python -m backend.export --kind all --out-dir data/exports
python -m backend.export --kind long --source human --completed-only --out data/long_human.csv
```

Per-page timing is in the `page_events` table (`shown_at`, `submitted_at`, `seconds`). `participants.total_seconds` runs from the first page shown to the final submission.

Example R model: `lmer(F_MOT_mean ~ condition + M_MOT_mean + order_position + (1 | participant_id), data = long)`.

**Delete all data.** At the bottom of `/admin`, **Delete all data…** opens a confirmation box: you type `DELETE` and press the final button. This permanently removes every participant (human and persona), response, message, flag and timing record, and compacts the SQLite file so deleted rows don't linger. The same action is available as an API call: `POST /api/admin/delete-all` with body `{"confirm": "DELETE"}`. Download any exports you need first. Exported CSVs on your own machines and `sim/output/` logs are not touched, so delete those by hand.

## 5. Study 3: personas

```bash
python -m sim.run_personas --n 40                 # add --concurrency 4 --seed 7 as needed
```

How it works:
- **Personas are planned in code.** Profile types (a)–(e) are spread evenly: 8 each when n = 40. Age range, goal area, goal duration and writing style vary.
- **`PERSONA_MODEL` fills in each persona card.** This is a separate call: name, life context, goal text, inner voice, and so on.
- **Each persona runs through `study.start_participant / get_state / submit / run_generation`.** These are the same functions the web API calls. Each persona has its own fresh conversation: its card (system prompt) plus each page's questions as JSON. The persona sees the real coach messages in its counterbalanced order. It never sees condition names, coach prompts or hypotheses (a test checks this).
- **Answers must be strict JSON** (`item_code → value`) and are validated against `survey.json` with the same validator humans go through. Invalid answers are re-asked up to 3 times.
- **Results are saved with `source="persona"`.** The card is stored in `participants.persona_card`, so the admin exports work unchanged. Personas have their own round-robin counter, so they don't shift the human Latin-square balance.

A JSONL log is written to `sim/output/`. Cost: roughly 20 persona calls plus 5 coach/safety calls per persona.

## 6. Study 3a: appraisal probe

```bash
python -m sim.appraisal_probe                     # 5 variants × 10 samples
python -m sim.appraisal_probe --samples 20 --embedding openai
```

- **Inputs.** Five descriptions of the same event and emotion that differ only in appraisal: stable, unstable, uncontrollable, self-blaming, low-coping. They are in `sim/prompts/probe_variants.json`.
- **Calls.** Each description is sent to the plain coach (system prompt exactly "You are a supportive health coach.") in a fresh context.
- **Outputs**, written to `sim/output/probe_<timestamp>/`:
  - `responses.csv`;
  - `similarity_matrix.csv`, the mean pairwise embedding cosine similarity within and between variants;
  - `confusion.csv`;
  - `summary.md`, which also reports the within-minus-between similarity with a permutation p-value.
- **Judge.** A judge in a separate call codes each response for whether it addresses a specific appraisal (yes/no) and which one. The judge is **blind**: it sees only the response, so "hit" means the judge recovered the prompting variant.
- **Embeddings.** OpenAI `text-embedding-3-small` if `OPENAI_API_KEY` is set; otherwise offline TF-IDF. TF-IDF is lexical, so prefer real embeddings for the paper.

## 7. Tests and seed data

```bash
pytest                                  # 45 tests, offline (mock LLM, temp database)
python -m backend.seed                  # 3 fake human participants into data/seed.db
python -m backend.export --db sqlite:///data/seed.db --kind all --out-dir data/exports_seed
```

The tests cover:
- the Latin square (Latin property and carryover balance), round-robin assignment, and labels;
- reverse-scoring and change scores;
- long and wide export shape;
- persona JSON validation, re-asks, and that personas never see condition names;
- branching, the safety stop, generation retries and the error page, the length regeneration, and admin auth;
- Latin-square rows assigned only at generation (screened-out, safety-stopped, abandoned and failed sessions don't use one);
- the debrief support text, "Delete all data", and that `[team contact email]` is the only placeholder left;
- markdown/config sync.

## 8. Deploying (Render or Railway)

The single `Dockerfile` builds the frontend and serves everything from one uvicorn process.

- **Render.** Push the repo and create a Blueprint from `render.yaml` (Docker, health check `/api/health`, 1 GB disk at `/data`). Then set `ANTHROPIC_API_KEY` and `ADMIN_PASSWORD` in the dashboard.
- **Railway.** Deploy from the repo (it detects the Dockerfile). Add a volume mounted at `/data`, then set `DATABASE_URL=sqlite:////data/study.db`, the API key and `ADMIN_PASSWORD`.

**SQLite must live on a persistent disk or volume.** Without one, every redeploy erases the data. Keep the service at one instance and one worker: participant numbering and the generation lock are in-process.

## 9. Safety and data notes

- The safety classifier runs before any feedback is generated. If the classifier itself fails after retries, the participant sees the error page; feedback is never generated unscreened.
- Coach prompts forbid medical advice, calorie or weight numbers, emojis, questions, and any mention of studies or AI. The STRICT prompt forbids insults and shaming the person.
- Participant session tokens are random. `pid` values are stored as given, so treat exports as identifiable if `pid` is a Prolific ID.
