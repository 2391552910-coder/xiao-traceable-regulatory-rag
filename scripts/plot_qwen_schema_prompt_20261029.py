"""Plot the post-hoc within-model prompt experiment from its saved score."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--summary', type=Path, required=True)
p.add_argument('--out-dir', type=Path, required=True)
a = p.parse_args()
summary = json.loads(a.summary.read_text(encoding='utf-8'))
g = next(x for x in summary['summaries'] if x['reference'] == 'post_output_erratum')
if g['planned_pairs'] != 8 or g['observed_pairs'] != 8:
    raise ValueError('Plot requires all eight paired answers')
keys = ['members_f1', 'dates_f1', 'count_exact', 'all_three_exact', 'schema_valid']
labels = ['Members\nF1', 'Dates\nF1', 'Count\nexact', 'All fields\nexact', 'Schema\nvalid']
x = np.arange(len(keys)); width = .34
fig, ax = plt.subplots(figsize=(8.4, 4.8), layout='constrained')
for offset, name, color, label in [(-width/2, 'baseline', '#4277a8', 'Original prompt'),
                                    (width/2, 'schema_example', '#cf8650', 'Added format example')]:
    vals = [g['metrics'][key][name] for key in keys]
    bars = ax.bar(x + offset, vals, width, color=color, label=label)
    ax.bar_label(bars, labels=[f'{v:.2f}' for v in vals], padding=3, fontsize=9)
ax.set_ylim(0, 1.12); ax.set_ylabel('Proportion or macro F1')
ax.set_xticks(x, labels); ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
ax.set_title('Post-hoc prompt development on the same 8 questions')
ax.legend(loc='upper center', ncol=2, frameon=False)
fig.text(.5, -.10, 'Existing assistant-extracted references with post-output correction; not independent validation.\n'
         'Schema validity does not establish that citations support the answer.', ha='center', fontsize=8)
a.out_dir.mkdir(parents=True, exist_ok=False)
fig.savefig(a.out_dir / 'schema_prompt_development.png', dpi=220, bbox_inches='tight')
fig.savefig(a.out_dir / 'schema_prompt_development.pdf', bbox_inches='tight')
