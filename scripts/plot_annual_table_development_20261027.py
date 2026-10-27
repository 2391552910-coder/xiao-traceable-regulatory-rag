"""Saved source-supply comparisons, including the budget-conflict negative case."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/runs/annual_table_development_20261027_03'


def plot():
    data=json.loads((OUT/'offline_analysis.json').read_bytes())
    audit=json.loads((OUT/'implementation_audit.json').read_bytes())
    labels=['Initial','Adjacent','Table\nBM25','Table\nbalanced','Table then\nadjacent']
    colors=['#8c96a2','#238f88','#5b83b0','#8264a8','#cb8743']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,1,figsize=(10.5,10),constrained_layout=True)
    values=[g['corrected_reference_page_coverage']*100 for g in data['groups']]
    bars=axes[0].bar(labels,values,color=colors,width=.65)
    axes[0].bar_label(bars,labels=[f'{v:.2f}%' for v in values],padding=4)
    axes[0].set_ylim(0,115);axes[0].set_ylabel('Reference-page coverage (%)')
    axes[0].set_title('(a) Eight exposed development questions: reference locations, not semantic recall',loc='left',fontsize=11)
    case={r['mode']:r for r in audit['cmb_date_source_case']}
    values=[case[g['mode']]['date_source_spans_supplied'] for g in data['groups']]
    bars=axes[1].bar(labels,values,color=colors,width=.65)
    axes[1].bar_label(bars,labels=[f'{v}/9' for v in values],padding=4)
    axes[1].set_ylim(0,10.5);axes[1].set_yticks([0,3,6,9]);axes[1].set_ylabel('Audit-date source spans supplied')
    axes[1].set_title('(b) CMB 2024 negative case: table-first packing blocks the needed prose continuation',loc='left',fontsize=11)
    values=[g['tokens'] for g in data['groups']]
    bars=axes[2].bar(labels,values,color=colors,width=.65)
    axes[2].bar_label(bars,labels=[f'{v:.0f}' for v in values],padding=4)
    axes[2].axhline(6000,color='#606974',linestyle='--',lw=1)
    axes[2].text(.02,.97,'Dashed line: cap = 6000',transform=axes[2].transAxes,va='top',fontsize=9,color='#606974')
    axes[2].set_ylim(0,6800);axes[2].set_ylabel('Mean reference tokens')
    axes[2].set_title('(c) Initial text, source records and citation IDs remain unchanged in every condition',loc='left',fontsize=11)
    for ax in axes:
        ax.set_axisbelow(True);ax.grid(axis='y',color='#e4e9ee',lw=.7);ax.tick_params(axis='x',length=0)
    fig.suptitle('Annual-report table parsing and retrieval: offline development\nNo model calls; no new generated-answer measurements',fontsize=14)
    (OUT/'figures').mkdir(exist_ok=True)
    for suffix in ('png','svg'):fig.savefig(OUT/'figures'/('table_retrieval_comparison.'+suffix),dpi=210)
    plt.close(fig)


if __name__=='__main__':plot()
