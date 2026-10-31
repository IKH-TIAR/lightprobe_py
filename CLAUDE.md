# Light Probe — Python desktop app (`lightprobe_py/`)

The active version of the client's Light Probe engine: a local Python desktop app (NiceGUI in a pywebview
window) with Anthropic Claude for the model steps. It replaces the Next.js app in the repo root, which stays
as a reference only. Started fresh: it does not import the Next.js universes.

Read `docs/REQUIREMENTS-TRACE.md` before changing behaviour: every feature is traced there to the client's
own words (Fiverr chat), marked ASKED / AGREED / SUPPORT. Keep it updated when features change.

## Decisions (2026-10-19, from the developer)

- Plain Python + the official `anthropic` SDK; no LangGraph. Our own gated state machine.
- Interface: NiceGUI (FastAPI underneath), same look as the old app (dark `#0a0a0a`, glass panels,
  purple/emerald/amber, Tailwind classes). Opens as a desktop window (`ui.run(native=True)`), `--browser` optional.
  Listens on 127.0.0.1 only.
- Local folders only (no Google Drive yet). Optional local LLM through Ollama; every model call still goes
  through `lightprobe/llm.py`.
- Models: `claude-sonnet-5-5` default for planning and writing, `claude-opus-5-5` selectable, and
  `llama3.1:8b` available for Ollama testing. Server-side refusal fallback
  (`server-side-fallback-2026-07-01`, `fallbacks="default"`) applies to Anthropic calls.

## The flow (what the client consistently asked for)

```
SORTING_MODE → INGESTION_REVIEW → BIBLE_REVIEW → STYLE_LAB → BIN_REVIEW → GAP_REVIEW → OUTLINE_REVIEW
→ FORESHADOWING_MODE → WRITING_MODE (⇄ CHAPTER_REVIEW every 3 chapters) → HANDOFF_MODE → … → COMPLETED
```

1. **Sort** (`pipeline/ingest.py`, prompts `ai/sorting.py`) — every MESS file, page by page (~24K chars), lossless.
   Drafts/voice samples copied verbatim by anchor quotes (`extract_span`) into `SORTED/material.json`. A page whose
   output is cut off is split and re-sorted (never condensed). Resumable per file. Contradictions → questions,
   auto-checked against the whole intake; answers → `AUTHOR-CLARIFICATIONS.md` canon.
2. **Bible** (`pipeline/bible.py`) — identity check (merge same person, split mixed notes by line number,
   verbatim), Universe Bible, Soul Roster, Arc Map. `repair_souls` backs up first.
3. **Style Lab** (`pipeline/style_lab.py`, `ai/style.py`) — candidates: author's own Voice DNA (events-only files
   excluded), a polished version, unique voices; each writes a test passage of the same scene. Creators refine
   with feedback, then lock → `03-AUTHOR-VOICE-DNA.md`, `01-AUTHOR-STYLE-REMINDER.md`, `01-AUTHOR-STYLE-LOCK.md`.
4. **Volume bins** (`pipeline/bins.py`, `ai/planning.py`) — **the fix for the "fake volumes" complaint**:
   - Volume count is fixed by the creators (`state.targetVolumes`); never changed. Empty = engine decides.
   - `state.volumePins` {MESS file → volume}: a finished volume (e.g. V1.txt = Volume 1) stays whole there.
   - A volume number the author wrote in a note ("Volume 1, Eighteen") is kept (`volume_tag`), as promised on Oct 05.
   - Everything else is placed by its events; file names never place material. **No count-balancing.**
   - Code enforces fixed placements after the roadmap call. Creators can move items (`MOVE_ITEM`) and edit volume text.
   - Writes `<MODE>/Volume_NN/BIN.md` (one folder per volume).
5. **Gap-fill** (`pipeline/gaps.py`) — per volume (Card 05): volume start, the author's main events, proposed
   mini-events (cause → effect → leads to main event), questions where only a new main event/world rule would close
   the gap. Creators accept/edit/reject/add, answer, confirm the volume (`MINI-EVENTS.md`). Pinned volumes are
   `FINISHED` (skipped unless asked). Ids: `E05-3` (mini-event), `Q05-1` (question).
6. **Outline** (`pipeline/outline.py`) — chapter counts from bin + confirmed mini-events inside the creators' range
   (`clamp_chapters` hard limit), 5-chapter batches, `sourceRefs` may include `E..` ids. Resumable.
   `APPROVE_PLAN` writes `Memory/chapters_outline.txt`, `initial_summary.txt`, `SOURCE-MATERIAL.md`; volumes that
   already have chapters go to `state.chaptersBeforePlan` (keep or reset before writing).
7. **Payoff** (`pipeline/payoff.py`) — AUTHOR/INFERRED threads; chapter refs validated (one correction retry,
   remaining invalid threads dropped and reported).
