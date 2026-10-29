"""Check the published development benchmark without creating new labels."""
from src.config import load_config
from src.data.benchmark import load_benchmark


def test_development_benchmark_loads_against_frozen_manifest():
    benchmark = load_benchmark(load_config())
    assert benchmark.manifest['usage'] == 'development_only'
    assert benchmark.manifest['label_origin'] == 'ai_dual_pass_adjudicated'
    assert (len(benchmark.documents), len(benchmark.chunks), len(benchmark.queries)) == (319, 7899, 40)
