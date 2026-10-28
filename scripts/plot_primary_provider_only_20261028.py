"""Render score figures from the provider-only post-hoc reanalysis."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json, sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/runs/primary_provider_only_robustness_20261028_01"
SCORES = OUT / "per_output_scores_primary_provider_only.json"
AUDIT = OUT / "robustness_audit_primary_provider_only.json"
FREEZE = ROOT / "results/runs/paper_execution_freeze_windows_20261020_01/execution_freeze.json"
sys.path.insert(0, str(ROOT))
from src.metrics.compact_paper_statistics import paired_company_statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIELDS = ["company_facts", "regulation", "citations", "uncertainty"]
LABEL = {"company_facts": "Company facts", "regulation": "Regulatory basis",
         "citations": "Citation support", "uncertainty": "Uncertainty"}
G1 = "merged_corpus_generic_cited_rag"
G2 = "dual_source_generic_cited_rag"
G3 = "dual_source_role_grounded_rag"


def ci_company_mean(values, draws=20000, seed=20261028):
    by = defaultdict(list)
    for company, value in values:
        by[company].append(value)
    means = np.asarray([np.mean(v) for _, v in sorted(by.items())])
    rng = np.random.default_rng(seed)
    samples = means[rng.integers(0, len(means), size=(draws, len(means)))].mean(axis=1)
    return float(means.mean()), np.quantile(samples, [.025, .975])


def main():
    if not all(p.exists() for p in (SCORES, AUDIT, FREEZE)):
        raise FileNotFoundError("Required provider-only analysis artifact is missing")
    rows = json.loads(SCORES.read_text(encoding="utf-8"))
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    by = {(r["question_id"], r["mode"]): r for r in rows}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 240, "pdf.fonttype": 42})

    # Figure 4: the three primary conditions only; intervals are conditional on
    # available outputs and show company-cluster uncertainty.
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    modes = [(G1, "G1 pooled"), (G2, "G2 dual source"), (G3, "G3 role prompt")]
    colors = {"R1": "#8699a8", "R2": "#bd764c", "mean": "#1b6a83"}
    offsets = {"R1": -.17, "R2": .17, "mean": 0.0}
    for rating in ("R1", "R2", "mean"):
        for i, (mode, label) in enumerate(modes):
            vals = [(r["company"], r[rating]["total"]) for r in rows if r["mode"] == mode]
            mean, bounds = ci_company_mean(vals, seed=20261028 + i)
            x = i + offsets[rating]
            ax.scatter(x, mean, s=36, color=colors[rating], zorder=3)
            if rating == "mean":
                ax.errorbar(x, mean, yerr=[[mean-bounds[0]], [bounds[1]-mean]],
                            fmt="none", color=colors[rating], capsize=3, lw=1.4)
    ax.set_xticks(range(3), [f"{label}\n{sum(r['mode']==mode for r in rows)}/60" for mode, label in modes])
    ax.set_ylim(5.5, 8.15); ax.set_ylabel("Human answer rating (0–8)")
    ax.set_title("Provider outputs only; available-case means")
    ax.grid(axis="y", alpha=.22)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0],[0],marker='o',color='none',markerfacecolor=colors[k],label=k,markersize=7) for k in ('R1','R2','mean')],
              frameon=False, ncol=3, loc='lower center', bbox_to_anchor=(.5,-.22))
    fig.tight_layout()
    fig.savefig(OUT / "primary_scores_provider_only.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 5: matched, company-weighted changes by rubric dimension.
    contrasts = [(G1,G2,"G2 − G1"),(G2,G3,"G3 − G2"),(G1,G3,"G3 − G1")]
    colors_f = ["#1b6a83", "#bd764c", "#668048"]
    fig, ax = plt.subplots(figsize=(11.0, 4.31))
    ybase = np.arange(len(FIELDS))
    for j,(a,b,name) in enumerate(contrasts):
        vals=[]
        for field in FIELDS:
            paired=[]
            for q in freeze["grouping"]:
                ra=by.get((q["question_id"],a)); rb=by.get((q["question_id"],b))
                if ra is not None and rb is not None:
                    paired.append({"question_id":q["question_id"],"company":q["company_cluster"],
                                   "baseline":ra["mean"][field],"treatment":rb["mean"][field]})
            s=paired_company_statistics(paired,draws=20000,seed=20261028 + j)
            vals.append((s["company_macro_difference_on_known_pairs"],s["company_cluster_bootstrap_ci95"]))
        off=(j-1)*.18
        for i,(v,ci) in enumerate(vals):
            if ci is not None:
                ax.errorbar(v, ybase[i]+off, xerr=[[v-ci[0]],[ci[1]-v]], fmt='o',
                            color=colors_f[j], capsize=2.5, markersize=4, label=name if i==0 else None)
            else:
                ax.scatter(v,ybase[i]+off,color=colors_f[j],label=name if i==0 else None)
    ax.axvline(0,color="#444",lw=.9,ls="--")
    ax.set_yticks(ybase, [LABEL[f] for f in FIELDS]); ax.invert_yaxis()
    ax.set_xlabel("Company-macro paired difference (0–2 per dimension)")
    ax.set_title("Observed matched questions only; company-clustered 95% intervals")
    ax.grid(axis="x",alpha=.2); ax.legend(frameon=False,ncol=3,loc="lower center",bbox_to_anchor=(.5,-.25))
    fig.tight_layout()
    fig.savefig(OUT / "dimension_effects_provider_only.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 6: ceiling and exact agreement for the 355 provider-generated ratings.
    fig, ax = plt.subplots(figsize=(9.5,4.28))
    score_rows=[]
    for field in FIELDS:
        xs=[r for r in rows if r["R1"][field] is not None and r["R2"][field] is not None]
        score_rows.append((field,
            100*sum(r["R1"][field]==2 for r in xs)/len(xs),
            100*sum(r["R2"][field]==2 for r in xs)/len(xs),
            100*sum(r["R1"][field]==r["R2"][field] for r in xs)/len(xs)))
    x=np.arange(len(FIELDS)); w=.24
    for offset,k,color in [(-w,"R1",colors["R1"]),(0,"R2",colors["R2"]),(w,"Exact agreement","#1b6a83")]:
        col=1 if k=="R1" else 2 if k=="R2" else 3
        ax.bar(x+offset,[r[col] for r in score_rows],width=w,label=k,color=color)
    ax.set_xticks(x,[LABEL[f] for f in FIELDS]); ax.set_ylim(0,105)
    ax.set_ylabel("Percentage of 355 scored provider outputs")
    ax.set_title("High full-score rates and agreement are not semantic validation")
    ax.grid(axis="y",alpha=.2); ax.legend(frameon=False,ncol=3,loc="lower center",bbox_to_anchor=(.5,-.25))
    fig.tight_layout()
    fig.savefig(OUT / "reviewer_ceiling_provider_only.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 7: interval, leave-one-company-out range and all-question bounds.
    names=["G2-G1","G3-G2","G3-G1","G3-NoRerank","G3-BM25"]
    colors_c=["#1b6a83","#bd764c","#1b6a83","#bd764c","#bd764c"]
    fig,ax=plt.subplots(figsize=(8.5,5.21))
    for i,name in enumerate(names):
        x=report["contrasts"][name]["mean"]
        lo,hi=x["full_question_average_bounds_using_available_counterparts"]
        cilo,cihi=x["cluster_ci95_20000"]; lolo,lohi=x["loco_range"]
        ax.plot([lo,hi],[i+.13,i+.13],color="#b5b5b5",lw=5,solid_capstyle='butt')
        ax.plot([cilo,cihi],[i-.10,i-.10],color=colors_c[i],lw=2)
        ax.plot([lolo,lohi],[i-.10,i-.10],color=colors_c[i],lw=7,alpha=.28)
        ax.scatter([x["observed_pair_company_macro"]],[i-.10],color=colors_c[i],s=28,zorder=3)
        ax.text(1.03,i,f"{x['observed_pairs']}/60",transform=ax.get_yaxis_transform(),va='center',fontsize=9)
    ax.axvline(0,color="#444",lw=.9,ls="--")
    ax.set_yticks(range(len(names)),[n.replace('-',' − ') for n in names]);ax.invert_yaxis()
    ax.set_xlabel("Company-macro difference on available pairs (0–8)")
    ax.set_xlim(-1.85,1.85);ax.grid(axis="x",alpha=.2)
    ax.set_title("Missing-output bounds include zero for every main contrast")
    ax.legend(handles=[Line2D([0],[0],color="#1b6a83",marker="o",lw=2,label="Observed estimate and 95% cluster interval"),
                       Line2D([0],[0],color="#1b6a83",alpha=.28,lw=7,label="Leave-one-company-out range"),
                       Line2D([0],[0],color="#b5b5b5",lw=5,label="Full-question bound using observed counterparts")],
              frameon=False,fontsize=8.2,loc="lower left",bbox_to_anchor=(-.02,-.31))
    fig.subplots_adjust(left=.18,right=.82,bottom=.25,top=.92)
    fig.savefig(OUT / "missingness_loco_provider_only.png",bbox_inches="tight")
    plt.close(fig)
    print("Rendered four provider-only score figures in", OUT)


if __name__ == "__main__":
    main()
