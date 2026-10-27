"""Plot saved offline material-supply measurements, never generated quality."""
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/runs/adjacent_evidence_development_20261027_02'


def plot():
    data = json.loads((OUT / 'offline_analysis.json').read_bytes())
    case = [r for r in data['rows'] if r['question_id'] == 'NEW-600036-2024-AUDIT']
    labels = ['Initial', 'Fixed\nqueries', 'Adjacent\nrank', 'Same-page\nfirst', 'Fixed then\nadjacent', 'Adjacent then\nfixed']
    colors = ['#87919d', '#d29740', '#567da2', '#258a85', '#b97442', '#258a85']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(3, 1, figsize=(10.5, 10.7), constrained_layout=True)
    values = [r['case_audit_date_spans_supplied'] for r in case]
    bars = axes[0].bar(labels, values, color=colors, width=.65)
    axes[0].bar_label(bars, labels=[f'{v}/9' for v in values], padding=4)
    axes[0].set_ylim(0, 10.5)
    axes[0].set_ylabel('Audit-date source spans supplied')
    axes[0].set_title('(a) CMB 2024: exact audit-committee date spans on physical PDF page 97', loc='left', fontsize=11)
    axes[0].set_yticks([0, 3, 6, 9])
    values = [r['final_tokens'] for r in case]
    bars = axes[1].bar(labels, values, color=colors, width=.65)
    axes[1].bar_label(bars, padding=4, fontsize=9)
    axes[1].axhline(6000, color='#4b5158', linestyle='--', linewidth=1.2)
    axes[1].text(.015, .97, 'Dashed line: cap = 6000', transform=axes[1].transAxes,
                 ha='left', va='top', color='#4b5158', fontsize=9)
    axes[1].set_ylim(0, 6650)
    axes[1].set_ylabel('Reference tokens')
    axes[1].set_title('(b) CMB 2024: whole chunks appended while retaining all original evidence', loc='left', fontsize=11)
    values = [g['new_unique_annual_characters'] for g in data['groups']]
    bars = axes[2].bar(labels, values, color=colors, width=.65)
    axes[2].bar_label(bars, labels=[f'{v:.0f}' for v in values], padding=4)
    axes[2].set_ylim(0, max(values) * 1.22)
    axes[2].set_ylabel('New unique annual-text characters')
    axes[2].set_title('(c) Eight exposed development questions: mean additional source characters', loc='left', fontsize=11)
    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(axis='y', color='#e6e9ec', linewidth=.7)
        ax.tick_params(axis='x', length=0)
    fig.suptitle('Offline evidence supply under a fixed context budget\nNo model calls; no new answer-quality measurement', fontsize=14)
    dest = OUT / 'figures'
    dest.mkdir(exist_ok=True)
    for suffix in ['png', 'pdf']:
        fig.savefig(dest / ('adjacent_evidence_comparison.' + suffix), dpi=220)
    plt.close(fig)
    print(dest / 'adjacent_evidence_comparison.png')


if __name__ == '__main__':
    plot()
