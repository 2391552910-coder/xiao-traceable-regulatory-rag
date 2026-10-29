from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analyze_qwen_cross_model_year_20261029.py"
SAVED = ROOT / "results/runs/qwen_cross_model_year_sensitivity_20261029_01"
OUTPUTS = (
    "year_stratified_summary.json",
    "year_stratified_models.csv",
    "year_stratified_pairs.csv",
)


def test_year_stratification_reproduces_saved_outputs_byte_for_byte(tmp_path):
    output_dir = tmp_path / "year_stratified"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    for filename in OUTPUTS:
        actual = (output_dir / filename).read_bytes()
        assert b"\r\n" not in actual
        assert actual == (SAVED / filename).read_bytes()

