"""One-token, unscored CUDA feasibility test on a saved public prompt.

Writes only a new smoke receipt; it does not write experimental answer records.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
# The isolated CUDA environment must precede project packages so its torch wins.
sys.path.append(str(ROOT / '.venv-data/Lib/site-packages'))
os.environ.update(TRANSFORMERS_OFFLINE='1', HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
MODEL = ROOT / 'models/Qwen3-0.6B-c1899de'
PACKETS = ROOT / 'results/paper/heldout_validation_20261023_01/packets'
MANIFEST = PACKETS.parent / 'release_package_manifest.json'
EXPECTED_MODEL_SHA256 = 'f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b'
EXPECTED_MANIFEST_SHA256 = '8113b0f59c035744011fae62cf29d1cd6c1ea4b845f25cbdb11f19b0355c068a'


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def frozen_packets():
    if sha256(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise ValueError('Saved release manifest differs from the pinned copy')
    entries = json.loads(MANIFEST.read_text(encoding='utf-8'))
    listed = [item for item in entries if '/packets/' in item['path'] and item['path'].endswith('.json')]
    by_name = {Path(item['path']).name: item for item in listed}
    packets = sorted(PACKETS.glob('*.json'))
    if len(listed) != 8 or len(by_name) != 8 or {p.name for p in packets} != set(by_name):
        raise ValueError('Saved packet list differs from the release manifest')
    for packet in packets:
        if packet.stat().st_size != by_name[packet.name]['bytes'] or sha256(packet) != by_name[packet.name]['sha256']:
            raise ValueError(f'Saved packet differs from the release manifest: {packet.name}')
    return packets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'started', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'model': 'Qwen/Qwen3-0.6B', 'revision': 'c1899de289a04d12100db370d81485cdf75e47ca',
               'script_sha256': sha256(Path(__file__)), 'max_new_tokens': 1,
               'scope': 'Feasibility smoke only; no answer score, no new labels, no external model calls.'}
    started = time.monotonic()
    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer

        receipt.update(torch_version=torch.__version__, transformers_version=transformers.__version__,
                       cuda_available=torch.cuda.is_available(), torch_cuda_build=torch.version.cuda,
                       checkpoint_sha256=sha256(MODEL / 'model.safetensors'))
        if receipt['checkpoint_sha256'] != EXPECTED_MODEL_SHA256:
            raise ValueError('Model checkpoint hash does not match the pinned source')
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable in the isolated environment')
        import accelerate
        receipt['accelerate_version'] = accelerate.__version__
        receipt['gpu_name'] = torch.cuda.get_device_name(0)
        receipt['gpu_free_bytes_before'], receipt['gpu_total_bytes'] = torch.cuda.mem_get_info(0)
        tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
        packets = frozen_packets()
        receipt['release_manifest_sha256'] = EXPECTED_MANIFEST_SHA256
        candidates = []
        for path in packets:
            payload = json.loads(path.read_text(encoding='utf-8'))
            rendered = tokenizer.apply_chat_template([{'role': 'user', 'content': payload['prompt']}],
                         tokenize=False, add_generation_prompt=True, enable_thinking=False)
            encoded = tokenizer(rendered, return_tensors='pt')
            candidates.append((encoded['input_ids'].shape[1], path, encoded))
        count, packet, encoded = min(candidates, key=lambda value: (value[0], value[1].name))
        receipt.update(packet=packet.name, packet_sha256=sha256(packet), prompt_tokens=count,
                       dtype='float16', device='cuda:0', do_sample=False, enable_thinking=False)
        model = AutoModelForCausalLM.from_pretrained(MODEL, local_files_only=True,
                    torch_dtype=torch.float16, attn_implementation='sdpa',
                    low_cpu_mem_usage=True, device_map={'': 'cuda:0'}).eval()
        inputs = {key: value.to('cuda:0') for key, value in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=1, do_sample=False,
                                       pad_token_id=tokenizer.eos_token_id)
        torch.cuda.synchronize()
        generated_ids = generated[0][count:].tolist()
        receipt.update(status='completed', generated_tokens=len(generated_ids),
                       generated_token_ids_sha256=hashlib.sha256(json.dumps(generated_ids).encode()).hexdigest(),
                       max_gpu_bytes_allocated=torch.cuda.max_memory_allocated())
        if len(generated_ids) != 1:
            raise RuntimeError('Expected exactly one generated token')
    except Exception as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
    finally:
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (args.out_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(receipt, ensure_ascii=False))
    if receipt['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
