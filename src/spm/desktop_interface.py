"""Desktop interface for the local vault, using Tk."""

import argparse
import sys
import time
from concurrent.futures import Future
from pathlib import Path
from threading import Event, Thread

from .sec_pass_manager import DEFAULT_LENGTH, MAX_LENGTH, MIN_LENGTH, generate_password
from .security_key import open_security_key
from .vault import (
    MIN_MASTER_LENGTH, Entry, Vault, VaultConflict, VaultError, default_vault_path, read_legacy,
    vault_has_security_key,
)
from .domain.review import MIN_REVIEW_LENGTH, review_credentials

try:
    import tkinter as tk
    from tkinter import filedialog, font, messagebox, ttk
except ImportError:
    tk = None

LOCK_AFTER = 300
CLIPBOARD_AFTER = 30
REVEAL_AFTER = 15
BACKGROUND = "#f3f6f5"
TEXT = "#182a24"
MUTED = "#50625a"
BORDER = "#acbcb5"
ACCENT = "#12624e"
ERROR = "#9d2830"


def _configure_style(root):
    if "Inter" in font.families(root):
        font.nametofont("TkDefaultFont", root).configure(family="Inter")
        font.nametofont("TkTextFont", root).configure(family="Inter")
    family = font.nametofont("TkDefaultFont", root).actual("family")
    root.configure(background=BACKGROUND)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BACKGROUND, foreground=TEXT, bordercolor=BORDER)
    style.configure("Title.TLabel", font=(family, 24, "bold"))
    style.configure("Heading.TLabel", font=(family, 13, "bold"))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Error.TLabel", foreground=ERROR)
    style.configure("TButton", background="white", padding=(10, 7), focuscolor=ACCENT)
    style.map("TButton", background=[("pressed", "#e0ece7"), ("active", "#ebf3ef")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", focuscolor="white")
    style.map("Accent.TButton", background=[("pressed", "#094032"), ("active", "#0e5140")])
    style.configure("Danger.TButton", foreground=ERROR)
    style.configure("TMenubutton", background="white", padding=(10, 7))
    style.configure("TEntry", padding=(7, 6), fieldbackground="white")
    style.map("TEntry", fieldbackground=[("readonly", "#fbfcfc")],
              bordercolor=[("focus", ACCENT)])
    style.configure("Treeview", rowheight=32, fieldbackground="white", background="white")
    style.configure("Treeview.Heading", padding=(7, 7), background="#e7eeeb", relief="flat")
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])


def _entry_widget(parent, variable, *, secret=False):
    widget = ttk.Entry(
        parent, textvariable=variable, exportselection=False, show="•" if secret else "",
    )
    if secret:
        widget.bind("<<Copy>>", lambda _event: "break")
        widget.bind("<<Cut>>", lambda _event: "break")
    return widget


