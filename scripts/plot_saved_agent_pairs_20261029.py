"""Plot the six available Agent versus three-round refinement pairs."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.summary.read_text(encoding='utf-8'))
    selected = [x for x in data['comparisons'] if x['reference_version'] == 'post_output_erratum'
                and x['baseline'] == 'k3_refine3']
    if len(selected) != 1 or selected[0]['observed_pairs'] != 6:
        raise ValueError('Expected the six observed pairs from the saved comparison')
    row = selected[0]
    keys = ['members_f1', 'dates_f1', 'count_exact', 'three_field_exact']
    labels = ['Member F1', 'Date F1', 'Meeting count\nexact match', 'All three fields\nexact match']
    xs = np.arange(4); width = 0.34
    fig, ax = plt.subplots(figsize=(8.2, 4.8), layout='constrained')
    for offset, field, label, color in [(-width/2, 'agent', 'Agent: two retrieval rounds', '#4277a8'),
                                         (width/2, 'baseline', 'Three-round fixed-evidence revision', '#cf8650')]:
        values = [row['means'][key][field] for key in keys]
        bars = ax.bar(xs + offset, values, width, label=label, color=color)
        ax.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3, fontsize=9)
    ax.set_ylim(0, 1.19); ax.set_ylabel('Proportion or macro F1')
    ax.set_xticks(xs, labels); ax.set_axisbelow(True); ax.grid(axis='y', alpha=.2)
    ax.set_title('Observed Agent vs revision pairs (6 of 8 questions)')
    ax.legend(loc='upper center', ncol=2, frameon=False, fontsize=9)
    fig.text(.5, -.12, 'Post-output corrected assistant-extracted references; two planned pairs unavailable.\n'
             'Both used three calls per observed pair, with different token totals and contexts.',
             ha='center', fontsize=8)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    fig.savefig(args.out_dir / 'agent_observed_pairs.png', dpi=220, bbox_inches='tight')
    fig.savefig(args.out_dir / 'agent_observed_pairs.pdf', bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
