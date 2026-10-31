"""End-to-end test of the whole flow against the fake Anthropic server."""

import time

import pytest

from lightprobe import actions, jobs, llm, storage
from lightprobe.pipeline import ingest, writing

NAME = "Test_Universe"

V1 = "\n".join([
    "SOUL: Kaho",
    "BEAT: Kaho finds the shoebox of letters",
    "BEAT: [Chapter 3] The first delivery",
    "DRAFT: The ocean held its breath the morning the first black envelope came to the stairs and Kaho took it",
]) + "\n\n" + ("filler line for the page size\n" * 300)
NOTES = "\n".join([
    "SOUL: Naseru",
    "BEAT: [Volume 2] The motel confrontation",
    "BEAT: The Winter Cup final",
    "BEAT: The Great Pause begins",
    "CONFLICT: Naseru is both 16 and 17",
    "DRAFT: Naseru walked the long way home along the canal counting the lamps that still worked tonight",
])


def wait_job(name: str) -> jobs.Job:
    for _ in range(600):
        job = jobs.current(name)
        if job and job.status != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def run(action: str, payload: dict | None = None) -> dict:
    """Runs an action through the gate-enforced dispatcher; waits for jobs."""
    out = actions.dispatch(NAME, action, payload)
    if isinstance(out, jobs.Job):
        job = wait_job(NAME)
        assert job.status == "done", f"{action}: {job.error}"
        jobs.clear(NAME)
    return storage.load_state(NAME)


@pytest.fixture(scope="module")
def universe(fake):
    storage.create_universe(NAME, "SLOW_BURN_MODE")
    storage.add_mess_file(NAME, "Delivery Message Protocol V1.txt", V1.encode())
    storage.add_mess_file(NAME, "Notes.txt", NOTES.encode())
    return NAME


