"""结构审计、冻结开发基准及导出人工盲审材料；不会自动修改 gold 标签。"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ROOT, load_config
from src.data.benchmark import export_review, load_benchmark, resolve_path, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--freeze", metavar="VERSION", help="审计后建立冻结版本；不允许同一版本悄悄更换数据")
    parser.add_argument("--output-dir", help="新的审计输出目录")
    args = parser.parse_args()
    cfg = load_config(str(resolve_path(args.config)) if args.config else None)
    benchmark = load_benchmark(cfg, verify_manifest=not bool(args.freeze))
    if args.freeze:
        manifest_path = resolve_path(cfg["evaluation"]["manifest_path"])
        manifest = {"schema_version": 1, "benchmark_id": args.freeze,
                    "status": "provisional", "usage": "development_only",
                    "label_origin": "ai_dual_pass_adjudicated",
                    "hashes": benchmark.hashes}
        if manifest_path.exists():
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old["benchmark_id"] == args.freeze and old["hashes"] != benchmark.hashes:
                raise ValueError("同一版本的数据发生变化，请使用新的基准版本号")
        write_json(manifest_path, manifest)
        benchmark.manifest = manifest
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = resolve_path(args.output_dir) if args.output_dir else ROOT / "results/runs" / f"audit_{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    audit = benchmark.audit()
    write_json(output / "audit.json", audit)
    count = export_review(benchmark, output / "human_review.csv")
    mean_kappa = audit['annotation_consistency']['mean_defined_kappa']
    mean_kappa_text = f"{mean_kappa:.6f}" if mean_kappa is not None else "未定义/无轮次记录"
    lines = ["# 检索开发基准审计", "", "状态：provisional / development_only。冻结保证版本可复现，不等于人工认证。", "",
             f"文档 {audit['n_documents']}；块 {audit['n_chunks']}；查询 {audit['n_queries']}；"
             f"正例对 {audit['n_positive_pairs']}（不同块 {audit['n_unique_positive_chunks']}）；盲审候选 {count}。", "",
             "## 尚待复核", "", *[f"- {note}" for note in audit["limitations"]], "",
             "## 一致性与重复语料", "",
             f"存在 {len(audit['duplicate_document_groups'])} 组完全相同的文档正文。",
             f"Kappa 未定义的查询：{audit['annotation_consistency']['n_undefined_kappa']}；"
             f"仅对可定义查询取平均：{mean_kappa_text}。", "",
             audit['annotation_consistency']['note'], "",
             "| 查询 | Kappa | 未解决分歧 | Gold 与轮次一致 |", "|---|---|---|---|"]
    for row in audit['annotation_consistency']['per_query']:
        if row['below_0_6'] or row['kappa'] is None or row['unresolved_disputes'] or not row['gold_matches_rounds']:
            lines.append(f"| {row['query_id']} | {row['kappa']} | {', '.join(row['unresolved_disputes']) or '—'} | {row['gold_matches_rounds']} |")
    lines += ["", "## 正例块结构问题", "", "| 块 | 查询 | 问题 | 存储条款号 | 所属条款号（自动推断） |",
             "|---|---|---|---|---|"]
    for issue in audit["structural_issues"]:
        lines.append(f"| {issue['chunk_id']} | {', '.join(issue['query_ids'])} | {', '.join(issue['flags'])} | "
                     f"{issue['stored_clause_no'] or '—'} | {issue['owner_clause_no'] or '—'} |")
    (output / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"结构校验通过；{len(audit['structural_issues'])} 个正例块存在结构复核项；盲审候选 {count}。")
    print(f"审计与人工复核材料：{output}")


if __name__ == "__main__":
    main()