8. **Writing** (`pipeline/writing.py`) — ONE chapter per call from its context bin; separate audit call. The result
   is a DRAFT in `state.draft` until `SAVE_DRAFT` (only saving writes the chapter, ledger entry, soul updates,
   background). Review gate after 3 saved chapters; 100-chapter milestone. `carry_context` is the single source for
   both the writer and the "Carried into Chapter N" panel. Start at any volume (reconstructed PASS-IN from the plan).
   `RESET_VOLUME` moves chapters + writing memory (+ a reconstructed PASS-IN) to `_backups/`.
9. **Handoff** — PASS-OUT from full ledger + soul index + seeds + final passage → next volume's PASS-IN.

## Launching

`Light Probe.bat` is the only launcher: first run finds Python 3.12-3.14 (winget offer for Python 3.13), creates `.venv`, installs
`requirements.txt` (reinstalls when it changes, marker `.venv/requirements.installed`), then runs
`run.py --stop` (closes a running copy via `lightprobe.pid` + taskkill /T) and starts `pythonw run.py` (desktop
window), checking http://127.0.0.1:8765 comes up. Extra arguments pass through (`--headless` for testing).
Without a console, output goes to `lightprobe.log`.

## Code map

```
lightprobe/
  config.py      paths (universes/, settings.json, cards/), API key (env ANTHROPIC_API_KEY wins)
  storage.py     all disk IO: universes, MESS (+ .docx/.pdf conversion), sorted store, cards, volumes, chapters, backups
  styles.py      STAGES / STATE_ORDER, style config + format_style_prompt, chapter-range helpers
  llm.py         the only Claude call layer: streaming, caching, JSON schema outputs, continuation, usage.json
  ai/            prompts per stage (sorting, canon, style, planning, writing)
  pipeline/      stages (state + files); common.py has lossless merge, alias hygiene, bin_text, item_index
  actions.py     every action + its stage gate (ACTIONS); dispatch() runs quick actions or starts a job
  jobs.py        background thread per universe, progress, stop-at-next-step, error capture
  ui/            theme.py (look), dashboard.py, universe.py (header, stepper, progress, dialogs), stages.py (panels)
  cards/         master_cards.json (the client's 18 cards, exported verbatim from the old app), genre_presets.json
tests/           fake_anthropic.py (SSE fake API), test_pipeline.py (full flow), test_ui.py (simulated clicks),
                 ui_preview.py (demo universes on a temp folder for screenshots)
```

## Stale results (invalidation)

When an earlier stage changes, everything built on it is backed up to `_backups/` and cleared, and
`furthestStatus` drops back so the later gates must be passed again (`common.invalidate_downstream`):
re-sort with changed/new/deleted files → bins, gap-fill, plan, payoff; `BUILD_BINS` → gap-fill, plan, payoff;
`MOVE_ITEM`/`EDIT_VOLUME` and any gap-fill change → plan, payoff; re-outlining → payoff. Approval actions
(`actions.APPROVALS`) clear `resumeStatus`. Re-sorting a changed file first removes what was taken from it
(`ingest._purge_file`); ids (B-/M-/V-/U-, E../Q..) come from persistent counters and are never reused.

Draft passages: `extract_span` returns `(text, exact)`; quotes/dashes match loosely; an unmatched end quote keeps
the passage to the end of the page (`anchor: "open-end"`, shown in amber in Review Intake) — never cut short.

## Invariants

- Never sample or condense MESS content; split the work or continue the output (`generate_text` continuations).
- One chapter per writer call. Writer ledger context = last ~8,000 chars; handoffs use the full ledger.
- The client's cards are never overwritten by the pipeline (generated files are listed in `storage.GENERATED_CORE_FILES`).
  Creators may edit any card in the Core Knowledge dialog.
- Stage gates live in `actions.ACTIONS`; never bypass them. `SET_STATUS` navigates back, or forward only to stages
  already reached; writing-loop stages only via their approvals (or returning to `resumeStatus`).
- One job per universe. A job re-reads state from disk and checkpoints as it goes.
- Never split a pinned (finished) volume; never balance volumes by count.

## Testing (offline, no credits)

```
.venv\Scripts\python -m pytest            # 14 tests: full pipeline, UI click-through, review regressions (fake API)
.venv\Scripts\python tests\ui_preview.py --port 8790   # demo universes at every stage, temp folder
```
`tests/live_smoke.py` spends real credits (~$2) on a temporary synthetic universe; run it only when asked.
Never test against the creators' real universes or the user's running app (see the memory note).
Screenshots: Edge headless (`msedge --headless=new --screenshot=... http://127.0.0.1:8790/...`).

## Status (2026-10-19)

All stages built and tested offline (14 tests). Live smoke test against the real API passed on 2026-10-19
(`tests/live_smoke.py`: synthetic 3-file universe, 4 volumes, whole flow + 1 chapter; 30 calls, est. $1.74; a chapter
takes ~6 min incl. the first-chapter PASS-IN/soul index). Fixed from that run: relative mentions ("After Volume 1")
no longer pin an item; no new INFERRED payoff seeds in finished volumes; gap-fill asks at most 5 questions.
Not yet run on a real universe (Kaho starts fresh). Not built: Google Drive, installer (.exe) packaging.
