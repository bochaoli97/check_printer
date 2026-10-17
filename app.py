"""
app.py -- Check Printer (GUI)

A window around make_check.py: fill in a check, get a PDF, print it at Actual size.
Run:    python app.py
Build:  run build_exe.bat on Windows (or build_from_wsl.sh from WSL) to get
        dist\\CheckPrinter\\CheckPrinter.exe (a folder build)

config.json and checks\\ are kept next to the program (or in %APPDATA%\\CheckPrinter if that
folder isn't writable); fonts\\ ships next to the exe.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import subprocess
import sys
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import make_check as mc

APP_NAME = "Check Printer"
APP_VERSION = "1.0"
PRINT_HINT = "Print at Actual size (100%), never Fit to page."

DATE_FORMATS = {  # shown in Settings -> strftime format
    "10/15/2026": "%m/%d/%Y",
    "October 15, 2026": "%B %d, %Y",
    "Oct 15, 2026": "%b %d, %Y",
    "2026-10-15": "%Y-%m-%d",
}
DEFAULT_CONFIG = {
    "payer": {"name": "", "address": []},
    "bank": {"name": "", "address": [], "fractional_routing": ""},
    "routing_number": "",
    "account_number": "",
    "first_check_number": 1001,
    "micr_style": "business",
    "micr_check_number_digits": 6,
    "date_format": "%m/%d/%Y",
    "signature_image": None,
    "offset_x": 0.0,
    "offset_y": 0.0,
}


# ======================================================================
# Paths and helpers
# ======================================================================
def resource_path(name: str) -> Path:
    """Location of resources bundled into the exe (the icon)."""
    return Path(getattr(sys, "_MEIPASS", mc.app_dir())) / name


def open_path(path: Path) -> None:
    """Open a file or folder with its default Windows/desktop app."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif "microsoft" in platform.release().lower():  # WSL: hand it to Windows
            win_path = subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
            subprocess.Popen(["explorer.exe", win_path])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        messagebox.showinfo(APP_NAME, f"File location:\n{path}")


def parse_date(text: str) -> dt.date:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date must look like 2026-10-15 or 10/15/2026, not {text!r}.")


def lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


