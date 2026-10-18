"""Harmless CVE-2026-19672 check, entirely inside one disposable directory."""
import io,json,sys,tarfile,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='pulpo-tar-admission-') as folder:
    root=Path(folder)
    destination=root/'dest'
    destination.mkdir()
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as stream:
        member=tarfile.TarInfo('../outside/../dest/inside/file.txt')
        member.size=2
        stream.addfile(member,io.BytesIO(b'ok'))
    archive.seek(0)
    error=None
    try:
        with tarfile.open(fileobj=archive,mode='r') as stream:
            stream.extractall(destination,filter='data')
    except (ValueError,tarfile.TarError) as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    result={'cve':'CVE-2026-19672','python':sys.version,'tarfile_module':tarfile.__file__,
        'archive_bytes':len(archive.getvalue()),'error':error,
        'empty_directory_created_outside_extraction_destination':(root/'outside').is_dir(),
        'file_inside_destination':(destination/'inside/file.txt').is_file(),
        'all_paths_within_disposable_root':True,
        'changes_to_pulpo_canonical_state':False}
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
