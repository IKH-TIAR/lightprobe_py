"""Regression tests for the issues found in the code review."""

import io

import pytest

from lightprobe import actions, storage
from lightprobe.ai import planning as ai_planning
from lightprobe.ai.sorting import extract_span
from lightprobe.pipeline import bible, ingest, writing


def test_extract_span_never_cuts_and_matches_loosely():
    long_passage = "It began. " + "x " * 5000 + "and the door closed."
    page = "Notes before.\n" + long_passage + "\nAfter."
    # Curly vs straight quotes and dashes in the model's anchors still match
    span, exact = extract_span("He said “wait” — then left.", 'He said "wait" - then', "- then left.")
    assert exact and span == "He said “wait” — then left."
    # End anchor not found: kept to the end of the page, never cut to 4,000 characters, marked inexact
    span, exact = extract_span(page, "It began. x x x", "words that are not on the page")
    assert not exact and span.startswith("It began.") and "and the door closed." in span and len(span) > 4000
    assert extract_span(page, "nowhere to be found", "x") == (None, False)


def _universe(name: str) -> None:
    storage.create_universe(name, "SLOW_BURN_MODE")


def test_resort_changed_file_does_not_duplicate(fake):
    name = "Fix_Resort"
    _universe(name)
    storage.add_mess_file(name, "A.txt", b"BEAT: First event\nBEAT: Second event")
    storage.add_mess_file(name, "B.txt", b"BEAT: Other file event")
    st = ingest.run_ingestion(name, storage.load_state(name))
    assert len(st["messSortResult"]["arcBeats"]) == 3
    # Pretend later stages exist, then change A.txt and delete B.txt
    st["bins"] = {"volumes": []}
    st["furthestStatus"] = "WRITING_MODE"
    st["resumeStatus"] = "WRITING_MODE"
    storage.save_state(name, st)
    (storage.mess_dir(name) / "A.txt").write_text("BEAT: First event\nBEAT: Second event\nBEAT: Third event", encoding="utf-8")
    storage.delete_mess_file(name, "B.txt")
    st = ingest.run_ingestion(name, storage.load_state(name))
    beats = st["messSortResult"]["arcBeats"]
    assert [b["event"] for b in beats] == ["First event", "Second event", "Third event"], "no duplicates, deleted file gone"
    assert [b["id"] for b in beats] == ["B-4", "B-5", "B-6"], "ids are never reused"
    assert st["bins"] is None and st["furthestStatus"] == "INGESTION_REVIEW" and st["resumeStatus"] is None, "stale stages invalidated"
    assert list((storage.universe_dir(name) / "_backups").iterdir()), "old results backed up"


def test_split_out_character_is_kept(fake, monkeypatch):
    name = "Fix_Split"
    _universe(name)
    storage.add_mess_file(name, "A.txt", b"SOUL: Kaho\nBEAT: Something")
    st = ingest.run_ingestion(name, storage.load_state(name))
    st["messSortResult"]["souls"][0]["essence"] = "Kaho is a courier.\nKaho's mother hides the letters."
    storage.save_state(name, st)
    monkeypatch.setattr(bible, "split_merged_soul", lambda *a, **k: {"aliases": [], "moved": [{"line": 2, "toName": "Kaho's mother"}]})
    st = bible.run_bible(name, storage.load_state(name))
    names = [s["name"] for s in st["soulRoster"]["souls"]]
    assert "Kaho's mother" in names and "Kaho" in names
    mother = next(s for s in st["messSortResult"]["souls"] if s["name"] == "Kaho's mother")
    assert "hides the letters" in mother["essence"]


def test_payoff_ids_are_safe_and_ordered(monkeypatch):
    res = {"overallStrategy": "s", "payoffs": [
        {"id": "thread:1/a", "threadName": "A", "origin": "AUTHOR", "setupVolume": 1, "setupChapterNumber": 2, "setupDescription": "",
         "payoffVolume": 2, "payoffChapterNumber": 1, "payoffDescription": "", "narrativeImpact": ""},
        {"id": "thread:1/a", "threadName": "B", "origin": "INFERRED", "setupVolume": 2, "setupChapterNumber": 3, "setupDescription": "",
         "payoffVolume": 2, "payoffChapterNumber": 1, "payoffDescription": "", "narrativeImpact": ""},
    ]}
    monkeypatch.setattr(ai_planning, "generate_json", lambda *a, **k: res)
    out = ai_planning.generate_payoff_plan("u", "ctx", "cards", {1: 3, 2: 3}, "claude-sonnet-5-5")
    assert [p["id"] for p in out["payoffs"]] == ["thread_1_a"], "unsafe id cleaned; payoff-before-setup dropped"
    assert out["dropped"] == 1


def test_payoff_due_in_later_volume_is_given_to_that_chapter():
    state = {"payoffPlan": {"payoffs": [{
        "setupVolume": 1, "setupChapterNumber": 2,
        "payoffVolume": 3, "payoffChapterNumber": 4,
    }]}}
    assert writing.seeds_for_chapter(state, 1, 2)
    assert not writing.payoffs_for_chapter(state, 1, 3)
    assert writing.payoffs_for_chapter(state, 3, 4)