# ======================================================================
# Main window
# ======================================================================
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.data = mc.data_dir()
        self.config_path = self.data / "config.json"
        self.checks_dir = self.data / "checks"
        self.register_path = self.checks_dir / "register.csv"
        self.cfg: dict | None = None

        root.title(APP_NAME)
        style = ttk.Style(root)
        style.configure("Heading.TLabel", font=("TkDefaultFont", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Error.TLabel", foreground="#b00020")
        style.configure("Words.TLabel", foreground="#1f6b4a")

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.check_tab = ttk.Frame(self.tabs, padding=14)
        self.settings_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.check_tab, text="Write a check")
        self.tabs.add(self.settings_tab, text="Settings")

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, style="Hint.TLabel", anchor="w").pack(
            fill="x", padx=14, pady=(0, 8))

        self.build_check_tab()
        self.build_settings_tab()
        self.load_config()
        self.set_next_number()

    # ------------------------------------------------------------------ config
    def load_config(self) -> None:
        if self.config_path.exists():
            try:
                self.cfg = mc.load_config(self.config_path)
            except (ValueError, OSError) as e:
                messagebox.showerror(APP_NAME, f"Could not read {self.config_path}:\n{e}")
                self.cfg = None
        self.fill_settings(self.cfg or DEFAULT_CONFIG)
        if self.cfg is None:
            self.tabs.select(self.settings_tab)
            self.status.set("First run: fill in your payer and bank details, then click Save.")
        else:
            self.status.set(f"Data folder: {self.data}")

    def require_config(self) -> dict:
        if self.cfg is None:
            self.tabs.select(self.settings_tab)
            raise ValueError("Set up your payer and bank details on the Settings tab and click Save first.")
        return self.cfg

    # ============================================================ check tab
    def build_check_tab(self) -> None:
        f = self.check_tab
        f.columnconfigure(1, weight=1)
        self.v_number = tk.StringVar()
        self.v_date = tk.StringVar(value=dt.date.today().isoformat())
        self.v_payee = tk.StringVar()
        self.v_amount = tk.StringVar()
        self.v_words = tk.StringVar()
        self.v_memo = tk.StringVar()

        row = 0
        top = ttk.Frame(f)
        top.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(top, text="Check No.").pack(side="left")
        ttk.Entry(top, textvariable=self.v_number, width=10).pack(side="left", padx=(6, 24))
        ttk.Label(top, text="Date").pack(side="left")
        ttk.Entry(top, textvariable=self.v_date, width=12).pack(side="left", padx=6)
        ttk.Button(top, text="Today", command=lambda: self.v_date.set(dt.date.today().isoformat())).pack(
            side="left")

        row += 1
        ttk.Label(f, text="Pay to the order of").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        payee = ttk.Entry(f, textvariable=self.v_payee)
        payee.grid(row=row, column=1, sticky="ew", pady=4)
        payee.focus_set()

        row += 1
        ttk.Label(f, text="Amount  $").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        amt = ttk.Frame(f)
        amt.grid(row=row, column=1, sticky="ew")
        ttk.Entry(amt, textvariable=self.v_amount, width=16).pack(side="left")
        ttk.Label(amt, textvariable=self.v_words, style="Words.TLabel").pack(side="left", padx=10)
        self.v_amount.trace_add("write", lambda *_: self.update_amount_hints())

        row += 1
        ttk.Label(f, text="Memo").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(f, textvariable=self.v_memo).grid(row=row, column=1, sticky="ew", pady=4)

        # actions
        row += 1
        buttons = ttk.Frame(f)
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text="Create check", command=lambda: self.make(sample=False)).pack(side="right")
        ttk.Button(buttons, text="Sample (VOID)", command=lambda: self.make(sample=True)).pack(
            side="right", padx=6)
        ttk.Button(buttons, text="Clear", command=self.clear_form).pack(side="left")
        ttk.Button(buttons, text="Open checks folder", command=self.open_checks_folder).pack(side="left", padx=6)
        row += 1
        ttk.Label(f, text="The PDF opens when it's ready. " + PRINT_HINT, style="Hint.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="e", pady=(4, 0))
        self.update_amount_hints()

    def update_amount_hints(self) -> None:
        try:
            self.v_words.set(mc.amount_in_words(mc.parse_amount(self.v_amount.get())) + " dollars")
        except ValueError:
            self.v_words.set("")

    def clear_form(self) -> None:
        for var in (self.v_payee, self.v_amount, self.v_memo):
            var.set("")
        self.v_date.set(dt.date.today().isoformat())
        self.set_next_number()
        self.update_amount_hints()

    def set_next_number(self) -> None:
        if self.cfg is None:
            return
        try:
            self.v_number.set(str(mc.next_check_number(self.cfg, mc.read_register(self.register_path))))
        except (OSError, ValueError, KeyError) as e:
            self.v_number.set("")
            messagebox.showerror(APP_NAME, f"Could not read {self.register_path}:\n{e}\n\n"
                                           "Fix the file (or move it away) and try again.")

    def make(self, sample: bool, guides: bool = False) -> None:
        """Create a check (or a VOID sample / alignment page) from the form."""
        try:
            cfg = self.require_config()
            register = mc.read_register(self.register_path)
            if guides:  # alignment page: the form doesn't need to be filled in
                kw = dict(number=mc.next_check_number(cfg, register), payee=self.v_payee.get().strip() or "Test",
                          amount=Decimal("1.00"), date=dt.date.today())
            else:
                try:
                    number = int(self.v_number.get().strip())
                except ValueError:
                    raise ValueError("Check No. must be a whole number.") from None
                payee = self.v_payee.get().strip()
                if not payee:
                    raise ValueError("Enter who the check is made out to.")
                if not self.v_amount.get().strip():
                    raise ValueError("Enter the amount.")
                kw = dict(number=number, payee=payee, amount=mc.parse_amount(self.v_amount.get()),
                          date=parse_date(self.v_date.get()), memo=self.v_memo.get().strip())
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not read {self.register_path}:\n{e}\n\n"
                                           "If it's open in Excel, close it and try again.")
            return

        if not sample and mc.is_printed(kw["number"], register) and not messagebox.askyesno(
                APP_NAME, f"Check #{kw['number']} is already in the register.\n\n"
                         "Create another check with the same number?\n"
                         "(To reprint the original, open its PDF from the checks folder.)",
                icon="warning"):
            return

        try:
            output = mc.write_check(cfg, self.checks_dir, sample=sample or guides, guides=guides, **kw)
        except PermissionError as e:
            messagebox.showerror(APP_NAME, f"Can't write {e.filename or 'the PDF'}.\n\n"
                                           "If it's open in another program (a PDF viewer or Excel), "
                                           "close it and try again.")
            return
        except (ValueError, KeyError, OSError, ArithmeticError) as e:
            messagebox.showerror(APP_NAME, f"Could not create the PDF:\n{e}")
            return

        open_path(output)
        if sample or guides:
            self.status.set(f"Wrote {output}. {PRINT_HINT}")
        else:
            self.status.set(f"Check #{kw['number']} for ${mc.money(kw['amount'])} to {kw['payee']} "
                            f"saved as {output.name}. {PRINT_HINT}")
            self.clear_form()

    def open_checks_folder(self) -> None:
        self.checks_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.checks_dir)

    # ========================================================= settings tab
    def build_settings_tab(self) -> None:
        f = self.settings_tab
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)
        self.s = {k: tk.StringVar() for k in (
            "payer_name", "bank_name", "fractional_routing", "routing_number", "account_number",
            "first_check_number", "micr_style", "micr_digits", "date_format", "signature_image",
            "offset_x", "offset_y")}

        def entry(row, col, label, key, width=None, hint=None):
            ttk.Label(f, text=label).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else 16, 6), pady=3)
            w = ttk.Entry(f, textvariable=self.s[key], width=width or 20)
            w.grid(row=row, column=col + 1, sticky="w" if width else "ew", pady=3)
            if hint:
                ttk.Label(f, text=hint, style="Hint.TLabel").grid(row=row + 1, column=col + 1, sticky="w")
            return w

        def text(row, col, label, height):
            ttk.Label(f, text=label).grid(row=row, column=col, sticky="nw", padx=(0 if col == 0 else 16, 6), pady=3)
            w = tk.Text(f, height=height, width=30, wrap="none", font="TkTextFont", relief="flat", borderwidth=0,
                        highlightthickness=1, highlightbackground="#a0a0a0", highlightcolor="#0078d4", padx=4, pady=2)
            w.grid(row=row, column=col + 1, sticky="ew", pady=3)
            return w

        ttk.Label(f, text="Your name / business", style="Heading.TLabel").grid(row=0, column=0, columnspan=2,
                                                                                sticky="w", pady=(0, 4))
        ttk.Label(f, text="Bank", style="Heading.TLabel").grid(row=0, column=2, columnspan=2, sticky="w",
                                                                padx=(16, 0), pady=(0, 4))
        entry(1, 0, "Name", "payer_name")
        entry(1, 2, "Bank name", "bank_name")
        self.t_payer_address = text(2, 0, "Address", 3)
        self.t_bank_address = text(2, 2, "City / address", 3)
        entry(3, 2, "Fractional routing", "fractional_routing", hint="Optional, e.g. 12-3456/7890")

        ttk.Label(f, text="MICR line (as printed on your existing checks)", style="Heading.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(14, 4))
        entry(6, 0, "Routing number", "routing_number", hint="9 digits")
        entry(6, 2, "Account number", "account_number", hint="Digits and dashes only")
        ttk.Label(f, text="Layout").grid(row=8, column=0, sticky="w", pady=3)
        ttk.Combobox(f, textvariable=self.s["micr_style"], values=("business", "personal"), state="readonly",
                     width=12).grid(row=8, column=1, sticky="w", pady=3)
        ttk.Label(f, text="business: check number first  ·  personal: check number last",
                  style="Hint.TLabel").grid(row=9, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="Check no. digits", padding=(16, 0, 6, 0)).grid(row=8, column=2, sticky="w")
        ttk.Spinbox(f, textvariable=self.s["micr_digits"], from_=4, to=8, width=6).grid(
            row=8, column=3, sticky="w")

        ttk.Label(f, text="Checks", style="Heading.TLabel").grid(row=10, column=0, columnspan=4, sticky="w",
                                                                  pady=(14, 4))
        entry(11, 0, "First check number", "first_check_number", width=10,
              hint="Used until the register has checks in it")
        ttk.Label(f, text="Date format", padding=(16, 0, 6, 0)).grid(row=11, column=2, sticky="w")
        ttk.Combobox(f, textvariable=self.s["date_format"], values=list(DATE_FORMATS), state="readonly",
                     width=18).grid(row=11, column=3, sticky="w")
        ttk.Label(f, text="Signature image").grid(row=13, column=0, sticky="w", pady=3)
        sig = ttk.Frame(f)
        sig.grid(row=13, column=1, columnspan=3, sticky="ew", pady=3)
        sig.columnconfigure(0, weight=1)
        ttk.Entry(sig, textvariable=self.s["signature_image"]).grid(row=0, column=0, sticky="ew")
        ttk.Button(sig, text="Browse...", command=self.browse_signature).grid(row=0, column=1, padx=4)
        ttk.Button(sig, text="None", command=lambda: self.s["signature_image"].set("")).grid(row=0, column=2)
        ttk.Label(f, text="Optional transparent PNG. Leave empty to sign by hand.", style="Hint.TLabel").grid(
            row=14, column=1, columnspan=3, sticky="w")

        ttk.Label(f, text="Printer calibration (inches)", style="Heading.TLabel").grid(
            row=15, column=0, columnspan=4, sticky="w", pady=(14, 4))
        cal = ttk.Frame(f)
        cal.grid(row=16, column=0, columnspan=4, sticky="w")
        ttk.Label(cal, text="Offset X").pack(side="left")
        ttk.Spinbox(cal, textvariable=self.s["offset_x"], from_=-1, to=1, increment=0.01, width=7,
                    format="%.2f").pack(side="left", padx=(6, 20))
        ttk.Label(cal, text="Offset Y").pack(side="left")
        ttk.Spinbox(cal, textvariable=self.s["offset_y"], from_=-1, to=1, increment=0.01, width=7,
                    format="%.2f").pack(side="left", padx=6)
        ttk.Label(cal, text="+X moves right, +Y moves down", style="Hint.TLabel").pack(side="left", padx=12)
        ttk.Label(f, text="Print the alignment page on plain paper, hold it behind a blank check against a window, "
                          "and adjust until the dashed lines match the perforations.",
                  style="Hint.TLabel", wraplength=620).grid(row=17, column=0, columnspan=4, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(f)
        buttons.grid(row=18, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(buttons, text="Save", command=self.save_settings).pack(side="right")
        ttk.Button(buttons, text="Save + alignment page", command=self.save_and_align).pack(side="right", padx=6)
        ttk.Button(buttons, text="Open data folder", command=lambda: open_path(self.data)).pack(side="left")

    def fill_settings(self, cfg: dict) -> None:
        payer, bank = cfg.get("payer", {}), cfg.get("bank", {})
        self.s["payer_name"].set(payer.get("name", ""))
        self.s["bank_name"].set(bank.get("name", ""))
        self.s["fractional_routing"].set(bank.get("fractional_routing") or "")
        self.s["routing_number"].set(cfg.get("routing_number", ""))
        self.s["account_number"].set(cfg.get("account_number", ""))
        self.s["first_check_number"].set(str(cfg.get("first_check_number", 1001)))
        self.s["micr_style"].set(cfg.get("micr_style", "business"))
        self.s["micr_digits"].set(str(cfg.get("micr_check_number_digits", 6)))
        fmt = cfg.get("date_format", "%m/%d/%Y")
        shown = next((k for k, v in DATE_FORMATS.items() if v == fmt), None)
        if shown is None:  # a custom format typed into config.json: offer it as-is
            shown = fmt
            DATE_FORMATS[fmt] = fmt
        self.s["date_format"].set(shown)
        self.s["signature_image"].set(cfg.get("signature_image") or "")
        self.s["offset_x"].set(f"{float(cfg.get('offset_x', 0)):.2f}")
        self.s["offset_y"].set(f"{float(cfg.get('offset_y', 0)):.2f}")
        for widget, value in ((self.t_payer_address, payer.get("address", [])),
                              (self.t_bank_address, bank.get("address", []))):
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(value))

    def settings_to_config(self) -> dict:
        """Read the Settings form into a config dict (keeping any extra keys), or raise ValueError."""
        s = {k: v.get().strip() for k, v in self.s.items()}
        cfg = dict(self.cfg or DEFAULT_CONFIG)
        if not s["payer_name"]:
            raise ValueError("Enter your name or business name.")
        if not s["bank_name"]:
            raise ValueError("Enter your bank's name.")
        cfg["payer"] = {**cfg.get("payer", {}), "name": s["payer_name"],
                        "address": lines(self.t_payer_address.get("1.0", "end"))}
        cfg["bank"] = {**cfg.get("bank", {}), "name": s["bank_name"],
                       "address": lines(self.t_bank_address.get("1.0", "end")),
                       "fractional_routing": s["fractional_routing"]}
        cfg["routing_number"] = s["routing_number"]
        cfg["account_number"] = s["account_number"]
        cfg["micr_style"] = s["micr_style"]
        cfg["date_format"] = DATE_FORMATS.get(s["date_format"], "%m/%d/%Y")
        cfg["signature_image"] = s["signature_image"] or None
        try:
            cfg["first_check_number"] = int(s["first_check_number"])
            cfg["micr_check_number_digits"] = int(s["micr_digits"])
        except ValueError:
            raise ValueError("First check number and check no. digits must be whole numbers.") from None
        try:
            cfg["offset_x"] = round(float(s["offset_x"]), 3)
            cfg["offset_y"] = round(float(s["offset_y"]), 3)
        except ValueError:
            raise ValueError("Offsets must be numbers, e.g. 0.05 or -0.1.") from None
        if max(abs(cfg["offset_x"]), abs(cfg["offset_y"])) > 1:
            raise ValueError("Offsets are in inches and should be small (between -1 and 1).")
        if cfg["signature_image"]:
            sig = Path(cfg["signature_image"])
            if not (sig if sig.is_absolute() else self.data / sig).exists():
                raise ValueError(f"Signature image not found:\n{sig}")
        mc.micr_characters(cfg, cfg["first_check_number"])  # validates routing / account / style
        return cfg

    def save_settings(self) -> bool:
        try:
            cfg = self.settings_to_config()
            mc.save_config(self.config_path, cfg)
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return False
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not save {self.config_path}:\n{e}")
            return False
        self.cfg = cfg
        self.set_next_number()
        self.status.set(f"Settings saved to {self.config_path}")
        return True

    def save_and_align(self) -> None:
        if self.save_settings():
            self.make(sample=True, guides=True)

    def browse_signature(self) -> None:
        name = filedialog.askopenfilename(title="Signature image", filetypes=[("PNG image", "*.png"),
                                                                                ("All files", "*.*")])
        if not name:
            return
        path = Path(name)
        try:  # keep it relative when it's inside the data folder, so the folder can be moved
            path = path.relative_to(self.data)
        except ValueError:
            pass
        self.s["signature_image"].set(str(path))


def main() -> None:
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    if sys.platform == "win32":
        try:
            root.iconbitmap(default=str(resource_path("icon.ico")))
        except tk.TclError:
            pass
    App(root)
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()


if __name__ == "__main__":
    main()
