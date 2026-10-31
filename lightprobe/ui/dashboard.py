"""Dashboard: the universes on this computer, creating one, and app settings."""

from __future__ import annotations

from nicegui import ui

from .. import config, llm, storage
from ..styles import DENSITIES, MODES, POV_MODES, STAGE_LABEL, genre_presets
from . import theme


def api_key_dialog(on_saved=None) -> ui.dialog:
    with ui.dialog() as dlg, ui.card().classes("w-[560px] p-6 gap-4"):
        ui.label("Settings").classes("text-xl font-bold text-white")
        ui.label("Choose Claude or a local Ollama server. The API key is only needed for Claude; Ollama "
                 "uses http://127.0.0.1:11434 on this computer.").classes("text-xs text-slate-400")
        provider = theme.select(config.PROVIDERS, value=config.provider(), label="AI provider")
        current = config.api_key()
        ui.label(f"Current Claude key: {'set (ends ' + current[-4:] + ')' if current else 'not set'}").classes("text-xs text-slate-300")
        key = theme.text_input("Anthropic API key", password_toggle_button=True)
        ollama = config.ollama_settings()
        ollama_url = theme.text_input("Ollama URL", ollama["url"])
        ollama_model = theme.text_input("Ollama model", ollama["model"])
        with ui.row().classes("w-full gap-3"):
            ollama_context = theme.number_input("Ollama context tokens", value=ollama["context"], min=4096, precision=0)
            ollama_output = theme.number_input("Ollama output tokens", value=ollama["output"], min=256, precision=0)
        with ui.row().classes("justify-end w-full gap-2"):
            theme.button("Cancel", dlg.close, "ghost")

            def save() -> None:
                if provider.value == "anthropic" and not (key.value or "").strip() and not config.api_key():
                    ui.notify("Paste the Anthropic key first.", type="warning")
                    return
                if (key.value or "").strip():
                    config.set_api_key(key.value)
                try:
                    config.save_provider_settings(provider.value, ollama_url.value, ollama_model.value,
                                                  int(ollama_context.value), int(ollama_output.value))
                except ValueError as err:
                    ui.notify(str(err), type="negative")
                    return
                ui.notify("AI settings saved on this computer.", type="positive")
                dlg.close()
                if on_saved:
                    on_saved()
            theme.button("Save settings", save, "primary")
    return dlg


def create_dialog() -> ui.dialog:
    with ui.dialog() as dlg, ui.card().classes("w-[720px] p-6 gap-4"):
        ui.label("Create New Universe").classes("text-2xl font-black text-white")
        ui.label("A universe is one series: its MESS notes, its volume bins and its chapters live in one folder on this computer.").classes("text-xs text-slate-400")
        name = theme.text_input("Universe name", placeholder="e.g. Kaho Delivery Message Protocol")
        mode = theme.select(MODES, value="SLOW_BURN_MODE", label="Mode")
        ui.label("Author style (you will test and lock the voice in the Style Lab)").classes("text-xs font-bold text-slate-300 uppercase tracking-wider mt-2")
        with ui.grid(columns=3).classes("w-full gap-3"):
            pov = theme.select(POV_MODES, value="THIRD_LIMITED", label="Point of view")
            lens = theme.select({g["id"]: g["label"] for g in genre_presets()}, value="DYNAMIC_PROBE_DETECT", label="Genre lens")
            density = theme.select(DENSITIES, value="EXTENSIVE_NOVEL", label="Prose density")
        ui.label("Models (choose Ollama in Settings to use local models)").classes("text-xs font-bold text-slate-300 uppercase tracking-wider mt-2")
        with ui.grid(columns=2).classes("w-full gap-3"):
            choices = config.SUPPORTED_MODELS + config.LOCAL_MODELS
            planning = theme.select(choices, value=config.DEFAULT_MODEL, label="Planning")
            writing = theme.select(choices, value=config.DEFAULT_MODEL, label="Writing")
        with ui.row().classes("justify-end w-full gap-2 mt-2"):
            theme.button("Cancel", dlg.close, "ghost")

            def create() -> None:
                try:
                    st = storage.create_universe(name.value or "", mode.value, {"povMode": pov.value, "genreLens": lens.value, "proseDensity": density.value},
                                                 {"planning": planning.value, "writing": writing.value})
                except ValueError as err:
                    ui.notify(str(err), type="negative")
                    return
                dlg.close()
                ui.navigate.to(f"/universe/{st['name']}")
            theme.button("Create Universe", create, "primary", icon="auto_awesome")
    return dlg


