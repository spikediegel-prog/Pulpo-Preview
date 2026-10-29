"""Local checksum comparison. This is not a signature or trust attestation."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
def main():
    manifest=json.loads((ROOT/'MANIFEST-SHA256.json').read_text())
    bad=[]
    for relative,expected in manifest.items():
        path=(ROOT/relative).resolve()
        if ROOT not in path.parents or not path.is_file():
            bad.append(relative);continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:bad.append(relative)
    print(json.dumps({'result':'FAIL' if bad else 'PASS','checked':len(manifest),'mismatches':bad,
                      'boundary':'Manifest comparison only; authenticity and completeness require independent custody'}))
    return 1 if bad else 0
if __name__=='__main__':raise SystemExit(main())
