"""Use installed local PDF libraries, falling back to the existing app bundle."""
import importlib.util
import sys
from pathlib import Path


def ensure_local_pdf_libraries():
    missing = [name for name in ('pdfplumber', 'pypdfium2') if importlib.util.find_spec(name) is None]
    if missing:
        bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages'
        if bundled.is_dir():
            sys.path.append(str(bundled))
    if any(importlib.util.find_spec(name) is None for name in ('pdfplumber', 'pypdfium2')):
        raise RuntimeError('Local PDF libraries are missing; use requirements-table-parsing.txt. No download or model fallback was attempted.')
