# Light Probe (Python)

A local desktop application that turns an author's raw notes into a multi-volume light novel, one volume
bin and one chapter at a time, with the creators confirming every stage.

It runs on your own computer, opens in its own window, and keeps every file in this folder.

## Run the app (Windows 10/11)

The easiest way to run Light Probe is to double-click **`Light Probe.bat`** in the project
folder.

- **First time:** it finds Python 3.12-3.14 (and offers to install Python 3.13 with winget if needed), creates a
  private environment in `.venv`, installs the packages (a few minutes, needs internet once), then opens the app.
- **Every time after:** it opens the app straight away.
- **Already open?** Double-clicking again closes the running copy and starts a fresh one.
- If `requirements.txt` ever changes, the packages are updated automatically on the next start.
- If the app does not come up, the window stays open and shows the end of `lightprobe.log`.

### Run from PowerShell

The batch file is recommended because it creates or repairs the virtual environment automatically.
If the environment is already set up, these commands run the same application manually:

```powershell
.venv\Scripts\python.exe run.py              # desktop window
.venv\Scripts\python.exe run.py --browser    # browser window
.venv\Scripts\python.exe run.py --headless   # local server without opening a window
.venv\Scripts\python.exe run.py --stop       # stop a running copy
```

In the app, open **Settings** (left side). For Anthropic, paste your API key once. It is saved only
in `settings.json` in this folder (an `ANTHROPIC_API_KEY` environment variable also works and takes
priority). For local models, start Ollama first, select **Local Ollama**, and choose a model that
has already been downloaded with `ollama pull`.

The app listens only on `127.0.0.1:8765`, so it is available only on the current computer.

To move the app to another computer, copy this whole folder (including `universes/`; `.venv` can be left out)
and double-click `Light Probe.bat` there.

## The flow

| Stage | What happens | The creators |
|---|---|---|
| 1. Ingestion | Every MESS file is read page by page and sorted into characters, world rules, arc beats, draft scenes (copied word for word), voice samples, themes. Nothing is sampled or skipped. | Drop files in; watch the sort |
| 2. Review Intake | Contradictions are checked against all the notes; what remains becomes questions. | Review; answer questions (optional) |
| 3. Universe Bible | Identity check (same person / mixed notes), Universe Bible, Soul Roster, Arc Map. | Review, repair characters, approve |
| 4. Author Style | Style Lab: the author's own voice (from their prose), a polished version, and unique voices, each with a test passage of the same scene. | Refine with feedback until right, then lock |
| 5. Volume Bins | Every item goes into the volume where it belongs. The volume count is fixed by the creators; finished volumes stay whole; the author's own volume numbers are kept; no balancing. | Move items, edit volume text, approve |
| 6. Gap-Fill | Per volume: where the story stands, the author's main events, and proposed mini-events that compound toward them by cause and effect. Never a new main event or world rule — those become questions. | Accept / edit / reject / add mini-events, answer questions, confirm each volume |
| 7. Volume Outline | Chapter outlines from each bin plus its confirmed mini-events, inside the chapters-per-volume range. | Review, approve |
| 8. Payoff Planner | Foreshadowing threads (author-implied or inferred), each planted in an existing chapter. | Review, approve |
| 9. Novel Writing | One chapter at a time from its own context bin, checked by a separate audit. Review gate every 3 chapters. Start at any volume. | Save / regenerate / elevate / discard each chapter |
| 10. Handoff | PASS-OUT / PASS-IN memory carries each volume into the next. | Approve |

Universe settings (top right of a universe): number of volumes, chapters per volume (min/max), which MESS
file is a finished volume, which files are events-only (their style is never copied), author style, models.

## Where everything is

```
universes/<Universe>/
    state.json                 progress and results of every stage
    MESS/                      the author's files (+ _sort-log.md, _ask-me.md)
    SORTED/material.json       verbatim author passages
    SHARED_CORE_KNOWLEDGE/     the client's cards + generated Bible, roster, voice DNA
    STYLE_LAB/                 style candidates and test passages
    SLOW_BURN_MODE/Volume_01/  BIN.md, MINI-EVENTS.md, Chapters/, Memory/ (one folder per volume)
    _backups/                  copies made before any reset or repair
    EXPORTS/                   exported manuscripts (.docx)
    usage.json                 API calls and estimated cost for this universe
```

## AI providers and external services

Light Probe supports Anthropic Claude and local Ollama. Claude remains the default for existing
universes. To test locally, install Ollama, download a model such as `llama3.1:8b`, open Settings,
choose **Local Ollama**, and keep the default URL `http://127.0.0.1:11434`. Start with a context
setting of 16K or 32K tokens; a model's advertised maximum does not guarantee that the computer can
run that context efficiently.

For local model comparisons, `qwen3:8b` is a good next test on an 8 GB GPU. A stronger computer
with about 24 GB of VRAM can test `qwen3:14b`. Download a model before selecting it:

From a terminal, the local setup is:

```
ollama pull llama3.1:8b
ollama pull qwen3:8b
# On a larger GPU:
ollama pull qwen3:14b
ollama list
```

The application sends requests to Ollama's local `/api/chat` endpoint. No Anthropic API key is needed
when Ollama is selected. Planning and writing model names can be changed later in the universe settings.

## External services and dependencies

| Dependency | Used for | Needs internet |
|---|---|---|
| Anthropic Claude API (`anthropic` package) | Every step that reads or writes story text: sorting, Bible, style, bins, gap-fill, outlines, payoff, chapters, handoff | Yes, for those steps only. Paid per use on your own Anthropic account. |
| Ollama | Optional local model provider for the same pipeline | No, after the model is downloaded |
| NiceGUI + pywebview | The interface and its desktop window | No |
| python-docx, pypdf | Reading .docx/.pdf uploads, exporting the manuscript | No |

No other servers, accounts or subscriptions. The app listens only on 127.0.0.1 (this computer).
Viewing, reviewing, editing, moving items, answering questions and exporting all work offline.
Every model call goes through one file, `lightprobe/llm.py`, so the provider can be changed without
rewriting the pipeline stages.

The header of each universe shows its API calls and estimated cost (`usage.json`).

## For developers

```
pip install -r requirements-dev.txt
python -m pytest            # offline: a fake Anthropic server answers every call
python tests/ui_preview.py  # the app with demo universes at every stage, on a temporary folder
```

- `lightprobe/ai/` — the prompts, one module per stage
- `lightprobe/pipeline/` — the stages (state + files)
- `lightprobe/actions.py` — every action and its stage gate
- `lightprobe/jobs.py` — background jobs (one per universe), progress, stop
- `lightprobe/ui/` — the interface
- `docs/REQUIREMENTS-TRACE.md` — every feature traced to the client's request
