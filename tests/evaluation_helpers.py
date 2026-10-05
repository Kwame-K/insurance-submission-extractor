import importlib.util
from pathlib import Path
from types import ModuleType


def load_generator() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "scripts" / "generate_golden_dataset.py"
    spec = importlib.util.spec_from_file_location("generate_golden_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
