"""Negative configuration and observer tests; no production data or authority."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

from clinical_config import load, validate
from clinical_observer import read_report, ClinicalPage
from render_report import render

ROOT=Path(__file__).resolve().parent

class ClinicalTests(unittest.TestCase):
    def setUp(self):
        self.config=load(ROOT/'config/clinical.example.json')
        self.report={'schema':'pulpo.clinical-evaluation.v0.1','synthetic_only':True,
                     'config':self.config,'engine':'canonical','source_pin':'0'*40,
                     'checks':[{'name':'synthetic-reader-fixture','passed':True,'detail':''}],
                     'result':'PASS','recorded_at_ns':1,'consequence_unknown':1,
                     'inventory':{},'enforcement':'fixture claim never retained',
                     'policy_hash':'0'*64,'audit_records':0,'audit_tip':None}
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'report.json'
    def write(self,value):
        self.path.write_text(json.dumps(value),encoding='utf-8')
        return self.path
    def test_platform_profiles(self):
        for platform in ['esxi','hyper-v','wsl','local']:
            v=copy.deepcopy(self.config);v['platform']=platform
            self.assertEqual(validate(v)['platform'],platform)
    def test_live_connection_and_credentials_refused(self):
        for field in ['wsus_url','athena_url','credential','password','token','patient_file','endpoint']:
            v=copy.deepcopy(self.config);v[field]='forbidden-input'
            with self.subTest(field=field),self.assertRaises(ValueError):validate(v)
    def test_non_synthetic_and_malformed_configuration_refused(self):
        cases=[('synthetic_only',False),('synthetic_only',1),('sites',['central','a','a']),
               ('sites',['central','clinic-a:escape','clinic-b']),('sites',['central','a']),
               ('window_seconds',True),('window_seconds',0),('window_seconds',3601),
               ('deployment','https://live.invalid'),('platform','production'),
               ('patch_ring','unbounded'),('optional_simulations',1)]
        for key,val in cases:
            v=copy.deepcopy(self.config);v[key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):validate(v)
    def test_large_config_refused(self):
        self.path.write_bytes(b' '*8193)
        with self.assertRaises(ValueError):load(self.path)
    def test_duplicate_json_keys_refused(self):
        self.path.write_text('{"synthetic_only":false,"synthetic_only":true}')
        with self.assertRaises(ValueError):load(self.path)
        with self.assertRaises(ValueError):read_report(self.path)
    def test_report_projection_accepts_snapshot_without_trusting_enforcement(self):
        r=read_report(self.write(self.report))
        self.assertNotIn('enforcement',r)
        self.assertNotIn('inventory',r)
        self.assertEqual(len(r['checks']),len(self.report['checks']))
    def test_malformed_false_status_and_oversize_report_refused(self):
        cases=[('synthetic_only',False),('schema','unknown'),('checks',[]),
               ('checks',[{'name':'forged','passed':1,'detail':''}]),('result','FAIL'),
               ('source_pin','injected'),('recorded_at_ns',0),('consequence_unknown',-1)]
        for key,val in cases:
            r=copy.deepcopy(self.report);r[key]=val
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):read_report(self.write(r))
        self.path.write_bytes(b' '*262145)
        with self.assertRaises(ValueError):read_report(self.path)
    def test_reader_cannot_retain_injected_permit_or_writer(self):
        r=copy.deepcopy(self.report);r['permit']='forged';r['writer']='forged'
        projected=read_report(self.write(r))
        self.assertNotIn('permit',projected);self.assertNotIn('writer',projected)
    def test_no_kernel_writer_signer_or_provider_import_in_clinical_ui(self):
        for name in ['clinical_observer.py','control_center_clinical.py','render_report.py']:
            tree=ast.parse((ROOT/name).read_text())
            imports=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):imports += [x.name for x in node.names]
                if isinstance(node,ast.ImportFrom):imports.append(node.module or '')
            self.assertFalse(any(x=='pulpo' or x.startswith('pulpo.') or x in {'socket','subprocess','fixture_authority'} or 'connection_collector' in x for x in imports),imports)
    def test_export_escapes_untrusted_text_and_is_offline(self):
        r=copy.deepcopy(self.report);r['checks'][0]['detail']='<script>alert(1)</script>'
        render(r,self.path)
        s=self.path.read_text()
        self.assertIn('&lt;script&gt;',s);self.assertNotIn('<script>',s)
        self.assertIn("default-src 'none'",s)
    def test_invalid_selection_withdraws_previous_ui_observation(self):
        class Table:
            def __init__(self):self.rows=['old']
            def get_children(self):return self.rows
            def delete(self,*args):self.rows=[]
        class Status:
            def configure(self,**kw):self.value=kw['text']
        class FakePage:pass
        page=FakePage();page.table=Table();page.status=Status();page.observation={'previous':'valid'}
        self.path.write_text('{}')
        self.assertFalse(ClinicalPage.load(page,self.path))
        self.assertIsNone(page.observation);self.assertEqual(page.table.rows,[])
        self.assertIn('Unknown',page.status.value)

if __name__=='__main__':unittest.main()
