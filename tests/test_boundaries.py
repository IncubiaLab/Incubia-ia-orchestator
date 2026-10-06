import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "incubia_orchestrator"
PROTECTED = (ROOT / "foundation", ROOT / "modules" / "governance" / "domain",
             ROOT / "modules" / "governance" / "ports",
             ROOT / "modules" / "orchestration" / "domain",
             ROOT / "modules" / "orchestration" / "ports",
             ROOT / "modules" / "orchestration" / "application")
FORBIDDEN = ("langgraph", "httpx", "openai", "incubia_orchestrator.bootstrap",
             "incubia_orchestrator.modules.orchestration.adapters",
             "incubia_orchestrator.modules.governance.adapters")


def imports(path):
    tree = ast.parse(path.read_text())
    return [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]


def test_protected_layers_have_no_infrastructure_imports():
    for directory in PROTECTED:
        for path in directory.rglob("*.py"):
            for module in imports(path):
                assert not module.startswith(FORBIDDEN), (path, module)


def test_transitive_local_import_boundaries():
    visited = set()
    def visit(path):
        if path in visited:
            return
        visited.add(path)
        for module in imports(path):
            assert not module.startswith(FORBIDDEN), (path, module)
            if module.startswith("incubia_orchestrator."):
                target = ROOT.parent / (module.replace(".", "/") + ".py")
                if target.exists():
                    visit(target)
    for directory in PROTECTED:
        for path in directory.rglob("*.py"):
            visit(path)


def test_cli_has_no_runtime_or_provider_imports():
    path = ROOT / "interfaces" / "cli" / "main.py"
    assert not any(m.startswith(("langgraph", "httpx", "openai", "incubia_orchestrator.modules.orchestration.adapters")) for m in imports(path))
