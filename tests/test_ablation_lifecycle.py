import importlib.util
import sys
import weakref
from pathlib import Path
from types import SimpleNamespace


def test_previous_model_released_before_next_index_load(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "experiments/04_ablation_study.py"
    spec = importlib.util.spec_from_file_location("ablation_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    refs = []

    class Index:
        def __init__(self):
            self.cycle = lambda: self  # Mirrors DenseRetriever's bound encode closures.

    def build(*args, **kwargs):
        assert all(ref() is None for ref in refs), "previous index still owns weights"
        index = Index()
        refs.append(weakref.ref(index))
        return [], index

    cfg = {"retrieval": {"top_k": 5, "vector_weight": .7},
           "evaluation": {"coverage_threshold": .5}}
    monkeypatch.setattr(module, "prepare_evaluation", lambda *a: (cfg, None, tmp_path / "out.csv"))
    monkeypatch.setattr(module, "build_knowledge_index", build)
    monkeypatch.setattr(module, "make_router", lambda index: SimpleNamespace(index=index))
    monkeypatch.setattr(module, "evaluate_queries", lambda *a, **k: [])
    monkeypatch.setattr(module, "save_run", lambda *a, **kw: None)
    monkeypatch.setattr(module, "summarize", lambda *a: [])
    monkeypatch.setattr(sys, "argv", [str(path)])
    module.main()
    assert len(refs) == 3
