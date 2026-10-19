"""Local tuning window. Only performance hints and disposable benchmarks."""
from __future__ import annotations

from pathlib import Path
import os
import queue
import json
import statistics
import subprocess
import sys
import tempfile
import threading
from time import perf_counter

from .evidence_tuning import (EvidenceSettings, default_profile_path, load_settings,
    machine, recommended, save_settings, restore_previous, check_settings, thread_limit)


def _prepare_tk_libraries():
    """Use bundled/local runtime data before Tk starts; retain explicit settings."""
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return
    roots = [Path(sys.prefix)]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        roots.insert(0, Path(bundled))
    for root in roots:
        candidates = [(root / "_tcl_data", root / "_tk_data")]
        candidates.extend((tcl, tcl.with_name("tk" + tcl.name[3:]))
                          for tcl in sorted((root / "tcl").glob("tcl[0-9]*")))
        for tcl, tk in candidates:
            if (tcl / "init.tcl").is_file() and (tk / "tk.tcl").is_file():
                # Relative paths let the native Tcl resolver use the same cwd
                # when an embedded environment maps Python's absolute paths.
                def native_path(path):
                    try:
                        return os.path.relpath(path).replace("\\", "/")
                    except ValueError:
                        return path.as_posix()
                os.environ.setdefault("TCL_LIBRARY", native_path(tcl))
                os.environ.setdefault("TK_LIBRARY", native_path(tk))
                return


def check_gui():
    """Packaging smoke check; constructs Tk widgets without opening the app."""
    _prepare_tk_libraries()
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        from .control_center import ControlCenter
        ControlCenter(root, default_profile_path())
        ttk.Frame(root).pack()
        ttk.Button(root, text="Apply setting").pack()
        ttk.Spinbox(root, from_=0, to=16).pack()
        tk.Text(root).pack()
        root.update_idletasks()
    finally:
        root.destroy()


def benchmark_threads(workers: int, surfaces=8, files=8, file_bytes=65536, repeats=5):
    """Capture-only benchmark, with serial equality outside each timing."""
    settings = EvidenceSettings(workers).validate()
    check_settings(settings)
    from .effect_reconcile import ParallelEvidenceCollector, SurfaceSpec, capture_surface
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory(prefix="pulpo-tuning-benchmark-") as temporary:
        roots = []
        for index in range(surfaces):
            root = Path(temporary) / str(index)
            root.mkdir()
            for number in range(files):
                (root / f"{number}.bin").write_bytes(b"x" * file_bytes)
            roots.append(SurfaceSpec(str(root), "evidence"))
        envelope = SimpleNamespace(surfaces=tuple(roots))
        collector = ParallelEvidenceCollector(workers=workers)
        values = []
        try:
            for _ in range(repeats):
                start = perf_counter()
                actual = collector.capture(envelope)
                values.append(perf_counter() - start)
                if actual != tuple(capture_surface(surface) for surface in roots):
                    raise ValueError("Benchmark snapshot differs from serial evidence")
        finally:
            collector.close()
    return {"workers": workers, "median_ms": statistics.median(values) * 1000,
            "samples_seconds": values, "files": surfaces * files, "correctness": "PASS"}


