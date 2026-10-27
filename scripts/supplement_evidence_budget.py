"""Export a jointly budgeted annual-table/continuation packet without model calls."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data.annual_tables import file_sha256
from src.generation.annual_audit_development import FrozenAuditIndex,answer_prompt
from src.generation.evidence_budget import POLICIES,allocate_evidence_budget
from src.retrieval.annual_table_index import AnnualTableIndex
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True);p.add_argument('--table-index',type=Path,required=True)
    p.add_argument('--window-index',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--policy',choices=POLICIES,default='boundary_first')
    p.add_argument('--tokenizer',type=Path);p.add_argument('--tokenizer-sha256')
    args=p.parse_args()
    if args.out_dir.exists():raise FileExistsError('Choose a fresh packet output directory')
    if args.tokenizer:
        if not args.tokenizer_sha256:raise ValueError('Expected tokenizer digest is required')
        tokenizer,expected=args.tokenizer,args.tokenizer_sha256
    else:
        plan=json.loads((ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json').read_bytes())
        protocol=json.loads((ROOT/'results/paper/heldout_validation_20261023_01/execution_protocol.json').read_bytes())
        tokenizer,expected=Path(plan['reference_tokenizer_file']),protocol['reference_tokenizer_sha256']
    counter=FrozenAuditIndex(args.window_index,tokenizer,tokenizer_sha256=expected).count
    packet=json.loads(args.packet.read_bytes());q=packet['question'];initial=packet['context']
    tables=AnnualTableIndex(args.table_index).search(q,q['query'],k=24,balanced=True)
    neighbors,audit=FrozenAdjacentIndex(args.window_index).select(q,initial,policy='continuation_first')
    final,packing=allocate_evidence_budget(q,initial,tables,neighbors,audit,counter,policy=args.policy)
    result=dict(question=q,context=final,prompt=answer_prompt(q,final['context']),budget_audit=packing,
        input_packet_sha256=file_sha256(args.packet),table_index_sha256=file_sha256(args.table_index),
        window_index_sha256=file_sha256(args.window_index),reference_tokenizer_sha256=expected,
        model_calls=0,generated_answer=None)
    args.out_dir.mkdir(parents=True)
    (args.out_dir/'augmented_packet.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='exported_offline',policy=args.policy,reference_tokens=final['reference_tokens'],new_sources=packing['accepted_count'],model_calls=0),ensure_ascii=False))


if __name__=='__main__':main()