def test_full_flow(universe, fake):
    requests_before = len(fake.requests)
    st = storage.load_state(NAME)
    assert len(list(storage.core_dir(NAME).glob("*.md"))) >= 18, "client cards copied into the universe"

    # Settings: 4 volumes, 4-5 chapters, V1 is the finished Volume 1 (events only)
    run("UPDATE_SETTINGS", {"targetVolumes": 4, "chapterRange": {"min": 4, "max": 5},
                            "volumePins": {"Delivery Message Protocol V1.txt": 1},
                            "messFileSettings": {"Delivery Message Protocol V1.txt": {"eventsOnly": True}}})

    # Gate: bins cannot be built before their stage
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "BUILD_BINS")

    # 1. Sort (first page comes back truncated -> split and re-sorted, nothing lost)
    fake.truncate_next_sort = True
    st = run("INGEST")
    sort = st["messSortResult"]
    assert st["status"] == "INGESTION_REVIEW" and sort["complete"]
    assert {b["event"] for b in sort["arcBeats"]} >= {"Kaho finds the shoebox of letters", "The Winter Cup final"}
    assert any("(part 1/" in r["prompt"] for r in fake.calls("MESS Sorter")), "truncated page was split"
    assert sort["chapterMaterial"] and storage.get_sorted_material(NAME)["items"]["M-1"]["verbatim"], "draft copied verbatim"
    assert all(u["status"] == "RESOLVED" for u in sort["unclear"]), "flagged item auto-checked"
    assert (storage.mess_dir(NAME) / "_sort-log.md").exists()

    # 2-3. Bible
    st = run("APPROVE_INGESTION")
    st = run("GENERATE_BIBLE")
    assert st["soulRoster"]["souls"] and storage.read_core(NAME, "UNIVERSE-BIBLE.md")
    st = run("APPROVE_BIBLE")
    assert st["status"] == "STYLE_LAB"

    # 4. Style Lab: V1 is events-only and is the only prose -> no author DNA, 3 unique candidates
    st = run("STYLE_GENERATE")
    cands = st["styleLab"]["candidates"]
    assert len(cands) == 3 and all(c["sample"] for c in cands)
    assert not fake.calls("Voice DNA Extractor"), "events-only file never teaches the voice"
    st = run("STYLE_REFINE", {"id": cands[0]["id"], "feedback": "Less telling."})
    assert st["styleLab"]["candidates"][0]["name"] == "Revised Voice"
    st = run("STYLE_LOCK", {"id": cands[1]["id"]})
    assert st["status"] == "BIN_REVIEW" and "v2" in storage.read_core(NAME, "03-AUTHOR-VOICE-DNA.md")

    # 5. Bins: fixed count, pinned file whole in Volume 1, author's "Volume 2" kept, no balancing
    st = run("BUILD_BINS")
    vols = st["bins"]["volumes"]
    assert len(vols) == 4
    v1_items = {b["id"] for b in st["messSortResult"]["arcBeats"] if b["source"].startswith("Delivery Message Protocol V1")} | \
               {m["id"] for m in st["messSortResult"]["chapterMaterial"] if m["source"].startswith("Delivery Message Protocol V1")}
    assert v1_items <= set(vols[0]["itemIds"]), "finished volume stays whole in Volume 1 (roadmap tried to move it)"
    assert vols[0]["pinnedFrom"] == ["Delivery Message Protocol V1.txt"]
    motel = next(b["id"] for b in st["messSortResult"]["arcBeats"] if "motel" in b["event"])
    assert motel in vols[1]["itemIds"], "the author's own 'Volume 2' tag is kept"
    roadmap_prompt = fake.calls("Universe Architect")[-1]["prompt"]
    assert "EXACTLY 4 volumes" in roadmap_prompt and "FIXED -> Volume 1" in roadmap_prompt
    assert (storage.volume_dir(NAME, "SLOW_BURN_MODE", 4) / "BIN.md").exists(), "one folder per volume"
    # Creators move an item
    draft = next(m["id"] for m in st["messSortResult"]["chapterMaterial"] if "canal" in storage.get_sorted_material(NAME)["items"][m["id"]]["text"])
    st = run("MOVE_ITEM", {"id": draft, "toVolume": 4})
    assert draft in st["bins"]["volumes"][3]["itemIds"] and all(draft not in v["itemIds"] for v in st["bins"]["volumes"][:3])
    st = run("APPROVE_BINS")
    assert st["status"] == "GAP_REVIEW"

    # 6. Gap-fill: finished Volume 1 skipped; others proposed; creators decide
    st = run("GAP_RUN")
    gv = st["gapFill"]["volumes"]
    assert gv["1"]["status"] == "FINISHED"
    assert gv["2"]["status"] == "PROPOSED" and len(gv["2"]["miniEvents"]) == 2 and gv["2"]["questions"]
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "APPROVE_GAPS")
    run("GAP_SET_STATUS", {"volume": 2, "id": "E02-1", "status": "ACCEPTED"})
    run("GAP_SET_STATUS", {"volume": 2, "id": "E02-2", "status": "REJECTED"})
    run("GAP_EDIT", {"volume": 2, "id": "E02-1", "fields": {"event": "Kaho reads the second letter"}})
    run("GAP_ADD", {"volume": 2, "fields": {"title": "Creators' idea", "event": "Naseru waits at the gate"}})
    run("GAP_ANSWER", {"volume": 2, "id": "Q02-1", "answer": "She wants the truth."})
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "GAP_CONFIRM", {"volume": 3})   # proposals still open
    st = run("GAP_CONFIRM", {"volume": 2})
    run("GAP_CONFIRM", {"volume": 3, "acceptRemaining": True})
    st = run("GAP_CONFIRM", {"volume": 4, "acceptRemaining": True})
    accepted2 = [e["id"] for e in st["gapFill"]["volumes"]["2"]["miniEvents"] if e["status"] == "ACCEPTED"]
    assert accepted2 == ["E02-1", "E02-3"]
    assert "Kaho reads the second letter" in storage.read_volume_file(NAME, "SLOW_BURN_MODE", 2, "MINI-EVENTS.md")
    assert "Q02-1" not in (storage.mess_dir(NAME) / "_ask-me.md").read_text(encoding="utf-8"), "answered questions leave _ask-me"
    st = run("APPROVE_GAPS")
    assert st["status"] == "OUTLINE_REVIEW"

    # 7. Outline: confirmed mini-events reach the outline; chapter range enforced
    st = run("OUTLINE_RUN")
    plan = st["plan"]
    assert all(4 <= len(v["chapters"]) <= 5 for v in plan["volumes"])
    assert plan["volumes"][1]["miniEventIds"] == ["E02-1", "E02-3"]
    v2_prompt = next(r for r in fake.calls("Chapter Architect") if 'VOLUME 2:' in r["prompt"])
    assert "[E02-1]" in v2_prompt["system"] and "E02-2" not in v2_prompt["system"], "only confirmed mini-events are used"
    assert all("Z-999" not in c["sourceRefs"] for v in plan["volumes"] for c in v["chapters"]), "unknown refs dropped"
    st = run("APPROVE_PLAN")
    assert st["status"] == "FORESHADOWING_MODE"
    assert "E02-1" in storage.read_memory(NAME, "SLOW_BURN_MODE", 2, "SOURCE-MATERIAL.md")

    # 8. Payoff: the invalid thread triggers one correction
    st = run("PAYOFF_RUN")
    assert [p["id"] for p in st["payoffPlan"]["payoffs"]] == ["t1"] and fake.payoff_calls == 2
    st = run("APPROVE_PAYOFF")
    assert st["status"] == "WRITING_MODE"

    # 9. Writing from Volume 2 (Volume 1 not written here -> PASS-IN rebuilt from the plan)
    st = run("SET_START_VOLUME", {"volume": 2})
    st = run("WRITE_CHAPTER")
    assert st["draft"]["chapterNumber"] == 1 and st["draft"]["auditStatus"]["overall"] == "APPROVED"
    assert storage.read_memory(NAME, "SLOW_BURN_MODE", 2, "PASS-IN.md").startswith(writing.RECONSTRUCTED_PASS_IN_MARK)
    writer_prompt = fake.calls("Chapter Writer (LNF-03v2)")[-1]["prompt"]
    assert "A shoebox." in writer_prompt, "seed for Volume 2 Chapter 1 is planted"
    assert "It opens." not in writer_prompt, "payoff never shown to the writer"
    assert not storage.list_chapters(NAME, "SLOW_BURN_MODE", 2), "nothing saved before the creators save"
    st = run("SAVE_DRAFT", {"title": "Chapter 1: Edited Title", "content": "Edited prose."})
    assert storage.chapter_text(NAME, "SLOW_BURN_MODE", 2, 1) == "Edited prose."
    assert "Ledger for chapter 1" in storage.read_memory(NAME, "SLOW_BURN_MODE", 2, "CONTINUITY-LEDGER.md")
    carry = writing.carry_context(NAME, st, 2, 2)
    assert carry["previousChapterTail"] == "Edited prose." and "Ledger for chapter 1" in carry["ledgerTail"]
    run("WRITE_CHAPTER")
    st = run("ELEVATE_DRAFT", {"title": "Chapter 2: Written", "content": "x"})
    assert st["draft"]["content"] == "Elevated prose."
    run("SAVE_DRAFT")
    run("WRITE_CHAPTER")
    st = run("SAVE_DRAFT")
    assert st["status"] == "CHAPTER_REVIEW", "review gate after 3 chapters"
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "WRITE_CHAPTER")
    st = run("SUBTLETY_AUDIT")
    assert st["subtletyAudit"]["averageSubtlety"] == 8
    st = run("APPROVE_PASS")
    while st["status"] == "WRITING_MODE":
        run("WRITE_CHAPTER")
        st = run("SAVE_DRAFT")
    assert st["status"] == "HANDOFF_MODE"
    st = run("HANDOFF")
    assert st["currentVolume"] == 3 and st["status"] == "WRITING_MODE"
    assert storage.read_memory(NAME, "SLOW_BURN_MODE", 3, "PASS-IN.md").startswith("# PASS-OUT")
    assert storage.summary_path(NAME, "SLOW_BURN_MODE", 2).exists()

    # Reset: chapters and writing memory go to a backup; a real PASS-IN is kept
    st = run("RESET_VOLUME", {"volume": 3})
    assert storage.read_memory(NAME, "SLOW_BURN_MODE", 3, "PASS-IN.md"), "handed-off PASS-IN kept"
    st = run("RESET_VOLUME", {"volume": 2})
    assert not storage.list_chapters(NAME, "SLOW_BURN_MODE", 2)
    backup = storage.universe_dir(NAME) / "_backups" / st["lastReset"]["backup"]
    assert len(list((backup / "Chapters").iterdir())) == len(st["plan"]["volumes"][1]["chapters"])
    assert (backup / "Memory" / "PASS-IN.md").exists(), "reconstructed PASS-IN moved to the backup"

    # Usage is tracked per universe
    assert llm.read_usage(NAME)["calls"] == len(fake.requests) - requests_before


