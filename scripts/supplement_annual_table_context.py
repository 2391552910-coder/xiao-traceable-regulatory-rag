"""Export a table-augmented prompt/context locally; never sends it to a model."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data.annual_tables import file_sha256
from src.generation.annual_audit_development import answer_prompt
from src.generation.annual_table_evidence import augment_with_table_evidence
from src.retrieval.annual_table_index import AnnualTableIndex


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--tokenizer',type=Path)
    parser.add_argument('--tokenizer-sha256')
    parser.add_argument('--bm25-only',action='store_true')
    args=parser.parse_args()
    if args.out_dir.exists():raise FileExistsError('Choose a fresh context output directory')
    if args.tokenizer:
        if not args.tokenizer_sha256:raise ValueError('An explicit tokenizer requires its expected SHA256')
        tok,expected=args.tokenizer,args.tokenizer_sha256
    else:
        plan=json.loads((ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json').read_bytes())
        original=json.loads((ROOT/'results/paper/heldout_validation_20261023_01/execution_protocol.json').read_bytes())
        tok,expected=Path(plan['reference_tokenizer_file']),original['reference_tokenizer_sha256']
    if file_sha256(tok)!=expected:raise ValueError('Tokenizer digest mismatch')
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(tok));tokenizer.no_padding();tokenizer.no_truncation()
    count=lambda text:len(tokenizer.encode(text,add_special_tokens=False).ids)
    packet=json.loads(args.packet.read_bytes())
    context,audit=augment_with_table_evidence(packet['question'],packet['context'],AnnualTableIndex(args.index),count,balanced=not args.bm25_only)
    result=dict(question=packet['question'],context=context,prompt=answer_prompt(packet['question'],context['context']),audit=audit,
                input_packet_sha256=file_sha256(args.packet),table_index_sha256=file_sha256(args.index),
                reference_tokenizer_sha256=expected,model_calls=0,generated_answer=None)
    args.out_dir.mkdir(parents=True)
    (args.out_dir/'augmented_packet.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='exported_offline',tokens=context['reference_tokens'],new_table_rows=audit['accepted_count'],
                         model_calls=0,output=str(args.out_dir.resolve())),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
