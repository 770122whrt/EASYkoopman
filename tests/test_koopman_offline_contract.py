from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_phase2_koopman_modules_do_not_import_isaac_runtime():
    forbidden = ("isaaclab", "omni.", "gymnasium", "torch")
    for source_path in (PROJECT_ROOT / "koopman").glob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{source_path.name} imports offline-forbidden token {token!r}"

