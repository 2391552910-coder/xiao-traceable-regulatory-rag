import json
import subprocess
import sys
from pathlib import Path


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
        saved = (SAVED / filename).read_bytes()
        assert b"\r\n" not in actual
        if filename == "year_stratified_summary.json":
            actual_report = json.loads(actual)
            saved_report = json.loads(saved)
            assert all("\\" not in path for path in actual_report["raw_output_sha256"])
            actual_report["raw_output_sha256"] = {
                path.replace("\\", "/"): digest
                for path, digest in actual_report["raw_output_sha256"].items()
            }
            saved_report["raw_output_sha256"] = {
                path.replace("\\", "/"): digest
                for path, digest in saved_report["raw_output_sha256"].items()
            }
            assert actual_report == saved_report
        else:
            assert actual == saved


