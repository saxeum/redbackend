"""Architecture guard: dependencies point inward only.

    api -> services -> domain
             |
             +-> repositories -> domain

Nothing inner may import something outer. This is the invariant that keeps the
service layer usable from a CLI or worker, and the domain free of FastAPI.
"""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# layer -> prefixes it must not import
FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "domain": ("app.api", "app.services", "app.repositories"),
    "services": ("app.api",),
    "repositories": ("app.api", "app.services"),
}


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def test_inner_layers_do_not_import_outward() -> None:
    violations: list[str] = []
    for layer, forbidden in FORBIDDEN_IMPORTS.items():
        for path in sorted((APP_ROOT / layer).rglob("*.py")):
            for module in _imported_modules(path):
                for prefix in forbidden:
                    if _matches(module, prefix):
                        violations.append(
                            f"{path.relative_to(APP_ROOT)} imports {module}"
                        )

    assert not violations, "outward import(s) found:\n" + "\n".join(violations)


def test_domain_imports_only_the_standard_library() -> None:
    third_party: list[str] = []
    for path in sorted((APP_ROOT / "domain").rglob("*.py")):
        for module in _imported_modules(path):
            root = module.split(".")[0]
            if root in {"app", "fastapi", "pydantic", "psycopg", "jwt"}:
                third_party.append(f"{path.relative_to(APP_ROOT)} imports {module}")

    assert not third_party, "\n".join(third_party)
