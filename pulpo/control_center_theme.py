"""Opaque glass-inspired presentation; no desktop effects or system settings."""

PALETTE = {
    "sidebar": "#242129", "sidebar_text": "#E8E2EF",
    "header": "#302A3A", "header_text": "#FAF8FD", "header_muted": "#D6CDDF",
    "background": "#EEEBF3", "surface": "#FCFAFE",
    "text": "#2B2633", "muted": "#62586D", "accent": "#674396",
    "selected": "#E4DAEF", "warning": "#865200", "error": "#A32935",
    "border": "#C9BFD4", "control_border": "#887797", "edge": "#FFFFFF",
    "shadow": "#D9D2E2", "chart": "#2B2633", "chart_border": "#65556F",
    "chart_grid": "#484050", "chart_muted": "#CFC5DC",
}


def configure(root):
    from tkinter import ttk
    p = PALETTE
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=p["background"])
    style.configure("TLabel", background=p["background"], foreground=p["text"], font=("TkDefaultFont", 11))
    style.configure("TButton", padding=(10, 8), font=("TkDefaultFont", 10),
                    background=p["surface"], foreground=p["accent"], bordercolor=p["control_border"],
                    lightcolor=p["edge"], darkcolor=p["border"], focuscolor=p["accent"], borderwidth=1)
    style.map("TButton", foreground=[("disabled", p["muted"])],
              background=[("disabled", p["background"]), ("pressed", p["selected"]), ("active", p["selected"])],
              bordercolor=[("focus", p["accent"])])
    style.configure("Nav.TButton", background=p["sidebar"], foreground=p["sidebar_text"],
                    anchor="w", borderwidth=0, padding=(12, 10), focuscolor=p["header_text"])
    style.map("Nav.TButton", background=[("pressed", p["accent"]), ("active", p["header"])],
              foreground=[("active", p["header_text"])])
    style.configure("Selected.Nav.TButton", background=p["accent"], foreground=p["header_text"])
    style.map("Selected.Nav.TButton", background=[("active", p["accent"])])
    style.configure("Title.TLabel", font=("TkDefaultFont", 22, "bold"))
    style.configure("Heading.TLabel", font=("TkDefaultFont", 13, "bold"))
    style.configure("Muted.TLabel", foreground=p["muted"])
    style.configure("Status.TLabel", foreground=p["warning"])
    style.configure("Header.TFrame", background=p["header"])
    style.configure("HeaderTitle.TLabel", background=p["header"], foreground=p["header_text"], font=("TkDefaultFont", 22, "bold"))
    style.configure("HeaderMuted.TLabel", background=p["header"], foreground=p["header_muted"], font=("TkDefaultFont", 10))
    for name in ("TRadiobutton", "TCheckbutton"):
        style.configure(name, background=p["background"], foreground=p["text"], font=("TkDefaultFont", 10), focuscolor=p["accent"])
        style.map(name, background=[("active", p["selected"])], foreground=[("disabled", p["muted"])])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=p["surface"], background=p["surface"], foreground=p["text"],
                        bordercolor=p["control_border"], lightcolor=p["edge"], darkcolor=p["border"],
                        arrowcolor=p["accent"], insertcolor=p["text"], padding=5)
        style.map(name, fieldbackground=[("disabled", p["background"]), ("readonly", p["surface"])],
                  foreground=[("disabled", p["muted"])], bordercolor=[("focus", p["accent"])],
                  selectbackground=[("!disabled", p["accent"])], selectforeground=[("!disabled", p["header_text"])])
    style.configure("TNotebook", background=p["background"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(12, 8), background=p["background"], foreground=p["muted"])
    style.map("TNotebook.Tab", background=[("selected", p["surface"]), ("active", p["selected"])],
              foreground=[("selected", p["accent"])], lightcolor=[("selected", p["edge"])])
    style.configure("Vertical.TScrollbar", background=p["control_border"], troughcolor=p["background"],
                    bordercolor=p["background"], lightcolor=p["control_border"], darkcolor=p["control_border"],
                    arrowcolor=p["header_text"], width=13)
    style.map("Vertical.TScrollbar", background=[("active", p["accent"])])
    style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"],
                    bordercolor=p["border"], rowheight=28, font=("TkDefaultFont", 10))
    style.map("Treeview", background=[("selected", p["accent"])], foreground=[("selected", p["header_text"])])
    style.configure("Treeview.Heading", background=p["selected"], foreground=p["text"], padding=(8, 7),
                    font=("TkDefaultFont", 10, "bold"), relief="flat")
    style.map("Treeview.Heading", background=[("active", p["selected"])])
    # Defaults stay inside this Tk application, including its review dialogs.
    for key, value in (("background", p["surface"]), ("foreground", p["text"]),
                       ("selectBackground", p["accent"]), ("selectForeground", p["header_text"]),
                       ("insertBackground", p["text"])):
        root.option_add("*Text." + key, value)
    root.option_add("*TCombobox*Listbox.background", p["surface"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["header_text"])
    style.configure("Card.TFrame", background=p["surface"])
    style.configure("Card.TLabel", background=p["surface"])
    style.configure("CardHeading.TLabel", background=p["surface"], font=("TkDefaultFont", 13, "bold"))
    style.configure("Range.TButton", padding=(8, 5), font=("TkDefaultFont", 9))
    style.configure("Active.Range.TButton", background=p["selected"])
    style.configure("Row.TButton", background=p["surface"], foreground=p["text"], anchor="w", borderwidth=0,
                    padding=(0, 4), font=("TkDefaultFont", 11, "bold"))


def surface(parent, *, dark=False):
    """Return a geometry-managed shadow and an opaque bordered content frame."""
    import tkinter as tk
    p = PALETTE
    shadow = tk.Frame(parent, background=p["shadow"], borderwidth=0)
    body = tk.Frame(shadow, background=p["chart" if dark else "surface"], borderwidth=0,
                    highlightthickness=1, highlightbackground=p["chart_border" if dark else "border"])
    body.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 3))
    # A fixed edge adds depth without alpha, desktop sampling or repaint loops.
    tk.Frame(body, background=p["chart_border" if dark else "edge"], height=1).pack(fill="x")
    return shadow, body
