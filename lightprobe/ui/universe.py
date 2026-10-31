"""The universe screen: header, stage stepper, live job progress, and the panel for the current stage."""

from __future__ import annotations

from nicegui import ui

from .. import actions, config, jobs, llm, storage
from ..styles import DENSITIES, MODES, POV_MODES, SENSORY, STAGES, STATE_ORDER, genre_presets
from . import stages, theme


class UniverseView:
    def __init__(self, name: str):
        self.name = name
        self.state = storage.load_state(name)
        self.auto_writing = False
        self.was_running = jobs.running(name)

    # ------------------------------------------------------------------ actions
    def reload(self) -> None:
        self.state = storage.load_state(self.name)

    def act(self, action: str, payload: dict | None = None) -> bool:
        """Runs an action; returns False (after telling the creators why) when it could not run."""
        try:
            result = actions.dispatch(self.name, action, payload or {})
        except (ValueError, RuntimeError, OSError, llm.MissingAPIKeyError) as err:
            ui.notify(str(err), type="negative", multi_line=True, timeout=8000)
            return False
        if isinstance(result, jobs.Job):
            self.was_running = True
            self.refresh_progress()
            self.refresh_header()
            return True
        self.state = result
        self.refresh_all()
        return True

    def confirm(self, title: str, message: str, on_yes, yes_label: str = "Continue") -> None:
        with ui.dialog() as dlg, ui.card().classes("w-[560px] p-6 gap-3"):
            ui.label(title).classes("text-lg font-bold text-white")
            ui.label(message).classes("text-sm text-slate-300 whitespace-pre-wrap")
            with ui.row().classes("justify-end w-full gap-2"):
                theme.button("Cancel", dlg.close, "ghost")

                def yes() -> None:
                    dlg.close()
                    on_yes()
                theme.button(yes_label, yes, "primary")
        dlg.open()

    def refresh_all(self) -> None:
        self.refresh_header()
        self.refresh_content()
        self.refresh_progress()

    # ------------------------------------------------------------------ polling
    def tick(self) -> None:
        job = jobs.current(self.name)
        running = bool(job and job.status == "running")
        if running:
            self.progress_message.set_text(job.message)
            self.progress_meta.set_text(f"{job.percentage}% • {theme.format_timer(job.elapsed)}")
            self.progress_bar.style(f"width: {max(5, job.percentage)}%")
            self.progress_logs.set_text("\n".join(f"[{t}] {m}" for t, m in job.logs[-5:-1]))
        if self.was_running and not running:
            self.was_running = False
            self.reload()
            self.refresh_all()
            if job and job.status == "done":
                ui.notify(job.message, type="positive", multi_line=True)
                jobs.clear(self.name)
        if not running and self.auto_writing:
            self.auto_step()

    def auto_step(self) -> None:
        st = self.state
        if st["status"] != "WRITING_MODE" or st["currentVolume"] in (st.get("chaptersBeforePlan") or []):
            self.auto_writing = False
            ui.notify("Auto-writing paused" + (" at the review gate." if st["status"] == "CHAPTER_REVIEW" else "."), type="info")
            self.refresh_content()
            return
        job = jobs.current(self.name)
        if job and job.status in ("error", "stopped"):
            self.auto_writing = False
            self.refresh_content()
            return
        if not self.act("SAVE_DRAFT" if st.get("draft") else "WRITE_CHAPTER"):
            self.auto_writing = False
            self.refresh_content()

    # ------------------------------------------------------------------ layout
    def build(self) -> None:
        theme.setup_page(f"{self.name} - Light Probe")
        if not self.state:
            with ui.column().classes("p-10"):
                ui.label("Universe not found.").classes("text-red-400 font-semibold")
                theme.button("Back to dashboard", lambda: ui.navigate.to("/"), "secondary")
            return
        with ui.column().classes("relative z-10 w-full gap-0 pb-24"):
            self.header_box = ui.column().classes("w-full gap-0 sticky top-0 z-30 border-b border-white/10 bg-[#0a0a0a]/90 backdrop-blur-2xl shadow-xl shadow-black/40")
            with ui.column().classes("w-full max-w-[1550px] mx-auto px-6 lg:px-10 py-8 gap-8"):
                self.progress_box = ui.column().classes("w-full gap-0")
                with self.progress_box:
                    self._build_progress()
                self.content_box = ui.column().classes("w-full gap-8")
        self.refresh_header()
        self.refresh_content()
        self.refresh_progress()
        ui.timer(0.5, self.tick)

    def _build_progress(self) -> None:
        self.progress_panel = ui.column().classes("w-full bg-[#0c0d16]/95 border border-purple-500/40 rounded-2xl p-4 gap-2")
        with self.progress_panel:
            with ui.row().classes("w-full items-center justify-between no-wrap gap-4"):
                self.progress_message = ui.label("").classes("text-xs font-mono text-purple-300 font-semibold")
                with ui.row().classes("items-center gap-3 no-wrap shrink-0"):
                    self.progress_meta = ui.label("").classes("text-xs font-mono text-white font-bold")
                    theme.button("Stop", lambda: (jobs.request_stop(self.name), ui.notify("Stopping after the current step...")), "danger", size="sm")
            with ui.element("div").classes("h-2 w-full bg-black/60 rounded-full overflow-hidden"):
                self.progress_bar = ui.element("div").classes("h-full bg-gradient-to-r from-purple-500 to-teal-400 transition-all duration-500").style("width: 5%")
            self.progress_logs = ui.label("").classes("lp-mono text-[10px] text-slate-400")
        self.error_panel = ui.row().classes("w-full bg-red-950/40 border border-red-500/40 rounded-2xl p-4 items-center justify-between gap-3")

    def refresh_progress(self) -> None:
        job = jobs.current(self.name)
        self.progress_panel.set_visibility(bool(job and job.status == "running"))
        self.error_panel.clear()
        show_error = bool(job and job.status in ("error", "stopped"))
        self.error_panel.set_visibility(show_error)
        if show_error:
            with self.error_panel:
                with ui.column().classes("gap-1"):
                    ui.label(f"{job.label} {'stopped' if job.status == 'stopped' else 'failed'}").classes("font-bold text-red-300 text-sm")
                    ui.label(job.error or job.message).classes("lp-mono text-xs text-red-200")
                    ui.label("Finished work is saved. Run the step again to continue from where it stopped.").classes("text-xs text-red-200/80")
                with ui.row().classes("gap-2"):
                    theme.button("Dismiss", lambda: (jobs.clear(self.name), self.refresh_progress()), "ghost", size="sm")
        if job and job.status == "running":
            self.tick()

    # ------------------------------------------------------------------ header
    def refresh_header(self) -> None:
        st = self.state
        self.header_box.clear()
        with self.header_box:
            with ui.row().classes("w-full max-w-[1550px] mx-auto px-6 lg:px-10 py-4 items-center justify-between gap-4"):
                with ui.row().classes("items-center gap-4 no-wrap"):
                    theme.button("", lambda: ui.navigate.to("/"), "secondary", icon="chevron_left", size="sm").tooltip("Back to dashboard")
                    with ui.column().classes("gap-1.5"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(st["name"]).classes("text-xl sm:text-2xl font-bold tracking-tight text-white")
                            theme.badge(MODES[st["mode"]], "orange" if st["mode"] == "RUSH_MODE" else "purple")
                            sc = st.get("styleConfig") or {}
                            theme.badge(f"{POV_MODES.get(sc.get('povMode'), '')} • {sc.get('genreLens', '').replace('_', ' ')}", "purple")
                            m = st.get("models") or {}
                            theme.badge(f"Plan {m.get('planning', '').replace('claude-', '')} • Write {m.get('writing', '').replace('claude-', '')}", "amber")
                        with ui.row().classes("items-center gap-2.5 text-xs text-slate-400"):
                            theme.badge(st["status"].replace("_", " "), "purple")
                            if st.get("totalVolumes") and st["status"] in STATE_ORDER[STATE_ORDER.index("FORESHADOWING_MODE"):]:
                                ui.label(f"Volume {st['currentVolume']} of {st['totalVolumes']} • {st['chaptersGeneratedInCurrentVolume']} / {st['chaptersPerVolume']} chapters written")
                            usage = llm.read_usage(self.name)
                            if usage:
                                ui.label(f"API use: {usage['calls']} calls • est. ${usage['estimatedUSD']:.2f}").tooltip(
                                    f"Input {usage['input']:,} • output {usage['output']:,} • cache read {usage['cacheRead']:,} tokens (estimate)")
                with ui.row().classes("items-center gap-2.5"):
                    theme.button("Settings", self.settings_dialog, "purple", icon="tune", size="sm")
                    if st.get("bins"):
                        theme.button("Volume Bins", self.bins_dialog, "purple", icon="layers", size="sm")
                    theme.button("Core Knowledge", self.core_dialog, "secondary", icon="menu_book", size="sm")
                    if st.get("totalChaptersWritten"):
                        theme.button("Export Manuscript", lambda: stages.export_manuscript(self), "secondary", icon="download", size="sm")
                    if st.get("parallelTrack"):
                        theme.button(f"Open {st['parallelTrack']}", lambda: ui.navigate.to(f"/universe/{st['parallelTrack']}"), "secondary", icon="call_split", size="sm")
                    elif actions.allowed("SPAWN_PARALLEL_TRACK", st):
                        other = "Rush" if st["mode"] == "SLOW_BURN_MODE" else "Slow Burn"
                        theme.button(f"Spawn Parallel {other}", lambda: self.confirm(
                            f"Create a parallel {other} track?", f"A new universe in {other} mode starts from this universe's sorted notes, Bible, roster and "
                            "locked style (no re-sorting). It gets its own volume bins, outlines and chapters.", lambda: self.act("SPAWN_PARALLEL_TRACK"), "Create"),
                            "secondary", icon="call_split", size="sm")
                    theme.button("Open Folder", self.open_folder, "secondary", icon="folder_open", size="sm")
            # Stage stepper
            current = STATE_ORDER.index(st["status"])
            with ui.row().classes("w-full max-w-[1550px] mx-auto px-6 lg:px-10 py-2.5 border-t border-white/5 gap-1 no-wrap overflow-x-auto"):
                for idx, (key, label) in enumerate(STAGES):
                    active, done = key == st["status"], idx < current
                    cls = ("text-white font-bold bg-purple-600/30 border border-purple-500/40" if active else
                           "text-slate-300 hover:text-white hover:bg-white/5" if done else "text-slate-500")
                    with ui.row().classes(f"items-center gap-2 py-1 px-2.5 rounded-lg cursor-pointer no-wrap whitespace-nowrap text-xs {cls}") \
                            .on("click", lambda _, k=key: self.act("SET_STATUS", {"status": k}) if k != self.state["status"] else None):
                        dot = ("bg-gradient-to-r from-purple-600 to-blue-600 text-white" if active else "bg-emerald-600 text-white" if done else "bg-white/10 text-slate-400")
                        ui.label("✓" if done else str(idx + 1)).classes(f"w-4 h-4 rounded-full flex items-center justify-center text-[10px] {dot}")
                        ui.label(label)

    def refresh_content(self) -> None:
        self.content_box.clear()
        with self.content_box:
            stages.render(self)

    def open_folder(self) -> None:
        import os
        import subprocess
        import sys
        path = str(storage.universe_dir(self.name))
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 - opens the universe folder in Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------------ dialogs
    def settings_dialog(self) -> None:
        st = self.state
        files = storage.list_mess_names(self.name)
        with ui.dialog() as dlg, ui.card().classes("w-[860px] max-w-[95vw] p-6 gap-4"):
            ui.label("Universe Settings").classes("text-xl font-bold text-white")
            ui.label("Volumes and chapters").classes("text-xs font-bold text-slate-300 uppercase tracking-wider")
            with ui.grid(columns=3).classes("w-full gap-3"):
                volumes = theme.number_input("Number of volumes (empty = the engine decides)", value=st.get("targetVolumes"), min=1, precision=0)
                cmin = theme.number_input("Chapters per volume - minimum", value=(st.get("chapterRange") or {}).get("min"), min=1, precision=0)
                cmax = theme.number_input("Chapters per volume - maximum", value=(st.get("chapterRange") or {}).get("max"), min=1, precision=0)
            ui.label("MESS files").classes("text-xs font-bold text-slate-300 uppercase tracking-wider mt-2")
            ui.label('"Finished volume": this file IS that volume (e.g. V1 = Volume 1). Its material stays whole in that volume and is never split. '
                     '"Events only": use the file\'s events but never its writing style.').classes("text-xs text-slate-400")
            pins, events_only = {}, {}
            with ui.column().classes("w-full gap-1 max-h-72 overflow-y-auto"):
                if not files:
                    ui.label("No MESS files yet.").classes("text-xs text-slate-500")
                for f in files:
                    with ui.row().classes("w-full items-center gap-3 no-wrap bg-black/20 rounded-lg px-3 py-1"):
                        ui.label(f).classes("text-xs text-slate-200 flex-1 break-all")
                        pins[f] = ui.number("Finished volume", value=(st.get("volumePins") or {}).get(f), min=1, precision=0) \
                            .props("dark outlined dense").classes("w-40")
                        events_only[f] = ui.checkbox("Events only", value=bool(((st.get("messFileSettings") or {}).get(f) or {}).get("eventsOnly"))).classes("text-xs")
            ui.label("Author style & models").classes("text-xs font-bold text-slate-300 uppercase tracking-wider mt-2")
            sc = st.get("styleConfig") or {}
            with ui.grid(columns=3).classes("w-full gap-3"):
                pov = theme.select(POV_MODES, value=sc.get("povMode"), label="Point of view")
                lens = theme.select({g["id"]: g["label"] for g in genre_presets()}, value=sc.get("genreLens"), label="Genre lens")
                density = theme.select(DENSITIES, value=sc.get("proseDensity"), label="Prose density")
                sensory = theme.select(SENSORY, value=sc.get("sensoryPriority"), label="Sensory priority")
                choices = config.SUPPORTED_MODELS + config.LOCAL_MODELS
                planning = theme.select(choices, value=(st.get("models") or {}).get("planning"), label="Planning model")
                writing = theme.select(choices, value=(st.get("models") or {}).get("writing"), label="Writing model")
            pacing = ui.checkbox("Pacing fluctuation (longer deep-dive chapters, short kinetic pivots)", value=bool(sc.get("pacingFluctuation", True)))
            notes = theme.text_area("Custom style notes", sc.get("customStyleNotes") or "", rows=3)
            if st.get("bins"):
                ui.label("Changing the volume count or finished volumes takes effect when you rebuild the Volume Bins.").classes("text-xs text-amber-300")
            with ui.row().classes("justify-end w-full gap-2"):
                theme.button("Cancel", dlg.close, "ghost")

                def save() -> None:
                    to_int = lambda v: int(v) if v else None  # noqa: E731
                    payload = {
                        "targetVolumes": to_int(volumes.value),
                        "chapterRange": {"min": to_int(cmin.value), "max": to_int(cmax.value)},
                        "volumePins": {f: to_int(w.value) for f, w in pins.items() if w.value},
                        "messFileSettings": {**(st.get("messFileSettings") or {}), **{f: {"eventsOnly": bool(w.value)} for f, w in events_only.items()}},
                        "styleConfig": {"povMode": pov.value, "genreLens": lens.value, "proseDensity": density.value, "sensoryPriority": sensory.value,
                                        "pacingFluctuation": bool(pacing.value), "customStyleNotes": notes.value or ""},
                        "models": {"planning": planning.value, "writing": writing.value},
                    }
                    try:
                        self.state = actions.dispatch(self.name, "UPDATE_SETTINGS", payload)
                    except (ValueError, RuntimeError) as err:
                        ui.notify(str(err), type="negative", multi_line=True)
                        return
                    dlg.close()
                    ui.notify("Settings saved.", type="positive")
                    self.refresh_all()
                theme.button("Save settings", save, "primary")
        dlg.open()

    def core_dialog(self) -> None:
        files = storage.list_core_files(self.name)
        with ui.dialog() as dlg, ui.card().classes("w-[1000px] max-w-[95vw] p-6 gap-3"):
            ui.label("System Core Knowledge").classes("text-xl font-bold text-white")
            ui.label("The client's cards and the engine's generated files for this universe (SHARED_CORE_KNOWLEDGE). "
                     "The engine never overwrites the client's cards; edits you save here are yours.").classes("text-xs text-slate-400")
            with ui.row().classes("w-full gap-4 no-wrap items-start"):
                with ui.column().classes("w-72 shrink-0 gap-1 max-h-[60vh] overflow-y-auto"):
                    for f in files:
                        theme.button(f, lambda _, f=f: show(f), "ghost", size="sm").classes("w-full justify-start")
                editor_box = ui.column().classes("flex-1 gap-2")

            def show(f: str) -> None:
                editor_box.clear()
                with editor_box:
                    generated = f in storage.GENERATED_CORE_FILES
                    with ui.row().classes("items-center gap-2"):
                        ui.label(f).classes("font-bold text-white")
                        theme.badge("generated by the engine" if generated else "client card", "teal" if generated else "purple")
                    area = ui.textarea(value=storage.read_core(self.name, f)).props("dark outlined rows=22").classes("w-full lp-mono text-xs")

                    def save() -> None:
                        storage.save_card_edit(self.name, f, area.value)
                        ui.notify(f"{f} saved.", type="positive")
                    theme.button("Save changes", save, "primary", size="sm")
            if files:
                show(files[0])
            with ui.row().classes("justify-end w-full"):
                theme.button("Close", dlg.close, "ghost")
        dlg.open()

    def bins_dialog(self) -> None:
        with ui.dialog() as dlg, ui.card().classes("w-[1100px] max-w-[95vw] p-6 gap-3"):
            ui.label("Volume Bins").classes("text-xl font-bold text-white")
            with ui.column().classes("w-full max-h-[70vh] overflow-y-auto gap-3"):
                stages.bins_overview(self, editable=False)
            with ui.row().classes("justify-end w-full"):
                theme.button("Close", dlg.close, "ghost")
        dlg.open()


def build(name: str) -> None:
    UniverseView(name).build()
