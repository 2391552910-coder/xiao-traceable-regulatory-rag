"""Post-hoc schema-example prompt on eight saved Qwen inputs and evidence."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / '.venv-data/Lib/site-packages'))
os.environ.update(TRANSFORMERS_OFFLINE='1', HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
from scripts.smoke_qwen_cuda_20261029 import (EXPECTED_MODEL_SHA256, EXPECTED_MANIFEST_SHA256,
                                               MODEL, frozen_packets, sha256)

PROMPT_SUFFIX = ('\n格式示例仅展示类型，空值不代表答案：'
    '{"members":[],"meeting_count":null,"meeting_dates":[],'
    '"citations":{"members":[],"meeting_count":[],"meeting_dates":[]},"limitations":[]}\n'
    'citations中的三个字段必须分别是来源编号字符串列表；无可靠来源时用空列表，'
    '不要把姓名、次数或日期写成来源编号。请根据材料填写答案，不要机械复制空示例。')


def save_new(path, payload):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-receipt', type=Path, required=True)
    parser.add_argument('--baseline-protocol', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    smoke = json.loads(args.smoke_receipt.read_text(encoding='utf-8'))
    if (smoke.get('status') != 'completed' or not smoke.get('cuda_available') or
            smoke.get('checkpoint_sha256') != EXPECTED_MODEL_SHA256 or smoke.get('generated_tokens') != 1):
        raise ValueError('A successful pinned-model CUDA smoke receipt is required')
    packets = frozen_packets()
    baseline = json.loads(args.baseline_protocol.read_text(encoding='utf-8'))
    if (baseline.get('checkpoint_sha256') != EXPECTED_MODEL_SHA256 or
            baseline.get('packet_sha256') != {p.name: sha256(p) for p in packets} or
            baseline.get('temperature') != 0.7 or baseline.get('top_p') != 0.8 or
            baseline.get('top_k') != 20 or baseline.get('max_new_tokens') != 2048 or
            baseline.get('seed_base') != 20261023 or baseline.get('do_sample') is not True):
        raise ValueError('Baseline protocol does not match the proposed paired settings')
    if sha256(MODEL / 'model.safetensors') != EXPECTED_MODEL_SHA256:
        raise ValueError('Expected the pinned model checkpoint')
    args.out_dir.mkdir(parents=True, exist_ok=False)

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from src.generation.llm_client import parse_json

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable in the current process')
    protocol = {'model': 'Qwen/Qwen3-0.6B', 'revision': 'c1899de289a04d12100db370d81485cdf75e47ca',
        'checkpoint_sha256': EXPECTED_MODEL_SHA256, 'smoke_receipt_sha256': sha256(args.smoke_receipt),
        'release_manifest_sha256': EXPECTED_MANIFEST_SHA256,
        'baseline_protocol_sha256': sha256(args.baseline_protocol),
        'prompt_suffix': PROMPT_SUFFIX,
        'prompt_suffix_sha256': hashlib.sha256(PROMPT_SUFFIX.encode('utf-8')).hexdigest(),
        'script_sha256': sha256(Path(__file__)), 'torch_version': torch.__version__,
        'transformers_version': transformers.__version__, 'gpu': torch.cuda.get_device_name(0),
        'dtype': 'float16', 'device': 'cuda:0', 'enable_thinking': False, 'do_sample': True,
        'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'max_new_tokens': 2048,
        'seed_base': 20261023, 'packet_sha256': {p.name: sha256(p) for p in packets},
        'scope': 'Post-hoc schema-prompt development after inspecting baseline errors; same eight saved '
                 'questions, evidence, model, sampling parameters and seeds. Prompts differ and new token '
                 'counts may differ; no independent evaluation or new human labels.',
        'automatic_retries': 0}
    save_new(args.out_dir / 'protocol.json', protocol)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, local_files_only=True,
                torch_dtype=torch.float16, attn_implementation='sdpa',
                low_cpu_mem_usage=True, device_map={'': 'cuda:0'}).eval()
    for index, packet in enumerate(packets):
        payload = json.loads(packet.read_text(encoding='utf-8'))
        question = payload['question']
        question_id = question['question_id']
        if not isinstance(question_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', question_id):
            raise ValueError('Question ID is unsafe for an output filename')
        prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': payload['prompt'] + PROMPT_SUFFIX}],
                     tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = {key: value.to('cuda:0') for key, value in tokenizer(prompt, return_tensors='pt').items()}
        prompt_tokens = inputs['input_ids'].shape[1]
        torch.manual_seed(20261023 + index)
        start = time.monotonic()
        result = {'question': question, 'packet': packet.name, 'packet_sha256': sha256(packet),
                  'seed': 20261023 + index, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=2048, do_sample=True,
                            temperature=0.7, top_p=0.8, top_k=20, pad_token_id=tokenizer.eos_token_id)
            torch.cuda.synchronize()
            ids = output[0][prompt_tokens:].tolist()
            body = tokenizer.decode(ids, skip_special_tokens=True)
            try:
                parsed = parse_json(body)
            except Exception:
                parsed = None
            result.update(status='completed', text=body, parsed=parsed,
                          finish_reason='eos' if ids and ids[-1] == tokenizer.eos_token_id else 'length',
                          prompt_tokens=prompt_tokens, completion_tokens=len(ids))
        except Exception as error:
            result.update(status='failed', error_type=type(error).__name__, error=str(error))
        result['elapsed_seconds'] = round(time.monotonic() - start, 3)
        save_new(args.out_dir / (question_id + '.json'), result)
        print(question_id, result['status'], flush=True)
        if result['status'] != 'completed':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
