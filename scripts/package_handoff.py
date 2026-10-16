"""Package Git-visible files using NUL-delimited paths and verify every archived byte."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def package(repo: Path, output: Path) -> dict:
    repo, output = repo.resolve(), output.resolve()
    if output.is_relative_to(repo):
        raise ValueError('Place the archive outside the repository')
    if output.exists():
        raise FileExistsError(output)
    names = set()
    for args in [['ls-files', '-z'], ['ls-files', '--others', '--exclude-standard', '-z']]:
        raw = subprocess.check_output(['git', *args], cwd=repo)
        names.update(p.decode('utf-8') for p in raw.split(b'\0') if p)
    digests = {}
    for name in sorted(names):
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Not a regular source file: {name}')
        if path.suffix in {'.safetensors', '.pem', '.key'} or path.name == '.env':
            raise ValueError(f'Unexpected weight or credential file: {name}')
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as tar:
        for name in sorted(names):
            tar.add(repo/name, arcname='xiao-integrated/'+name, recursive=False)
    with tarfile.open(output, 'r:gz') as tar:
        members = tar.getmembers()
        assert len(members) == len(names)
        assert {m.name.removeprefix('xiao-integrated/') for m in members} == names
        for member in members:
            key = member.name.removeprefix('xiao-integrated/')
            stream = tar.extractfile(member)
            assert stream is not None
            assert hashlib.sha256(stream.read()).hexdigest() == digests[key], key
    return {'archive': str(output), 'file_count': len(names), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'all_file_bytes_verified': True, 'source_files_sha256': digests}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    args = p.parse_args()
    if args.manifest.exists():
        raise FileExistsError(args.manifest)
    result = package(args.repo, args.output)
    args.manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_files_sha256'}, indent=2))