def test_navigation_rules(universe):
    st = storage.load_state(NAME)
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "SET_STATUS", {"status": "CHAPTER_REVIEW"})   # writing loop only via approval
    st = actions.dispatch(NAME, "SET_STATUS", {"status": "GAP_REVIEW"})       # back to an earlier stage
    assert st["status"] == "GAP_REVIEW" and st["resumeStatus"] == "WRITING_MODE"
    st = actions.dispatch(NAME, "SET_STATUS", {"status": "WRITING_MODE"})    # return to where the creators left
    assert st["status"] == "WRITING_MODE"


def test_settings_validation(universe):
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "UPDATE_SETTINGS", {"volumePins": {"Delivery Message Protocol V1.txt": 9}})
    with pytest.raises(ValueError):
        actions.dispatch(NAME, "UPDATE_SETTINGS", {"chapterRange": {"min": 20, "max": 15}})


def test_helpers():
    from lightprobe.ai.planning import volume_tag
    from lightprobe.ai.sorting import extract_span, paginate
    assert volume_tag("Volume 1, Eighteen") == 1 and volume_tag("Vol. 4 Arc") == 4 and volume_tag("the volume was loud") is None
    pages = paginate("para\n\n" * 10000, 24000)
    assert "".join(pages) == "para\n\n" * 10000 and all(len(p) <= 24000 for p in pages)
    page = "Before. The quick brown fox jumps over the lazy dog today. After it ends here now. Tail."
    assert extract_span(page, "The quick brown fox", "it ends here now.") == ("The quick brown fox jumps over the lazy dog today. After it ends here now.", True)
    assert writing._upsert_section("# L\n", "### Chapter ", 2, "two") == "# L\n\n### Chapter 2\ntwo\n"
    doc = writing._upsert_section("# L\n\n### Chapter 2\ntwo\n", "### Chapter ", 1, "one")
    assert doc.index("Chapter 1") < doc.index("Chapter 2")
    assert ingest.count_unclear({"unclear": [{"status": "OPEN"}, {"status": "RESOLVED"}]})["OPEN"] == 1
