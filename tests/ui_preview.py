"""Starts the app on a temporary data folder with demo universes at different stages, answered by the
fake Anthropic server. For looking at the screens without touching real universes or spending credits:

    python tests/ui_preview.py --port 8790
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="lightprobe-preview-"))
os.environ["LIGHTPROBE_DATA"] = str(tmp / "universes")
os.environ["LIGHTPROBE_SETTINGS"] = str(tmp / "settings.json")
os.environ["ANTHROPIC_API_KEY"] = "preview-key"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_anthropic import FakeAnthropic  # noqa: E402

fake = FakeAnthropic().start()
os.environ["ANTHROPIC_BASE_URL"] = fake.url

from lightprobe import llm, storage  # noqa: E402
from lightprobe.app import main  # noqa: E402
from lightprobe.pipeline import bible, bins, gaps, ingest, outline, payoff, style_lab, writing  # noqa: E402
from test_pipeline import NOTES, V1  # noqa: E402


def seed(name: str, until: str) -> None:
    storage.create_universe(name, "SLOW_BURN_MODE")
    storage.add_mess_file(name, "Delivery Message Protocol V1.txt", V1.encode())
    storage.add_mess_file(name, "Notes.txt", NOTES.encode())
    st = storage.load_state(name)
    st.update(targetVolumes=4, chapterRange={"min": 4, "max": 5}, volumePins={"Delivery Message Protocol V1.txt": 1},
              messFileSettings={"Delivery Message Protocol V1.txt": {"eventsOnly": True}})
    storage.save_state(name, st)
    if until == "SORTING_MODE":
        return
    token = llm.current_universe.set(name)
    steps = [
        ("INGESTION_REVIEW", lambda s: ingest.run_ingestion(name, s)),
        ("BIBLE_REVIEW", lambda s: bible.run_bible(name, s)),
        ("STYLE_LAB", lambda s: (s.update(status="STYLE_LAB"), style_lab.run_style_lab(name, s))[1]),
        ("BIN_REVIEW", lambda s: (style_lab.lock_style(name, s, s["styleLab"]["candidates"][1]["id"]), bins.run_bins(name, s))[1]),
        ("GAP_REVIEW", lambda s: (bins.approve_bins(name, s), gaps.run_gap_fill(name, s))[1]),
        ("OUTLINE_REVIEW", lambda s: ([gaps.confirm_volume(name, s, n, True) for n in (2, 3, 4)], gaps.approve_gaps(name, s), outline.run_outline(name, s))[2]),
        ("FORESHADOWING_MODE", lambda s: (outline.approve_plan(name, s), payoff.run_payoff(name, s))[1]),
        ("WRITING_MODE", lambda s: (payoff.approve_payoff(name, s), writing.set_start_volume(name, s, 2), writing.generate_chapter(name, s))[2]),
        ("CHAPTER_REVIEW", lambda s: [writing.save_draft(name, s) if s.get("draft") else writing.generate_chapter(name, s) for _ in range(6)][-1]),
    ]
    st = storage.load_state(name)
    for stage, fn in steps:
        st = fn(st) or st
        if stage == until:
            break
    llm.current_universe.reset(token)


if __name__ in {"__main__", "__mp_main__"}:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    if __name__ == "__main__":
        for stage in ("SORTING_MODE", "INGESTION_REVIEW", "STYLE_LAB", "BIN_REVIEW", "GAP_REVIEW", "OUTLINE_REVIEW", "WRITING_MODE", "CHAPTER_REVIEW"):
            seed(f"Demo_{stage.title().replace('_', '')}", stage)
        print(f"PREVIEW DATA: {tmp}", flush=True)
    main(native=False, port=args.port, open_window=False)