class DesktopApp:  # pylint: disable=too-many-instance-attributes
    """Manage the unlocked session and its desktop views."""

    def __init__(self, root, path: Path):
        self.root = root
        self.path = path
        self.vault = None
        self.view = None
        self.dialog = None
        self.last_activity = time.monotonic()
        self.clipboard_value = None
        self.clipboard_timer = None
        self.reveal_timer = None
        self.listing = self.detail = self.reveal_button = None

        root.title("Secure Password Manager")
        root.geometry("900x580")
        root.minsize(740, 550)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind_all("<KeyPress>", self._record_activity)
        root.bind_all("<ButtonPress>", self._record_activity)

        _configure_style(root)
        self.lock()
        root.after(1000, self._check_idle)

    def _record_activity(self, _event=None):
        self.last_activity = time.monotonic()

    def _check_idle(self):
        if self.vault and time.monotonic() - self.last_activity >= LOCK_AFTER:
            self.lock()
        self.root.after(1000, self._check_idle)

    def _clear_clipboard(self):
        if self.clipboard_timer is not None:
            self.root.after_cancel(self.clipboard_timer)
            self.clipboard_timer = None
        if self.clipboard_value is not None:
            try:
                if self.root.clipboard_get() == self.clipboard_value:
                    self.root.clipboard_clear()
            except tk.TclError:
                pass
            self.clipboard_value = None

    def close(self):
        """Clear secrets managed by the interface and close the window."""
        self._clear_clipboard()
        self.vault = None
        self.root.destroy()

    def _new_view(self, *, centered=False):
        if self.view is not None:
            self.view.destroy()
        self.view = ttk.Frame(self.root, padding=24)
        self.view.pack(expand=True, fill="none" if centered else "both")
        return self.view

    def lock(self):
        """Discard the unlocked snapshot and return to the master password form."""
        if self.reveal_timer is not None:
            self._hide_password()
        if self.dialog is not None:
            self.dialog.destroy()
            self.dialog = None
        self._clear_clipboard()
        self.vault = None
        self.names = []
        self.query = self.status = self.password_display = None
        self._show_unlock()

    def _show_unlock(self):
        view = self._new_view(centered=True)
        view.columnconfigure(0, weight=1)
        create = not self.path.expanduser().exists()
        title = "Create your vault" if create else "Unlock your vault"
        ttk.Label(view, text=title, style="Title.TLabel").grid(sticky="w", pady=(0, 8))
        ttk.Label(
            view, text=str(self.path.expanduser()), style="Muted.TLabel", wraplength=420,
        ).grid(sticky="w", pady=(0, 22))
        master = tk.StringVar(view)
        confirmation = tk.StringVar(view)
        master_label = "Master password"
        if create:
            master_label += f" (at least {MIN_MASTER_LENGTH} characters)"
        ttk.Label(view, text=master_label).grid(sticky="w")
        master_field = _entry_widget(view, master, secret=True)
        master_field.grid(sticky="ew", pady=(5, 12), ipadx=85)
        if create:
            ttk.Label(view, text="Confirm password").grid(sticky="w")
            _entry_widget(view, confirmation, secret=True).grid(sticky="ew", pady=(5, 12))

        error = tk.StringVar(view)
        ttk.Label(view, textvariable=error, wraplength=420, style="Error.TLabel").grid(
            sticky="w", pady=(0, 12),
        )

        def submit(_event=None):
            value = master.get()
            try:
                if create:
                    if value != confirmation.get():
                        raise VaultError("The master passwords do not match.")
                    Vault.create(self.path, value)
                self.vault = Vault(self.path, value)
            except (OSError, VaultError, ValueError) as problem:
                error.set(str(problem))
                return
            finally:
                master.set("")
                confirmation.set("")
            self._record_activity()
            self._show_vault()

        buttons = ttk.Frame(view)
        buttons.grid(sticky="ew")
        label = "Create vault" if create else "Unlock"
        ttk.Button(buttons, text=label, style="Accent.TButton", command=submit).pack(side="left")
        if not create and vault_has_security_key(self.path):
            ttk.Button(buttons, text="Use FIDO2 key", command=self._security_key_dialog).pack(
                side="left", padx=(8, 0),
            )
        ttk.Button(buttons, text="Open file…", command=self._choose_vault).pack(side="right")
        ttk.Button(buttons, text="Generator…", command=self._standalone_generator).pack(
            side="right", padx=8,
        )
        for child in view.winfo_children():
            if isinstance(child, ttk.Entry):
                child.bind("<Return>", submit)
        master_field.focus_set()

    def _choose_vault(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Open encrypted vault",
            filetypes=[("Vaults", "*.spm"), ("All files", "*")],
        )
        if path:
            self.path = Path(path)
            self.lock()

    def _vault_header(self, view):
        header = ttk.Frame(view)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="Vault", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Lock", command=self.lock).pack(side="right")
        actions = ttk.Menubutton(header, text="File")
        menu = tk.Menu(actions, tearoff=False)
        menu.add_command(label="Save encrypted backup…", command=self._backup)
        menu.add_command(label="Import .key files…", command=self._import)
        menu.add_command(label="Change master password…", command=self._change_master)
        key_label, key_action = (("Remove FIDO2 key…", "remove") if self.vault.has_security_key
                                 else ("Register FIDO2 key…", "add"))
        menu.add_command(label=key_label, command=lambda: self._security_key_dialog(key_action))
        menu.add_separator()
        menu.add_command(label="Generate without saving…", command=self._standalone_generator)
        actions.configure(menu=menu)
        actions.pack(side="right", padx=8)
        ttk.Button(header, text="Review vault", command=self._review_vault).pack(side="right")

    def _show_vault(self):
        view = self._new_view()
        self._vault_header(view)
        self.status = tk.StringVar(view)
        ttk.Label(view, textvariable=self.status, style="Muted.TLabel").pack(
            side="bottom", anchor="w", pady=(12, 0),
        )

        body = ttk.Frame(view)
        body.pack(expand=True, fill="both")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=3, minsize=365)
        body.columnconfigure(1, weight=2, minsize=285)
        collection = ttk.Frame(body)
        collection.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        toolbar = ttk.Frame(collection)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.query = tk.StringVar(toolbar)
        ttk.Button(
            toolbar, text="New credential", style="Accent.TButton", command=self._edit,
        ).pack(side="right")
        search = _entry_widget(toolbar, self.query)
        search.pack(side="left", expand=True, fill="x", padx=8)

        table = ttk.Frame(collection)
        table.pack(expand=True, fill="both")
        self.listing = ttk.Treeview(
            table, columns=("name", "user"), show="headings", selectmode="browse",
        )
        for column, label in (("name", "Name"), ("user", "Username")):
            self.listing.heading(column, text=label, anchor="w")
            self.listing.column(column, width=170, minwidth=110)
        self.listing.pack(side="left", expand=True, fill="both")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.listing.yview)
        scroll.pack(side="right", fill="y")
        self.listing.configure(yscrollcommand=scroll.set)

        self.detail = ttk.Frame(body, padding=(4, 0, 0, 0))
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.query.trace_add("write", self._refresh)
        self.listing.bind("<<TreeviewSelect>>", self._show_details)
        self.listing.bind("<Return>", self._edit_selected)
        self.listing.bind("<Double-1>", self._edit_selected)
        self._refresh()
        search.focus_set()

    def _refresh(self, *_trace, select=None):
        self.listing.delete(*self.listing.get_children())
        self.names = []
        for entry in self.vault.list(self.query.get()):
            index = str(len(self.names))
            self.names.append(entry.name)
            self.listing.insert("", "end", iid=index, values=(entry.name, entry.username))
            if entry.name == select:
                self.listing.selection_set(index)
                self.listing.focus(index)
                self.listing.see(index)
        self._show_details()
        count = len(self.names)
        self.status.set(f"{count} credential" if count == 1 else f"{count} credentials")

    def _selected(self):
        selected = self.listing.selection()
        if self.vault and selected:
            return self.vault.get(self.names[int(selected[0])])
        return None

    def _show_details(self, _event=None):
        if self.vault is None:
            return
        self._hide_password()
        for widget in self.detail.winfo_children():
            widget.destroy()
        entry = self._selected()
        if entry is None:
            message = "Select a credential." if self.names else "No credentials yet."
            ttk.Label(self.detail, text=message, wraplength=260).pack(anchor="w", pady=8)
            return
        content = ttk.Frame(self.detail)
        buttons = ttk.Frame(self.detail)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))
        content.pack(expand=True, fill="both")
        ttk.Label(content, text=entry.name, style="Heading.TLabel", wraplength=265).pack(
            anchor="w", pady=(0, 14),
        )
        for label, value in (("Username", entry.username), ("Website", entry.url)):
            if value:
                ttk.Label(content, text=label).pack(anchor="w")
                field = ttk.Entry(content, exportselection=False)
                field.insert(0, value)
                field.configure(state="readonly")
                field.pack(fill="x", pady=(3, 9))
        ttk.Label(content, text="Password").pack(anchor="w")
        self.password_display = tk.StringVar(content, value="••••••••••••")
        field = _entry_widget(content, self.password_display)
        field.bind("<<Copy>>", lambda _event: "break")
        field.configure(state="readonly")
        field.pack(fill="x", pady=(3, 5))
        password_actions = ttk.Frame(content)
        password_actions.pack(fill="x", pady=(0, 9))
        ttk.Button(
            password_actions, text="Copy", style="Accent.TButton",
            command=lambda: self._copy(entry.password, self.status),
        ).pack(side="left")
        self.reveal_button = ttk.Button(
            password_actions, text="Show", command=lambda: self._reveal(entry.password),
        )
        self.reveal_button.pack(side="left", padx=6)
        if entry.notes:
            ttk.Label(content, text="Notes").pack(anchor="w")
            notes = tk.Text(
                content, wrap="word", height=4, width=25, exportselection=False,
                font="TkTextFont", background="white", foreground=TEXT,
                relief="flat", padx=8, pady=6,
            )
            notes.insert("1.0", entry.notes)
            notes.configure(state="disabled")
            notes.pack(expand=True, fill="both", pady=(3, 9))
        ttk.Button(buttons, text="Edit", command=lambda: self._edit(entry)).pack(side="left")
        ttk.Button(
            buttons, text="Delete", style="Danger.TButton", command=lambda: self._delete(entry),
        ).pack(side="right")

    def _copy(self, password, status):
        if not password:
            status.set("Generate a password before copying.")
            return
        self._clear_clipboard()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(password)
        except tk.TclError:
            status.set("Could not access the clipboard.")
            return
        self.clipboard_value = password
        self.clipboard_timer = self.root.after(
            CLIPBOARD_AFTER * 1000, self._expire_clipboard, status,
        )
        status.set(f"Password copied for {CLIPBOARD_AFTER} seconds.")

    def _expire_clipboard(self, status):
        self.clipboard_timer = None
        self._clear_clipboard()
        status.set("Temporary clipboard copy expired.")

    def _reveal(self, password):
        if self.reveal_timer is not None:
            self._hide_password()
            return
        self.password_display.set(password)
        self.reveal_button.configure(text="Hide")
        self.reveal_timer = self.root.after(REVEAL_AFTER * 1000, self._hide_password)

    def _hide_password(self):
        if self.reveal_timer is not None:
            self.root.after_cancel(self.reveal_timer)
            self.reveal_timer = None
            self.password_display.set("••••••••••••")
            self.reveal_button.configure(text="Show")

    def _edit_selected(self, _event):
        entry = self._selected()
        if entry is not None:
            self._edit(entry)

    def _review_vault(self):
        self._hide_password()
        report = review_credentials(self.vault.list())
        form = self._open_dialog("Vault review")
        summary = f"Credentials reviewed: {report.total}"
        if report.total == 0:
            summary = "Add credentials to review their passwords."
        elif not report.short and not report.reused:
            summary += f"\nAll passwords are unique and at least {MIN_REVIEW_LENGTH} characters."
        ttk.Label(form, text=summary, style="Heading.TLabel", wraplength=540).pack(
            anchor="w", pady=(0, 12),
        )
        if report.short or report.reused:
            findings = {name: ["Short"] for name in report.short}
            for number, group in enumerate(report.reused, start=1):
                for name in group:
                    findings.setdefault(name, []).append(f"Reused (group {number})")
            self._review_results(form, findings)
        else:
            ttk.Button(form, text="Close", command=self._close_dialog).pack(anchor="e")

    def _review_results(self, form, findings):
        hint = (
            f"Short passwords have fewer than {MIN_REVIEW_LENGTH} characters. "
            "Credentials in the same group share a password."
        )
        ttk.Label(form, text=hint, wraplength=540).pack(anchor="w", pady=(0, 12))
        container = ttk.Frame(form)
        container.pack(fill="x")
        table = ttk.Treeview(
            container, columns=("name", "finding"), show="headings", selectmode="browse",
            height=min(len(findings), 8),
        )
        for column, label in (("name", "Credential"), ("finding", "Findings")):
            table.heading(column, text=label, anchor="w")
            table.column(column, width=260)
        table.pack(side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(container, orient="vertical", command=table.yview)
        scroll.pack(side="right", fill="y")
        table.configure(yscrollcommand=scroll.set)
        names = sorted(findings, key=str.casefold)
        for index, name in enumerate(names):
            table.insert("", "end", iid=str(index), values=(name, " · ".join(findings[name])))
        table.selection_set("0")
        table.focus("0")
        table.focus_set()

        def show_credential(_event=None):
            selection = table.selection()
            if selection:
                name = names[int(selection[0])]
                self._close_dialog()
                if self.query.get():
                    self.query.set("")
                self._refresh(select=name)
                self.listing.focus_set()

        table.bind("<Return>", show_credential)
        buttons = ttk.Frame(form)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=self._close_dialog).pack(side="left")
        ttk.Button(
            buttons, text="View credential", style="Accent.TButton", command=show_credential,
        ).pack(side="right")

    def _open_dialog(self, title):
        dialog = tk.Toplevel(self.root)
        self.dialog = dialog
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background=BACKGROUND)
        dialog.grab_set()
        dialog.bind("<Escape>", self._close_dialog)
        dialog.protocol("WM_DELETE_WINDOW", self._close_dialog)
        form = ttk.Frame(dialog, padding=20)
        form.pack(fill="both")
        return form

    def _close_dialog(self, _event=None):
        self.dialog.destroy()
        self.dialog = None

    @staticmethod
    def _generator(form, password, error):
        controls = ttk.Frame(form)
        length = tk.StringVar(form, value=str(DEFAULT_LENGTH))
        symbols = tk.BooleanVar(form, value=True)
        ttk.Label(controls, text="Length").pack(side="left")
        ttk.Spinbox(
            controls, from_=MIN_LENGTH, to=MAX_LENGTH, textvariable=length, width=4,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(controls, text="Symbols", variable=symbols).pack(side="left")

        def generate():
            try:
                password.set(generate_password(int(length.get()), symbols=symbols.get()))
                error.set("")
            except ValueError:
                error.set(f"Choose between {MIN_LENGTH} and {MAX_LENGTH} characters.")

        ttk.Button(controls, text="Generate", command=generate).pack(side="right")
        return controls

    def _standalone_generator(self):
        form = self._open_dialog("Password generator")
        password = tk.StringVar(form)
        status = tk.StringVar(form)
        field = _entry_widget(form, password, secret=True)
        field.configure(state="readonly", width=44)
        field.pack(fill="x", pady=(0, 10))
        self._generator(form, password, status).pack(fill="x")
        ttk.Label(form, textvariable=status, style="Muted.TLabel").pack(anchor="w", pady=(8, 6))
        actions = ttk.Frame(form)
        actions.pack(fill="x")
        visible = tk.BooleanVar(form)
        ttk.Checkbutton(
            actions, text="Show", variable=visible,
            command=lambda: field.configure(show="" if visible.get() else "•"),
        ).pack(side="left")
        ttk.Button(
            actions, text="Copy", style="Accent.TButton",
            command=lambda: self._copy(password.get(), status),
        ).pack(side="right")
        field.focus_set()

    def _edit(self, current=None):
        form = self._open_dialog("Edit credential" if current else "New credential")
        form.columnconfigure(1, weight=1, minsize=320)
        values = {}
        for row, (name, label) in enumerate((
            ("name", "Name"), ("username", "Username"),
            ("url", "Website"), ("password", "Password"),
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=5)
            values[name] = tk.StringVar(form, value=getattr(current, name, ""))
            field = _entry_widget(form, values[name], secret=name == "password")
            field.grid(row=row, column=1, sticky="ew", pady=5)
            if row == 0:
                field.focus_set()

        error = tk.StringVar(form)
        self._generator(form, values["password"], error).grid(
            row=4, column=1, sticky="ew", pady=(3, 10),
        )
        ttk.Label(form, text="Notes").grid(row=5, column=0, sticky="nw", pady=5)
        notes = tk.Text(form, wrap="word", height=4, width=30, exportselection=False,
                        font="TkTextFont", padx=8, pady=6)
        notes.grid(row=5, column=1, sticky="ew", pady=5)
        if current:
            notes.insert("1.0", current.notes)
        ttk.Label(form, textvariable=error, style="Error.TLabel", wraplength=400).grid(
            row=6, columnspan=2, sticky="w", pady=(5, 10),
        )

        def save():
            try:
                fields = {name: variable.get() for name, variable in values.items()}
                entry = Entry(**fields, notes=notes.get("1.0", "end-1c"))
                if current:
                    self.vault.edit(current.name, entry)
                else:
                    self.vault.add([entry])
            except VaultConflict as problem:
                self._conflict(problem)
                return
            except (OSError, VaultError, ValueError) as problem:
                error.set(str(problem))
                return
            self._close_dialog()
            self.query.set("")
            self._refresh(select=entry.name)
            self.status.set("Credential saved.")

        buttons = ttk.Frame(form)
        buttons.grid(row=7, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self._close_dialog).pack(side="left")
        ttk.Button(buttons, text="Save", style="Accent.TButton", command=save).pack(side="right")

    def _conflict(self, error):
        self.lock()
        messagebox.showerror("Vault changed", str(error), parent=self.root)

    def _delete(self, entry):
        vault = self.vault
        confirm = messagebox.askyesno(
            "Delete credential", f"Delete “{entry.name}”?", parent=self.root,
        )
        if confirm and self.vault is vault:
            self._perform(lambda: vault.delete(entry.name), "Credential deleted.", refresh=True)

    def _backup(self):
        vault = self.vault
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Save encrypted backup", initialfile="vault-backup.spm",
            defaultextension=".spm", confirmoverwrite=False,
        )
        if destination and self.vault is vault:
            self._perform(lambda: vault.backup(Path(destination)), "Encrypted backup saved.")

    def _import(self):
        vault = self.vault
        paths = filedialog.askopenfilenames(
            parent=self.root, title="Import credentials",
            filetypes=[("Legacy .key files", "*.key")],
        )
        if paths and self.vault is vault:
            self.query.set("")
            self._perform(
                lambda: vault.add(read_legacy(Path(path)) for path in paths),
                f"Imported {len(paths)} credentials. Original .key files remain on disk.",
                refresh=True,
            )

    def _security_key_dialog(self, action="unlock"):
        title = {
            "unlock": "Unlock with FIDO2 key", "add": "Register FIDO2 key",
            "remove": "Remove FIDO2 key",
        }[action]
        form = self._open_dialog(title)
        master = tk.StringVar(form)
        pin = tk.StringVar(form)
        if action != "unlock":
            ttk.Label(form, text="Current master password").pack(anchor="w")
            _entry_widget(form, master, secret=True).pack(fill="x", pady=(4, 12))
        if action != "remove" and sys.platform != "win32":
            ttk.Label(form, text="FIDO2 key PIN").pack(anchor="w")
            _entry_widget(form, pin, secret=True).pack(fill="x", pady=(4, 6))
            ttk.Label(form, text="Leave the PIN blank if you use a fingerprint.").pack(anchor="w")
        if action == "add":
            ttk.Label(
                form, text="Keep the master password for recovery.", wraplength=390,
            ).pack(anchor="w", pady=(6, 0))
        status = tk.StringVar(form)
        ttk.Label(form, textvariable=status, wraplength=390, style="Muted.TLabel").pack(
            anchor="w", pady=(12, 8),
        )
        actions = ttk.Frame(form)
        actions.pack(fill="x")
        button = ttk.Button(actions, text=title, style="Accent.TButton")

        def submit(_event=None):
            if button.instate(("disabled",)):
                return
            password, device_pin = master.get(), pin.get()
            master.set("")
            pin.set("")
            try:
                if action == "remove":
                    self.vault.remove_security_key(password)
                    self._key_settings_saved("FIDO2 key removed from the active vault.")
                else:
                    if action == "add":
                        self.vault.verify_master(password)
                    self._start_key_request(action, password, device_pin, status, button)
            except VaultConflict as error:
                self._conflict(error)
            except (OSError, VaultError, ValueError) as error:
                status.set(str(error))

        button.configure(command=submit)
        ttk.Button(actions, text="Cancel", command=self._close_dialog).pack(side="left")
        button.pack(side="right")
        self.dialog.bind("<Return>", submit)
        fields = (field for field in form.winfo_children() if isinstance(field, ttk.Entry))
        first_field = next(fields, button)
        first_field.focus_set()

    def _start_key_request(self, action, master, pin, status, button):
        dialog = self.dialog
        path = self.path
        window = self.root.winfo_id()
        cancel = Event()
        result = Future()
        dialog.bind("<Destroy>", lambda event: cancel.set() if event.widget is dialog else None)
        button.state(("disabled",))
        status.set(
            "Connect the USB key and touch it when it blinks. "
            "Registration may require a second touch."
            if action == "add" else "Connect the USB key and touch it when it blinks."
        )

        def request():
            try:
                with open_security_key(
                    lambda: pin, lambda _message: None, cancel=cancel, window=window,
                ) as key:
                    value = key.enroll() if action == "add" else Vault(path, security_key=key)
            except Exception as error:  # pylint: disable=broad-exception-caught
                result.set_exception(error)
            else:
                result.set_result(value)

        def complete():
            if self.dialog is not dialog:
                return
            if not result.done():
                self.root.after(70, complete)
                return
            try:
                value = result.result()
                if action == "add":
                    self.vault.add_security_key(master, value)
                    self._key_settings_saved("FIDO2 key registered.")
                else:
                    self._close_dialog()
                    self.vault = value
                    self._record_activity()
                    self._show_vault()
            except VaultConflict as error:
                self._conflict(error)
            except (OSError, VaultError, ValueError) as error:
                status.set(str(error))
                button.state(("!disabled",))
            except Exception:  # pylint: disable=broad-exception-caught
                status.set("Could not use the FIDO2 key. Try again.")
                button.state(("!disabled",))

        Thread(target=request, daemon=True).start()
        self.root.after(70, complete)

    def _key_settings_saved(self, message):
        self._close_dialog()
        self._show_vault()
        self.status.set(message)

    def _change_master(self):
        form = self._open_dialog("Change master password")
        had_key = self.vault.has_security_key
        if had_key:
            ttk.Label(
                form, text="Changing the master password removes the FIDO2 key.", wraplength=280,
            ).pack(anchor="w", pady=(0, 10))
        current, master, confirmation = [tk.StringVar(form) for _ in range(3)]
        for label, variable in (("Current password", current),
                                (f"Nueva clave (at least {MIN_MASTER_LENGTH} characters)", master),
                                ("Confirm the new password", confirmation)):
            ttk.Label(form, text=label).pack(anchor="w")
            field = _entry_widget(form, variable, secret=True)
            field.pack(fill="x", pady=(4, 10))
            if variable is current:
                field.focus_set()
        error = tk.StringVar(form)
        ttk.Label(form, textvariable=error, style="Error.TLabel", wraplength=280).pack(anchor="w")

        def save(_event=None):
            try:
                if master.get() != confirmation.get():
                    raise VaultError("The master passwords do not match.")
                self.vault.verify_master(current.get())
                self.vault.change_master(master.get())
            except VaultConflict as problem:
                self._conflict(problem)
                return
            except (OSError, VaultError, ValueError) as problem:
                error.set(str(problem))
                return
            if had_key:
                self._key_settings_saved("Master password updated. FIDO2 key removed.")
            else:
                self._close_dialog()
                self.status.set("Master password updated.")

        ttk.Button(form, text="Change password", style="Accent.TButton", command=save).pack(
            anchor="e", pady=(10, 0),
        )
        self.dialog.bind("<Return>", save)

    def _perform(self, operation, success, *, refresh=False):
        try:
            operation()
        except VaultConflict as error:
            self._conflict(error)
        except (OSError, VaultError, ValueError) as error:
            messagebox.showerror("Operation failed", str(error), parent=self.root)
        else:
            if refresh:
                self._refresh()
            self.status.set(success)


def main(argv: list[str] | None = None) -> int:
    """Open the desktop app on the current display."""
    parser = argparse.ArgumentParser(description="Open the local vault in a desktop window.")
    parser.add_argument(
        "--vault", type=Path, default=default_vault_path(), help="vault path",
    )
    args = parser.parse_args(argv)
    if tk is None:
        print("The desktop app requires Tkinter. You can run cpass in a terminal.", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError:
        print("Could not open a window. Check that a desktop session is running.",
              file=sys.stderr)
        return 1
    DesktopApp(root, args.vault)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
