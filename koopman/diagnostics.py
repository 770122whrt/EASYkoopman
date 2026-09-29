"""Output reservation and JSON-safe diagnostics for current experiments."""
from pathlib import Path
import re
import numpy as np
def reserve_output(root, run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', run_id):
        raise ValueError('diagnostic_run_id_invalid')
    root = Path(root).resolve()
    target = root / run_id
    if not target.resolve().is_relative_to(root):
        raise ValueError('diagnostic_output_escape')
    target.mkdir(parents=True, exist_ok=False)
    return target

def json_safe(value):
    """Keep nonfinite diagnostics explicit without emitting invalid JSON."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    return value
