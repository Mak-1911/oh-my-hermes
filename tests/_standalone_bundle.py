from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


_STANDALONE_BUNDLE_MODULE_NAME = "_test_omh_standalone_bundle"


def _load_standalone_bundle_awareness():
    """Load bundled awareness without access to the installed ``omh`` package."""
    for name in list(sys.modules):
        if name == _STANDALONE_BUNDLE_MODULE_NAME or name.startswith(
            f"{_STANDALONE_BUNDLE_MODULE_NAME}."
        ):
            sys.modules.pop(name, None)

    bundle_dir = Path(__file__).resolve().parents[1] / "src" / "plugin_bundle" / "omh"
    spec = importlib.util.spec_from_file_location(
        _STANDALONE_BUNDLE_MODULE_NAME,
        bundle_dir / "__init__.py",
        submodule_search_locations=[str(bundle_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load the vendored plugin bundle standalone")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_STANDALONE_BUNDLE_MODULE_NAME] = module
    real_import = builtins.__import__

    def standalone_import(name: str, *args: object, **kwargs: object):
        if name == "omh" or name.startswith("omh."):
            raise ImportError("standalone plugin host has no installed omh package")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=standalone_import):
        spec.loader.exec_module(module)
        return importlib.import_module(f"{_STANDALONE_BUNDLE_MODULE_NAME}.awareness")
