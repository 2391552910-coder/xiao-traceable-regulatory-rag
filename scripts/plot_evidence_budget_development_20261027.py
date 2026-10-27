"""Plot saved source-supply diagnostics; do not label them answer metrics."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/runs/evidence_budget_development_20261027_01'


def plot():
    data=json.loads((OUT/'offline_analysis.json').read_bytes())
    rows=[r for r in data['rows'] if r['question_id']=='NEW-600036-2024-AUDIT']
    labels=['Initial','Table first','Adjacent first','Boundary first','Boundary +\nround robin']
    x=np.arange(5);fig,axes=plt.subplots(2,1,figsize=(10.8,8.4),constrained_layout=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    date=[r['case_date_source_spans_supplied'] for r in rows];names=[r['supplied_table_member_candidates'] for r in rows]
    bars=axes[0].bar(x-.19,[v/9*100 for v in date],width=.36,color='#258e88',label='Audit-date spans in supplied PDF windows')
    axes[0].bar_label(bars,labels=[f'{v}/9' for v in date],padding=4)
    bars=axes[0].bar(x+.19,[v/6*100 for v in names],width=.36,color='#627cb1',label='Name candidates in added table views')
    axes[0].bar_label(bars,labels=[f'{v}/6' for v in names],padding=4)
    axes[0].set_ylim(0,140);axes[0].set_yticks([0,25,50,75,100]);axes[0].set_ylabel('Source representation supplied (%)')
    axes[0].legend(loc='upper left',frameon=False,fontsize=9)
    axes[0].set_title('(a) CMB 2024: simultaneously supply the two source representations',loc='left',fontsize=11)
    values=[r['reference_tokens'] for r in rows]
    bars=axes[1].bar(x,values,width=.6,color=['#8f99a5','#c58a49','#7297b5','#258e88','#8d77b4'])
    axes[1].bar_label(bars,padding=4)
    axes[1].axhline(6000,color='#5d6773',ls='--',lw=1)
    axes[1].text(.02,.97,'Dashed line: cap = 6000',transform=axes[1].transAxes,va='top',fontsize=9,color='#5d6773')
    axes[1].set_ylim(0,6850);axes[1].set_ylabel('Reference tokens')
    axes[1].set_title('(b) Whole chunks; all initial evidence and citation IDs retained',loc='left',fontsize=11)
    for ax in axes:
        ax.set_xticks(x,labels);ax.spines[['top','right']].set_visible(False);ax.set_axisbelow(True);ax.grid(axis='y',color='#e4e9ee',lw=.7);ax.tick_params(axis='x',length=0)
    fig.suptitle('Fixed-budget evidence allocation: exposed development case\nNo model calls; these are source-supply diagnostics, not answer scores',fontsize=13)
    (OUT/'figures').mkdir(exist_ok=True)
    for suffix in ('png','svg'):fig.savefig(OUT/'figures'/('joint_source_supply.'+suffix),dpi=210)
    plt.close(fig)


if __name__=='__main__':plot()
