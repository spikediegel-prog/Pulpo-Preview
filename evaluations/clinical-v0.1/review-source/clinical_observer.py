"""Bounded report projection. No Pulpo kernel imports or canonical-state access."""
import json
from pathlib import Path
import re
import stat
from clinical_config import validate, unique_object

def read_report(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 262144:
        raise ValueError('Select a regular clinical report under 256 KiB')
    with path.open('rb') as stream:
        raw = stream.read(262145)
    if len(raw) > 262144:
        raise ValueError('Report too large')
    r = json.loads(raw,object_pairs_hook=unique_object)
    if type(r) is not dict or r.get('schema') != 'pulpo.clinical-evaluation.v0.1' or r.get('synthetic_only') is not True:
        raise ValueError('Unsupported synthetic report')
    config = validate(r['config'])
    if r.get('engine') not in {'canonical','preview'} or not re.fullmatch('[a-f0-9]{40}',r.get('source_pin','')):
        raise ValueError('Invalid engine provenance')
    checks = r['checks']
    if type(checks) is not list or not 1 <= len(checks) <= 128:
        raise ValueError('Invalid checks')
    for c in checks:
        if (type(c) is not dict or type(c.get('passed')) is not bool
            or any(type(c.get(k)) is not str or len(c[k]) > 512 or any(ord(x)<32 and x not in '\t' for x in c[k]) for k in ['name','detail'])):
            raise ValueError('Invalid check row')
    expected = 'PASS' if all(c['passed'] for c in checks) else 'FAIL'
    if r.get('result') != expected or type(r.get('recorded_at_ns')) is not int or r['recorded_at_ns'] <= 0:
        raise ValueError('Inconsistent result or timestamp')
    if type(r.get('consequence_unknown')) is not int or not 0 <= r['consequence_unknown'] <= 128:
        raise ValueError('Invalid consequence count')
    # Whitelist a small non-authoritative presentation. Never retain raw permits,
    # arbitrary input fields, database handles, or callbacks into a runner.
    return {'engine':r['engine'],'source_pin':r['source_pin'],'config':config,
            'checks':[{'name':c['name'],'passed':c['passed'],'detail':c['detail']} for c in checks],
            'result':expected,'recorded_at_ns':r['recorded_at_ns'],
            'consequence_unknown':r['consequence_unknown']}

class ClinicalPage:
    def __init__(self, center):
        from tkinter import ttk, filedialog
        self.center = center
        self.observation = None
        page = ttk.Frame(center.container)
        center.pages['Clinical lab'] = page
        button = ttk.Button(center.sidebar, text='Clinical lab', style='Nav.TButton',
                            command=lambda:center.show('Clinical lab'))
        button.pack(fill='x',pady=3)
        center.navigation['Clinical lab'] = button
        center.text(page, 'Clinical evaluation · synthetic only', 'Title.TLabel')
        center.section(page,'Production enforcement: Unknown',
            'Central IT and satellite clinics. This observer cannot activate directives, issue permits, approve patches or connect to a clinical system.')
        center.section(page,'Site scopes / WSUS simulation / evidence',
            'Select an exported report from the separate lab runner. No report is read automatically or remembered as a live result.')
        self.status = center.text(page,'No report selected · current clinical evidence Unknown','Status.TLabel')
        ttk.Button(page,text='Open synthetic report…',command=lambda:self.choose(filedialog)).pack(anchor='w',pady=10)
        columns = ('result','check','detail')
        self.table = ttk.Treeview(page,columns=columns,show='headings',height=13)
        for name,width in [('result',80),('check',310),('detail',430)]:
            self.table.heading(name,text=name.title()); self.table.column(name,width=width,minwidth=70)
        self.table.pack(fill='both',expand=True)
        scroll = ttk.Scrollbar(page,orient='horizontal',command=self.table.xview)
        self.table.configure(xscrollcommand=scroll.set); scroll.pack(fill='x')
        center.section(page,'VM and WSL boundary',
            'ESXi / Hyper-V setup profiles are not qualification. WSL is a smoke-test path. Host, guest and source context stay distinct. Snapshot rollback can restore spent authority; no automatic replay or recovery.')
        center.section(page,'Offline behavior',
            'Missing authority blocks new activation. A preissued local permit can remain usable within its window. Remote revocation freshness and partition-safe execution remain unproved.')
    def choose(self, filedialog):
        selected = filedialog.askopenfilename(parent=self.center.root,title='Select synthetic clinical report',filetypes=[('JSON','*.json')])
        if selected:
            self.load(selected)
    def load(self,path):
        self.observation = None
        self.table.delete(*self.table.get_children())
        try:
            r = read_report(path)
        except (ValueError,OSError,KeyError,TypeError,RecursionError):
            self.status.configure(text='Unreadable or invalid report · clinical evidence Unknown')
            return False
        self.observation = r
        passed = sum(c['passed'] for c in r['checks'])
        self.status.configure(text=f"Recorded snapshot · {r['engine']} · {passed}/{len(r['checks'])} assertions · platform setting {r['config']['platform']} · production enforcement Unknown")
        for c in r['checks']:
            self.table.insert('', 'end', values=('PASS' if c['passed'] else 'FAIL',c['name'],c['detail']))
        return True
