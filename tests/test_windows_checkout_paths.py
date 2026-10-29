"""Keep tracked paths checkoutable on Windows, without altering data bytes."""
import re
import subprocess

import pytest


def invalid_component(part):
    return (bool(re.search(r'[<>:"\\|?*\x00-\x1f]', part))
            or part.endswith((' ', '.'))
            or bool(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)))


@pytest.mark.parametrize('part', ['file*name.txt', 'name.', 'a|b', 'CON.txt', 'LPT1', 'trailing '])
def test_invalid_windows_component(part):
    assert invalid_component(part)


def test_windows_alias_is_valid():
    assert not invalid_component('DOC304_证监会对＊ST普利重大财务造假案依法从严行政处罚.txt')


def test_tracked_paths_are_windows_compatible():
    output = subprocess.check_output(['git', '-c', 'gc.auto=0', 'ls-files', '-z'])
    paths = output.decode('utf-8').split('\0')
    invalid = [path for path in paths if path and any(invalid_component(part) for part in path.split('/'))]
    assert not invalid, f'Paths invalid on Windows: {invalid}'


def test_corpus_checkout_preserves_blob_bytes():
    result = subprocess.check_output([
        'git', '-c', 'gc.auto=0', 'check-attr', '-z', 'text', '--',
        'data/knowledge_base/DOC001_disclosure_measures.txt',
    ]).split(b'\0')
    assert result[1:3] == [b'text', b'unset']
