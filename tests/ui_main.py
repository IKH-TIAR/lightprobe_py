"""Main file for NiceGUI's simulated-user tests (no browser, no server)."""

from nicegui import ui

from lightprobe.app import register_pages

register_pages()
ui.run(dark=True, storage_secret="test")
