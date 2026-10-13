import subprocess
import tarfile
import pytest
from scripts.package_handoff import package


def test_unicode_git_paths_are_included_and_archive_is_not_overwritten(tmp_path):
    repo=tmp_path/'repo'
    repo.mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'法规及日期.txt').write_text('原文与日期证据\n')
    (repo/'plain.txt').write_text('plain\n')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    archive=tmp_path/'handoff.tar.gz'
    result=package(repo,archive)
    assert result['file_count']==2 and result['all_file_bytes_verified']
    with tarfile.open(archive) as tar:
        assert tar.extractfile('xiao-integrated/法规及日期.txt').read().decode()=='原文与日期证据\n'
    with pytest.raises(FileExistsError): package(repo,archive)
