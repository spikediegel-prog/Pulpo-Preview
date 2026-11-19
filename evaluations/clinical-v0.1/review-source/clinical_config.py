"""Only synthetic topology settings; no URLs, credentials or imported clinical data."""
import json
from pathlib import Path
import re

FIELDS = {'schema', 'synthetic_only', 'deployment', 'platform', 'sites',
          'patch_ring', 'window_seconds', 'optional_simulations'}

def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result

def validate(value):
    if type(value) is not dict or set(value) != FIELDS:
        raise ValueError('Unexpected configuration fields; endpoints and credentials are unsupported')
    if value['schema'] != 'pulpo.clinical-config.v0.1' or value['synthetic_only'] is not True:
        raise ValueError('Synthetic mode is mandatory')
    token = lambda v: type(v) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,31}', v)
    if not token(value['deployment']) or value['platform'] not in {'esxi', 'hyper-v', 'wsl', 'local'}:
        raise ValueError('Invalid deployment or platform')
    sites = value['sites']
    if (type(sites) is not list or not 3 <= len(sites) <= 12 or sites[0] != 'central'
            or any(not token(s) for s in sites) or len(sites) != len(set(sites))):
        raise ValueError('Use central plus 2–11 distinct synthetic clinic identifiers')
    if value['patch_ring'] not in {'pilot', 'broad'}:
        raise ValueError('Unknown synthetic patch ring')
    if type(value['window_seconds']) is not int or not 30 <= value['window_seconds'] <= 3600:
        raise ValueError('Window must be 30–3600 simulated seconds')
    if type(value['optional_simulations']) is not bool:
        raise ValueError('optional_simulations must be boolean')
    return value

def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError('Configuration must be a small regular JSON file')
    with path.open('rb') as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('Configuration too large')
    return validate(json.loads(raw,object_pairs_hook=unique_object))
