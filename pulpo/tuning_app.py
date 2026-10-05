"""Local tuning window. Only performance hints and disposable benchmarks."""
from __future__ import annotations

from pathlib import Path
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


def check_gui():
    """Packaging smoke check; constructs Tk widgets without opening the app."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
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
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    profile = Path(profile) if profile else default_profile_path()
    root = tk.Tk()
    root.title("Pulpo performance tuning — Preview")
    root.geometry("920x610")
    panel = ttk.Frame(root, padding=20)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Tune evidence collection", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(panel, text=f"{machine()['logical_cpus']} logical CPUs • worker limit {thread_limit()}").pack(anchor="w", pady=8)
    ttk.Label(panel, text="Approval, audit and evidence rules are fixed. Settings take effect on the next collection.").pack(anchor="w")
    resolved = load_settings(profile)
    mode = tk.StringVar(value="Recommended" if resolved == recommended() else "Custom")
    workers = tk.StringVar(value=str(resolved.workers))
    choices = ttk.Frame(panel)
    choices.pack(fill="x", pady=14)
    ttk.Radiobutton(choices, text="Recommended (up to 2 threads)", variable=mode,
                    value="Recommended").pack(side="left")
    ttk.Radiobutton(choices, text="Custom thread count", variable=mode, value="Custom").pack(side="left", padx=12)
    spin = ttk.Spinbox(choices, from_=0, to=thread_limit(), width=5, textvariable=workers)
    spin.pack(side="left")
    ttk.Label(panel, text="0 or 1 collects serially. More workers may increase memory use; no hard RAM cap is promised.").pack(anchor="w")
    ttk.Label(panel, text=f"Profile: {profile}", wraplength=740).pack(anchor="w", pady=8)
    if profile != default_profile_path():
        ttk.Label(panel, text="Custom profile: runtime use requires passing it to create_collector().").pack(anchor="w")
    output = tk.Text(panel, height=15, wrap="word", state="disabled")
    output.pack(fill="both", expand=True, pady=8)
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    status = tk.StringVar(value="Ready. Process collectors are available for experiments only.")
    ttk.Label(panel, textvariable=status, wraplength=740).pack(anchor="w", pady=10)
    events = queue.Queue()
    active = False
    controls = []
    latest_report = None

    def append(message):
        output.configure(state="normal")
        output.insert("end", message + "\n")
        output.see("end")
        output.configure(state="disabled")

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
            counts = sorted({0, recommended().workers, selected().workers})
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

    for label, action in (("Compare thread settings", compare), ("Apply setting", apply),
                          ("Recommended", restore), ("Undo setting", rollback), ("Process experiment", experiment),
                          ("Save results", export)):
        button = ttk.Button(buttons, text=label, command=action)
        button.pack(side="left", padx=(0, 8))
        controls.append(button)

    def poll():
        nonlocal active, latest_report
        while True:
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                active = False
                for control in controls:
                    control.configure(state="normal")
                status.set("Ready. Process experiments never apply runtime settings.")
            elif kind == "error":
                append("FAILED: " + value + "\nNo setting was applied by the failed operation.")
            elif kind == "report":
                latest_report = value
            else:
                append(value)
        root.after(100, poll)

    def close():
        if active:
            messagebox.showinfo("Operation in progress", "Wait for the operation to finish before closing.")
            return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()