def launch(profile=None):
    _prepare_tk_libraries()
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    profile = Path(profile) if profile else default_profile_path()
    root = tk.Tk()
    from .control_center import ControlCenter
    center = ControlCenter(root, profile)
    panel = ttk.Frame(center.pages["Evidence"])
    panel.pack(fill="both", expand=True)
    center.text(panel, "Tune evidence collection", "Heading.TLabel")
    center.text(panel, f"Recorded • {machine()['logical_cpus']} logical CPUs • worker limit {thread_limit()}")
    center.text(panel, "Compare settings on disposable fixtures before saving a local performance hint. "
                "Approval, audit and evidence rules stay fixed. Settings take effect on the next collection.")
    resolved = load_settings(profile)
    mode = tk.StringVar(value="Recommended" if resolved == recommended() else "Custom")
    workers = tk.StringVar(value=str(resolved.workers))
    choices = ttk.Frame(panel)
    choices.pack(fill="x", pady=14)
    ttk.Radiobutton(choices, text="Default (serial, no helpers)", variable=mode,
                    value="Recommended").grid(row=0, column=0, columnspan=2, sticky="w", pady=6)
    ttk.Radiobutton(choices, text="Opt in: helper count", variable=mode, value="Custom").grid(row=1, column=0, sticky="w", pady=6)
    spin = ttk.Spinbox(choices, from_=0, to=thread_limit(), width=5, textvariable=workers)
    spin.grid(row=1, column=1, padx=12)
    ttk.Label(choices, text="Evidence worker count").grid(row=2, column=1, padx=12)
    def sync_mode(*_):
        spin.configure(state="normal" if mode.get() == "Custom" else "disabled")
    mode.trace_add("write", sync_mode)
    sync_mode()
    center.text(panel, "0 or 1 collects serially. More workers may increase memory use; no hard RAM cap is promised.")
    center.text(panel, f"Profile: {profile}")
    if profile != default_profile_path():
        center.text(panel, "Custom profile: runtime use requires passing it to create_collector().")
    center.text(panel, "Results appear in Activity. Save results exports the latest measurements only.", "Muted.TLabel")
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x", pady=10)
    status = tk.StringVar(value="Ready. No check has run in this session.")
    status_label = center.text(panel, "")
    status_label.configure(textvariable=status)
    events = queue.Queue()
    active = False
    controls = []
    latest_report = None

    def append(message):
        center.append(message)

    def selected():
        return recommended() if mode.get() == "Recommended" else EvidenceSettings(int(workers.get())).validate()

    def job(operation):
        nonlocal active
        if active:
            return
        active = True
        for control in controls:
            control.configure(state="disabled")
        status.set("Working on temporary fixtures…")
        append("Recorded: operation started on disposable fixtures. Awaiting result.")
        center.show("Activity")
        def run():
            try:
                events.put(("result", operation()))
            except Exception as exc:
                events.put(("error", str(exc)))
            finally:
                events.put(("done", None))
        threading.Thread(target=run, daemon=True).start()

    def apply():
        try:
            settings = selected()
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return
        job(lambda: f"Saved {settings.workers} workers after fresh correctness checks: {save_settings(settings, profile)}")

    def restore():
        job(lambda: f"Restored recommended settings after correctness checks: {save_settings(recommended(), profile)}")

    def rollback():
        job(lambda: f"Restored previous settings after fresh checks: {restore_previous(profile)}")

    def compare():
        try:
            counts = sorted({0, min(2, thread_limit()), selected().workers})
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return
        def run():
            rows = [benchmark_threads(count) for count in counts]
            events.put(("report", {"schema": "pulpo.thread-tuning-measurements.v1",
                "claim": "Recorded disposable capture-only measurements", "machine": machine(),
                "results": rows, "authority_effect": "none"}))
            return "Recorded temporary 64-file capture measurements (not full-cycle timings):\n" + "\n".join(
                f"{row['workers']} workers: {row['median_ms']:.2f} ms — canonical equality PASS" for row in rows)
        job(run)

    def experiment():
        # Fixed script/arguments; no command field, shell, or user-supplied code.
        script = Path(__file__).resolve().parent.parent / "scripts/benchmark_pulpo_cycle.py"
        if getattr(sys, "frozen", False) or not script.is_file():
            messagebox.showinfo("Experiment requires a source checkout",
                "Process full-cycle experiments use the source checkout's benchmark scripts. "
                "Process settings cannot be applied to the runtime in this release.")
            return
        def run():
            import psutil
            def checked(command, timeout):
                child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    stdout, stderr = child.communicate(timeout=timeout)
                    if child.returncode:
                        raise ValueError((stderr or stdout)[-4000:])
                    return stdout
                except BaseException:
                    # Stop only this benchmark's descendants on timeout/failure.
                    try:
                        processes = psutil.Process(child.pid).children(recursive=True)
                    except psutil.Error:
                        processes = []
                    for process in reversed(processes):
                        try:
                            process.terminate()
                        except psutil.Error:
                            pass
                    _, alive = psutil.wait_procs(processes, timeout=3)
                    for process in alive:
                        try:
                            process.kill()
                        except psutil.Error:
                            pass
                    if child.poll() is None:
                        child.kill()
                    child.communicate()
                    raise
            with tempfile.TemporaryDirectory(prefix="pulpo-tuning-process-") as temporary:
                result = Path(temporary) / "result.json"
                command = [sys.executable, str(script), "--repo", str(script.parent.parent),
                    "--sizes", "1000", "--repeats", "2", "--iterations", "10", "--workers", "2",
                    "--processes", str(min(8, thread_limit())), "--surfaces", "32",
                    "--files-per-surface", "4", "--file-bytes", "65536", "--json", str(result)]
                checked([sys.executable, str(script), "--repo", str(script.parent.parent),
                         "--self-test"], 180)
                stdout = checked(command, 600)
                document = json.loads(result.read_text(encoding="utf-8"))
                events.put(("report", document))
                events.put(("result", stdout.strip()))
                return "Recorded process experiment completed. Settings unchanged.\n" + str(document["claim"])
        job(run)

    def export():
        if latest_report is None:
            messagebox.showinfo("No measurements", "Run a comparison first.")
            return
        name = filedialog.asksaveasfilename(title="Save performance measurements",
            defaultextension=".json", initialfile="pulpo-tuning-results.json",
            filetypes=[("JSON measurements", "*.json")])
        if name:
            try:
                Path(name).write_text(json.dumps(latest_report, indent=2) + "\n", encoding="utf-8")
                append("Measurements saved: " + name)
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc))

    for index, (label, action) in enumerate((("Compare thread settings", compare), ("Apply setting", apply),
                          ("Serial default", restore), ("Undo setting", rollback), ("Process experiment", experiment),
                          ("Save results", export))):
        button = ttk.Button(buttons, text=label, command=action)
        button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=4)
        controls.append(button)
    for column in (0, 1):
        buttons.columnconfigure(column, weight=1)

    poll_handle = None

    def poll():
        nonlocal active, latest_report, poll_handle
        while True:
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                active = False
                for control in controls:
                    control.configure(state="normal")
                center.refresh_profile()
                status.set("Finished. Review the result in Activity. Process experiments never apply runtime settings.")
            elif kind == "error":
                append("FAILED: " + value + "\nReview System troubleshooting. "
                       "Refresh the local profile status to inspect the effective fallback.")
            elif kind == "report":
                latest_report = value
            else:
                append(value)
        poll_handle = root.after(100, poll)

    def cancel_poll(event):
        nonlocal poll_handle
        if event.widget is root and poll_handle is not None:
            root.after_cancel(poll_handle)
            poll_handle = None

    root.bind("<Destroy>", cancel_poll, add="+")

    def close():
        if active:
            messagebox.showinfo("Operation in progress", "Wait for the operation to finish before closing.")
            return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()
