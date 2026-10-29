"""Launch the existing native Control Center with a read-only clinical lab page."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report',help='Explicit synthetic report to read once')
    parser.add_argument('--check',action='store_true',help='Construct and close widgets; does not prove visible rendering')
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/'vendor/control-center'))
    import tkinter as tk
    from pulpo_control_center.control_center import ControlCenter
    from clinical_observer import ClinicalPage
    root = tk.Tk()
    center = ControlCenter(root,ROOT/'local-settings'/'evidence-performance.json')
    root.title('Pulpo Control Center · Clinical Evaluation v0.1 · Synthetic only')
    clinical = ClinicalPage(center)
    if args.report:
        clinical.load(args.report)
    center.show('Clinical lab')
    if args.check:
        root.update_idletasks();root.destroy()
        print('PASS native widget construction; visible Ubuntu/WSLg rendering unproved')
    else:
        root.mainloop()

if __name__ == '__main__':
    main()
