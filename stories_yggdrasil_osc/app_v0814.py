from __future__ import annotations

import os
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from . import OSC_API_MINIMUM, OSC_API_RECOMMENDED, __version__
from .app import THEME, StoriesOSCApp
from .config import (
    get_app_data_dir,
    get_log_path,
    save_config,
    save_runtime_state,
)
from .qol import (
    action_key,
    append_grouped_activity,
    build_action_catalog,
    clamp_ui_scale,
    create_support_bundle as build_support_bundle,
    filter_actions,
    filter_activity,
    filter_npcs,
    safe_window_geometry,
    should_suppress_activity_repeat,
)


class StoriesOSCAppV0814(StoriesOSCApp):
    """v0.8.14 daily-use QOL layer over the stable v0.8.12 bridge."""

    def __init__(self, root: tk.Tk) -> None:
        try:
            self._base_tk_scaling = float(root.tk.call("tk", "scaling"))
        except Exception:
            self._base_tk_scaling = 1.3333333333
        self.current_page = "dashboard"
        self.last_sam_success_epoch = 0.0
        self._ui_dirty = False
        self._last_action_signature: tuple[Any, ...] | None = None
        self._activity_view_suspended = False
        self.action_catalog: list[dict[str, Any]] = []
        self.action_by_row: dict[str, dict[str, Any]] = {}
        super().__init__(root)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self._mark_ui_dirty()

    # ------------------------------------------------------------------
    # UI state and visual setup
    # ------------------------------------------------------------------
    def _ui(self) -> dict[str, Any]:
        return self.config.setdefault("ui", {})

    def _setup_styles(self) -> None:
        ui = self.config.setdefault("ui", {})
        scale = clamp_ui_scale(ui.get("scale", 1.0))
        try:
            self.root.tk.call("tk", "scaling", self._base_tk_scaling * scale)
        except Exception:
            pass
        super()._setup_styles()
        style = ttk.Style()
        style.configure("NavSelected.TButton", background="#2a2518", foreground=THEME["gold2"], borderwidth=0)
        style.map("NavSelected.TButton", background=[("active", "#39301c")])
        style.configure("Strip.TFrame", background=THEME["panel2"])
        style.configure("Strip.TLabel", background=THEME["panel2"], foreground=THEME["muted"], font=("Segoe UI Semibold", 8))
        style.configure("StripOn.TLabel", background="#183827", foreground="#75e69f", padding=(8, 4), font=("Segoe UI Semibold", 8))
        style.configure("StripWarn.TLabel", background="#4a3815", foreground="#f5d879", padding=(8, 4), font=("Segoe UI Semibold", 8))
        style.configure("StripOff.TLabel", background="#442126", foreground="#f28a91", padding=(8, 4), font=("Segoe UI Semibold", 8))

    def _build_ui(self) -> None:
        requested_page = str(self._ui().get("last_page") or "dashboard")
        geometry = safe_window_geometry(self._ui().get("window_geometry"), "1220x760")
        try:
            self.root.geometry(geometry)
        except Exception:
            pass
        super()._build_ui()
        if requested_page in self.pages:
            self.show_page(requested_page)

    def _build_topbar(self) -> None:
        top = ttk.Frame(self.content, style="Panel.TFrame")
        top.pack(fill=tk.X, padx=22, pady=(18, 16))

        main = ttk.Frame(top, style="Panel.TFrame")
        main.pack(fill=tk.X)
        brand = ttk.Frame(main, style="Panel.TFrame")
        brand.pack(side=tk.LEFT, padx=18, pady=(12, 8))
        ttk.Label(brand, text="Stories Of Yggdrasil OSC", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"Version {__version__}", style="Version.TLabel").pack(anchor="w")

        self.update_button = ttk.Button(main, text="Check for updates", command=self.check_for_updates)
        self.update_button.pack(side=tk.RIGHT, padx=(8, 18), pady=12)
        ttk.Button(main, text="Reconnect All", command=self.reconnect_all).pack(side=tk.RIGHT, padx=4, pady=12)
        ttk.Button(main, text="Copy Diagnostics", command=self.copy_diagnostic_summary).pack(side=tk.RIGHT, padx=4, pady=12)
        self.update_progress_frame = ttk.Frame(main, style="Panel.TFrame")
        self.update_progress_frame.pack(side=tk.RIGHT, padx=(8, 0), pady=8)
        self.update_progress_label = ttk.Label(self.update_progress_frame, text="", style="Muted.Panel.TLabel")
        self.update_progress_label.pack(anchor="e")
        self.update_progress_bar = ttk.Progressbar(self.update_progress_frame, mode="determinate", maximum=100, length=190)
        self.update_progress_bar.pack(anchor="e", pady=(3, 0))
        self.update_progress_frame.pack_forget()

        strip = ttk.Frame(top, style="Strip.TFrame")
        strip.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.global_status_labels: dict[str, ttk.Label] = {}
        for key, text in (
            ("sam", "SAM —"),
            ("vrchat", "VRCHAT —"),
            ("avatar", "AVATAR —"),
            ("combat", "RP COMBAT —"),
            ("gate", "DM GATE —"),
            ("api", "API —"),
            ("sync", "SYNC —"),
        ):
            label = ttk.Label(strip, text=text, style="Strip.TLabel")
            label.pack(side=tk.LEFT, padx=3, pady=4)
            self.global_status_labels[key] = label

    def show_page(self, key: str) -> None:
        if not hasattr(self, "pages") or key not in self.pages:
            return
        super().show_page(key)
        self.current_page = key
        for nav_key, button in self.nav_buttons.items():
            button.configure(style="NavSelected.TButton" if nav_key == key else "Nav.TButton")
        self._ui()["last_page"] = key
        self._mark_ui_dirty()
        if key == "actions":
            self._refresh_action_tree()
        elif key == "npc":
            self._refresh_npc_values()
        elif key == "dashboard":
            self._refresh_activity_view(force=True)

    # ------------------------------------------------------------------
    # Dashboard and activity QOL
    # ------------------------------------------------------------------
    def _build_overview_page(self) -> ttk.Frame:
        page = super()._build_overview_page()
        right = self.event_tree.master
        toolbar = ttk.Frame(right, style="CardInner.TFrame")
        toolbar.pack(fill=tk.X, padx=18, pady=(0, 8), before=self.event_tree)

        ui = self._ui()
        self.activity_filter_var = tk.StringVar(value=str(ui.get("activity_filter") or "All"))
        self.activity_search_var = tk.StringVar(value=str(ui.get("activity_search") or ""))
        self.activity_paused_var = tk.BooleanVar(value=bool(ui.get("activity_paused", False)))

        ttk.Label(toolbar, text="Filter", style="Muted.Card.TLabel").pack(side=tk.LEFT)
        self.activity_filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.activity_filter_var,
            values=("All", "SYSTEM", "SAM", "SAM ERROR", "DAMAGE", "HEAL", "HEALING", "STATUS", "BLOCK", "WARNING", "ERROR", "AVATAR", "RECOVERY", "CAST", "TECHNICK", "ITEM"),
            state="readonly",
            width=12,
        )
        self.activity_filter_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.activity_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._activity_controls_changed())
        search = tk.Entry(
            toolbar,
            textvariable=self.activity_search_var,
            bg=THEME["panel3"], fg=THEME["text"], insertbackground=THEME["text"],
            relief=tk.FLAT, width=25,
        )
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.activity_search_var.trace_add("write", lambda *_: self._activity_controls_changed())
        self.activity_pause_button = ttk.Button(toolbar, text="Pause", command=self.toggle_activity_pause)
        self.activity_pause_button.pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(toolbar, text="Clear View", command=self.clear_activity).pack(side=tk.RIGHT, padx=6)
        ttk.Button(toolbar, text="Erase Log", command=self.erase_activity_log).pack(side=tk.RIGHT, padx=6)
        self.event_tree.bind("<Double-1>", lambda _e: self.copy_selected_activity())
        return page

    def _activity_controls_changed(self) -> None:
        self._ui()["activity_filter"] = self.activity_filter_var.get()
        self._ui()["activity_search"] = self.activity_search_var.get()
        self._mark_ui_dirty()
        self._refresh_activity_view(force=True)

    def toggle_activity_pause(self) -> None:
        paused = not bool(self.activity_paused_var.get())
        self.activity_paused_var.set(paused)
        self._ui()["activity_paused"] = paused
        self.activity_pause_button.configure(text="Resume" if paused else "Pause")
        self._mark_ui_dirty()
        if not paused:
            self._refresh_activity_view(force=True)

    def _refresh_activity_view(self, *, force: bool = False) -> None:
        if not hasattr(self, "event_tree"):
            return
        if bool(getattr(self, "activity_paused_var", tk.BooleanVar(value=False)).get()) and not force:
            return
        rows = filter_activity(
            self.event_rows,
            category=self.activity_filter_var.get() if hasattr(self, "activity_filter_var") else "All",
            search=self.activity_search_var.get() if hasattr(self, "activity_search_var") else "",
        )
        selected_values = None
        selected = self.event_tree.selection()
        if selected:
            selected_values = self.event_tree.item(selected[0], "values")
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)
        for row in reversed(rows[-200:]):
            count = int(row.get("count", 1) or 1)
            message = str(row.get("event") or "")
            if count > 1:
                message = f"{message}  ×{count}"
            item = self.event_tree.insert("", tk.END, values=(row.get("time", ""), row.get("type", ""), message))
            if selected_values and tuple(self.event_tree.item(item, "values")) == tuple(selected_values):
                self.event_tree.selection_set(item)

    def _append_activity(self, category: str, message: str) -> None:
        now = time.time()
        if should_suppress_activity_repeat(
            self.event_rows,
            category,
            message,
            now=now,
        ):
            return
        self.last_event = str(message)
        self.event_rows, _row = append_grouped_activity(
            self.event_rows,
            category,
            message,
            now=now,
        )
        self._refresh_activity_view()
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            self._rotate_activity_log()
            with get_log_path().open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] [{category}] {message}\n")
        except Exception:
            pass

    def clear_activity(self) -> None:
        self.event_rows.clear()
        self._refresh_activity_view(force=True)
        self.last_event = "Activity view cleared. The log file was preserved."

    def erase_activity_log(self) -> None:
        if not messagebox.askyesno("Erase Activity Log", "Erase the saved events.log file?\n\nThis does not affect Sam.py or character data."):
            return
        try:
            get_log_path().write_text("", encoding="utf-8")
            self._append_activity("SYSTEM", "Saved activity log erased.")
        except Exception as exc:
            messagebox.showerror("Activity Log", f"Could not erase the activity log.\n\n{exc}")

    def copy_selected_activity(self) -> None:
        selected = self.event_tree.selection() if hasattr(self, "event_tree") else ()
        if not selected:
            return
        values = self.event_tree.item(selected[0], "values")
        text = " | ".join(str(value) for value in values)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ------------------------------------------------------------------
    # Searchable actions, availability reasons, and favorites
    # ------------------------------------------------------------------
    def _build_recovery_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Actions", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Refresh from Sam.py", command=self.refresh_recovery_options).pack(side=tk.RIGHT)
        self.recovery_summary_label = ttk.Label(page, text="Sam.py remains authoritative for costs, restrictions, targets, and cooldowns.", style="Muted.TLabel")
        self.recovery_summary_label.pack(anchor="w", pady=(0, 8))
        self.action_availability_label = ttk.Label(page, text="Unavailable actions stay visible with an exact reason.", style="Muted.TLabel", wraplength=1000, justify="left")
        self.action_availability_label.pack(anchor="w", pady=(0, 8))

        filters = self._card(page)
        filters.pack(fill=tk.X, pady=(0, 10))
        ui = self._ui()
        self.action_search_var = tk.StringVar(value=str(ui.get("action_search") or ""))
        self.action_filter_var = tk.StringVar(value=str(ui.get("action_filter") or "All"))
        self.action_favorites_only_var = tk.BooleanVar(value=bool(ui.get("action_favorites_only", False)))
        ttk.Label(filters, text="Search", style="Card.TLabel").grid(row=0, column=0, padx=(18, 6), pady=12, sticky="w")
        entry = tk.Entry(filters, textvariable=self.action_search_var, bg=THEME["panel3"], fg=THEME["text"], insertbackground=THEME["text"], relief=tk.FLAT)
        entry.grid(row=0, column=1, sticky="ew", pady=12, ipady=6)
        ttk.Label(filters, text="Type", style="Card.TLabel").grid(row=0, column=2, padx=(16, 6), pady=12)
        self.action_filter_combo = ttk.Combobox(filters, textvariable=self.action_filter_var, values=("All", "Consumable", "Item", "Magick", "Technick", "Recovery"), state="readonly", width=14)
        self.action_filter_combo.grid(row=0, column=3, pady=12)
        ttk.Checkbutton(filters, text="Favorites only", variable=self.action_favorites_only_var, command=self._action_filters_changed).grid(row=0, column=4, padx=16, pady=12)
        filters.columnconfigure(1, weight=1)
        self.action_search_var.trace_add("write", lambda *_: self._action_filters_changed())
        self.action_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._action_filters_changed())

        quick = self._card(page)
        quick.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(quick, text="Quick Actions", style="CardTitle.TLabel").pack(anchor="w", padx=18, pady=(12, 4))
        self.quick_actions_frame = ttk.Frame(quick, style="CardInner.TFrame")
        self.quick_actions_frame.pack(fill=tk.X, padx=14, pady=(0, 12))

        card = self._card(page)
        card.pack(fill=tk.BOTH, expand=True)
        self.recovery_tree = ttk.Treeview(card, columns=("fav", "kind", "name", "effect", "cost", "status", "reason"), show="headings")
        for key, title, width in (
            ("fav", "★", 38), ("kind", "Type", 85), ("name", "Action", 170),
            ("effect", "Effect / Target", 220), ("cost", "Cost", 95),
            ("status", "Status", 90), ("reason", "Availability / Reason", 310),
        ):
            self.recovery_tree.heading(key, text=title)
            self.recovery_tree.column(key, width=width, anchor="center" if key in {"fav", "status"} else "w", stretch=key in {"effect", "reason"})
        self.recovery_tree.pack(fill=tk.BOTH, expand=True, padx=18, pady=(18, 10))
        self.recovery_tree.bind("<<TreeviewSelect>>", lambda _e: self._action_selection_changed())
        self.recovery_tree.bind("<Double-1>", lambda _e: self.use_selected_recovery())
        actions = ttk.Frame(card, style="CardInner.TFrame")
        actions.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.recovery_notice_label = ttk.Label(actions, text="Select an action to see whether it can be used from the Desktop.", style="Muted.Card.TLabel", wraplength=720, justify="left")
        self.recovery_notice_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.favorite_action_button = ttk.Button(actions, text="☆ Favorite", command=self.toggle_selected_action_favorite)
        self.favorite_action_button.pack(side=tk.RIGHT, padx=(6, 0))
        self.use_recovery_button = ttk.Button(actions, text="Use Selected", style="Green.TButton", command=self.use_selected_recovery)
        self.use_recovery_button.pack(side=tk.RIGHT)
        return page

    def _populate_recovery(self, options: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        self.recovery_options = [item for item in options if isinstance(item, dict)]
        missing_hp = int(payload.get("missing_hp", 0) or 0)
        missing_mp = int(payload.get("missing_mp", 0) or 0)
        self.recovery_summary_label.configure(text=f"Missing HP: {missing_hp:,}  •  Missing MP: {missing_mp:,}  •  Recovery values include owned lores and equipment effects.")
        self._rebuild_action_catalog()

    def _rebuild_action_catalog(self) -> None:
        profile = self.remote_state.get("combat_profile") if isinstance(self.remote_state.get("combat_profile"), dict) else {}
        favorites = self._ui().get("action_favorites") if isinstance(self._ui().get("action_favorites"), list) else []
        self.action_catalog = build_action_catalog(
            self.recovery_options,
            profile,
            current_mp=self.remote_mp,
            favorites=favorites,
        )
        if hasattr(self, "action_filter_combo"):
            kinds = sorted({str(row.get("kind") or "") for row in self.action_catalog if str(row.get("kind") or "")}, key=str.casefold)
            self.action_filter_combo.configure(values=("All", *kinds))
            if self.action_filter_var.get() not in {"All", *kinds}:
                self.action_filter_var.set("All")
        self._refresh_action_tree()
        self._refresh_quick_actions()

    def _action_filters_changed(self) -> None:
        ui = self._ui()
        ui["action_search"] = self.action_search_var.get()
        ui["action_filter"] = self.action_filter_var.get()
        ui["action_favorites_only"] = bool(self.action_favorites_only_var.get())
        self._mark_ui_dirty()
        self._refresh_action_tree()

    def _refresh_action_tree(self) -> None:
        if not hasattr(self, "recovery_tree"):
            return
        rows = filter_actions(
            self.action_catalog,
            search=self.action_search_var.get() if hasattr(self, "action_search_var") else "",
            kind=self.action_filter_var.get() if hasattr(self, "action_filter_var") else "All",
            favorites_only=bool(self.action_favorites_only_var.get()) if hasattr(self, "action_favorites_only_var") else False,
        )
        selected_key = None
        selected = self.recovery_tree.selection()
        if selected:
            selected_key = self.action_by_row.get(selected[0], {}).get("key")
        self.action_by_row.clear()
        for item in self.recovery_tree.get_children():
            self.recovery_tree.delete(item)
        selected_row = None
        for row in rows:
            item = self.recovery_tree.insert("", tk.END, values=(
                "★" if row.get("favorite") else "",
                row.get("kind", ""), row.get("name", ""), row.get("effect", ""),
                row.get("cost", ""), row.get("status", ""), row.get("reason", ""),
            ))
            self.action_by_row[item] = row
            if row.get("key") == selected_key:
                selected_row = item
        if selected_row:
            self.recovery_tree.selection_set(selected_row)
            self.recovery_tree.see(selected_row)
        self.recovery_notice_label.configure(text=f"Showing {len(rows)} of {len(self.action_catalog)} action(s). Double-click an executable recovery action to use it.")
        self._action_selection_changed()

    def _selected_action(self) -> dict[str, Any] | None:
        selected = self.recovery_tree.selection() if hasattr(self, "recovery_tree") else ()
        return self.action_by_row.get(selected[0]) if selected else None

    def _action_selection_changed(self) -> None:
        row = self._selected_action()
        if not row:
            self.use_recovery_button.state(["disabled"])
            self.favorite_action_button.configure(text="☆ Favorite")
            return
        can_execute = bool(row.get("executable")) and bool(row.get("available"))
        self.use_recovery_button.state(["!disabled"] if can_execute else ["disabled"])
        self.favorite_action_button.configure(text="★ Unfavorite" if row.get("favorite") else "☆ Favorite")
        self.recovery_notice_label.configure(text=str(row.get("reason") or "Ready"))

    def toggle_selected_action_favorite(self) -> None:
        row = self._selected_action()
        if not row:
            return
        key = str(row.get("key") or action_key(row.get("kind"), row.get("name")))
        favorites = [str(value) for value in self._ui().get("action_favorites", []) if str(value)]
        folded = {value.casefold() for value in favorites}
        if key.casefold() in folded:
            favorites = [value for value in favorites if value.casefold() != key.casefold()]
        else:
            favorites.append(key)
        self._ui()["action_favorites"] = favorites
        self._mark_ui_dirty()
        self._rebuild_action_catalog()

    def _refresh_quick_actions(self) -> None:
        if not hasattr(self, "quick_actions_frame"):
            return
        for child in self.quick_actions_frame.winfo_children():
            child.destroy()
        favorites = [row for row in self.action_catalog if row.get("favorite")][:8]
        if not favorites:
            ttk.Label(self.quick_actions_frame, text="Favorite actions appear here.", style="Muted.Card.TLabel").pack(side=tk.LEFT, padx=4, pady=4)
            return
        for row in favorites:
            button = ttk.Button(
                self.quick_actions_frame,
                text=str(row.get("name") or "Action"),
                command=lambda item=dict(row): self._run_quick_action(item),
            )
            button.pack(side=tk.LEFT, padx=4, pady=4)
            if not (row.get("executable") and row.get("available")):
                button.state(["disabled"])

    def _run_quick_action(self, row: dict[str, Any]) -> None:
        if not row.get("executable") or not row.get("available"):
            return
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        self.sam_client.use_recovery(str(payload.get("kind") or ""), str(payload.get("name") or ""))
        self.recovery_notice_label.configure(text=f"Requesting {row.get('name')} from Sam.py…")

    def use_selected_recovery(self) -> None:
        row = self._selected_action()
        if not row:
            self.recovery_notice_label.configure(text="Select an action first.")
            return
        if not row.get("executable"):
            self.recovery_notice_label.configure(text="This action is displayed for readiness visibility. Use it through the VRChat action menu.")
            return
        if not row.get("available"):
            self.recovery_notice_label.configure(text=str(row.get("reason") or "That action is unavailable."))
            return
        self._run_quick_action(row)

    # ------------------------------------------------------------------
    # NPC search, favorites, and safer controls
    # ------------------------------------------------------------------
    def _build_npc_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="NPC Mode", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Refresh Rosters", command=self.refresh_npc_roster).pack(side=tk.RIGHT)
        ttk.Button(header, text="Disable NPC Mode", style="Danger.TButton", command=self.disable_npc_mode).pack(side=tk.RIGHT, padx=8)
        npc_card = self._card(page)
        npc_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(npc_card, text="Authoritative NPC Runtime", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=5, sticky="w", padx=20, pady=(18, 10))
        npc_cfg = self.config.get("npc_mode", {})
        ui = self._ui()
        self.npc_mode_var = tk.BooleanVar(value=bool(npc_cfg.get("enabled", False)))
        self.npc_enemy_var = tk.StringVar(value=str(npc_cfg.get("enemy_name") or ""))
        self.npc_search_var = tk.StringVar(value=str(ui.get("npc_search") or ""))
        self.npc_favorites_only_var = tk.BooleanVar(value=bool(ui.get("npc_favorites_only", False)))
        self.npc_attacker_mode_var = tk.StringVar(value=str(npc_cfg.get("attacker_mode") or "verified"))
        self.npc_attacker_player_var = tk.StringVar(value=str(npc_cfg.get("attacker_player_label") or npc_cfg.get("attacker_user_id") or ""))
        self.npc_attacker_char_var = tk.StringVar(value=str(npc_cfg.get("attacker_char_name") or ""))

        ttk.Checkbutton(npc_card, text="Use this Desktop link as an NPC enemy", variable=self.npc_mode_var, command=self._refresh_npc_attacker_status).grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=6)
        self.npc_favorite_button = ttk.Button(npc_card, text="☆ Favorite NPC", command=self.toggle_current_npc_favorite)
        self.npc_favorite_button.grid(row=1, column=4, sticky="e", padx=(0, 20), pady=6)
        ttk.Label(npc_card, text="Search", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=20, pady=6)
        npc_search = tk.Entry(npc_card, textvariable=self.npc_search_var, bg=THEME["panel3"], fg=THEME["text"], insertbackground=THEME["text"], relief=tk.FLAT)
        npc_search.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=6, ipady=6)
        ttk.Checkbutton(npc_card, text="Favorites only", variable=self.npc_favorites_only_var, command=self._npc_filters_changed).grid(row=2, column=3, columnspan=2, sticky="w", padx=(0, 20), pady=6)
        self.npc_search_var.trace_add("write", lambda *_: self._npc_filters_changed())

        ttk.Label(npc_card, text="NPC roster", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=20, pady=6)
        self.npc_enemy_combo = ttk.Combobox(npc_card, textvariable=self.npc_enemy_var, values=(), state="readonly")
        self.npc_enemy_combo.grid(row=3, column=1, columnspan=4, sticky="ew", padx=(0, 20), pady=6)
        self.npc_enemy_combo.bind("<<ComboboxSelected>>", self._npc_selected)
        self.npc_preview_label = ttk.Label(npc_card, text="Select an NPC to preview its authoritative level, HP, DEF, RES, EVA, and affinities.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_preview_label.grid(row=4, column=0, columnspan=5, sticky="w", padx=20, pady=(2, 12))
        ttk.Separator(npc_card, orient="horizontal").grid(row=5, column=0, columnspan=5, sticky="ew", padx=20, pady=6)
        ttk.Label(npc_card, text="Player → NPC Damage Attacker", style="CardTitle.TLabel").grid(row=6, column=0, columnspan=5, sticky="w", padx=20, pady=(8, 8))
        ttk.Label(npc_card, text="Attacking player", style="Card.TLabel").grid(row=7, column=0, sticky="w", padx=20, pady=6)
        self.npc_attacker_player_combo = ttk.Combobox(npc_card, textvariable=self.npc_attacker_player_var, values=(), state="normal")
        self.npc_attacker_player_combo.grid(row=7, column=1, columnspan=3, sticky="ew", padx=(0, 10), pady=6)
        self.npc_attacker_player_combo.bind("<<ComboboxSelected>>", self._on_npc_attacker_player_selected)
        self.npc_attacker_player_combo.bind("<KeyRelease>", lambda _event: self._refresh_npc_attacker_status())
        ttk.Button(npc_card, text="Use Linked Character", command=self._use_linked_character_as_attacker).grid(row=7, column=4, sticky="e", padx=(0, 20), pady=6)
        ttk.Label(npc_card, text="Attacking character", style="Card.TLabel").grid(row=8, column=0, sticky="w", padx=20, pady=6)
        self.npc_attacker_char_combo = ttk.Combobox(npc_card, textvariable=self.npc_attacker_char_var, values=(), state="normal")
        self.npc_attacker_char_combo.grid(row=8, column=1, columnspan=4, sticky="ew", padx=(0, 20), pady=6)
        self.npc_attacker_char_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_npc_attacker_status())
        self.npc_attacker_char_combo.bind("<KeyRelease>", lambda _event: self._refresh_npc_attacker_status())
        ttk.Radiobutton(npc_card, text="Verified Sam.py stats", value="verified", variable=self.npc_attacker_mode_var, command=self._refresh_npc_attacker_status).grid(row=9, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        ttk.Radiobutton(npc_card, text="Compatibility fallback", value="fallback", variable=self.npc_attacker_mode_var, command=self._refresh_npc_attacker_status).grid(row=9, column=2, columnspan=3, sticky="w", padx=10, pady=4)
        self.npc_attacker_status_label = ttk.Label(npc_card, text="", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_attacker_status_label.grid(row=10, column=0, columnspan=5, sticky="w", padx=20, pady=(4, 6))
        self.npc_hit_diagnostics_label = ttk.Label(npc_card, text="Last hit diagnostics: no Player → NPC hit has been returned by Sam.py yet.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_hit_diagnostics_label.grid(row=11, column=0, columnspan=5, sticky="w", padx=20, pady=(2, 6))
        self.npc_notice_label = ttk.Label(npc_card, text="NPC Mode uses a device-local runtime copy. Verified attacker stats come from Sam.py API 0.8.14.", style="Muted.Card.TLabel", wraplength=950, justify="left")
        self.npc_notice_label.grid(row=12, column=0, columnspan=5, sticky="w", padx=20, pady=(4, 16))
        for column in (1, 2, 3):
            npc_card.columnconfigure(column, weight=1)
        self._refresh_npc_attacker_status()
        return page

    def _npc_filters_changed(self) -> None:
        self._ui()["npc_search"] = self.npc_search_var.get()
        self._ui()["npc_favorites_only"] = bool(self.npc_favorites_only_var.get())
        self._mark_ui_dirty()
        self._refresh_npc_values()

    def _refresh_npc_values(self) -> None:
        if not hasattr(self, "npc_enemy_combo"):
            return
        rows = filter_npcs(
            self.npc_roster,
            search=self.npc_search_var.get() if hasattr(self, "npc_search_var") else "",
            favorites=self._ui().get("npc_favorites", []),
            favorites_only=bool(self.npc_favorites_only_var.get()) if hasattr(self, "npc_favorites_only_var") else False,
        )
        names = [str(row.get("name") or "") for row in rows if str(row.get("name") or "")]
        current = str(self.npc_enemy_var.get() or "")
        if current and current not in names:
            names.insert(0, current)
        self.npc_enemy_combo.configure(values=names)
        if not current and names:
            self.npc_enemy_var.set(names[0])
        favorites = {str(value).casefold() for value in self._ui().get("npc_favorites", [])}
        self.npc_favorite_button.configure(text="★ Unfavorite NPC" if current.casefold() in favorites else "☆ Favorite NPC")
        self._refresh_npc_preview()

    def _npc_selected(self, _event=None) -> None:
        name = str(self.npc_enemy_var.get() or "").strip()
        if name:
            recent = [str(value) for value in self._ui().get("recent_npcs", []) if str(value)]
            recent = [value for value in recent if value.casefold() != name.casefold()]
            recent.insert(0, name)
            self._ui()["recent_npcs"] = recent[:12]
            self._mark_ui_dirty()
        self._refresh_npc_values()

    def toggle_current_npc_favorite(self) -> None:
        name = str(self.npc_enemy_var.get() or "").strip()
        if not name:
            return
        favorites = [str(value) for value in self._ui().get("npc_favorites", []) if str(value)]
        if name.casefold() in {value.casefold() for value in favorites}:
            favorites = [value for value in favorites if value.casefold() != name.casefold()]
        else:
            favorites.append(name)
        self._ui()["npc_favorites"] = favorites
        self._mark_ui_dirty()
        self._refresh_npc_values()

    def disable_npc_mode(self) -> None:
        self.npc_mode_var.set(False)
        self.config.setdefault("npc_mode", {})["enabled"] = False
        save_config(self.config)
        self._send_parameter(self.config["parameters"]["enemy_mode"], False)
        self.controller.telemetry["enemy_mode"] = False
        self._schedule_sam_sync("npc_mode_disabled", immediate=True, vrc_trigger=False)
        self._append_activity("SYSTEM", "NPC Mode disabled.")
        self._refresh_npc_attacker_status()

    # ------------------------------------------------------------------
    # Diagnostics and support bundle
    # ------------------------------------------------------------------
    def _build_diagnostics_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Diagnostics", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Create Support Bundle", style="Gold.TButton", command=self.create_support_bundle).pack(side=tk.RIGHT)
        ttk.Button(header, text="Copy Summary", command=self.copy_diagnostic_summary).pack(side=tk.RIGHT, padx=8)
        ttk.Button(header, text="Reconnect All", command=self.reconnect_all).pack(side=tk.RIGHT, padx=8)
        ttk.Button(header, text="Test Sam.py", command=self.test_sam_connection).pack(side=tk.RIGHT, padx=8)
        card = self._card(page)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="Connection & Contract", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(18, 8))
        self.diagnostics_summary_label = ttk.Label(card, text="Waiting for Sam.py state…", style="Muted.Card.TLabel", wraplength=980, justify="left")
        self.diagnostics_summary_label.pack(anchor="w", padx=20, pady=(0, 8))
        self.diagnostics_detail_label = ttk.Label(card, text="No diagnostics have been received.", style="Muted.Card.TLabel", wraplength=980, justify="left")
        self.diagnostics_detail_label.pack(anchor="w", padx=20, pady=(0, 18))
        info = self._card(page)
        info.pack(fill=tk.BOTH, expand=True)
        ttk.Label(info, text="Self-checks", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(18, 8))
        self.diagnostics_checks_label = ttk.Label(info, text="Waiting for the first refresh.", style="Muted.Card.TLabel", wraplength=980, justify="left")
        self.diagnostics_checks_label.pack(anchor="w", padx=20, pady=(0, 18))
        return page

    def _refresh_diagnostics_view(self) -> None:
        super()._refresh_diagnostics_view()
        if not hasattr(self, "diagnostics_checks_label"):
            return
        payload = self._diagnostic_payload()
        checks = [
            ("Sam.py paired", payload["sam_paired"]),
            (f"OSC API {payload['api_version'] or 'unknown'} compatible", payload["api_compatible"]),
            ("VRChat listener running", payload["listener_running"]),
            ("Avatar detected", payload["avatar_detected"]),
            ("Combat profile loaded", payload["combat_profile"]),
            ("NPC attacker roster loaded", payload["attacker_roster"]),
            ("Single-instance guard", True),
            ("Settings folder writable", payload["settings_writable"]),
        ]
        self.diagnostics_checks_label.configure(text="\n".join(f"{'✓' if ok else '•'} {label}" for label, ok in checks))

    def _diagnostic_payload(self) -> dict[str, Any]:
        paired = bool(str(self.config.get("sam", {}).get("token") or "").strip())
        api = self.sam_api_version or ""
        recent_vrchat = bool(self.controller.last_input_at and time.monotonic() - self.controller.last_input_at <= float(self.config["osc"].get("activity_timeout_seconds", 5.0)))
        try:
            probe = get_app_data_dir() / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable = True
        except Exception:
            writable = False
        return {
            "desktop_version": __version__,
            "api_version": api,
            "api_minimum": OSC_API_MINIMUM,
            "api_recommended": OSC_API_RECOMMENDED,
            "api_compatible": bool(api and self._version_tuple(api) >= self._version_tuple(OSC_API_MINIMUM)),
            "sam_paired": paired,
            "sam_recent_success": bool(self.last_sam_success_epoch and time.time() - self.last_sam_success_epoch <= 30),
            "listener_running": bool(self.osc.running),
            "vrchat_recent_activity": recent_vrchat,
            "avatar_detected": self.last_avatar_id != "—",
            "active_character": str(self.remote_character.get("name") or ""),
            "combat_profile": bool(self.remote_state.get("combat_profile")),
            "attacker_roster": bool(self.npc_attacker_roster),
            "dm_gate_active": bool((self.remote_state.get("dm_gate") or {}).get("active", False)) if isinstance(self.remote_state.get("dm_gate"), dict) else False,
            "last_event": self.last_event,
            "settings_writable": writable,
        }

    def copy_diagnostic_summary(self) -> None:
        payload = self._diagnostic_payload()
        text = "\n".join(f"{key}: {value}" for key, value in payload.items())
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._append_activity("SYSTEM", "Diagnostic summary copied to the clipboard.")

    def create_support_bundle(self) -> None:
        try:
            bundle = build_support_bundle(
                get_app_data_dir(),
                config=self.config,
                runtime_state={
                    "current_hp": int(self.state.current_hp),
                    "combat_enabled": bool(self.state.combat_enabled),
                    "remote_state": self.remote_state,
                },
                event_rows=self.event_rows,
                diagnostics=self._diagnostic_payload(),
                version=__version__,
                install_dir=self.install_dir,
                log_path=get_log_path(),
            )
            self._append_activity("SYSTEM", f"Sanitized support bundle created: {bundle.name}")
            messagebox.showinfo("Support Bundle", f"Created a sanitized support bundle:\n\n{bundle}\n\nTokens, pairing secrets, and Discord IDs were redacted.")
        except Exception as exc:
            messagebox.showerror("Support Bundle", f"Could not create the support bundle.\n\n{exc}")

    def reconnect_all(self) -> None:
        if self.osc.running:
            self.restart_listener()
        else:
            self.start_listener()
        if str(self.config.get("sam", {}).get("token") or "").strip():
            self.sam_client.test()
            self.sam_client.pull()
            self.sam_client.recovery_options()
            self.sam_client.npc_catalog()
        self._append_activity("SYSTEM", "Reconnect and refresh requested for VRChat OSC and Sam.py.")

    # ------------------------------------------------------------------
    # Settings QOL
    # ------------------------------------------------------------------
    def _build_settings_page(self) -> ttk.Frame:
        page = super()._build_settings_page()
        canvas = next((child for child in page.winfo_children() if isinstance(child, tk.Canvas)), None)
        body = next((child for child in canvas.winfo_children() if isinstance(child, ttk.Frame)), None) if canvas else None
        if body is not None:
            ui = self._ui()
            card = self._card(body)
            first = body.winfo_children()[0] if body.winfo_children() else None
            card.pack(fill=tk.X, pady=(0, 10), before=first)
            ttk.Label(card, text="Interface & Accessibility", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
            self.ui_scale_var = tk.StringVar(value=str(clamp_ui_scale(ui.get("scale", 1.0))))
            self.reduced_motion_var = tk.BooleanVar(value=bool(ui.get("reduced_motion", False)))
            self.compact_mode_var = tk.BooleanVar(value=bool(ui.get("compact_mode", False)))
            ttk.Label(card, text="UI scale", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=20, pady=6)
            ttk.Combobox(card, textvariable=self.ui_scale_var, values=("0.8", "0.9", "1.0", "1.1", "1.2", "1.35", "1.5", "1.6"), state="readonly", width=10).grid(row=1, column=1, sticky="w", pady=6)
            ttk.Checkbutton(card, text="Reduced motion and slower visual refresh", variable=self.reduced_motion_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=5)
            ttk.Checkbutton(card, text="Compact dashboard text", variable=self.compact_mode_var).grid(row=2, column=2, columnspan=2, sticky="w", padx=20, pady=5)
            ttk.Button(card, text="Create Support Bundle", command=self.create_support_bundle).grid(row=3, column=0, sticky="w", padx=20, pady=(8, 16))
            ttk.Label(card, text="Window position, page, filters, favorites, and selections are saved automatically.", style="Muted.Card.TLabel", wraplength=680, justify="left").grid(row=3, column=1, columnspan=3, sticky="w", padx=(0, 20), pady=(8, 16))
            card.columnconfigure(3, weight=1)
        return page

    def save_settings(self) -> None:
        ui = self._ui()
        if hasattr(self, "ui_scale_var"):
            ui["scale"] = clamp_ui_scale(self.ui_scale_var.get())
            ui["reduced_motion"] = bool(self.reduced_motion_var.get())
            ui["compact_mode"] = bool(self.compact_mode_var.get())
        self._capture_ui_state()
        super().save_settings()
        try:
            self.root.tk.call("tk", "scaling", self._base_tk_scaling * clamp_ui_scale(ui.get("scale", 1.0)))
        except Exception:
            pass
        save_config(self.config)
        self._ui_dirty = False

    # ------------------------------------------------------------------
    # Sam event and refresh enhancements
    # ------------------------------------------------------------------
    def _handle_sam_event(self, event) -> None:
        super()._handle_sam_event(event)
        if event.ok:
            self.last_sam_success_epoch = time.time()
        if event.kind == "npc_catalog" and event.ok:
            self._refresh_npc_values()
        if event.kind in {"recovery_options", "state", "paired", "test"} and event.ok:
            self._rebuild_action_catalog()
        self._refresh_global_status()

    def _apply_sam_state(self, state: dict[str, Any], *, source: str, force: bool) -> None:
        super()._apply_sam_state(state, source=source, force=force)
        self.last_sam_success_epoch = time.time()
        self._rebuild_action_catalog()

    def _refresh_loop(self) -> None:
        if self.closing:
            return
        self._refresh_ui()
        try:
            minimized = self.root.state() == "iconic"
        except Exception:
            minimized = False
        if minimized:
            delay = 1500
        else:
            delay = 850 if bool(self._ui().get("reduced_motion", False)) else 500
        self.root.after(delay, self._refresh_loop)

    def _refresh_ui(self) -> None:
        super()._refresh_ui()
        self._refresh_global_status()
        snap = self.state.snapshot()
        critical = bool(int(snap["current_hp"]) > 0 and float(snap["hp_ratio"]) <= 0.15)
        if hasattr(self, "hp_value_label"):
            self.hp_value_label.configure(
                foreground=THEME["red"] if critical else THEME["muted"],
                text=(f"CRITICAL • {int(snap['current_hp']):,} / {int(snap['maximum_hp']):,}" if critical else f"{int(snap['current_hp']):,} / {int(snap['maximum_hp']):,}"),
            )
        signature = (
            repr(self.remote_state.get("combat_profile", {})),
            self.remote_mp,
            tuple(self._ui().get("action_favorites", [])),
        )
        if signature != self._last_action_signature:
            self._last_action_signature = signature
            self._rebuild_action_catalog()

    def _refresh_global_status(self) -> None:
        if not hasattr(self, "global_status_labels"):
            return
        now = time.time()
        paired = bool(str(self.config.get("sam", {}).get("token") or "").strip())
        sam_recent = bool(self.last_sam_success_epoch and now - self.last_sam_success_epoch <= 30)
        vrchat_recent = bool(self.controller.last_input_at and time.monotonic() - self.controller.last_input_at <= float(self.config["osc"].get("activity_timeout_seconds", 5.0)))
        avatar = self.last_avatar_id != "—"
        gate = self.remote_state.get("dm_gate") if isinstance(self.remote_state.get("dm_gate"), dict) else {}
        api = self.sam_api_version or "—"
        sync_text = "never" if not self.last_sam_success_epoch else f"{max(0, int(now - self.last_sam_success_epoch))}s ago"

        values = {
            "sam": (f"SAM {'CONNECTED' if sam_recent else 'PAIRED' if paired else 'OFF'}", "on" if sam_recent else "warn" if paired else "off"),
            "vrchat": (f"VRCHAT {'ACTIVE' if vrchat_recent else 'LISTENING' if self.osc.running else 'OFF'}", "on" if vrchat_recent else "warn" if self.osc.running else "off"),
            "avatar": (f"AVATAR {'DETECTED' if avatar else 'WAITING'}", "on" if avatar else "warn"),
            "combat": (f"RP COMBAT {'ON' if self.state.combat_enabled else 'OFF'}", "on" if self.state.combat_enabled else "off"),
            "gate": (f"DM GATE {'OPEN' if gate.get('active') else 'CLOSED'}", "on" if gate.get("active") else "off"),
            "api": (f"API {api}", "on" if api != "—" and self._version_tuple(api) >= self._version_tuple(OSC_API_MINIMUM) else "warn"),
            "sync": (f"SYNC {sync_text}", "on" if sam_recent else "warn"),
        }
        for key, (text, state) in values.items():
            self.global_status_labels[key].configure(
                text=text,
                style={"on": "StripOn.TLabel", "warn": "StripWarn.TLabel", "off": "StripOff.TLabel"}.get(state, "Strip.TLabel"),
            )

    # ------------------------------------------------------------------
    # Persistent UI state
    # ------------------------------------------------------------------
    def _on_root_configure(self, event) -> None:
        if event.widget is self.root:
            self._mark_ui_dirty()

    def _mark_ui_dirty(self) -> None:
        self._ui_dirty = True

    def _capture_ui_state(self) -> None:
        ui = self._ui()
        ui["last_page"] = self.current_page
        try:
            if self.root.state() == "normal":
                ui["window_geometry"] = safe_window_geometry(self.root.geometry(), "1220x760")
        except Exception:
            pass
        if hasattr(self, "activity_filter_var"):
            ui["activity_filter"] = self.activity_filter_var.get()
            ui["activity_search"] = self.activity_search_var.get()
            ui["activity_paused"] = bool(self.activity_paused_var.get())
        if hasattr(self, "action_filter_var"):
            ui["action_filter"] = self.action_filter_var.get()
            ui["action_search"] = self.action_search_var.get()
            ui["action_favorites_only"] = bool(self.action_favorites_only_var.get())
        if hasattr(self, "npc_search_var"):
            ui["npc_search"] = self.npc_search_var.get()
            ui["npc_favorites_only"] = bool(self.npc_favorites_only_var.get())

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
        if self._ui_dirty:
            self._capture_ui_state()
            try:
                save_config(self.config)
                self._ui_dirty = False
            except Exception:
                pass
        delay = 1800 if bool(self._ui().get("reduced_motion", False)) else 1000
        self.root.after(delay, self._autosave_tick)

    def close(self) -> None:
        if self.closing:
            return
        self._capture_ui_state()
        try:
            save_config(self.config)
        except Exception:
            pass
        super().close()


def run() -> None:
    root = tk.Tk()
    StoriesOSCAppV0814(root)
    root.mainloop()
