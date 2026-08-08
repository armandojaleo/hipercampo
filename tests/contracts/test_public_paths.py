"""
The import paths the DOCUMENTATION promises. These are a contract with people who
already use hipercampo, not an internal detail: breaking them is an incompatible
change, and splitting the package into layers is exactly when they break without
anyone noticing.

What is protected here, and where it is promised:

    from hipercampo import Hipercampo             README, __init__
    from hipercampo import encoder                docs/INSTALL.md and .es
    from hipercampo.roles import ItemMemory, ...  README and docs/README.es
    python -m hipercampo.cli ...                  hooks in .claude/settings.json
    python -m hipercampo.server                   the users' own .mcp.json
    hipercampo = "hipercampo.cli:main"            pyproject [project.scripts]
"""

import importlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, ejecutar  # noqa: E402

# The package layers, bottom to top. A layer may import from the ones BELOW it,
# never from the ones above.
LAYERS = ["core", "support", "storage", "cycle"]


def test_main_api():
    from hipercampo import Hipercampo
    assert Hipercampo.__name__ == "Hipercampo"


def test_encoder_by_attribute_and_by_import():
    """BOTH forms. A `sys.modules` entry alone lets the import through but leaves
    attribute access broken — and attribute access is exactly how INSTALL shows it
    (`from hipercampo import encoder`)."""
    import hipercampo
    from hipercampo import encoder as via_from
    module = importlib.import_module("hipercampo.encoder")
    assert hipercampo.encoder is module, "the package attribute is missing"
    assert via_from is module
    assert callable(module.enable_semantic)


def test_encoder_is_one_module_with_one_state():
    """The alias must not be a COPY of names: the semantic hook is module-level
    global state, and with two views, enabling it through one path would not be
    visible from the other. They have to be the same object."""
    import hipercampo.encoder as alias
    from hipercampo.core import encoder as real
    assert alias is real
    real.set_semantic_hook(lambda t: None)
    try:
        assert alias.semantic_active() is True, "state is not shared"
    finally:
        real.set_semantic_hook(None)
    assert alias.semantic_active() is False


def test_roles_public_path():
    from hipercampo.roles import ItemMemory, encode_fact, query_role
    assert len(ItemMemory()) == 0
    assert callable(encode_fact) and callable(query_role)


def test_cli_and_server_still_run_as_modules():
    """`python -m hipercampo.cli` is wired into the hooks and `hipercampo.server`
    into the .mcp.json of anyone who already installed it: neither can move."""
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", "version"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and r.stdout.strip(), r.stderr
    r = subprocess.run([sys.executable, "-c", "import hipercampo.server"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr


def test_console_script_points_somewhere_real():
    """`pyproject` declares hipercampo = "hipercampo.cli:main". If cli moved, the
    installed command would stop existing without any import failing first."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'hipercampo = "hipercampo.cli:main"' in text
    from hipercampo.cli import main
    assert callable(main)


def test_the_layers_exist():
    """Guard for the guard below. It walks each layer's files, so if a layer is
    renamed the walk finds nothing and the dependency check passes VACUOUSLY —
    green while checking nothing. That already happened once, when the layers were
    renamed from Spanish to English and this list was left behind."""
    for layer in LAYERS:
        directory = ROOT / "hipercampo" / layer
        assert directory.is_dir(), f"the layer '{layer}' does not exist: {directory}"
        assert any(directory.glob("*.py")), f"the layer '{layer}' has no modules"


def test_layers_do_not_look_upwards():
    """The direction of dependencies is what holds the organisation up: if `core`
    starts importing from `cycle`, the layers are decoration and the core can no
    longer be measured — or embedded — on its own."""
    for i, layer in enumerate(LAYERS):
        above = LAYERS[i + 1:]
        for py in (ROOT / "hipercampo" / layer).glob("*.py"):
            text = py.read_text(encoding="utf-8")
            for upper in above:
                assert f"..{upper}" not in text, (
                    f"{layer}/{py.name} imports from the upper layer '{upper}'")


if __name__ == "__main__":
    raise SystemExit(ejecutar(dict(globals())))
