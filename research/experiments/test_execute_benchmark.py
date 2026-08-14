import importlib.util
from pathlib import Path


PATH = Path(__file__).with_name("execute_benchmark.py")


def load_module():
    spec = importlib.util.spec_from_file_location("execute_benchmark", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_infer_decision_specific_identity_rejection():
    m = load_module()
    assert m.infer_decision(400, "Missing X-Agent-ID header\n") == "DENY"
    assert m.infer_decision(400, "invalid request body\n") == "UNKNOWN"
    assert m.infer_decision(400, "bad parameter\n") == "UNKNOWN"
    assert m.infer_decision(401, "Unauthorized\n") == "DENY"
    assert m.infer_decision(403, "Forbidden\n") == "DENY"
    assert m.infer_decision(200, '{"status":"ALLOW"}') == "ALLOW"
