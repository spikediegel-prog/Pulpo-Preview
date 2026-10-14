"""Export selected VM evidence without modifying originals or repository source."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

PIN = 'd935987f016cfc1038b624a7b4cb6a03ad9f8baa'
BASE = 'd674dbb7a00b471d69bcca84d2f034cf74705e1a'
ROOT_REQUIRED = (
    'baseline.sha', 'preview.sha', 'environment.txt', 'dependencies.txt',
    'baseline-full.log', 'baseline-full.exit', 'preview-full.log', 'preview-full.exit',
    'sqlite-comparison.json', 'traffic-matrix.json', 'traffic-synthetic.json',
    'batch-recovery.json', 'idle-stress.json',
)
ROOT_OPTIONAL = (
    'preview-remotes.txt', 'baseline-remotes.txt', 'fetched-branches.txt',
    'latest-commits.txt', 'source-diff-stat.txt', 'focused-source.diff',
    'baseline-status-after.txt', 'preview-status-after.txt',
)
PREFIXES = (
    'ed25519.', 'routing-confirmation.', 'mixed-100ms.', 'mixed-arrivals.',
    'mixed-diagnostic.', 'mixed-boundary.', 'portable-smoke.',
)
EXTENSIONS = {'.json', '.log', '.exit', '.py', '.txt', '.sha', '.csv', '.diff'}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def digest(content):
    return hashlib.sha256(content).hexdigest()

def select(results):
    paths = []
    for name in ROOT_REQUIRED:
        path = results / name
        require(path.is_file() and not path.is_symlink(), f'Missing ordinary evidence file: {name}')
        paths.append(path)
    require((results / 'preview.sha').read_text().strip() == PIN, 'Preview SHA mismatch')
    require((results / 'baseline.sha').read_text().strip() == BASE, 'Baseline SHA mismatch')
    for name in ROOT_OPTIONAL:
        if (results / name).is_file():
            paths.append(results / name)
    for path in results.iterdir():
        if path.is_file() and path.suffix in {'.log', '.exit'} and (
            path.name.startswith(('baseline-common-', 'preview-common-')) or
            path.stem in {'preview-routing-batching', 'sqlite-comparison', 'traffic-synthetic',
                          'traffic-matrix', 'batch-recovery', 'idle-stress'}):
            paths.append(path)
    for prefix in PREFIXES:
        directories = sorted(results.glob(prefix + '*'))
        directories = [d for d in directories if d.is_dir()]
        require(directories, f'Missing evidence group: {prefix}')
        for directory in directories:
            require(not directory.is_symlink(), f'Linked directory excluded: {directory.name}')
            for path in directory.rglob('*'):
                require(not path.is_symlink(), f'Linked evidence excluded: {path}')
                if path.is_file() and path.suffix in EXTENSIONS:
                    paths.append(path)
            report_file = directory / 'report.json'
            if report_file.is_file():
                report = json.loads(report_file.read_text())
                expected_hash = report.get('script_sha256')
                if expected_hash:
                    scripts = [directory / name for name in
                               ('arrival_test.py', 'benchmark_mixed_arrivals.py')]
                    require(any(p.is_file() and digest(p.read_bytes()) == expected_hash for p in scripts),
                            f'Archived harness missing or mismatched in {directory.name}')
            if prefix == 'portable-smoke.':
                report = json.loads(report_file.read_text())
                require(report.get('schema') == 'pulpo.mixed-arrival-fixture.v1', 'Wrong portable report')
                require(report.get('source_sha') == PIN and report.get('source_clean_after'),
                        'Portable smoke source provenance failed')
                require(set(report.get('modes', [])) == {'fifo', 'ptc', 'ptc_poll'},
                        'Portable smoke must cover all modes')
                require(report.get('samples') and all(r.get('correctness_passed') for r in report['samples']),
                        'Portable smoke correctness failed')
                require((directory / 'run.exit').read_text().strip() == '0', 'Portable smoke exit failed')
    for path in paths:
        require(not path.is_symlink(), f'Linked evidence excluded: {path}')
        if path.suffix == '.exit':
            require(path.read_text().strip() == '0', f'Nonzero correctness stage: {path.name}')
    return sorted(set(paths))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.results.is_symlink(), 'Results root must not be a link')
    results = args.results.resolve()
    output = args.output.resolve()
    require(results.is_dir(), 'Results directory missing')
    require(output.name.endswith('.tar.gz'), 'Output must end in .tar.gz')
    require(output != results and results not in output.parents, 'Archive must be outside evidence root')
    require(not output.exists(), 'Archive already exists; choose a fresh output path')
    paths = select(results)
    entries, payloads = [], []
    replacements = (
        (str(results), '<RESULTS_ROOT>'),
        (str(results.parent), '<COMPARISON_ROOT>'),
    )
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        for original, placeholder in replacements:
            text = text.replace(original, placeholder)
        text = re.sub(r'/home/[^/\s\"\'<>]+', '/home/<USER>', text)
        published = text.encode('utf-8')
        relative = path.relative_to(results).as_posix()
        payloads.append(('results/' + relative, published))
        entries.append(dict(path=relative, original_sha256=digest(raw),
            published_sha256=digest(published), path_redactions_applied=raw != published,
            original_bytes=len(raw), published_bytes=len(published)))
    manifest = dict(schema='pulpo.publication-evidence-export.v1',
        created_utc=datetime.now(timezone.utc).isoformat(), preview_sha=PIN, baseline_sha=BASE,
        files=entries, originals_unchanged=True,
        scope='Selected historical fixture evidence plus portable smoke validation. '
              'Latency target failures remain in the measurements; exit status checks concern correctness.',
        transformations='UTF-8 text replacement of comparison/result roots and /home usernames. '
                        'Hashes identify original and exported bytes separately. '
                        'Original script hashes in reports continue identifying the original harness.',
        limitations='Original baseline filenames were reused between executions and contain their latest '
                    'saved content. Separate arrival directories preserve early timing failures.')
    manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as archive:
        with tarfile.open(fileobj=archive, mode='w:gz') as bundle:
            for name, content in [('manifest.json', manifest_bytes)] + payloads:
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(content), 0o644, 0
                bundle.addfile(info, io.BytesIO(content))
    checksum = digest(output.read_bytes())
    output.with_name(output.name + '.sha256').write_text(f'{checksum}  {output.name}\n')
    print(f'Exported {len(entries)} files; {sum(e["path_redactions_applied"] for e in entries)} path-redacted')
    print('Archive:', output)
    print('SHA256:', checksum)

if __name__ == '__main__':
    main()
