"""Everything on disk. One folder per universe:

    universes/<Universe>/
        state.json
        MESS/                      raw notes (+ engine-written _sort-log.md, _ask-me.md)
        SORTED/material.json       verbatim author passages by id (M-n, V-n)
        SHARED_CORE_KNOWLEDGE/     the client's cards (read-only) + generated Bible, roster, voice DNA
        STYLE_LAB/                 style candidates and their test passages
        <MODE>/Volume_01 ... /     one folder per volume (the volume bins)
            BIN.md                 the author's material sorted into this volume
            MINI-EVENTS.md         creator-confirmed mini-events (gap-fill)
            Chapters/              ch-001 - Title.txt, ...
            Memory/                outline, source material, soul index, ledger, PASS-IN/OUT, seeds
        SUMMARIES (per mode)       VOL-01.md, ...
        _backups/                  copies made before any reset or repair
"""

from __future__ import annotations

import io
import json
import re
import shutil
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .config import CARDS_DIR, DATA_DIR
from .styles import STATE_ORDER, default_models, default_style_config, format_style_prompt

# Client cards copied into every universe. Never overwritten by the engine afterwards.
STANDING_CARD_FILES = [
    "00-LAWS.md",
    "01-LIGHT-PROBE.md",
    "01-AUTHOR-STYLE-LOCK.md",
    "01-AUTHOR-STYLE-REMINDER.md",
    "02-MOST-RECENT-PRESENT.md",
    "03-AUTHOR-VOICE.md",
    "03-AUTHOR-VOICE-DNA.md",
    "04-NO-DRIFT-NO-SLOP.md",
    "05-GAP-FILL.md",
    "06-MULTI-QUADRANT.md",
]
# Files the engine generates in SHARED_CORE_KNOWLEDGE (everything else there is the client's)
GENERATED_CORE_FILES = {
    "01-AUTHOR-STYLE-LOCK.md", "01-AUTHOR-STYLE-REMINDER.md", "03-AUTHOR-VOICE-DNA.md",
    "UNIVERSE-BIBLE.md", "SOUL-ROSTER.md", "ARC-MAP.md", "AUTHOR-CLARIFICATIONS.md",
}
TEXT_UPLOADS = {".txt", ".md", ".json"}
CONVERTED_UPLOADS = {".docx", ".pdf"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


@lru_cache(maxsize=1)
def master_cards() -> list[dict]:
    return json.loads((CARDS_DIR / "master_cards.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Universes
# ---------------------------------------------------------------------------

def safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())


def universe_dir(name: str) -> Path:
    return DATA_DIR / name


def core_dir(name: str) -> Path:
    return universe_dir(name) / "SHARED_CORE_KNOWLEDGE"


def mess_dir(name: str) -> Path:
    return universe_dir(name) / "MESS"


def list_universes() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir() and (d / "state.json").exists():
            state = load_state(d.name)
            if state:
                out.append(state)
    return out


def new_state(name: str, mode: str, style: dict | None = None, models: dict | None = None) -> dict:
    return {
        "name": name,
        "mode": mode,
        "status": "SORTING_MODE",
        "furthestStatus": "SORTING_MODE",
        "resumeStatus": None,
        "createdAt": now_iso(),
        "styleConfig": {**default_style_config(), **(style or {})},
        "models": {**default_models(), **(models or {})},
        # Creator settings (Settings panel)
        "targetVolumes": None,          # fixed number of volumes; None = the engine decides
        "chapterRange": {"min": None, "max": None},
        "volumePins": {},               # MESS file -> volume number (finished volumes, never split)
        "messFileSettings": {},         # MESS file -> {"eventsOnly": bool}
        # Pipeline results
        "messSortResult": None,
        "universeBible": None,
        "soulRoster": None,
        "styleLab": None,
        "bins": None,
        "gapFill": None,
        "plan": None,
        "payoffPlan": None,
        # Writing loop
        "currentVolume": 1,
        "totalVolumes": 1,
        "chaptersPerVolume": 0,
        "chaptersGeneratedInCurrentVolume": 0,
        "chaptersInCurrentPass": 0,
        "totalChaptersWritten": 0,
        "milestoneNotice": None,
        "chaptersBeforePlan": [],
        "subtletyAudit": None,
        "draft": None,                  # the chapter written but not yet saved
        "lastReset": None,
        "lastHandoff": None,
        "parallelTrack": None,
    }


def create_universe(name: str, mode: str, style: dict | None = None, models: dict | None = None) -> dict:
    name = safe_name(name)
    if not name:
        raise ValueError("Please enter a universe name.")
    udir = universe_dir(name)
    if udir.exists():
        raise ValueError(f'A universe named "{name}" already exists.')
    (udir / "MESS").mkdir(parents=True)
    core = core_dir(name)
    core.mkdir()
    for card in master_cards():
        (core / card["filename"]).write_text(card["content"], encoding="utf-8")
    state = new_state(name, mode, style, models)
    write_core(name, "01-AUTHOR-STYLE-LOCK.md", f"# 01-AUTHOR-STYLE-LOCK\n{format_style_prompt(state['styleConfig'])}")
    save_state(name, state)
    return state


def delete_universe(name: str) -> None:
    udir = universe_dir(safe_name(name))
    if udir.exists():
        shutil.rmtree(udir)


def load_state(name: str) -> dict | None:
    p = universe_dir(name) / "state.json"
    if not p.exists():
        return None
    for attempt in range(20):
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
            break
        except PermissionError:  # the file is being swapped in by another thread (Windows)
            if attempt == 19:
                raise
            time.sleep(0.05)
    # Fill fields added in later versions so older universes keep working
    for k, v in new_state(state.get("name", name), state.get("mode", "SLOW_BURN_MODE")).items():
        state.setdefault(k, v)
    return state


def atomic_write(path: Path, text: str) -> None:
    """Write to a temp file, then swap it in, so a reader never sees half a file. On Windows the swap fails
    while another thread has the file open for a moment, so it is retried briefly."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(20):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def save_state(name: str, state: dict) -> None:
    furthest = state.get("furthestStatus") or state["status"]
    if STATE_ORDER.index(state["status"]) > STATE_ORDER.index(furthest):
        state["furthestStatus"] = state["status"]
    atomic_write(universe_dir(name) / "state.json", json.dumps(state, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# MESS
# ---------------------------------------------------------------------------

def get_mess_files(name: str) -> list[dict]:
    """Input files in MESS, sorted by name. Files starting with "_" are engine output, not input."""
    d = mess_dir(name)
    if not d.exists():
        return []
    files = []
    for p in sorted(d.iterdir(), key=lambda x: x.name):
        if p.is_file() and not p.name.startswith("_"):
            files.append({"name": p.name, "content": decode_text(p.read_bytes())})
    return files


def list_mess_names(name: str) -> list[str]:
    d = mess_dir(name)
    return sorted(p.name for p in d.iterdir() if p.is_file() and not p.name.startswith("_")) if d.exists() else []


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without a byte-order mark); otherwise the Windows code page that Notepad and Word use
    for "ANSI" text, so curly quotes and dashes survive."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _docx_text(data: bytes) -> str:
    """Paragraphs and tables in document order, then headers and footers."""
    import docx  # python-docx
    doc = docx.Document(io.BytesIO(data))
    parts = []
    for block in doc.iter_inner_content():
        if hasattr(block, "rows"):
            for row in block.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        else:
            parts.append(block.text)
    for section in doc.sections:
        for part in (section.header, section.footer):
            text = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def convert_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (stored filename, text). .docx and .pdf are converted to .txt; text files kept as is."""
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_UPLOADS:
        return filename, decode_text(data)
    stem = Path(filename).stem
    if suffix == ".docx":
        return f"{stem}.txt", _docx_text(data)
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return f"{stem}.txt", "\n\n".join((page.extract_text() or "") for page in reader.pages)
    raise ValueError(f"Unsupported file type {suffix}. Use .txt, .md, .json, .docx or .pdf.")


def add_mess_file(name: str, filename: str, data: bytes) -> str:
    """Adds a file to MESS. A different file with the same name is never overwritten: the new one gets a
    numbered name. Uploading the identical file again changes nothing."""
    stored, text = convert_upload(Path(filename).name, data)
    if not text.strip():
        raise ValueError(f"{filename}: no text could be read from this file.")
    d = mess_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    target = d / stored
    n = 2
    while target.exists():
        if decode_text(target.read_bytes()) == text:
            return target.name
        target = d / f"{Path(stored).stem} ({n}){Path(stored).suffix}"
        n += 1
    target.write_text(text, encoding="utf-8")
    return target.name


def delete_mess_file(name: str, filename: str) -> None:
    p = mess_dir(name) / Path(filename).name
    if p.exists():
        p.unlink()


def write_mess_file(name: str, filename: str, content: str) -> None:
    mess_dir(name).mkdir(parents=True, exist_ok=True)
    (mess_dir(name) / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Sorted material (verbatim author text by id)
# ---------------------------------------------------------------------------

def get_sorted_material(name: str) -> dict:
    p = universe_dir(name) / "SORTED" / "material.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": {}}


def save_sorted_material(name: str, store: dict) -> None:
    d = universe_dir(name) / "SORTED"
    d.mkdir(parents=True, exist_ok=True)
    (d / "material.json").write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core knowledge cards
# ---------------------------------------------------------------------------

def read_core(name: str, filename: str) -> str:
    p = core_dir(name) / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_core(name: str, filename: str, content: str) -> None:
    """Engine-generated files only; the client's cards are never overwritten by the pipeline."""
    core_dir(name).mkdir(parents=True, exist_ok=True)
    (core_dir(name) / filename).write_text(content, encoding="utf-8")


def list_core_files(name: str) -> list[str]:
    d = core_dir(name)
    return sorted(p.name for p in d.iterdir() if p.is_file()) if d.exists() else []


def save_card_edit(name: str, filename: str, content: str) -> None:
    """The creators' own edit of a card (from the Core Knowledge screen)."""
    write_core(name, Path(filename).name, content)


def standing_cards(name: str, extra: list[str] | None = None) -> str:
    parts = []
    for f in STANDING_CARD_FILES + (extra or []):
        content = read_core(name, f).strip()
        if content:
            parts.append(f"=== {f} ===\n{content}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

def vol_folder(n: int) -> str:
    return f"Volume_{n:02d}"


def volume_dir(name: str, mode: str, n: int) -> Path:
    return universe_dir(name) / mode / vol_folder(n)


def ensure_volume_folders(name: str, mode: str, total: int) -> None:
    for n in range(1, total + 1):
        for sub in ("Chapters", "Memory"):
            (volume_dir(name, mode, n) / sub).mkdir(parents=True, exist_ok=True)


def write_volume_file(name: str, mode: str, n: int, filename: str, content: str) -> None:
    d = volume_dir(name, mode, n)
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(content, encoding="utf-8")


def read_volume_file(name: str, mode: str, n: int, filename: str) -> str:
    p = volume_dir(name, mode, n) / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""


def memory_path(name: str, mode: str, n: int, filename: str) -> Path:
    return volume_dir(name, mode, n) / "Memory" / filename


def read_memory(name: str, mode: str, n: int, filename: str) -> str:
    p = memory_path(name, mode, n, filename)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_memory(name: str, mode: str, n: int, filename: str, content: str) -> None:
    p = memory_path(name, mode, n, filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def delete_memory(name: str, mode: str, n: int, filename: str) -> None:
    p = memory_path(name, mode, n, filename)
    if p.exists():
        p.unlink()


def list_memory(name: str, mode: str, n: int) -> list[str]:
    d = volume_dir(name, mode, n) / "Memory"
    return sorted(p.name for p in d.iterdir() if p.is_file()) if d.exists() else []


def append_background(name: str, mode: str, n: int, content: str) -> None:
    if not content.strip():
        return
    p = memory_path(name, mode, n, "05-BACKGROUND.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n=== OVERFLOW CAPTURE [{now_iso()}] ===\n{content.strip()}\n")


def read_background(name: str, mode: str, n: int) -> str:
    return read_memory(name, mode, n, "05-BACKGROUND.txt")


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

def _chapter_number(filename: str) -> int:
    m = re.match(r"ch-(\d+)", filename, re.I) or re.search(r"(\d+)", filename)
    return int(m.group(1)) if m else 10**9


def chapters_dir(name: str, mode: str, n: int) -> Path:
    return volume_dir(name, mode, n) / "Chapters"


def list_chapters(name: str, mode: str, n: int) -> list[dict]:
    d = chapters_dir(name, mode, n)
    if not d.exists():
        return []
    files = sorted((p for p in d.iterdir() if p.suffix == ".txt"), key=lambda p: (_chapter_number(p.name), p.name))
    return [{"chapterNumber": _chapter_number(p.name), "file": p.name, "content": p.read_text(encoding="utf-8")} for p in files]


def chapter_text(name: str, mode: str, n: int, chapter: int) -> str:
    for c in list_chapters(name, mode, n):
        if c["chapterNumber"] == chapter:
            return c["content"]
    return ""


def save_chapter(name: str, mode: str, n: int, chapter: int, title: str, content: str) -> None:
    """One chapter, one file: ch-001 - Title.txt. Re-saving a chapter number replaces its file."""
    d = chapters_dir(name, mode, n)
    d.mkdir(parents=True, exist_ok=True)
    prefix = f"ch-{chapter:03d}"
    for p in d.iterdir():
        if p.name.startswith(prefix):
            p.unlink()
    clean = re.sub(r"^chapter\s+\d+\s*[:\-–—]?\s*", "", title, flags=re.I)
    clean = re.sub(r"[^a-zA-Z0-9_\- ]", "_", clean).strip()[:80]
    (d / f"{prefix}{' - ' + clean if clean else ''}.txt").write_text(content, encoding="utf-8")


def save_summary(name: str, mode: str, n: int, content: str) -> None:
    d = universe_dir(name) / mode / "SUMMARIES"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"VOL-{n:02d}.md").write_text(content, encoding="utf-8")


def summary_path(name: str, mode: str, n: int) -> Path:
    return universe_dir(name) / mode / "SUMMARIES" / f"VOL-{n:02d}.md"


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

def new_backup_dir(name: str, label: str) -> Path:
    d = universe_dir(name) / "_backups" / f"{stamp()}-{label}"
    d.mkdir(parents=True, exist_ok=True)
    state_file = universe_dir(name) / "state.json"
    if state_file.exists():
        shutil.copy2(state_file, d / "state.json")
    return d
