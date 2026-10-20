"""Independent WSL Control Center setup/repair. Never imports Pulpo."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

NAME = "pulpo-control-center"
MARKER = "pulpo.wsl.application.v1"
LAUNCHER = '''import fcntl, os, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
if "--help" not in sys.argv:
    lock = os.open(root.parent / ".pulpo-control-center.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_SH)
sys.path.insert(0, str(root / "app"))
from pulpo.cli import main
raise SystemExit(main())
'''


def default_root():
    return Path.home() / ".local/share" / NAME


def environment():
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")
    if platform.system() != "Linux" or "microsoft" not in platform.release().lower():
        raise ValueError("This package supports WSL only; no Windows application is installed")
    if os.geteuid() == 0:
        raise ValueError("Run as your normal WSL user, without sudo")


def safe_root(value):
    root = Path(os.path.abspath(value))
    if root.name != NAME or root.parent == Path("/"):
        raise ValueError(f"Installation directory must be named {NAME} below a user directory")
    # Refuse substituted parents before any mkdir, rename or removal.
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("Installation paths must not contain symbolic links")
    return root


def inventory(root):
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            mode = path.lstat().st_mode
            kind = "directory" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "unsafe"
            if kind == "unsafe":
                raise ValueError("Unexpected link or special file; installation left untouched")
            result[path.relative_to(root).as_posix()] = kind
    return result


def owned(root, expected_root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Installation directory is not an owned application directory")
    marker = root / "install.json"
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 2_000_000:
        raise ValueError("Missing or invalid ownership record; directory left untouched")
    record = json.loads(marker.read_text(encoding="utf-8"))
    if record.get("owner") != MARKER or record.get("root") != str(expected_root):
        raise ValueError("Directory is not owned by this WSL package")
    expected = record.get("inventory")
    if not isinstance(expected, dict) or expected.get("install.json") != "file":
        raise ValueError("Invalid ownership inventory")
    actual = inventory(root)
    if any(expected.get(path) != kind for path, kind in actual.items()):
        raise ValueError("Unexpected files found; move personal files out before repair/removal")
    # Missing or damaged owned files are repairable. Extra files are never deleted.
    return record


class Package:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextlib.contextmanager
    def validated(self):
        with zipfile.ZipFile(self.path) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or len({i.filename for i in infos}) != len(infos):
                raise ValueError("Invalid package member count or duplicate names")
            if sum(i.file_size for i in infos) > 64 * 1024 * 1024:
                raise ValueError("Package exceeds the bounded application size")
            document = json.loads(archive.read("package.json"))
            files = document.get("files")
            if document.get("schema") != 1 or not isinstance(files, dict) or not files:
                raise ValueError("Invalid package manifest")
            if set(archive.namelist()) != set(files) | {"__main__.py", "package.json"}:
                raise ValueError("Unexpected package contents")
            for name, digest in files.items():
                parts = PurePosixPath(name).parts
                if (not name.startswith("app/pulpo/") or ".." in parts or "\\" in name
                        or PurePosixPath(name).as_posix() != name):
                    raise ValueError("Unsafe application path")
                mode = archive.getinfo(name).external_attr >> 16
                if stat.S_ISLNK(mode) or hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    raise ValueError("Package content hash mismatch or unsafe link")
            if "app/pulpo/cli.py" not in files:
                raise ValueError("Missing application entry point")
            yield archive, document


@contextlib.contextmanager
def locked(root):
    import fcntl
    root.parent.mkdir(parents=True, exist_ok=True)
    path = root.parent / ("." + NAME + ".lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Unsafe maintenance lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Control Center or another setup/repair is running; close it before maintenance") from error
        yield
    finally:
        os.close(descriptor)


def recover(root):
    previous = root.with_name(NAME + ".previous")
    if previous.exists() or previous.is_symlink():
        owned(previous, root)
        if root.exists():
            # Do not discard the older install after an interrupted replacement.
            raise ValueError("Interrupted repair: previous installation retained. Uninstall the current package first, then run repair again to recover the previous copy")
        previous.rename(root)


def install(package, value, repair=False):
    environment()
    root = safe_root(value)
    # Validate before creating anything or touching an existing installation.
    with package.validated() as (archive, document):
        with locked(root):
            recover(root)
            if root.exists():
                owned(root, root)
                if not repair:
                    raise ValueError("Already installed; choose Repair / Reinstall")
            elif repair:
                # Repair also supports reinstalling an installation already removed.
                pass
            stage = Path(tempfile.mkdtemp(prefix="." + NAME + "-stage-", dir=root.parent))
            previous = root.with_name(NAME + ".previous")
            try:
                for name in document["files"]:
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
                (stage / "launch.py").write_text(LAUNCHER, encoding="utf-8")
                shutil.copyfile(package.path, stage / "Pulpo-Setup.pyz")
                interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
                record = {"owner": MARKER, "root": str(root), "version": document["version"],
                          "source_revision": document["source_revision"], "python": interpreter,
                          "inventory": inventory(stage) | {"install.json": "file"}}
                (stage / "install.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
                # Check construction independently of any source checkout or GUI/display.
                subprocess.run([interpreter, "-I", "-B", str(stage / "launch.py"), "--help"],
                               check=True, stdout=subprocess.DEVNULL, timeout=30)
                if root.exists():
                    root.rename(previous)
                try:
                    stage.rename(root)
                except BaseException:
                    if previous.exists():
                        previous.rename(root)
                    raise
                if previous.exists():
                    # All entries were checked as package-owned before replacement.
                    shutil.rmtree(previous)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
    return f"Installed {document['version']}. Settings and evidence were not changed."


def uninstall(value):
    environment()
    root = safe_root(value)
    with locked(root):
        # Deliberately do not recover a previous installation on uninstall.
        if not root.exists():
            return "Application is already absent. Settings and evidence retained."
        owned(root, root)
        shutil.rmtree(root)
    return "Application removed. Settings and evidence retained."


def launch(value, gui_check=False):
    environment()
    root = safe_root(value)
    with locked(root):
        record = owned(root, root)
        # Never execute an interpreter path obtained from mutable install metadata.
        interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
        command = [interpreter, "-I", "-B", str(root / "launch.py"), "tune"]
        if gui_check:
            # The child owns a shared lifetime lock; release our exclusive lock
            # before waiting for its GUI construction check.
            pass
        else:
            subprocess.Popen(command, cwd=Path.home(), start_new_session=True)
    if gui_check:
        return subprocess.run(command + ["--gui-check"], check=True, timeout=30).returncode
    return f"Started Control Center {record['version']}; graphical startup unverified, enforcement unassessed."


def diagnose(value):
    environment()
    root = safe_root(value)
    lines = ["WSL detected", f"Python {platform.python_version()}"]
    try:
        import tkinter
        lines.append(f"Tk available ({tkinter.TkVersion})")
    except ImportError:
        lines.append("Tk missing: install Ubuntu's python3-tk package before opening the GUI")
    lines.append("Display configured; reachability unverified" if os.environ.get("DISPLAY") else
                 "No DISPLAY configured: WSL graphical applications may not open")
    if not root.exists():
        lines.append("Application not installed")
    else:
        lines.append(f"Installed version: {owned(root, root)['version']}")
        with Package(root / "Pulpo-Setup.pyz").validated() as (_, manifest):
            damaged = sum(not (root / name).is_file() or
                          hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
                          for name, digest in manifest["files"].items())
        lines.append(f"Application files differing from package: {damaged} (integrity check, not publisher authentication)")
    lines.append("No settings, evidence, credentials or source exports were read")
    return "\n".join(lines)


def gui(package, root):
    import tkinter as tk
    from tkinter import messagebox, ttk
    environment()
    with package.validated() as (_, manifest):
        version = manifest["version"]
    window = tk.Tk()
    window.title("Pulpo — WSL Setup & Repair")
    window.geometry("740x550")
    window.minsize(600, 450)
    window.configure(background="#25222b")
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure("TFrame", background="#25222b")
    style.configure("TLabel", background="#25222b", foreground="#f4f0f7", font=("TkDefaultFont", 11))
    style.configure("TButton", padding=10, background="#64418a", foreground="#ffffff")
    panel = ttk.Frame(window, padding=24)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Control Center · WSL", font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
    description = ttk.Label(panel, text=f"Package {version}\nInstall or repair the application. Saved settings and evidence stay separate.", wraplength=660)
    description.pack(fill="x", pady=(10, 12))
    ttk.Label(panel, text=str(root), wraplength=660).pack(fill="x")
    actions = ttk.Frame(panel)
    actions.pack(fill="x", pady=12)
    output = tk.Text(panel, height=10, wrap="word", background="#f4f0f7", foreground="#25222b", padx=12, pady=12)
    output.pack(fill="both", expand=True)
    buttons = []

    def report(text):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", text)
        output.configure(state="disabled")

    def run(action):
        if action == "uninstall" and not messagebox.askyesno("Remove Control Center?", "Remove only installed application files? Saved settings and evidence will be retained.", parent=window):
            return
        for button in buttons:
            button.configure(state="disabled")
        report("Working…")
        window.update_idletasks()
        try:
            result = {"install": lambda: install(package, root), "repair": lambda: install(package, root, True),
                      "uninstall": lambda: uninstall(root), "launch": lambda: launch(root),
                      "check": lambda: diagnose(root)}[action]()
            report(str(result))
        except Exception as error:
            report(f"Could not complete operation: {error}\n\nApplication repair cannot repair the WSL graphics service. No automatic settings reset is performed.")
        finally:
            for button in buttons:
                button.configure(state="normal")

    for index, (text, action) in enumerate((("Install", "install"), ("Repair / Reinstall", "repair"),
            ("Open", "launch"), ("Uninstall", "uninstall"), ("Check setup", "check"))):
        button = ttk.Button(actions, text=text, command=lambda key=action: run(key))
        button.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
        actions.columnconfigure(index % 3, weight=1)
        buttons.append(button)
    report("Use a trusted package. Internal hashes detect damaged contents; they do not authenticate the publisher.\n\nInstallation does not start a workload or verify enforcement.")
    panel.bind("<Configure>", lambda event: (description.configure(wraplength=max(200, panel.winfo_width() - 50))))
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("install", "repair", "uninstall", "check", "launch", "gui-check"))
    parser.add_argument("--root", type=Path, default=default_root(), help="directory named pulpo-control-center; default: ~/.local/share/pulpo-control-center")
    parser.add_argument("--yes", action="store_true", help="confirm CLI application removal")
    args = parser.parse_args()
    try:
        environment()
        package = Package(sys.argv[0])
        if not args.action:
            gui(package, safe_root(args.root))
            return 0
        if args.action == "uninstall" and not args.yes:
            parser.error("uninstall requires --yes; settings and evidence will be retained")
        result = {"install": lambda: install(package, args.root),
                  "repair": lambda: install(package, args.root, True),
                  "uninstall": lambda: uninstall(args.root), "check": lambda: diagnose(args.root),
                  "launch": lambda: launch(args.root), "gui-check": lambda: launch(args.root, True)}[args.action]()
        print(result)
        return 0
    except Exception as error:
        print(f"Setup could not continue: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
