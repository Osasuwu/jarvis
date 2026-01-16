"""Simple smoke test to verify package imports correctly."""


def test_import_jarvis() -> None:
    """Test that jarvis package can be imported."""
    import jarvis

    assert hasattr(jarvis, "__version__")
    assert jarvis.__version__ == "0.1.0"


def test_import_main() -> None:
    """Test that main module can be imported."""
    from jarvis.main import app

    assert app is not None