def delete_dialog(name: str, on_done) -> ui.dialog:
    with ui.dialog() as dlg, ui.card().classes("w-[520px] p-6 gap-3"):
        ui.label("Delete Universe").classes("text-2xl font-extrabold text-white")
        ui.label(f'This permanently deletes "{name}" from this computer: its MESS notes, bins, chapters and backups. '
                 "Type the universe name to confirm.").classes("text-sm text-slate-300")
        confirm = theme.text_input("Universe name")
        with ui.row().classes("justify-end w-full gap-2"):
            theme.button("Cancel", dlg.close, "ghost")

            def delete() -> None:
                if confirm.value != name:
                    ui.notify("The name does not match.", type="warning")
                    return
                storage.delete_universe(name)
                dlg.close()
                ui.notify(f'"{name}" deleted.')
                on_done()
            theme.button("Delete permanently", delete, "danger")
    return dlg


def build() -> None:
    theme.setup_page("Light Probe")
    with ui.row().classes("relative z-10 w-full min-h-screen items-stretch gap-0 no-wrap"):
        with ui.column().classes("w-64 shrink-0 border-r border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl p-6 gap-6"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome").classes("text-purple-400 text-2xl")
                ui.label("Light Probe").classes("text-xl font-extrabold tracking-tight text-white")
            ui.label("Local novel engine").classes("text-xs text-slate-500 -mt-4")
            ui.separator().classes("bg-white/10")
            key_set = bool(config.api_key())
            with ui.row().classes("items-center gap-2"):
                ui.element("span").classes(f"w-2 h-2 rounded-full {'bg-emerald-400' if key_set or config.provider() == 'ollama' else 'bg-amber-400 animate-pulse'}")
                ui.label("Ollama selected" if config.provider() == "ollama" else ("API key set" if key_set else "API key not set")).classes("text-xs text-slate-300")
            theme.button("Settings", lambda: api_key_dialog(lambda: ui.navigate.reload()).open(), "secondary", icon="settings", size="sm")
            ui.label(f"Data folder:\n{config.DATA_DIR}").classes("text-[10px] text-slate-500 lp-mono break-all")
        with ui.column().classes("flex-1 p-10 gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-1"):
                    ui.label("Your Universes").classes("text-2xl font-bold text-white")
                    ui.label("Each universe is one series. Click one to continue where you left off.").classes("text-sm text-slate-400")
                theme.button("Create New Universe", lambda: create_dialog().open(), "primary", icon="add", size="lg")
            grid = ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 w-full")

            def render() -> None:
                grid.clear()
                universes = storage.list_universes()
                with grid:
                    if not universes:
                        with ui.column().classes(f"{theme.PANEL} items-center text-center col-span-full py-16 gap-3"):
                            ui.icon("travel_explore").classes("text-5xl text-purple-400")
                            ui.label("The Void is Empty").classes("text-2xl font-bold text-white")
                            ui.label("Create your first universe, then drop the author's notes into its MESS folder.").classes("text-slate-400")
                    for st in universes:
                        usage = llm.read_usage(st["name"])
                        with ui.column().classes(f"{theme.PANEL} gap-3 hover:border-purple-500/40 transition-all"):
                            with ui.column().classes("w-full gap-3 cursor-pointer").on("click", lambda _, n=st["name"]: ui.navigate.to(f"/universe/{n}")):
                                with ui.row().classes("w-full items-start justify-between no-wrap"):
                                    ui.label(st["name"].replace("_", " ")).classes("text-lg font-bold text-white break-all")
                                    theme.badge(MODES.get(st["mode"], st["mode"]), "orange" if st["mode"] == "RUSH_MODE" else "purple")
                                theme.badge(STAGE_LABEL.get(st["status"], st["status"]), "emerald")
                                with ui.row().classes("gap-6"):
                                    theme.stat("volumes", st.get("totalVolumes", 0), "layers")
                                    theme.stat("chapters", st.get("totalChaptersWritten", 0), "auto_stories")
                                    theme.stat("API calls", usage.get("calls", 0), "bolt")
                            theme.button("Delete", lambda n=st["name"]: delete_dialog(n, render).open(),
                                         "danger", icon="delete", size="sm")
            render()
    return None
