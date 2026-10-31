"""Clicks through the interface with NiceGUI's simulated user (no browser): every stage's main buttons,
background jobs answered by the fake Anthropic server, and the screens they lead to."""

import asyncio

from nicegui.testing import User
from nicegui.testing.user_interaction import UserInteraction

from lightprobe import actions, jobs, storage
from test_pipeline import NOTES, V1

NAME = "UI_Test"


async def click(user: User, text: str, index: int = 0) -> None:
    """Clicks one of several elements with the same text (user.find(...).click() would click them all)."""
    elements = sorted(user.find(text).elements, key=lambda e: e.id)
    assert elements, f"no element '{text}'"
    UserInteraction(user, {elements[index]}, text).click()


async def wait_job(user: User, expect: str, timeout: float = 20) -> None:
    await asyncio.sleep(0.3)
    for _ in range(int(timeout / 0.2)):
        job = jobs.current(NAME)
        if not job or job.status != "running":
            break
        await asyncio.sleep(0.2)
    job = jobs.current(NAME)
    assert not job or job.status in ("done", "running"), f"job failed: {job.error}"
    await asyncio.sleep(1.2)   # let the page's 0.5 s timer pick up the result and redraw
    await user.should_see(expect, retries=30)


async def test_click_through(user: User, fake) -> None:
    await user.open("/")
    await user.should_see("Your Universes")
    user.find("Create New Universe").click()
    await user.should_see("Universe name")
    user.find("Universe name").type(NAME)
    user.find("Create Universe").click()
    await user.should_see("Ingest the author's notes", retries=20)

    storage.add_mess_file(NAME, "Delivery Message Protocol V1.txt", V1.encode())
    storage.add_mess_file(NAME, "Notes.txt", NOTES.encode())
    actions.dispatch(NAME, "UPDATE_SETTINGS", {"targetVolumes": 3, "chapterRange": {"min": 4, "max": 4},
                                               "volumePins": {"Delivery Message Protocol V1.txt": 1}})
    await user.open(f"/universe/{NAME}")
    await user.should_see("Notes.txt")
    user.find("Settings").click()
    await user.should_see("Universe Settings")
    user.find("Save settings").click()
    await user.should_see("Settings saved.")

    user.find("Start MESS Sort").click()
    await wait_job(user, "What the sorter found")
    user.find("Approve Intake → Universe Bible").click()
    await user.should_see("Build Universe Bible")
    user.find("Build Universe Bible").click()
    await wait_job(user, "Soul Roster (")
    user.find("Approve Bible → Style Lab").click()
    await user.should_see("Find the author style")
    user.find("Generate style candidates").click()
    await wait_job(user, "Test passage")
    await click(user, "Lock this style → Volume Bins")
    await user.should_see("Lock this style?")
    user.find("Lock style").click()
    await user.should_see("Place every item in its volume", retries=20)

    user.find("Build volume bins").click()
    await wait_job(user, "Approve Bins → Gap-Fill")
    await user.should_see("FINISHED (Delivery Message Protocol V1.txt)")
    user.find("Approve Bins → Gap-Fill").click()
    await user.should_see("Fill what is missing, with your confirmation")
    user.find("Run gap-fill for all volumes").click()
    await wait_job(user, "needs your review")
    for n in (2, 3):
        user.find(f"Accept the 2 remaining & confirm Volume {n}").click()
        await asyncio.sleep(0.2)
    await user.should_see("Approve Gap-Fill → Volume Outline", retries=20)
    user.find("Approve Gap-Fill → Volume Outline").click()
    await user.should_see("Generate chapter outlines")
    user.find("Generate chapter outlines").click()
    await wait_job(user, "Approve Plan → Payoff Planner")
    user.find("Approve Plan → Payoff Planner").click()
    await user.should_see("Generate payoff plan")
    user.find("Generate payoff plan").click()
    await wait_job(user, "Approve Payoff Plan → Writing")
    user.find("Approve Payoff Plan → Writing").click()
    await user.should_see("Write Chapter 1")
    user.find("Write Chapter 1").click()
    await wait_job(user, "Approve & Save Chapter 1")
    user.find("Approve & Save Chapter 1").click()
    await user.should_see("Write Chapter 2", retries=20)
    await user.should_see("Carried into Chapter 2")
    assert storage.chapter_text(NAME, "SLOW_BURN_MODE", 1, 1)
