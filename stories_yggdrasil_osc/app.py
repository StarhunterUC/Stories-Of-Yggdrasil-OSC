from __future__ import annotations

import os
import queue
import subprocess
import sys
import time
import uuid
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from . import OSC_API_MINIMUM, OSC_API_RECOMMENDED, __version__
from .combat import CombatState
from .config import get_app_data_dir, get_log_path, load_config, load_runtime_state, save_config, save_runtime_state
from .controller import BridgeController
from .models import EventResult
from .osc_service import OSCEvent, OSCService
from .sam_client import SamClient, SamEvent
from .telemetry import coerce_percent, diablos_warning_label, percent_to_avatar_float
from .update_manager import UpdateEvent, UpdateManager

THEME = {
    "bg": "#090a0d",
    "sidebar": "#0e1014",
    "panel": "#12151a",
    "panel2": "#181c22",
    "panel3": "#20262d",
    "border": "#2e3740",
    "gold": "#d6b45b",
    "gold2": "#f1d98e",
    "text": "#edf0f2",
    "muted": "#98a1aa",
    "green": "#39b96d",
    "blue": "#4c87c7",
    "red": "#c84e55",
    "yellow": "#d6a947",
}


class StoriesOSCApp:
    POLL_MS = 45

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Stories Of Yggdrasil OSC {__version__}")
        self.root.geometry("1220x760")
        self.root.minsize(1040, 680)
        self.root.configure(bg=THEME["bg"])

        self.install_dir = Path(__file__).resolve().parents[1]
        self._logo_image: ImageTk.PhotoImage | None = None
        self._set_window_icon()

        self.config = load_config()
        profile = self.config["profile"]
        runtime = load_runtime_state(int(profile.get("starting_hp", profile["maximum_hp"])))
        self.state = CombatState(
            maximum_hp=int(profile["maximum_hp"]),
            current_hp=int(runtime.get("current_hp", profile.get("starting_hp", profile["maximum_hp"]))),
            damage_values=self.config["combat"]["damage"],
            invulnerability_seconds=float(self.config["combat"]["global_invulnerability_seconds"]),
            critical_hp_percent=float(profile.get("critical_hp_percent", 0.15)),
            status_rules=self.config["statuses"],
            clear_statuses_when_disabled=bool(self.config["combat"].get("clear_statuses_when_disabled", True)),
            combat_enabled=bool(runtime.get("combat_enabled", False)),
        )

        self.osc_events: queue.Queue[OSCEvent] = queue.Queue()
        self.sam_events: queue.Queue[SamEvent] = queue.Queue()
        self.update_events: queue.Queue[UpdateEvent] = queue.Queue()
        self.osc = self._make_osc_service()
        self.sam_client = SamClient(self.sam_events, self.config.get("sam", {}))
        self.update_manager = UpdateManager(self.update_events, __version__)
        self.controller = BridgeController(
            config=self.config,
            state=self.state,
            send_parameter=self._send_parameter,
            pulse_parameter=self._pulse_parameter,
            event_sink=self._on_result,
        )

        self.closing = False
        self.output_cache: dict[str, Any] = {}
        self.last_avatar_id = "—"
        self.last_event = "Program started."
        self.event_rows: list[dict[str, str]] = []
        self.remote_character: dict[str, Any] = {}
        self.remote_state: dict[str, Any] = {}
        self.remote_mp = 0
        self.remote_max_mp = 0
        self.recovery_options: list[dict[str, Any]] = []
        self.recovery_by_row: dict[str, dict[str, Any]] = {}
        self.latest_release: dict[str, Any] = {}
        self.update_check_automatic = False
        self.update_progress_visible = False
        self.npc_roster: list[dict[str, Any]] = []
        self.npc_by_name: dict[str, dict[str, Any]] = {}
        self.npc_attacker_roster: list[dict[str, Any]] = []
        self.npc_attackers_by_player: dict[str, list[dict[str, Any]]] = {}
        self.npc_attacker_player_ids: dict[str, str] = {}
        self.link_info: dict[str, Any] = {}
        self.sam_api_version = ""
        self.npc_last_hit_diagnostics: dict[str, Any] = {}
        self.enemy_mode_pending_value: bool | None = None
        self.enemy_mode_pending_until = 0.0

        self.sam_sync_due_at = 0.0
        self.sam_sync_inflight = False
        self.sam_local_dirty = False
        self.sam_client_seq = 0
        self.sam_client_session = uuid.uuid4().hex
        self.sam_last_event_name = "startup"
        self.sam_last_event_vrc_trigger = False
        self.sam_last_revision = -1
        self.sam_last_dm_gate_active = False
        self.sam_last_rejection_at = 0.0
        self.sam_status_handoff_signature = ""
        self.sam_seen_status_event_ids: set[str] = set()
        self.sam_seen_status_event_order: list[str] = []

        self._last_saved_runtime_state = {
            "current_hp": int(runtime.get("current_hp", self.state.current_hp)),
            "combat_enabled": bool(runtime.get("combat_enabled", self.state.combat_enabled)),
        }
        self._last_ui_signature: tuple[Any, ...] | None = None

        self._setup_styles()
        self._build_ui()
        self.sam_client.start()
        self._append_activity("SYSTEM", f"Stories Of Yggdrasil OSC v{__version__} started.")
        self._refresh_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(self.POLL_MS, self._poll)
        self.root.after(500, self._refresh_loop)
        self.root.after(1000, self._autosave_tick)
        if self.config["osc"].get("auto_start_listener", True):
            self.root.after(120, self.start_listener)
        if str(self.config.get("sam", {}).get("token") or "").strip():
            self.root.after(900, self.refresh_npc_roster)
        if self.config.get("updates", {}).get("check_on_start", True):
            self.root.after(1600, lambda: self.check_for_updates(automatic=True))
        update_hours = max(1.0, float(self.config.get("updates", {}).get("check_interval_hours", 6.0) or 6.0))
        self.root.after(int(update_hours * 60 * 60 * 1000), self._automatic_update_tick)

    # ------------------------------------------------------------------
    # Window / style
    # ------------------------------------------------------------------
    def _asset_path(self, name: str) -> Path:
        return self.install_dir / "assets" / name

    def _set_window_icon(self) -> None:
        try:
            ico = self._asset_path("stories_osc_icon.ico")
            if os.name == "nt" and ico.exists():
                self.root.iconbitmap(default=str(ico))
            png = self._asset_path("stories_osc_icon.png")
            if png.exists():
                image = Image.open(png).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                self._logo_image = ImageTk.PhotoImage(image)
                self.root.iconphoto(True, self._logo_image)
        except Exception:
            pass

    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Sidebar.TFrame", background=THEME["sidebar"])
        style.configure("Panel.TFrame", background=THEME["panel"])
        style.configure("Card.TFrame", background=THEME["panel2"], relief="solid", borderwidth=1)
        style.configure("CardInner.TFrame", background=THEME["panel2"], relief="flat", borderwidth=0)
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"], font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=THEME["panel"], foreground=THEME["text"])
        style.configure("Card.TLabel", background=THEME["panel2"], foreground=THEME["text"])
        style.configure("Muted.TLabel", background=THEME["bg"], foreground=THEME["muted"])
        style.configure("Muted.Panel.TLabel", background=THEME["panel"], foreground=THEME["muted"])
        style.configure("Muted.Card.TLabel", background=THEME["panel2"], foreground=THEME["muted"])
        style.configure("Brand.TLabel", background=THEME["panel"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 18))
        style.configure("Version.TLabel", background=THEME["panel"], foreground=THEME["muted"], font=("Segoe UI", 9))
        style.configure("PageTitle.TLabel", background=THEME["bg"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 16))
        style.configure("CardTitle.TLabel", background=THEME["panel2"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 11))
        style.configure("Character.TLabel", background=THEME["panel2"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 18))
        style.configure("BigValue.TLabel", background=THEME["panel2"], foreground=THEME["text"], font=("Segoe UI Semibold", 13))
        style.configure("StatusOff.TLabel", background=THEME["panel3"], foreground=THEME["muted"], padding=(10, 5), font=("Segoe UI Semibold", 9))
        style.configure("StatusOn.TLabel", background="#183827", foreground="#75e69f", padding=(10, 5), font=("Segoe UI Semibold", 9))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI Semibold", 9), background=THEME["panel3"], foreground=THEME["text"], bordercolor=THEME["border"])
        style.map("TButton", background=[("active", "#2a333c"), ("pressed", "#333e49")])
        style.configure("Gold.TButton", background=THEME["gold"], foreground="#15120b")
        style.map("Gold.TButton", background=[("active", THEME["gold2"])])
        style.configure("Green.TButton", background="#1e7142", foreground=THEME["text"])
        style.map("Green.TButton", background=[("active", "#279055")])
        style.configure("Danger.TButton", background="#6a252b", foreground=THEME["text"])
        style.map("Danger.TButton", background=[("active", "#8d323a")])
        style.configure("Nav.TButton", background=THEME["sidebar"], foreground=THEME["muted"], borderwidth=0, padding=(10, 13), font=("Segoe UI Semibold", 10))
        style.map("Nav.TButton", background=[("active", THEME["panel2"])], foreground=[("active", THEME["gold2"])])
        style.configure("HP.Horizontal.TProgressbar", troughcolor="#28312c", background=THEME["green"], lightcolor=THEME["green"], darkcolor=THEME["green"], bordercolor=THEME["border"])
        style.configure("MP.Horizontal.TProgressbar", troughcolor="#242c36", background=THEME["blue"], lightcolor=THEME["blue"], darkcolor=THEME["blue"], bordercolor=THEME["border"])
        style.configure("Diablos.Horizontal.TProgressbar", troughcolor="#2d1117", background="#b11f37", lightcolor="#b11f37", darkcolor="#7d1025", bordercolor=THEME["border"])
        style.configure("DiablosWarn.Horizontal.TProgressbar", troughcolor="#331017", background="#e05a37", lightcolor="#e05a37", darkcolor="#a53422", bordercolor=THEME["border"])
        style.configure("DiablosCritical.Horizontal.TProgressbar", troughcolor="#35080f", background="#ff153d", lightcolor="#ff153d", darkcolor="#b00025", bordercolor=THEME["border"])
        style.configure("Treeview", background=THEME["panel2"], fieldbackground=THEME["panel2"], foreground=THEME["text"], rowheight=28, bordercolor=THEME["border"])
        style.configure("Treeview.Heading", background=THEME["panel3"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#374654")])
        style.configure("TCheckbutton", background=THEME["panel2"], foreground=THEME["text"])
        style.map("TCheckbutton", background=[("active", THEME["panel2"])])
        style.configure("TCombobox", fieldbackground=THEME["panel3"], background=THEME["panel3"], foreground=THEME["text"])

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.shell = ttk.Frame(self.root)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.sidebar = ttk.Frame(self.shell, style="Sidebar.TFrame", width=150)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        self.content = ttk.Frame(self.shell)
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        logo_wrap = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        logo_wrap.pack(fill=tk.X, pady=(20, 20))
        try:
            png = self._asset_path("stories_osc_icon.png")
            image = Image.open(png).convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
            self.sidebar_logo = ImageTk.PhotoImage(image)
            ttk.Label(logo_wrap, image=self.sidebar_logo, background=THEME["sidebar"]).pack()
        except Exception:
            ttk.Label(logo_wrap, text="Y", background=THEME["sidebar"], foreground=THEME["gold2"], font=("Georgia", 32, "bold")).pack()

        self.nav_buttons: dict[str, ttk.Button] = {}
        for key, label in (
            ("dashboard", "◈  Dashboard"),
            ("actions", "✦  Actions"),
            ("npc", "⚔  NPC Mode"),
            ("connection", "↔  Connection"),
            ("diagnostics", "⌁  Diagnostics"),
            ("settings", "⚙  Settings"),
        ):
            button = ttk.Button(self.sidebar, text=label, style="Nav.TButton", command=lambda k=key: self.show_page(k))
            button.pack(fill=tk.X, padx=10, pady=3)
            self.nav_buttons[key] = button
        ttk.Label(self.sidebar, text=f"v{__version__}", background=THEME["sidebar"], foreground=THEME["muted"], font=("Segoe UI", 9)).pack(side=tk.BOTTOM, pady=16)

        self._build_topbar()
        self.page_host = ttk.Frame(self.content)
        self.page_host.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 20))
        self.pages: dict[str, ttk.Frame] = {}
        self.pages["dashboard"] = self._build_overview_page()
        self.pages["actions"] = self._build_recovery_page()
        self.pages["npc"] = self._build_npc_page()
        self.pages["connection"] = self._build_connection_page()
        self.pages["diagnostics"] = self._build_diagnostics_page()
        self.pages["settings"] = self._build_settings_page()
        self.show_page("dashboard")

        self.footer = ttk.Frame(self.content, style="Panel.TFrame")
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer_listener = ttk.Label(self.footer, text="OSC stopped", style="Muted.Panel.TLabel")
        self.footer_listener.pack(side=tk.LEFT, padx=18, pady=7)
        self.footer_sam = ttk.Label(self.footer, text="Sam.py not paired", style="Muted.Panel.TLabel")
        self.footer_sam.pack(side=tk.RIGHT, padx=18, pady=7)

    def _build_topbar(self) -> None:
        top = ttk.Frame(self.content, style="Panel.TFrame")
        top.pack(fill=tk.X, padx=22, pady=(18, 16))
        brand = ttk.Frame(top, style="Panel.TFrame")
        brand.pack(side=tk.LEFT, padx=18, pady=12)
        ttk.Label(brand, text="Stories Of Yggdrasil OSC", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"Version {__version__}", style="Version.TLabel").pack(anchor="w")
        self.update_button = ttk.Button(top, text="Check for updates", command=self.check_for_updates)
        self.update_button.pack(side=tk.RIGHT, padx=(8, 18), pady=16)
        self.update_progress_frame = ttk.Frame(top, style="Panel.TFrame")
        self.update_progress_frame.pack(side=tk.RIGHT, padx=(8, 0), pady=10)
        self.update_progress_label = ttk.Label(self.update_progress_frame, text="", style="Muted.Panel.TLabel")
        self.update_progress_label.pack(anchor="e")
        self.update_progress_bar = ttk.Progressbar(self.update_progress_frame, mode="determinate", maximum=100, length=190)
        self.update_progress_bar.pack(anchor="e", pady=(3, 0))
        self.update_progress_frame.pack_forget()

    def _new_page(self) -> ttk.Frame:
        page = ttk.Frame(self.page_host)
        return page

    def _card(self, parent: tk.Misc) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame")

    def show_page(self, key: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        if key == "actions":
            self.refresh_recovery_options()
        elif key == "npc":
            self.refresh_npc_roster()
        elif key == "diagnostics":
            self._refresh_diagnostics_view()

    def _build_overview_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Character Combat Dashboard", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(page)
        body.pack(fill=tk.BOTH, expand=True)
        left = self._card(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = self._card(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        self.character_name_label = ttk.Label(left, text="Not paired", style="Character.TLabel")
        self.character_name_label.pack(anchor="w", padx=22, pady=(22, 3))
        self.character_meta_label = ttk.Label(left, text="Pair this device with Sam.py to load a character.", style="Muted.Card.TLabel")
        self.character_meta_label.pack(anchor="w", padx=22, pady=(0, 18))

        hp_head = ttk.Frame(left, style="CardInner.TFrame")
        hp_head.pack(fill=tk.X, padx=22)
        ttk.Label(hp_head, text="HP", style="BigValue.TLabel").pack(side=tk.LEFT)
        self.hp_value_label = ttk.Label(hp_head, text="0 / 0", style="Muted.Card.TLabel")
        self.hp_value_label.pack(side=tk.RIGHT)
        self.hp_bar = ttk.Progressbar(left, maximum=100, value=100, style="HP.Horizontal.TProgressbar")
        self.hp_bar.pack(fill=tk.X, padx=22, pady=(6, 16), ipady=7)

        mp_head = ttk.Frame(left, style="CardInner.TFrame")
        mp_head.pack(fill=tk.X, padx=22)
        ttk.Label(mp_head, text="MP", style="BigValue.TLabel").pack(side=tk.LEFT)
        self.mp_value_label = ttk.Label(mp_head, text="0 / 0", style="Muted.Card.TLabel")
        self.mp_value_label.pack(side=tk.RIGHT)
        self.mp_bar = ttk.Progressbar(left, maximum=100, value=0, style="MP.Horizontal.TProgressbar")
        self.mp_bar.pack(fill=tk.X, padx=22, pady=(6, 18), ipady=7)

        profile_card = ttk.Frame(left, style="CardInner.TFrame")
        profile_card.pack(fill=tk.X, padx=22, pady=(0, 14))
        ttk.Label(profile_card, text="Effective Combat Profile", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 5))
        self.combat_stats_label = ttk.Label(profile_card, text="ATK —  DEF —  MAG —  RES —  SPD —  EVA —  VIT —", style="Muted.Card.TLabel", wraplength=500, justify="left")
        self.combat_stats_label.pack(anchor="w")
        self.affinities_label = ttk.Label(profile_card, text="Affinities: waiting for Sam.py API 0.8.14", style="Muted.Card.TLabel", wraplength=500, justify="left")
        self.affinities_label.pack(anchor="w", pady=(3, 0))
        self.magicks_profile_label = ttk.Label(profile_card, text="Magicks: waiting for authoritative profile", style="Muted.Card.TLabel", wraplength=500, justify="left")
        self.magicks_profile_label.pack(anchor="w", pady=(3, 0))

        self.diablos_frame = ttk.Frame(left, style="CardInner.TFrame")
        diablos_head = ttk.Frame(self.diablos_frame, style="CardInner.TFrame")
        diablos_head.pack(fill=tk.X)
        ttk.Label(diablos_head, text="Curse Of Diablos", style="BigValue.TLabel").pack(side=tk.LEFT)
        self.diablos_value_label = ttk.Label(diablos_head, text="0%", style="Muted.Card.TLabel")
        self.diablos_value_label.pack(side=tk.RIGHT)
        self.diablos_bar = ttk.Progressbar(self.diablos_frame, maximum=100, value=0, style="Diablos.Horizontal.TProgressbar")
        self.diablos_bar.pack(fill=tk.X, pady=(6, 5), ipady=6)
        self.diablos_warning_label = ttk.Label(self.diablos_frame, text="Stable", style="Muted.Card.TLabel")
        self.diablos_warning_label.pack(anchor="w", pady=(0, 12))

        toggle_row = ttk.Frame(left, style="CardInner.TFrame")
        self.combat_toggle_row = toggle_row
        toggle_row.pack(fill=tk.X, padx=22, pady=(0, 16))
        ttk.Label(toggle_row, text="RP Combat", style="CardTitle.TLabel").pack(side=tk.LEFT)
        self.combat_var = tk.BooleanVar(value=self.state.combat_enabled)
        self.combat_toggle = ttk.Checkbutton(toggle_row, text="Enabled", variable=self.combat_var, command=self._combat_toggle_from_ui)
        self.combat_toggle.pack(side=tk.RIGHT)

        ttk.Label(left, text="Active Status", style="CardTitle.TLabel").pack(anchor="w", padx=22, pady=(4, 8))
        self.status_frame = ttk.Frame(left, style="CardInner.TFrame")
        self.status_frame.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.status_labels: dict[str, ttk.Label] = {}
        for index, name in enumerate(("Burn", "Bleed", "Silence", "Freeze", "Bind")):
            label = ttk.Label(self.status_frame, text=name, style="StatusOff.TLabel")
            label.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
            self.status_labels[name.lower()] = label
        for col in range(3):
            self.status_frame.columnconfigure(col, weight=1)

        self.dm_gate_label = ttk.Label(left, text="Dungeon Master Gate: CLOSED", style="Muted.Card.TLabel")
        self.dm_gate_label.pack(anchor="w", padx=22, pady=(0, 22))

        title_row = ttk.Frame(right, style="CardInner.TFrame")
        title_row.pack(fill=tk.X, padx=18, pady=(18, 8))
        ttk.Label(title_row, text="Recent Activity", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_row, text="Clear", command=self.clear_activity).pack(side=tk.RIGHT)
        self.event_tree = ttk.Treeview(right, columns=("time", "type", "event"), show="headings", height=18)
        self.event_tree.heading("time", text="Time")
        self.event_tree.heading("type", text="Type")
        self.event_tree.heading("event", text="Event")
        self.event_tree.column("time", width=78, anchor="center", stretch=False)
        self.event_tree.column("type", width=86, anchor="center", stretch=False)
        self.event_tree.column("event", width=520)
        self.event_tree.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        return page

    def _build_recovery_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Actions & Recovery", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Refresh", command=self.refresh_recovery_options).pack(side=tk.RIGHT)
        self.recovery_summary_label = ttk.Label(page, text="Potions, ethers, and restorative magick are calculated by Sam.py.", style="Muted.TLabel")
        self.recovery_summary_label.pack(anchor="w", pady=(0, 10))

        self.action_availability_label = ttk.Label(page, text="Sam.py remains authoritative for Magicks, Technicks, MP costs, Silence, KO, targets, items, and cooldowns.", style="Muted.TLabel", wraplength=1000, justify="left")
        self.action_availability_label.pack(anchor="w", pady=(0, 8))
        card = self._card(page)
        card.pack(fill=tk.BOTH, expand=True)
        self.recovery_tree = ttk.Treeview(card, columns=("kind", "name", "effect", "cost", "available"), show="headings")
        for key, title, width in (("kind", "Type", 85), ("name", "Recovery", 190), ("effect", "Expected Result", 250), ("cost", "Cost", 130), ("available", "Available", 110)):
            self.recovery_tree.heading(key, text=title)
            self.recovery_tree.column(key, width=width, anchor="w")
        self.recovery_tree.pack(fill=tk.BOTH, expand=True, padx=18, pady=(18, 10))
        actions = ttk.Frame(card, style="CardInner.TFrame")
        actions.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.use_recovery_button = ttk.Button(actions, text="Use Selected", style="Green.TButton", command=self.use_selected_recovery)
        self.use_recovery_button.pack(side=tk.RIGHT)
        self.recovery_notice_label = ttk.Label(actions, text="Select an option. Actual recovery cannot exceed missing HP or MP.", style="Muted.Card.TLabel")
        self.recovery_notice_label.pack(side=tk.LEFT)
        return page

    def _build_connection_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Connection", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(page)
        row.pack(fill=tk.BOTH, expand=True)
        sam_card = self._card(row)
        sam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        osc_card = self._card(row)
        osc_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(sam_card, text="Sam.py Pairing", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 12))
        sam_cfg = self.config.get("sam", {})
        self.sam_url_var = tk.StringVar(value=str(sam_cfg.get("base_url") or "https://admin.storiesofyggdrasil.com/api/osc"))
        self.sam_device_var = tk.StringVar(value=str(sam_cfg.get("device_name") or "Stories OSC Desktop"))
        self.sam_code_var = tk.StringVar()
        self._entry(sam_card, 1, "Server", self.sam_url_var)
        self._entry(sam_card, 2, "Device", self.sam_device_var)
        self._entry(sam_card, 3, "Pairing code", self.sam_code_var, show="")
        buttons = ttk.Frame(sam_card, style="CardInner.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=12)
        ttk.Button(buttons, text="Pair Device", style="Gold.TButton", command=self.pair_with_sam).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Test", command=self.test_sam_connection).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Unlink", style="Danger.TButton", command=self.unlink_from_sam).pack(side=tk.LEFT, padx=6)
        self.sam_status_label = ttk.Label(sam_card, text="Not paired", style="Muted.Card.TLabel", wraplength=430, justify="left")
        self.sam_status_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=20, pady=(2, 6))
        self.sam_api_label = ttk.Label(sam_card, text=f"OSC API: unknown • minimum {OSC_API_MINIMUM} • recommended {OSC_API_RECOMMENDED}", style="Muted.Card.TLabel", wraplength=430, justify="left")
        self.sam_api_label.grid(row=6, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))
        sam_card.columnconfigure(1, weight=1)

        ttk.Label(osc_card, text="VRChat OSC", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 12))
        self.listener_status_label = ttk.Label(osc_card, text="Listener stopped", style="Muted.Card.TLabel")
        self.listener_status_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        self.avatar_status_label = ttk.Label(osc_card, text="Avatar: —", style="Muted.Card.TLabel")
        self.avatar_status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        self.activity_status_label = ttk.Label(osc_card, text="VRChat activity: none", style="Muted.Card.TLabel")
        self.activity_status_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        osc_buttons = ttk.Frame(osc_card, style="CardInner.TFrame")
        osc_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=18)
        ttk.Button(osc_buttons, text="Start Listener", style="Green.TButton", command=self.start_listener).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(osc_buttons, text="Stop", command=self.stop_listener).pack(side=tk.LEFT, padx=6)
        ttk.Button(osc_buttons, text="Restart", command=self.restart_listener).pack(side=tk.LEFT, padx=6)
        ttk.Label(osc_card, text="VRChat defaults: receive 9000, send 9001.", style="Muted.Card.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))
        return page

    def _build_npc_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="NPC Mode", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Refresh Rosters", command=self.refresh_npc_roster).pack(side=tk.RIGHT)
        npc_card = self._card(page)
        npc_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(npc_card, text="Authoritative NPC Runtime", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        npc_cfg = self.config.get("npc_mode", {})
        self.npc_mode_var = tk.BooleanVar(value=bool(npc_cfg.get("enabled", False)))
        self.npc_enemy_var = tk.StringVar(value=str(npc_cfg.get("enemy_name") or ""))
        self.npc_attacker_mode_var = tk.StringVar(value=str(npc_cfg.get("attacker_mode") or "verified"))
        self.npc_attacker_player_var = tk.StringVar(value=str(npc_cfg.get("attacker_player_label") or npc_cfg.get("attacker_user_id") or ""))
        self.npc_attacker_char_var = tk.StringVar(value=str(npc_cfg.get("attacker_char_name") or ""))
        ttk.Checkbutton(npc_card, text="Use this Desktop link as an NPC enemy", variable=self.npc_mode_var, command=self._refresh_npc_attacker_status).grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=6)
        ttk.Label(npc_card, text="NPC roster", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=20, pady=6)
        self.npc_enemy_combo = ttk.Combobox(npc_card, textvariable=self.npc_enemy_var, values=(), state="readonly")
        self.npc_enemy_combo.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(0, 20), pady=6)
        self.npc_enemy_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_npc_preview())
        self.npc_preview_label = ttk.Label(npc_card, text="Select an NPC to preview its authoritative level, HP, DEF, RES, EVA, and affinities.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_preview_label.grid(row=3, column=0, columnspan=4, sticky="w", padx=20, pady=(2, 12))
        ttk.Separator(npc_card, orient="horizontal").grid(row=4, column=0, columnspan=4, sticky="ew", padx=20, pady=6)
        ttk.Label(npc_card, text="Player → NPC Damage Attacker", style="CardTitle.TLabel").grid(row=5, column=0, columnspan=4, sticky="w", padx=20, pady=(8, 8))
        ttk.Label(npc_card, text="Attacking player", style="Card.TLabel").grid(row=6, column=0, sticky="w", padx=20, pady=6)
        self.npc_attacker_player_combo = ttk.Combobox(npc_card, textvariable=self.npc_attacker_player_var, values=(), state="normal")
        self.npc_attacker_player_combo.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=6)
        self.npc_attacker_player_combo.bind("<<ComboboxSelected>>", self._on_npc_attacker_player_selected)
        self.npc_attacker_player_combo.bind("<KeyRelease>", lambda _event: self._refresh_npc_attacker_status())
        ttk.Button(npc_card, text="Use Linked Character", command=self._use_linked_character_as_attacker).grid(row=6, column=3, sticky="e", padx=(0, 20), pady=6)
        ttk.Label(npc_card, text="Attacking character", style="Card.TLabel").grid(row=7, column=0, sticky="w", padx=20, pady=6)
        self.npc_attacker_char_combo = ttk.Combobox(npc_card, textvariable=self.npc_attacker_char_var, values=(), state="normal")
        self.npc_attacker_char_combo.grid(row=7, column=1, columnspan=3, sticky="ew", padx=(0, 20), pady=6)
        self.npc_attacker_char_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_npc_attacker_status())
        self.npc_attacker_char_combo.bind("<KeyRelease>", lambda _event: self._refresh_npc_attacker_status())
        ttk.Radiobutton(npc_card, text="Verified Sam.py stats", value="verified", variable=self.npc_attacker_mode_var, command=self._refresh_npc_attacker_status).grid(row=8, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        ttk.Radiobutton(npc_card, text="Compatibility fallback", value="fallback", variable=self.npc_attacker_mode_var, command=self._refresh_npc_attacker_status).grid(row=8, column=2, columnspan=2, sticky="w", padx=10, pady=4)
        self.npc_attacker_status_label = ttk.Label(npc_card, text="", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_attacker_status_label.grid(row=9, column=0, columnspan=4, sticky="w", padx=20, pady=(4, 6))
        self.npc_hit_diagnostics_label = ttk.Label(npc_card, text="Last hit diagnostics: no Player → NPC hit has been returned by Sam.py yet.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_hit_diagnostics_label.grid(row=10, column=0, columnspan=4, sticky="w", padx=20, pady=(2, 6))
        self.npc_notice_label = ttk.Label(npc_card, text="NPC Mode uses a device-local runtime copy. The static enemy roster is never edited, and verified attacker stats come from Sam.py API 0.8.14.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_notice_label.grid(row=11, column=0, columnspan=4, sticky="w", padx=20, pady=(4, 16))
        npc_card.columnconfigure(1, weight=1)
        npc_card.columnconfigure(2, weight=1)
        self._refresh_npc_attacker_status()
        return page

    def _build_diagnostics_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Diagnostics", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Test Sam.py", command=self.test_sam_connection).pack(side=tk.RIGHT)
        card = self._card(page)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="Connection & Contract", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(18, 8))
        self.diagnostics_summary_label = ttk.Label(card, text="Waiting for Sam.py state…", style="Muted.Card.TLabel", wraplength=980, justify="left")
        self.diagnostics_summary_label.pack(anchor="w", padx=20, pady=(0, 8))
        self.diagnostics_detail_label = ttk.Label(card, text="No diagnostics have been received.", style="Muted.Card.TLabel", wraplength=980, justify="left")
        self.diagnostics_detail_label.pack(anchor="w", padx=20, pady=(0, 18))
        info = self._card(page)
        info.pack(fill=tk.BOTH, expand=True)
        ttk.Label(info, text="Audit Guidance", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(18, 8))
        ttk.Label(info, text="API 0.8.14 verifies the NPC attacker roster, authoritative player writes, combat-profile data, and effective affinities. Rejected actions should appear as structured messages instead of HTTP 500 errors. Review Recent Activity for the last local OSC event and this page for server compatibility.", style="Muted.Card.TLabel", wraplength=980, justify="left").pack(anchor="w", padx=20, pady=(0, 18))
        return page

    def _refresh_diagnostics_view(self) -> None:
        if not hasattr(self, "diagnostics_summary_label"):
            return
        paired = bool(str(self.config.get("sam", {}).get("token") or "").strip())
        api = self.sam_api_version or "unknown"
        profile = self.remote_state.get("combat_profile") if isinstance(self.remote_state.get("combat_profile"), dict) else {}
        caps = self.remote_state.get("capabilities") if isinstance(self.remote_state.get("capabilities"), dict) else {}
        self.diagnostics_summary_label.configure(text=f"Sam.py: {'paired' if paired else 'not paired'}  •  API {api}  •  Desktop minimum {OSC_API_MINIMUM} / recommended {OSC_API_RECOMMENDED}  •  OSC listener: {'running' if self.osc.running else 'stopped'}")
        details = [
            f"Combat profile: {'available' if profile else 'waiting'}",
            f"Effective affinities: {'available' if profile.get('affinities') else 'waiting'}",
            f"Attacker catalog: {'loaded' if self.npc_attacker_roster else 'waiting'}",
            f"Last event: {self.last_event}",
        ]
        self.diagnostics_detail_label.configure(text="\n".join(details))

    def _build_settings_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Settings", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        canvas = tk.Canvas(page, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        settings_window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(settings_window, width=max(1, event.width)))
        canvas.configure(yscrollcommand=scrollbar.set)
        def _settings_wheel(event):
            delta = -1 if event.delta > 0 else 1
            canvas.yview_scroll(delta * 3, "units")
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _settings_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        osc = self.config["osc"]
        combat = self.config["combat"]
        bridge = self.config["avatar_bridge"]
        sam = self.config["sam"]
        updates = self.config["updates"]

        network = self._card(body)
        network.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(network, text="Network", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        self.listen_ip_var = tk.StringVar(value=str(osc["listen_ip"]))
        self.listen_port_var = tk.StringVar(value=str(osc["listen_port"]))
        self.vrchat_ip_var = tk.StringVar(value=str(osc["vrchat_ip"]))
        self.vrchat_port_var = tk.StringVar(value=str(osc["vrchat_port"]))
        self.auto_start_var = tk.BooleanVar(value=bool(osc.get("auto_start_listener", True)))
        self._entry(network, 1, "Listen IP", self.listen_ip_var, col=0)
        self._entry(network, 1, "Listen port", self.listen_port_var, col=2)
        self._entry(network, 2, "VRChat IP", self.vrchat_ip_var, col=0)
        self._entry(network, 2, "VRChat port", self.vrchat_port_var, col=2)
        ttk.Checkbutton(network, text="Start listener automatically", variable=self.auto_start_var).grid(row=3, column=0, columnspan=4, sticky="w", padx=20, pady=(4, 16))
        for col in (1, 3): network.columnconfigure(col, weight=1)

        damage = self._card(body)
        damage.pack(fill=tk.X, pady=10)
        ttk.Label(damage, text="Offline / Compatibility Contact Damage", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        ttk.Label(damage, text="Used only when Sam.py is unavailable or an older compatibility client is active. Paired combat damage is calculated by Sam.py.", style="Muted.Card.TLabel", wraplength=900, justify="left").grid(row=1, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 8))
        self.damage_vars: dict[str, tk.StringVar] = {}
        for index, key in enumerate(("weak", "average", "strong", "critical")):
            var = tk.StringVar(value=str(combat["damage"][key]))
            self.damage_vars[key] = var
            self._entry(damage, 2 + index // 2, key.title(), var, col=(index % 2) * 2)
        for col in (1, 3): damage.columnconfigure(col, weight=1)

        avatar = self._card(body)
        avatar.pack(fill=tk.X, pady=10)
        ttk.Label(avatar, text="Avatar Health Bridge", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        self.input_mode_var = tk.StringVar(value=str(bridge.get("input_mode", "auto")))
        ttk.Label(avatar, text="Input mode", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=20, pady=6)
        ttk.Combobox(avatar, textvariable=self.input_mode_var, values=("auto", "external", "direct"), state="readonly").grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=6)
        self.observe_health_var = tk.BooleanVar(value=bool(bridge.get("observe_health", True)))
        self.health_invert_var = tk.BooleanVar(value=bool(bridge.get("health_invert", True)))
        self.drive_health_var = tk.BooleanVar(value=bool(sam.get("drive_avatar_health_from_sam", False)))
        self.drive_status_var = tk.BooleanVar(value=bool(sam.get("drive_avatar_statuses_from_sam", False)))
        ttk.Checkbutton(avatar, text="Observe avatar Health parameter", variable=self.observe_health_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Health value represents accumulated damage", variable=self.health_invert_var).grid(row=2, column=2, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Drive avatar Health from Sam.py", variable=self.drive_health_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Drive avatar status parameters from Sam.py", variable=self.drive_status_var).grid(row=3, column=2, columnspan=2, sticky="w", padx=20, pady=(5, 16))
        avatar.columnconfigure(1, weight=1)

        update_card = self._card(body)
        update_card.pack(fill=tk.X, pady=10)
        ttk.Label(update_card, text="Updates", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(18, 10))
        self.github_repo_var = tk.StringVar(value=str(updates.get("github_repo") or ""))
        self.update_on_start_var = tk.BooleanVar(value=bool(updates.get("check_on_start", True)))
        self._entry(update_card, 1, "GitHub repository", self.github_repo_var)
        ttk.Checkbutton(update_card, text="Automatically check at startup and every six hours", variable=self.update_on_start_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=(5, 16))
        update_card.columnconfigure(1, weight=1)

        actions = ttk.Frame(body)
        actions.pack(fill=tk.X, pady=(10, 20))
        ttk.Button(actions, text="Save Settings", style="Gold.TButton", command=self.save_settings).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Open Settings Folder", command=self.open_settings_folder).pack(side=tk.RIGHT, padx=8)
        return page

    def _entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable, *, col: int = 0, show: str | None = None) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=col, sticky="w", padx=20, pady=6)
        kwargs: dict[str, Any] = {"textvariable": variable, "bg": THEME["panel3"], "fg": THEME["text"], "insertbackground": THEME["text"], "relief": tk.FLAT}
        if show is not None:
            kwargs["show"] = show
        entry = tk.Entry(parent, **kwargs)
        entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, 20), pady=6, ipady=6)

    # ------------------------------------------------------------------
    # OSC processing
    # ------------------------------------------------------------------
    def _make_osc_service(self) -> OSCService:
        cfg = self.config["osc"]
        return OSCService(
            listen_ip=str(cfg["listen_ip"]),
            listen_port=int(cfg["listen_port"]),
            vrchat_ip=str(cfg["vrchat_ip"]),
            vrchat_port=int(cfg["vrchat_port"]),
            event_queue=self.osc_events,
        )

    def start_listener(self) -> None:
        try:
            self.osc.start()
            self._append_activity("SYSTEM", f"OSC listening on {self.osc.listen_ip}:{self.osc.listen_port}.")
        except Exception as exc:
            self._append_activity("ERROR", f"OSC listener failed: {exc}")
            messagebox.showerror("OSC Listener", f"Could not start the OSC listener.\n\n{exc}")
        self._refresh_ui()

    def stop_listener(self) -> None:
        self.osc.stop()
        self._append_activity("SYSTEM", "OSC listener stopped.")
        self._refresh_ui()

    def restart_listener(self) -> None:
        self.stop_listener()
        self.root.after(150, self.start_listener)

    def _poll(self) -> None:
        if self.closing:
            return
        try:
            while True:
                self._handle_osc_event(self.osc_events.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_sam_event(self.sam_events.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_update_event(self.update_events.get_nowait())
        except queue.Empty:
            pass
        self.controller.tick()
        if self.sam_sync_due_at and time.monotonic() >= self.sam_sync_due_at and not self.sam_sync_inflight:
            self._push_sam_state()
        try:
            minimized = self.root.state() == "iconic"
        except Exception:
            minimized = False
        self.root.after(125 if minimized else self.POLL_MS, self._poll)

    def _handle_osc_event(self, event: OSCEvent) -> None:
        if event.kind == "system":
            return
        if event.address == "/avatar/change":
            self.last_avatar_id = str(event.values[0]) if event.values else "—"
            self.output_cache.clear()
            self.controller.handle_osc(event.address, event.values, event.received_at_monotonic)
            self._append_activity("AVATAR", f"Loaded avatar {self._short_avatar(self.last_avatar_id)}.")
            return
        if event.address.startswith("/avatar/parameters/") and self.last_avatar_id == "—":
            self.last_avatar_id = "Build & Test / local"
        self.controller.handle_osc(event.address, event.values, event.received_at_monotonic)

    def _send_parameter(self, name: str, value: Any) -> None:
        if not name:
            return
        if self.output_cache.get(name, object()) == value:
            return
        self.output_cache[name] = value
        try:
            self.osc.send_avatar_parameter(name, value)
        except Exception:
            pass

    def _pulse_parameter(self, name: str, duration: float) -> None:
        try:
            self.osc.pulse_avatar_parameter(name, duration)
        except Exception:
            pass

    def _combat_toggle_from_ui(self) -> None:
        result = self.state.set_combat_enabled(bool(self.combat_var.get()))
        self.controller.commit_result(result)
        self._send_parameter(self.config["parameters"]["combat_enabled"], bool(self.state.combat_enabled))

    def _on_result(self, result: EventResult) -> None:
        category = "EVENT" if result.accepted else "IGNORED"
        if result.event in {"damage", "dot_damage"}: category = "DAMAGE"
        elif result.event in {"healing", "revive"}: category = "HEAL"
        elif "status" in result.event: category = "STATUS"
        elif result.event == "blocked": category = "BLOCK"
        elif result.event == "external_detected": category = "AVATAR"
        self._append_activity(category, result.message)
        if result.accepted and result.event in {
            "damage", "dot_damage", "healing", "revive", "set_hp", "external_health_update",
            "status_applied", "status_expired", "statuses_cleared", "external_status_active",
            "external_status_cleared", "combat_toggle", "hit_contact", "status_contact",
        }:
            source = str(result.metadata.get("source") or "")
            is_vrc_trigger = source in {"direct", "external", "binary_contact_bus"}
            self._schedule_sam_sync(
                result.event,
                immediate=result.event in {"hit_contact", "status_contact"},
                vrc_trigger=is_vrc_trigger,
            )
        elif result.accepted and result.event == "telemetry":
            if "enemy_mode" in result.metadata:
                value = bool(result.metadata.get("enemy_mode"))
                self.enemy_mode_pending_value = value
                self.enemy_mode_pending_until = time.monotonic() + 4.0
                self._schedule_sam_sync("enemy_mode", immediate=True, vrc_trigger=True)
                return
            # Direct Int values come from this avatar's expression-menu buttons
            # and represent local cast/use intent. Binary buses are incoming
            # Contacts received by this avatar. Keep the two directions separate
            # so Sam.py never charges the target's MP or consumes the target's item.
            for field, event_name in (
                ("spell_cast_type", "spell_cast"),
                ("technick_use_type", "technick_use"),
                ("item_use_type", "item_use"),
                ("spell_type", "spell_contact"),
                ("technick_type", "technick_contact"),
                ("item_type", "item_contact"),
            ):
                action_id = int(result.metadata.get(field, 0) or 0)
                if action_id > 0:
                    self._schedule_sam_sync(event_name, immediate=True, vrc_trigger=True)
                    break

    # ------------------------------------------------------------------
    # Sam.py link and recovery
    # ------------------------------------------------------------------
    def _save_sam_form(self) -> dict[str, Any]:
        cfg = self.config.setdefault("sam", {})
        cfg["base_url"] = str(self.sam_url_var.get()).strip().rstrip("/") or "https://admin.storiesofyggdrasil.com/api/osc"
        cfg["device_name"] = str(self.sam_device_var.get()).strip() or "Stories OSC Desktop"
        save_config(self.config)
        self.sam_client.reconfigure(cfg)
        return cfg

    def pair_with_sam(self) -> None:
        cfg = self._save_sam_form()
        code = str(self.sam_code_var.get()).strip()
        if not code:
            messagebox.showwarning("Pairing Code", "Run /osc_link in Discord, then enter the one-use code.")
            return
        cfg["enabled"] = True
        self.sam_client.reconfigure(cfg)
        self.sam_status_label.configure(text="Pairing…", foreground=THEME["yellow"])
        self.sam_client.pair(code, str(cfg.get("device_name") or "Stories OSC Desktop"))

    def unlink_from_sam(self) -> None:
        if str(self.config.get("sam", {}).get("token") or "").strip():
            self.sam_client.unlink()
        else:
            self._clear_local_sam_link()

    def _clear_local_sam_link(self) -> None:
        cfg = self.config.setdefault("sam", {})
        cfg["token"] = ""
        cfg["enabled"] = False
        save_config(self.config)
        self.sam_client.reconfigure(cfg)
        self.remote_character = {}
        self.remote_state = {}
        self.link_info = {}
        self.sam_api_version = ""
        self.sam_status_label.configure(text="Not paired", foreground=THEME["muted"])
        if hasattr(self, "sam_api_label"):
            self.sam_api_label.configure(text=f"OSC API: unknown • minimum {OSC_API_MINIMUM} • recommended {OSC_API_RECOMMENDED}", foreground=THEME["muted"])
        self._append_activity("SAM", "Sam.py device link removed.")
        self._refresh_ui()

    def test_sam_connection(self) -> None:
        self._save_sam_form()
        self.sam_client.test()

    def refresh_recovery_options(self) -> None:
        if not str(self.config.get("sam", {}).get("token") or "").strip():
            self.recovery_notice_label.configure(text="Pair this device with Sam.py before using recovery.")
            return
        self.recovery_notice_label.configure(text="Refreshing recovery options…")
        self.sam_client.recovery_options()

    def refresh_npc_roster(self) -> None:
        if not str(self.config.get("sam", {}).get("token") or "").strip():
            self.npc_notice_label.configure(text="Pair this device with Sam.py before loading the NPC roster.")
            return
        self.npc_notice_label.configure(text="Loading Sam.py NPC and attacker rosters…")
        self.sam_client.npc_catalog()

    def use_selected_recovery(self) -> None:
        selected = self.recovery_tree.selection()
        if not selected:
            messagebox.showinfo("Recovery", "Select a potion, ether, or spell first.")
            return
        option = self.recovery_by_row.get(selected[0])
        if not option:
            return
        if not bool(option.get("usable", True)):
            messagebox.showwarning("Recovery", str(option.get("unavailable_reason") or "That option cannot be used right now."))
            return
        name = str(option.get("name") or "")
        kind = str(option.get("kind") or "")
        if not messagebox.askyesno("Use Recovery", f"Use {name}?\n\n{option.get('effect_text', '')}"):
            return
        self.recovery_notice_label.configure(text=f"Using {name}…")
        self.sam_client.use_recovery(kind, name)

    def _schedule_sam_sync(
        self,
        event_name: str,
        *,
        immediate: bool = False,
        vrc_trigger: bool = False,
    ) -> None:
        cfg = self.config.get("sam", {})
        if not bool(cfg.get("enabled", False)) or not str(cfg.get("token") or "").strip():
            return
        self.sam_local_dirty = True
        self.sam_last_event_name = str(event_name or "state_change")
        self.sam_last_event_vrc_trigger = bool(vrc_trigger)
        delay = 0.0 if immediate else max(0.05, float(cfg.get("push_debounce_seconds", 0.30)))
        self.sam_sync_due_at = time.monotonic() + delay

    def _build_sam_sync_payload(self) -> dict[str, Any]:
        cfg = self.config.get("sam", {})
        snap = self.state.snapshot()
        self.sam_client_seq += 1
        payload: dict[str, Any] = {
            "client_seq": self.sam_client_seq,
            "client_session": self.sam_client_session,
            "client_event": self.sam_last_event_name,
            "client_version": __version__,
            "vrc_trigger": bool(self.sam_last_event_vrc_trigger),
            "avatar_id": self.last_avatar_id,
            "source_mode": self.controller.active_input_mode,
            "client_drives_remote_statuses": bool(cfg.get("drive_avatar_statuses_from_sam", False)),
        }
        if bool(cfg.get("sync_hp", True)):
            payload["hp"] = int(snap["current_hp"])
            payload["hp_ratio"] = float(snap["hp_ratio"])
        if bool(cfg.get("sync_combat_toggle", True)):
            payload["combat_enabled"] = bool(snap["combat_enabled"])
        payload.update(dict(self.controller.telemetry))
        # Alignment is event-scoped. Damage/debuff Contacts use the dedicated
        # source receiver; spells/Technicks/items use their action-bus receiver.
        if str(payload.get("hit_event") or "") or str(payload.get("status_event") or ""):
            payload["source_enemy"] = bool(payload.get("damage_source_enemy", False))
        elif any(int(payload.get(field, 0) or 0) > 0 for field in ("spell_type", "technick_type", "item_type")):
            payload["source_enemy"] = bool(payload.get("healing_source_enemy", False))
        elif any(int(payload.get(field, 0) or 0) > 0 for field in ("spell_cast_type", "technick_use_type", "item_use_type")):
            payload["source_enemy"] = bool(payload.get("enemy_mode", False))
        npc_cfg = self.config.get("npc_mode", {})
        payload["npc_mode"] = bool(npc_cfg.get("enabled", False))
        payload["npc_enemy_key"] = str(npc_cfg.get("enemy_key") or "")
        verified_attacker = str(npc_cfg.get("attacker_mode") or "verified").lower() == "verified"
        payload["npc_attacker_user_id"] = str(npc_cfg.get("attacker_user_id") or "") if verified_attacker else ""
        payload["npc_attacker_char_name"] = str(npc_cfg.get("attacker_char_name") or "") if verified_attacker else ""
        for field in (
            "spell_cast_type", "technick_use_type", "item_use_type",
            "spell_type", "technick_type", "item_type",
        ):
            action_id = int(payload.get(field, 0) or 0)
            if action_id <= 0:
                payload.pop(field, None)
            else:
                # Contact actions are one-shot events. Keeping a value latched
                # would repeat it during later unrelated state synchronization.
                self.controller.telemetry[field] = 0
        self.sam_last_event_vrc_trigger = False
        hit_event = str(payload.get("hit_event") or "")
        if hit_event:
            self.controller.telemetry["hit_event"] = ""
        status_event = str(payload.get("status_event") or "")
        if status_event:
            self.controller.telemetry["status_event"] = ""
        if hit_event or status_event:
            consume_alignment = getattr(self.controller, "consume_damage_alignment", None)
            if callable(consume_alignment):
                consume_alignment()
            else:
                self.controller.telemetry["damage_source_enemy"] = False
        if bool(cfg.get("sync_statuses", True)) and not self.controller.authoritative_sam_actions:
            active = snap.get("statuses", {})
            statuses: dict[str, Any] = {}
            for name in ("burn", "bleed", "silence", "freeze", "bind"):
                info = active.get(name)
                remaining = None
                if isinstance(info, dict):
                    try:
                        raw = info.get("remaining")
                        remaining = None if raw is None or raw == float("inf") else max(1, int(float(raw)))
                    except Exception:
                        remaining = None
                statuses[name] = {"active": info is not None, "duration_seconds": remaining}
            payload["statuses"] = statuses
        return payload

    def _push_sam_state(self) -> None:
        self.sam_sync_due_at = 0.0
        if self.sam_sync_inflight:
            return
        self.sam_sync_inflight = True
        self.sam_client.sync(self._build_sam_sync_payload())

    def _handle_sam_event(self, event: SamEvent) -> None:
        if not event.ok:
            self.sam_sync_inflight = False
            self.sam_status_label.configure(text=event.message, foreground=THEME["red"])
            self._append_activity("SAM ERROR", event.message)
            return
        self._record_sam_api_version(event.data)
        if event.kind == "npc_catalog":
            rows = event.data.get("enemies") if isinstance(event.data.get("enemies"), list) else []
            self.npc_roster = [row for row in rows if isinstance(row, dict)]
            self.npc_by_name = {str(row.get("name") or ""): row for row in self.npc_roster if str(row.get("name") or "")}
            names = sorted(self.npc_by_name, key=str.casefold)
            self.npc_enemy_combo.configure(values=names)
            current = str(self.npc_enemy_var.get() or "")
            if current not in self.npc_by_name and names:
                self.npc_enemy_var.set(names[0])
            self._refresh_npc_preview()

            attacker_rows = event.data.get("attackers") if isinstance(event.data.get("attackers"), list) else []
            self._load_npc_attacker_roster([row for row in attacker_rows if isinstance(row, dict)])
            if self.npc_attacker_roster:
                eligible = sum(1 for row in self.npc_attacker_roster if bool(row.get("eligible", True)))
                self.npc_notice_label.configure(text=f"Loaded {len(names)} enemies and {eligible} eligible attacker character(s) from Sam.py.")
            else:
                self.npc_notice_label.configure(text=f"Loaded {len(names)} enemies. API {self.sam_api_version or 'unknown'} does not publish an attacker roster; manual Discord ID and character-name entry remains available.")
            self._refresh_npc_attacker_status()
            return
        if event.kind == "paired":
            self.link_info = dict(event.data.get("link") or {}) if isinstance(event.data.get("link"), dict) else {}
            token = str(event.data.get("token") or "")
            if not token:
                self.sam_status_label.configure(text="Pairing failed: no device token returned.", foreground=THEME["red"])
                return
            cfg = self.config.setdefault("sam", {})
            cfg["token"] = token
            cfg["enabled"] = True
            save_config(self.config)
            self.sam_client.reconfigure(cfg)
            self.sam_code_var.set("")
            state = event.data.get("state")
            if isinstance(state, dict):
                self._apply_sam_state(state, source="pair", force=True)
            self.sam_status_label.configure(text="Paired and connected.", foreground=THEME["green"])
            self._append_activity("SAM", "Device paired with Sam.py.")
            self.sam_client.recovery_options()
            self.sam_client.npc_catalog()
            return
        if event.kind == "unlinked":
            self._clear_local_sam_link()
            return
        if event.kind == "test":
            state_response = event.data.get("state_response")
            if isinstance(state_response, dict) and isinstance(state_response.get("link"), dict):
                self.link_info = dict(state_response.get("link") or {})
            if isinstance(state_response, dict) and isinstance(state_response.get("state"), dict):
                self._apply_sam_state(state_response["state"], source="test", force=False)
            self.sam_status_label.configure(text="Connection test passed.", foreground=THEME["green"])
            return
        if event.kind == "recovery_options":
            options = event.data.get("options") if isinstance(event.data.get("options"), list) else []
            self._populate_recovery(options, event.data)
            return
        if event.kind == "recovery_used":
            state = event.data.get("state")
            if isinstance(state, dict):
                self._apply_sam_state(state, source="recovery", force=True)
            self._append_activity("RECOVERY", event.message)
            self.recovery_notice_label.configure(text=event.message)
            self.sam_client.recovery_options()
            return
        if event.kind == "state":
            self.sam_sync_inflight = False
            if isinstance(event.data.get("link"), dict):
                self.link_info = dict(event.data.get("link") or {})
            state = event.data.get("state")
            rejected = False
            if isinstance(state, dict):
                sync_result = state.get("sync_result") if isinstance(state.get("sync_result"), dict) else {}
                rejected = bool(sync_result) and not bool(sync_result.get("accepted", True))
                self._apply_sam_state(state, source=event.source, force=event.source in {"sync", "pull"} or rejected)
                for result_key, accepted_label, info_label, fallback in (
                    ("hit_result", "DAMAGE", "HIT INFO", "Incoming attack processed."),
                    ("status_result", "STATUS", "STATUS INFO", "Incoming status processed."),
                    ("spell_cast_result", "CAST", "CAST INFO", "Spell cast processed."),
                    ("technick_use_result", "TECHNICK", "TECHNICK INFO", "Technick use processed."),
                    ("item_use_result", "ITEM", "ITEM INFO", "Item use processed."),
                    ("spell_result", "SPELL", "SPELL INFO", "Incoming spell contact processed."),
                    ("technick_result", "TECHNICK", "TECHNICK INFO", "Incoming Technick contact identified."),
                    ("item_result", "ITEM", "ITEM INFO", "Incoming item contact identified."),
                ):
                    action_result = sync_result.get(result_key) if isinstance(sync_result.get(result_key), dict) else {}
                    if action_result:
                        action_message = str(action_result.get("message") or fallback)
                        self._append_activity(
                            accepted_label if bool(action_result.get("applied", False)) else info_label,
                            action_message,
                        )
                        if result_key == "hit_result":
                            self._update_npc_hit_diagnostics(action_result)
                            if bool(action_result.get("applied", False)):
                                self.controller.authoritative_hit_feedback(
                                    str(action_result.get("hit_type") or action_result.get("tier") or "average"),
                                    blocked=bool(action_result.get("blocked", False)),
                                )
                if rejected:
                    warning = str(sync_result.get("message") or "No Active DM's - No Hit Registered")
                    self._append_activity("WARNING", warning)
                    self.sam_status_label.configure(text=warning, foreground=THEME["red"])
                    self._restore_avatar_after_rejection(state, sync_result)
            if event.source == "sync":
                self.sam_local_dirty = False
            if not rejected:
                self.sam_status_label.configure(text="Connected to Sam.py.", foreground=THEME["green"])

    @staticmethod
    def _version_tuple(value: Any) -> tuple[int, int, int]:
        parts = []
        for token in str(value or "").strip().lstrip("vV").split(".")[:3]:
            digits = "".join(ch for ch in token if ch.isdigit())
            parts.append(int(digits or 0))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _record_sam_api_version(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        candidate = str(payload.get("api_version") or payload.get("version") or "").strip()
        nested = payload.get("state_response") if isinstance(payload.get("state_response"), dict) else {}
        candidate = candidate or str(nested.get("api_version") or "").strip()
        if candidate:
            self.sam_api_version = candidate
        if hasattr(self, "sam_api_label"):
            api = self.sam_api_version or "unknown"
            api_ok = self._version_tuple(api) >= self._version_tuple(OSC_API_MINIMUM) if api != "unknown" else False
            roster_ok = self._version_tuple(api) >= self._version_tuple(OSC_API_RECOMMENDED) if api != "unknown" else False
            status = "compatible" if api_ok else ("not verified" if api == "unknown" else "update required")
            roster = "attacker roster available" if roster_ok else "manual attacker entry"
            self.sam_api_label.configure(
                text=f"OSC API: {api} • {status} • {roster} • minimum {OSC_API_MINIMUM}",
                foreground=THEME["green"] if api_ok else THEME["red"] if api != "unknown" else THEME["muted"],
            )
        self._refresh_npc_attacker_status()

    def _refresh_npc_preview(self) -> None:
        if not hasattr(self, "npc_preview_label"):
            return
        row = self.npc_by_name.get(str(self.npc_enemy_var.get() or "").strip())
        if not isinstance(row, dict):
            self.npc_preview_label.configure(text="Select an NPC to preview its authoritative level, HP, DEF, RES, EVA, and affinities.")
            return
        weaknesses = ", ".join(str(x) for x in row.get("weaknesses", []) if str(x)) or "none listed"
        resistances = ", ".join(str(x) for x in row.get("resistances", []) if str(x)) or "none listed"
        self.npc_preview_label.configure(text=(
            f"Level {int(row.get('level', 1) or 1)} • HP {int(row.get('max_hp', 1) or 1):,} • MP {int(row.get('max_mp', 0) or 0):,} • "
            f"ATK {int(row.get('atk', 0) or 0)} • DEF {int(row.get('def', 0) or 0)} • MAG {int(row.get('mag', 0) or 0)} • RES {int(row.get('res', 0) or 0)} • "
            f"SPD {int(row.get('spd', 0) or 0)} • EVA {int(row.get('eva', 0) or 0)} • VIT {int(row.get('vit', row.get('vitality', 0)) or 0)}\n"
            f"Physical affinity: {row.get('physical_affinity') or 'normal'} • Magick affinity: {row.get('magick_affinity') or 'normal'} • Weaknesses: {weaknesses} • Resistances: {resistances}"
        ))

    def _load_npc_attacker_roster(self, rows: list[dict[str, Any]]) -> None:
        self.npc_attacker_roster = list(rows)
        self.npc_attackers_by_player.clear()
        self.npc_attacker_player_ids.clear()
        for row in self.npc_attacker_roster:
            uid = str(row.get("user_id") or "").strip()
            if not uid.isdigit():
                continue
            player_label = str(row.get("player_label") or row.get("account_name") or uid).strip()
            if uid not in player_label:
                player_label = f"{player_label} — {uid}"
            self.npc_attackers_by_player.setdefault(player_label, []).append(row)
            self.npc_attacker_player_ids[player_label] = uid
        player_values = sorted(self.npc_attackers_by_player, key=str.casefold)
        self.npc_attacker_player_combo.configure(values=player_values)

        current_uid = str(self.config.get("npc_mode", {}).get("attacker_user_id") or "")
        current_label = str(self.npc_attacker_player_var.get() or "")
        if current_label not in self.npc_attackers_by_player and current_uid:
            match = next((label for label, uid in self.npc_attacker_player_ids.items() if uid == current_uid), "")
            if match:
                self.npc_attacker_player_var.set(match)
                current_label = match
        if current_label in self.npc_attackers_by_player:
            self._on_npc_attacker_player_selected(None)

    def _on_npc_attacker_player_selected(self, _event: Any) -> None:
        label = str(self.npc_attacker_player_var.get() or "").strip()
        rows = self.npc_attackers_by_player.get(label, [])
        names = sorted({str(row.get("character_name") or "") for row in rows if str(row.get("character_name") or "")}, key=str.casefold)
        self.npc_attacker_char_combo.configure(values=names)
        current = str(self.npc_attacker_char_var.get() or "")
        if current not in names and names:
            preferred = next((str(row.get("character_name") or "") for row in rows if bool(row.get("active", False)) and bool(row.get("eligible", True))), "")
            if not preferred:
                preferred = next((str(row.get("character_name") or "") for row in rows if bool(row.get("eligible", True))), names[0])
            self.npc_attacker_char_var.set(preferred)
        self._refresh_npc_attacker_status()

    def _use_linked_character_as_attacker(self) -> None:
        uid = str(self.link_info.get("user_id") or self.remote_state.get("user_id") or "").strip()
        char_name = str(self.remote_character.get("name") or self.remote_state.get("active_character") or "").strip()
        if not uid or not char_name:
            messagebox.showwarning("NPC Attacker", "Pair the Desktop with Sam.py and load the linked character before using this shortcut.")
            return
        label = next((label for label, candidate_uid in self.npc_attacker_player_ids.items() if candidate_uid == uid), uid)
        self.npc_attacker_player_var.set(label)
        self.npc_attacker_char_var.set(char_name)
        self.npc_attacker_mode_var.set("verified")
        self._on_npc_attacker_player_selected(None)

    def _refresh_npc_attacker_status(self) -> None:
        if not hasattr(self, "npc_attacker_status_label"):
            return
        api = self.sam_api_version or "unknown"
        api_ok = self._version_tuple(api) >= self._version_tuple(OSC_API_MINIMUM) if api != "unknown" else False
        mode = str(self.npc_attacker_mode_var.get() or "verified").lower()
        player_text = str(self.npc_attacker_player_var.get() or "").strip()
        uid = str(self.npc_attacker_player_ids.get(player_text) or player_text).strip()
        char_name = str(self.npc_attacker_char_var.get() or "").strip()
        if mode == "fallback":
            text = "Compatibility fallback selected. Sam.py will use an equal-level benchmark that does not scale from NPC HP, but it will not use a real player's ATK/MAG/SPD."
            color = THEME["yellow"]
        elif uid.isdigit() and char_name:
            text = f"Verified attacker requested: {char_name} ({uid}). Sam.py reads that character's current stats and eligibility from players.json; the Desktop sends identity only."
            color = THEME["green"] if api_ok else THEME["yellow"]
        else:
            text = "Verified mode requires a numeric Discord user ID and exact character name. Refresh Rosters for selectors, or enter them manually."
            color = THEME["red"]
        if api != "unknown" and not api_ok:
            text += f" Connected OSC API {api} is older than the required {OSC_API_MINIMUM}."
            color = THEME["red"]
        elif api != "unknown":
            text += f" Connected OSC API: {api}; recommended for roster selectors: {OSC_API_RECOMMENDED}."
        self.npc_attacker_status_label.configure(text=text, foreground=color)

    def _update_npc_hit_diagnostics(self, result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return
        model = str(result.get("damage_model") or "")
        if "npc" not in model:
            return
        self.npc_last_hit_diagnostics = dict(result)
        attacker = result.get("attacker") if isinstance(result.get("attacker"), dict) else {}
        attacker_stats = result.get("attacker_stats") if isinstance(result.get("attacker_stats"), dict) else {}
        target = result.get("target_stats") if isinstance(result.get("target_stats"), dict) else {}
        name = str(attacker.get("name") or attacker.get("character_name") or "Compatibility fallback")
        eligibility = str(attacker.get("reason") or "ok")
        amount = int(result.get("damage", 0) or 0)
        tier = str(result.get("hit_type") or result.get("tier") or "average").title()
        text = (
            f"Last hit: {tier} • {amount:,} damage • model {model} • attacker {name} ({eligibility}) • "
            f"ATK {int(attacker_stats.get('atk', 0) or 0)} / MAG {int(attacker_stats.get('mag', 0) or 0)} / SPD {int(attacker_stats.get('spd', 0) or 0)} • "
            f"target Lv {int(target.get('level', 1) or 1)} / DEF {int(target.get('def', 0) or 0)} / RES {int(target.get('res', 0) or 0)} • mitigation {float(result.get('mitigation_percent', 0) or 0):.1f}%"
        )
        self.npc_hit_diagnostics_label.configure(text=text, foreground=THEME["green"] if bool(result.get("applied", False)) else THEME["yellow"])

    def _populate_recovery(self, options: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        self.recovery_options = [x for x in options if isinstance(x, dict)]
        self.recovery_by_row.clear()
        for row in self.recovery_tree.get_children():
            self.recovery_tree.delete(row)
        for option in self.recovery_options:
            kind = str(option.get("kind") or "").title()
            name = str(option.get("name") or "")
            effect = str(option.get("effect_text") or "")
            cost = str(option.get("cost_text") or "—")
            available = str(option.get("available_text") or "")
            row = self.recovery_tree.insert("", tk.END, values=(kind, name, effect, cost, available))
            self.recovery_by_row[row] = option
        missing_hp = int(payload.get("missing_hp", 0) or 0)
        missing_mp = int(payload.get("missing_mp", 0) or 0)
        self.recovery_summary_label.configure(text=f"Missing HP: {missing_hp:,}   •   Missing MP: {missing_mp:,}   •   Values include owned item lores and equipment effects.")
        self.recovery_notice_label.configure(text=f"{len(self.recovery_options)} recovery option(s) available.")

    def _restore_avatar_after_rejection(self, state: dict[str, Any], sync_result: dict[str, Any]) -> None:
        char = state.get("character") if isinstance(state.get("character"), dict) else {}
        hp = max(0, int(char.get("hp", 0) or 0))
        max_hp = max(1, int(char.get("max_hp", max(hp, 1)) or 1))
        self.state.set_hp(hp)
        self.output_cache.clear()
        self.controller.sync_outputs()
        bridge = self.config.get("avatar_bridge", {})
        health_parameter = str(bridge.get("health_parameter", "Health") or "Health").strip()
        if health_parameter:
            ratio = max(0.0, min(1.0, hp / max_hp))
            value = 1.0 - ratio if bool(bridge.get("health_invert", True)) else ratio
            self._send_parameter(health_parameter, value)
        rejected = {str(x).lower() for x in sync_result.get("rejected_events", []) if str(x)}
        params = bridge.get("status_parameters", {})
        if isinstance(params, dict):
            for name in ("burn", "bleed", "silence", "freeze", "bind"):
                if f"status:{name}" in rejected and str(params.get(name) or "").strip():
                    self._send_parameter(str(params[name]), False)

    def _apply_sam_state(self, state: dict[str, Any], *, source: str, force: bool) -> None:
        char = state.get("character")
        if not isinstance(char, dict):
            return
        self.remote_state = dict(state)
        self.remote_character = dict(char)
        osc_state = state.get("osc") if isinstance(state.get("osc"), dict) else {}
        for param_key, value_key in (("enemy_mode", "enemy_mode"), ("mist_charge", "mist_charge"), ("mist_max", "mist_max"), ("mist_percent", "mist_percent"), ("diablos_applicable", "diablos_applicable"), ("diablos_percent", "diablos_percent")):
            parameter = str(self.config.get("parameters", {}).get(param_key) or "").strip()
            if not parameter:
                continue
            value = osc_state.get(value_key, False if "applicable" in value_key or "enemy" in value_key else 0)
            if param_key == "enemy_mode":
                npc_active = str(state.get("profile_mode") or "player") == "npc"
                if npc_active:
                    value = True
                pending = self.enemy_mode_pending_value
                if pending is not None:
                    if bool(value) == bool(pending):
                        self.enemy_mode_pending_value = None
                        self.enemy_mode_pending_until = 0.0
                    elif time.monotonic() < self.enemy_mode_pending_until:
                        continue
                    else:
                        self.enemy_mode_pending_value = None
                        self.enemy_mode_pending_until = 0.0
            if param_key == "diablos_percent":
                # The VPS stores 0..100, while the avatar radial Float expects 0..1.
                value = float(percent_to_avatar_float(value))
            elif param_key == "mist_percent":
                try:
                    value = max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    value = 0.0
            self._send_parameter(parameter, value)
        rejected_heal = bool(osc_state.get("healing_rejected", False))
        if rejected_heal:
            parameter = str(self.config.get("parameters", {}).get("healing_rejected") or "").strip()
            if parameter:
                self._pulse_parameter(parameter, 0.25)
        name = str(char.get("name") or state.get("active_character") or "Unknown")
        hp = max(0, int(char.get("hp", 0) or 0))
        max_hp = max(1, int(char.get("max_hp", max(hp, 1)) or 1))
        self.remote_mp = max(0, int(char.get("mp", 0) or 0))
        self.remote_max_mp = max(0, int(char.get("max_mp", self.remote_mp) or 0))
        revision = int(state.get("revision", 0) or 0)
        self.sam_last_revision = max(self.sam_last_revision, revision)
        gate = state.get("dm_gate") if isinstance(state.get("dm_gate"), dict) else {}
        self.sam_last_dm_gate_active = bool(gate.get("active", False))

        cfg = self.config.get("sam", {})
        if bool(cfg.get("pull_remote_changes", True)) and not (source == "poll" and (self.sam_local_dirty or self.sam_sync_inflight) and not force):
            npc_active = str(state.get("profile_mode") or "player") == "npc"
            if not npc_active:
                self.config["profile"]["name"] = name
                self.config["profile"]["maximum_hp"] = max_hp
            self.state.reconfigure(
                maximum_hp=max_hp,
                damage_values=self.config["combat"]["damage"],
                invulnerability_seconds=self.config["combat"]["global_invulnerability_seconds"],
                critical_hp_percent=self.config["profile"].get("critical_hp_percent", 0.15),
                status_rules=self.config["statuses"],
                preserve_ratio=False,
            )
            self.state.set_hp(hp)
            if bool(cfg.get("sync_combat_toggle", True)):
                enabled = bool(state.get("combat_enabled", self.state.combat_enabled))
                if enabled != self.state.combat_enabled:
                    self.state.set_combat_enabled(enabled)
            names = {str(x).strip().lower() for x in char.get("status_names", [])}
            self.state.replace_authoritative_statuses(
                names.intersection({"burn", "bleed", "silence", "freeze", "bind"})
            )
            self.output_cache.clear()
            self.controller.sync_outputs()
            self._send_parameter(self.config["parameters"]["combat_enabled"], self.state.combat_enabled)
            bridge = self.config.get("avatar_bridge", {})
            if bool(cfg.get("drive_avatar_health_from_sam", False)):
                ratio = max(0.0, min(1.0, hp / max_hp))
                value = 1.0 - ratio if bool(bridge.get("health_invert", True)) else ratio
                self._send_parameter(str(bridge.get("health_parameter") or "Health"), value)
            if bool(cfg.get("drive_avatar_statuses_from_sam", False)):
                params = bridge.get("status_parameters", {})
                if isinstance(params, dict):
                    for status_name in ("burn", "bleed", "silence", "freeze", "bind"):
                        if str(params.get(status_name) or "").strip():
                            self._send_parameter(str(params[status_name]), status_name in names)
                signature = ",".join(sorted(names.intersection({"burn", "bleed", "silence", "freeze", "bind"})))
                if signature != self.sam_status_handoff_signature:
                    self.sam_status_handoff_signature = signature
        status_events = state.get("status_events") if isinstance(state.get("status_events"), list) else []
        for row in status_events:
            if not isinstance(row, dict):
                continue
            event_id = str(row.get("id") or "").strip()
            if not event_id or event_id in self.sam_seen_status_event_ids:
                continue
            self.sam_seen_status_event_ids.add(event_id)
            self.sam_seen_status_event_order.append(event_id)
            while len(self.sam_seen_status_event_order) > 200:
                stale = self.sam_seen_status_event_order.pop(0)
                self.sam_seen_status_event_ids.discard(stale)
            event_name = str(row.get("event") or "status").casefold()
            label = "STATUS"
            if event_name in {"dot_tick", "ko"}:
                label = "DAMAGE" if event_name == "dot_tick" else "KO"
            elif event_name == "hot_tick":
                label = "HEALING"
            self._append_activity(label, str(row.get("message") or "Status updated."))

        self._refresh_ui()

    # ------------------------------------------------------------------
    # Updates and settings
    # ------------------------------------------------------------------
    def _show_update_progress(self, message: str, percent: float = 0.0) -> None:
        if not self.update_progress_visible:
            self.update_progress_frame.pack(side=tk.RIGHT, padx=(8, 0), pady=10, before=self.update_button)
            self.update_progress_visible = True
        self.update_progress_label.configure(text=str(message or "Working…"))
        self.update_progress_bar.configure(value=max(0.0, min(100.0, float(percent))))

    def _hide_update_progress(self, delay_ms: int = 800) -> None:
        def hide() -> None:
            if self.update_progress_visible:
                self.update_progress_frame.pack_forget()
                self.update_progress_visible = False
        self.root.after(max(0, int(delay_ms)), hide)

    def _automatic_update_tick(self) -> None:
        if self.closing:
            return
        updates = self.config.get("updates", {})
        interval_hours = max(1.0, float(updates.get("check_interval_hours", 6.0) or 6.0))
        if bool(updates.get("check_on_start", True)) and not self.update_manager.busy:
            self.check_for_updates(automatic=True)
        self.root.after(int(interval_hours * 60 * 60 * 1000), self._automatic_update_tick)

    def check_for_updates(self, automatic: bool = False) -> None:
        updates = self.config.get("updates", {})
        repo = str(updates.get("github_repo") or "StarhunterUC/Stories-Of-Yggdrasil-OSC").strip()
        self.update_check_automatic = bool(automatic)
        self.update_button.configure(text="Checking…", command=self.check_for_updates)
        self._show_update_progress("Checking for updates…", 2)
        self.update_manager.check(repo, str(updates.get("asset_pattern") or ""))

    def _handle_update_event(self, event: UpdateEvent) -> None:
        if event.kind == "update_progress":
            self._show_update_progress(event.message, float(event.data.get("percent", 0) or 0))
            return
        if event.kind == "update_available":
            self.latest_release = dict(event.data)
            version = str(event.data.get("latest_version") or "new")
            self.update_button.configure(
                text=f"Install update {version}",
                style="Green.TButton",
                command=self.install_available_update,
                state=tk.NORMAL,
            )
            self._show_update_progress(f"Version {version} is available.", 100)
            self._hide_update_progress(2200)
            self._append_activity("UPDATE", f"Version {version} is available. Click Install update to begin.")
        elif event.kind == "update_current":
            self.update_button.configure(text="Up to date", style="TButton", command=self.check_for_updates, state=tk.NORMAL)
            self._show_update_progress("The application is up to date.", 100)
            self._hide_update_progress(1200)
        elif event.kind == "update_ready":
            script = str(event.data.get("script") or "")
            version = str(event.data.get("version") or self.latest_release.get("latest_version") or "new")
            try:
                self._show_update_progress(f"Launching the {version} installer…", 100)
                UpdateManager.launch_installer(script)
                self.root.after(350, self.close)
            except Exception as exc:
                self.update_button.configure(text="Install update", style="Green.TButton", command=self.install_available_update)
                self._hide_update_progress(0)
                messagebox.showerror("Update", str(exc))
        else:
            self.update_button.configure(text="Update check unavailable", style="TButton", command=self.check_for_updates, state=tk.NORMAL)
            self._hide_update_progress(0)
            if event.message and "not configured" not in event.message.lower():
                self._append_activity("UPDATE", event.message)
                if not self.update_check_automatic:
                    messagebox.showwarning("Update Check", event.message)

    def install_available_update(self) -> None:
        if not self.latest_release:
            self.check_for_updates(automatic=False)
            return
        version = str(self.latest_release.get("latest_version") or "new")
        notes = str(self.latest_release.get("release_notes") or "").strip()
        summary = notes[:700] + ("…" if len(notes) > 700 else "")
        if not messagebox.askyesno(
            "Install Update",
            f"Install Stories Of Yggdrasil OSC {version}?\n\n{summary}\n\nA progress window will remain visible while the application files are replaced.",
        ):
            return
        self.update_button.configure(text="Downloading update…", state=tk.DISABLED)
        self._show_update_progress("Starting update download…", 1)
        self.update_manager.download_and_install(self.latest_release)

    def save_settings(self) -> None:
        try:
            osc = self.config["osc"]
            osc["listen_ip"] = str(self.listen_ip_var.get()).strip() or "127.0.0.1"
            osc["listen_port"] = int(self.listen_port_var.get())
            osc["vrchat_ip"] = str(self.vrchat_ip_var.get()).strip() or "127.0.0.1"
            osc["vrchat_port"] = int(self.vrchat_port_var.get())
            osc["auto_start_listener"] = bool(self.auto_start_var.get())
            for key, var in self.damage_vars.items():
                self.config["combat"]["damage"][key] = max(0, int(var.get()))
            bridge = self.config["avatar_bridge"]
            bridge["input_mode"] = str(self.input_mode_var.get())
            bridge["observe_health"] = bool(self.observe_health_var.get())
            bridge["health_invert"] = bool(self.health_invert_var.get())
            sam = self.config["sam"]
            sam["drive_avatar_health_from_sam"] = bool(self.drive_health_var.get())
            sam["drive_avatar_statuses_from_sam"] = bool(self.drive_status_var.get())
            npc_cfg = self.config.setdefault("npc_mode", {})
            npc_enabled = bool(self.npc_mode_var.get())
            npc_name = str(self.npc_enemy_var.get()).strip()
            npc_row = self.npc_by_name.get(npc_name, {})
            npc_key = str(npc_row.get("key") or npc_cfg.get("enemy_key") or "")
            if npc_enabled and not npc_key:
                raise ValueError("Select an NPC from the Sam.py roster before enabling NPC Mode.")

            attacker_mode = str(self.npc_attacker_mode_var.get() or "verified").lower()
            if attacker_mode not in {"verified", "fallback"}:
                attacker_mode = "verified"
            player_text = str(self.npc_attacker_player_var.get() or "").strip()
            attacker_user_id = str(self.npc_attacker_player_ids.get(player_text) or player_text).strip()
            attacker_char_name = str(self.npc_attacker_char_var.get() or "").strip()
            if attacker_mode == "verified" and npc_enabled:
                if not attacker_user_id or not attacker_user_id.isdigit():
                    raise ValueError("Verified Player → NPC damage requires the attacking player's numeric Discord ID or a player selected from the Sam.py attacker roster.")
                if not attacker_char_name:
                    raise ValueError("Verified Player → NPC damage requires an attacking character.")
                selected = next((row for row in self.npc_attacker_roster if str(row.get("user_id") or "") == attacker_user_id and str(row.get("character_name") or "").casefold() == attacker_char_name.casefold()), None)
                if isinstance(selected, dict) and not bool(selected.get("eligible", True)):
                    raise ValueError(str(selected.get("unavailable_reason") or "That attacker is not eligible to attack."))

            npc_cfg["enabled"] = npc_enabled
            npc_cfg["enemy_name"] = npc_name
            npc_cfg["enemy_key"] = npc_key
            npc_cfg["attacker_mode"] = attacker_mode
            npc_cfg["attacker_user_id"] = attacker_user_id if attacker_mode == "verified" else ""
            npc_cfg["attacker_char_name"] = attacker_char_name if attacker_mode == "verified" else ""
            npc_cfg["attacker_player_label"] = player_text if attacker_mode == "verified" else ""
            updates = self.config["updates"]
            updates["github_repo"] = str(self.github_repo_var.get()).strip()
            updates["check_on_start"] = bool(self.update_on_start_var.get())
            save_config(self.config)
            was_running = self.osc.running
            self.osc.reconfigure(listen_ip=osc["listen_ip"], listen_port=osc["listen_port"], vrchat_ip=osc["vrchat_ip"], vrchat_port=osc["vrchat_port"], restart=was_running)
            self.state.reconfigure(
                maximum_hp=self.config["profile"]["maximum_hp"],
                damage_values=self.config["combat"]["damage"],
                invulnerability_seconds=self.config["combat"]["global_invulnerability_seconds"],
                critical_hp_percent=self.config["profile"].get("critical_hp_percent", 0.15),
                status_rules=self.config["statuses"],
                preserve_ratio=True,
            )
            self.controller.reconfigure(self.config)
            self.sam_client.reconfigure(sam)
            if npc_enabled:
                self._send_parameter(self.config["parameters"]["enemy_mode"], True)
                self.controller.telemetry["enemy_mode"] = True
            self._schedule_sam_sync("npc_mode", immediate=True, vrc_trigger=False)
            self._refresh_npc_attacker_status()
            messagebox.showinfo("Settings", "Settings saved and applied.")
        except Exception as exc:
            messagebox.showerror("Settings", f"Could not apply settings.\n\n{exc}")

    # ------------------------------------------------------------------
    # UI refresh and persistence
    # ------------------------------------------------------------------
    def _refresh_loop(self) -> None:
        if self.closing:
            return
        self._refresh_ui()
        try:
            minimized = self.root.state() == "iconic"
        except Exception:
            minimized = False
        self.root.after(1500 if minimized else 500, self._refresh_loop)

    def _refresh_ui(self) -> None:
        snap = self.state.snapshot()
        hp = int(snap["current_hp"])
        max_hp = int(snap["maximum_hp"])
        osc_state_for_signature = (
            self.remote_state.get("osc")
            if isinstance(self.remote_state.get("osc"), dict)
            else {}
        )
        gate_for_signature = (
            self.remote_state.get("dm_gate")
            if isinstance(self.remote_state.get("dm_gate"), dict)
            else {}
        )
        char_for_signature = self.remote_character or {}
        recent_for_signature = bool(
            self.controller.last_input_at
            and (
                time.monotonic() - self.controller.last_input_at
                <= float(
                    self.config["osc"].get(
                        "activity_timeout_seconds",
                        5.0,
                    )
                )
            )
        )
        ui_signature = (
            hp,
            max_hp,
            int(self.remote_mp),
            int(self.remote_max_mp),
            bool(snap.get("combat_enabled")),
            tuple(sorted(str(x) for x in (snap.get("statuses") or {}).keys())),
            int(self.remote_state.get("revision", -1) or -1),
            bool(gate_for_signature.get("active", False)),
            tuple(str(x) for x in gate_for_signature.get("dm_names", []) if str(x)),
            bool(self.osc.running),
            recent_for_signature,
            self.last_avatar_id,
            str(char_for_signature.get("name") or ""),
            int(char_for_signature.get("level", 0) or 0),
            str(char_for_signature.get("class") or ""),
            tuple(str(x) for x in char_for_signature.get("classes", []) if str(x)),
            str(char_for_signature.get("race") or ""),
            str(char_for_signature.get("region") or ""),
            bool(osc_state_for_signature.get("diablos_applicable", False)),
            round(coerce_percent(osc_state_for_signature.get("diablos_percent", 0)), 3),
            bool(str(self.config.get("sam", {}).get("token") or "").strip()),
            repr(self.remote_state.get("combat_profile", {})),
        )
        if ui_signature == self._last_ui_signature:
            return
        self._last_ui_signature = ui_signature
        self.hp_bar.configure(value=float(snap["hp_ratio"]) * 100.0)
        self.hp_value_label.configure(text=f"{hp:,} / {max_hp:,}")
        mp_ratio = self.remote_mp / self.remote_max_mp if self.remote_max_mp else 0.0
        self.mp_bar.configure(value=max(0.0, min(100.0, mp_ratio * 100.0)))
        self.mp_value_label.configure(text=f"{self.remote_mp:,} / {self.remote_max_mp:,}")

        osc_state = self.remote_state.get("osc") if isinstance(self.remote_state.get("osc"), dict) else {}
        diablos_applicable = bool(osc_state.get("diablos_applicable", False))
        diablos_percent = coerce_percent(osc_state.get("diablos_percent", 0))
        if diablos_applicable:
            if not self.diablos_frame.winfo_manager():
                self.diablos_frame.pack(fill=tk.X, padx=22, pady=(0, 10), before=self.combat_toggle_row)
            self.diablos_bar.configure(value=diablos_percent)
            self.diablos_value_label.configure(text=f"{diablos_percent:.0f}%")
            warning_text = diablos_warning_label(diablos_percent)
            self.diablos_warning_label.configure(text=warning_text, foreground=THEME["red"] if diablos_percent >= 25 else THEME["muted"])
            style_name = "DiablosCritical.Horizontal.TProgressbar" if diablos_percent >= 90 else "DiablosWarn.Horizontal.TProgressbar" if diablos_percent >= 25 else "Diablos.Horizontal.TProgressbar"
            self.diablos_bar.configure(style=style_name)
        elif self.diablos_frame.winfo_manager():
            self.diablos_frame.pack_forget()

        self.combat_var.set(bool(snap["combat_enabled"]))

        char = self.remote_character
        if char:
            name = str(char.get("name") or self.remote_state.get("active_character") or "Unknown")
            classes = char.get("classes") if isinstance(char.get("classes"), list) else []
            class_text = " / ".join(str(x) for x in classes if x and str(x) != "None") or str(char.get("class") or "—")
            self.character_name_label.configure(text=name)
            self.character_meta_label.configure(text=f"Level {int(char.get('level', 1) or 1)}  •  {class_text}  •  {char.get('race') or 'Unknown'}  •  {char.get('region') or 'Unknown'}")
        else:
            self.character_name_label.configure(text=str(self.config["profile"].get("name") or "Local Character"))
            self.character_meta_label.configure(text="Pair with Sam.py to load class, race, MP, inventory, and recovery options.")

        profile = self.remote_state.get("combat_profile") if isinstance(self.remote_state.get("combat_profile"), dict) else {}
        stats = profile.get("stats") if isinstance(profile.get("stats"), dict) else {}
        if stats:
            self.combat_stats_label.configure(text="  •  ".join(f"{key} {int(stats.get(key, 0) or 0)}" for key in ("ATK", "DEF", "MAG", "RES", "SPD", "EVA", "VIT")))
        else:
            self.combat_stats_label.configure(text="ATK —  DEF —  MAG —  RES —  SPD —  EVA —  VIT —")
        affinities = profile.get("affinities") if isinstance(profile.get("affinities"), dict) else {}
        affinity_text = ", ".join(f"{name}: {relation.title()}" for name, relation in sorted(affinities.items())) or "None reported"
        self.affinities_label.configure(text=f"Affinities: {affinity_text}")
        magicks = profile.get("magicks") if isinstance(profile.get("magicks"), list) else []
        magick_names = [f"{row.get('name')} ({row.get('mp_cost', 0)} MP)" for row in magicks[:8] if isinstance(row, dict)]
        extra = f" +{len(magicks)-8} more" if len(magicks) > 8 else ""
        self.magicks_profile_label.configure(text="Magicks: " + (", ".join(magick_names) + extra if magick_names else "None available or profile pending"))
        if hasattr(self, "action_availability_label"):
            blockers = profile.get("casting_blockers") if isinstance(profile.get("casting_blockers"), list) else []
            tech_count = len(profile.get("technicks") or []) if isinstance(profile.get("technicks"), list) else 0
            self.action_availability_label.configure(text=f"Authoritative profile: {len(magicks)} Magick(s), {tech_count} Technick(s). Casting blockers: {', '.join(blockers) if blockers else 'None'}.")
        self._refresh_diagnostics_view()

        active = snap.get("statuses", {})
        for key, label in self.status_labels.items():
            label.configure(style="StatusOn.TLabel" if key in active else "StatusOff.TLabel")
        gate = self.remote_state.get("dm_gate") if isinstance(self.remote_state.get("dm_gate"), dict) else {}
        if bool(gate.get("active", False)):
            names = ", ".join(str(x) for x in gate.get("dm_names", []) if str(x))
            self.dm_gate_label.configure(text=f"Dungeon Master Gate: ACTIVE{(' — ' + names) if names else ''}", foreground=THEME["green"])
        else:
            self.dm_gate_label.configure(text="Dungeon Master Gate: CLOSED — incoming damage will be rejected", foreground=THEME["red"])

        running = bool(self.osc.running)
        listener_text = f"Listening {self.osc.listen_ip}:{self.osc.listen_port}" if running else "Listener stopped"
        self.listener_status_label.configure(text=listener_text, foreground=THEME["green"] if running else THEME["muted"])
        self.footer_listener.configure(text=f"OSC: {listener_text}", foreground=THEME["green"] if running else THEME["muted"])
        recent = self.controller.last_input_at and (time.monotonic() - self.controller.last_input_at) <= float(self.config["osc"].get("activity_timeout_seconds", 5.0))
        self.activity_status_label.configure(text="VRChat activity: active" if recent else "VRChat activity: waiting", foreground=THEME["green"] if recent else THEME["muted"])
        self.avatar_status_label.configure(text=f"Avatar: {self._short_avatar(self.last_avatar_id)}")
        paired = bool(str(self.config.get("sam", {}).get("token") or "").strip())
        self.footer_sam.configure(text=f"Sam.py: {'paired' if paired else 'not paired'}", foreground=THEME["green"] if paired else THEME["muted"])

    @staticmethod
    def _rotate_activity_log(max_bytes: int = 5 * 1024 * 1024, keep: int = 3) -> None:
        path = get_log_path()
        try:
            if not path.exists() or path.stat().st_size < max_bytes:
                return
            keep = max(1, int(keep))
            oldest = path.with_name(path.name + f".{keep}")
            if oldest.exists():
                oldest.unlink()
            for index in range(keep - 1, 0, -1):
                source = path.with_name(path.name + f".{index}")
                target = path.with_name(path.name + f".{index + 1}")
                if source.exists():
                    source.replace(target)
            path.replace(path.with_name(path.name + ".1"))
        except Exception:
            pass

    def _append_activity(self, category: str, message: str) -> None:
        self.last_event = str(message)
        stamp = datetime.now().strftime("%H:%M:%S")
        row = {"time": stamp, "type": str(category), "event": str(message)}
        self.event_rows.append(row)
        self.event_rows = self.event_rows[-100:]
        try:
            self.event_tree.insert("", 0, values=(stamp, category, message))
            for item in self.event_tree.get_children()[60:]:
                self.event_tree.delete(item)
        except Exception:
            pass
        try:
            self._rotate_activity_log()
            with get_log_path().open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] [{category}] {message}\n")
        except Exception:
            pass

    def clear_activity(self) -> None:
        self.event_rows.clear()
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)
        try:
            get_log_path().write_text("", encoding="utf-8")
        except Exception:
            pass

    def _autosave_tick(self) -> None:
        if self.closing:
            return
        payload = {
            "current_hp": int(self.state.current_hp),
            "combat_enabled": bool(self.state.combat_enabled),
        }
        if payload != self._last_saved_runtime_state:
            save_runtime_state(payload)
            self._last_saved_runtime_state = dict(payload)
        self.root.after(1000, self._autosave_tick)

    def open_settings_folder(self) -> None:
        path = get_app_data_dir()
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showinfo("Settings Folder", f"{path}\n\n{exc}")

    @staticmethod
    def _short_avatar(value: str) -> str:
        return value if len(value) <= 28 else value[:14] + "…" + value[-10:]

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        payload = {
            "current_hp": int(self.state.current_hp),
            "combat_enabled": bool(self.state.combat_enabled),
        }
        save_runtime_state(payload)
        self._last_saved_runtime_state = dict(payload)
        try: self.osc.stop()
        except Exception: pass
        try: self.sam_client.stop()
        except Exception: pass
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    StoriesOSCApp(root)
    root.mainloop()
