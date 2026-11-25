import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_production_threads_do_not_use_deprecated_set_daemon_api():
    deprecated_calls = []

    for path in PROJECT_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setDaemon"
            ):
                deprecated_calls.append(f"{path.name}:{node.lineno}")

    assert deprecated_calls == []