def test_uploads_decode_windows_text_and_never_overwrite():
    name = "Fix_Upload"
    _universe(name)
    assert storage.add_mess_file(name, "notes.txt", "Kaho’s “letter” — one".encode("cp1252")) == "notes.txt"
    assert storage.get_mess_files(name)[0]["content"] == "Kaho’s “letter” — one"
    assert storage.add_mess_file(name, "notes.txt", "Kaho’s “letter” — one".encode("utf-8")) == "notes.txt", "identical: no copy"
    assert storage.add_mess_file(name, "notes.txt", b"different") == "notes (2).txt", "a different file is never overwritten"
    import docx
    d = docx.Document()
    d.add_paragraph("Before the table.")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Volume 4", "The motel"
    buf = io.BytesIO()
    d.save(buf)
    stored = storage.add_mess_file(name, "plan.docx", buf.getvalue())
    text = (storage.mess_dir(name) / stored).read_text(encoding="utf-8")
    assert "Before the table." in text and "Volume 4 | The motel" in text, "table text is kept"


def test_approvals_and_rebuilds_close_the_writing_shortcut():
    name = "Fix_Gates"
    _universe(name)
    st = storage.load_state(name)
    st.update(status="OUTLINE_REVIEW", furthestStatus="WRITING_MODE", resumeStatus="WRITING_MODE",
              bins={"universeSummary": "", "volumes": [{"volumeNumber": 1, "title": "V", "premise": "", "summary": "", "targetChapterCount": 3,
                                                         "itemIds": [], "pinnedFrom": []}]},
              plan={"universeSummary": "", "totalVolumes": 1, "volumes": [{"volumeNumber": 1, "title": "V", "premise": "", "summary": "",
                                                                          "targetChapterCount": 3, "sourceItemIds": [], "miniEventIds": [],
                                                                          "chapters": [{"chapterNumber": 1, "title": "c", "synopsis": "s"}]}]},
              payoffPlan={"overallStrategy": "", "payoffs": []})
    storage.save_state(name, st)
    # Re-outlining a volume invalidates the payoff plan and the shortcut back into writing
    from lightprobe.pipeline import outline
    st["plan"]["volumes"][0]["chapters"] = []
    from lightprobe.pipeline.common import invalidate_downstream
    invalidate_downstream(name, st, "OUTLINE_REVIEW", "test", ("payoffPlan",))
    storage.save_state(name, st)
    with pytest.raises(ValueError):
        actions.dispatch(name, "SET_STATUS", {"status": "WRITING_MODE"})
    with pytest.raises(ValueError):
        actions.dispatch(name, "SET_STATUS", {"status": "FORESHADOWING_MODE"})
    assert outline  # module used above


def test_keep_chapters_syncs_the_counter():
    name = "Fix_Keep"
    _universe(name)
    st = storage.load_state(name)
    st.update(status="WRITING_MODE", currentVolume=1, chaptersBeforePlan=[1], chaptersGeneratedInCurrentVolume=0,
              plan={"volumes": [{"volumeNumber": 1, "title": "V", "premise": "", "summary": "", "targetChapterCount": 2,
                                 "chapters": [{"chapterNumber": 1, "title": "a", "synopsis": ""}, {"chapterNumber": 2, "title": "b", "synopsis": ""}]}]})
    for n in (1, 2, 3):
        storage.save_chapter(name, "SLOW_BURN_MODE", 1, n, f"Ch {n}", "text")
    storage.save_state(name, st)
    st = writing.keep_volume_chapters(name, st, 1)
    assert st["chaptersGeneratedInCurrentVolume"] == 2 and st["status"] == "HANDOFF_MODE"


def test_relative_volume_mentions_do_not_place():
    from lightprobe.ai.planning import volume_tag
    assert volume_tag("After Volume 1") is None and volume_tag("before vol. 3") is None and volume_tag("End of Volume 2") is None
    assert volume_tag("Volume 2") == 2 and volume_tag("Volume 1, Eighteen") == 1
    assert volume_tag("after the fight, Volume 3") == 3


def test_no_inferred_seeds_in_finished_volumes(monkeypatch):
    base = {"threadName": "T", "setupChapterNumber": 1, "setupDescription": "", "payoffVolume": 2, "payoffChapterNumber": 2,
            "payoffDescription": "", "narrativeImpact": ""}
    res = {"overallStrategy": "", "payoffs": [{**base, "id": "a", "origin": "AUTHOR", "setupVolume": 1},
                                              {**base, "id": "b", "origin": "INFERRED", "setupVolume": 1},
                                              {**base, "id": "c", "origin": "INFERRED", "setupVolume": 2, "payoffChapterNumber": 3}]}
    prompts = []
    monkeypatch.setattr(ai_planning, "generate_json", lambda opts, prompt: (prompts.append(prompt), res)[1])
    out = ai_planning.generate_payoff_plan("u", "ctx", "cards", {1: 3, 2: 3}, "claude-sonnet-5-5", finished=frozenset({1}))
    assert [p["id"] for p in out["payoffs"]] == ["a", "c"] and "Volumes 1 are FINISHED" in prompts[0]
