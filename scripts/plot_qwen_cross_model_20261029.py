"""Plot exploratory field matches and schema compliance from saved scores."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.summary.read_text(encoding='utf-8'))
    groups = {g['mode']: g for g in data['summaries'] if g['reference'] == 'post_output_erratum'}
    if set(groups) != {'qwen06', 'k3_single'} or any(g['successful_nonempty'] != 8 for g in groups.values()):
        raise ValueError('This plot requires all eight successful answers in each condition')
    keys = ['members_f1', 'dates_f1', 'meeting_count_exact', 'schema_valid']
    labels = ['Member F1', 'Date F1', 'Meeting count\nexact match', 'Schema\ncompliance']
    xs = np.arange(len(keys)); width = 0.34
    fig, ax = plt.subplots(figsize=(8.2, 4.8), layout='constrained')
    for offset, mode, color, label in [(-width/2, 'qwen06', '#4277a8', 'Qwen3-0.6B'),
                                       (width/2, 'k3_single', '#cf8650', 'K3 service alias')]:
        values = [groups[mode]['macro_successful'][key] for key in keys]
        bars = ax.bar(xs + offset, values, width, label=label, color=color)
        ax.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3, fontsize=9)
    ax.set_ylim(0, 1.16); ax.set_ylabel('Proportion or macro F1')
    ax.set_xticks(xs, labels); ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    ax.set_title('Exploratory cross-family comparison (8 questions)')
    ax.legend(loc='upper center', ncol=2, frameon=False)
    fig.text(.5, -.12, 'Post-output corrected assistant-extracted references; different model budgets.\n'
             'Field overlap and valid structure do not establish semantic citation support.',
             ha='center', fontsize=8)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    fig.savefig(args.out_dir / 'cross_model_exploratory.png', dpi=220, bbox_inches='tight')
    fig.savefig(args.out_dir / 'cross_model_exploratory.pdf', bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
