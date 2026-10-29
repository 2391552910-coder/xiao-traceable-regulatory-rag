"""Rasterize new pages and identify pages that changed relative to the prior render."""
from pathlib import Path
import hashlib
import pypdfium2 as pdfium

root = Path(__file__).resolve().parents[1] / 'results/paper'
for folder in ['condensed_candidate_20261028_01', 'english_translation_current_20261028_01']:
    base = root/folder
    old = pdfium.PdfDocument(str(base/'qa_agent_20261029/paper_native.pdf'))
    new = pdfium.PdfDocument(str(base/'qa_schema_prompt_20261029_v2/paper_native.pdf'))
    out = base/'qa_schema_prompt_20261029_v2/pages'
    out.mkdir(exist_ok=True)
    changed=[]
    for i in range(len(new)):
        im = new[i].render(scale=1.3).to_pil().convert('RGB')
        a = hashlib.sha256(im.tobytes()).digest()
        b = hashlib.sha256(old[i].render(scale=1.3).to_pil().convert('RGB').tobytes()).digest() if i < len(old) else None
        if a != b:
            im.save(out/f'page-{i+1:02d}.png')
            changed.append(i+1)
    print(folder, 'old/new', len(old), len(new), 'changed', changed)
