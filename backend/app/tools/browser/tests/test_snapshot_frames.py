from app.tools.browser.snapshot.generator import SnapshotGenerator


def test_snapshot_accepts_include_frames_parameter():
    generator = SnapshotGenerator()

    assert "include_frames" in generator.generate.__code__.co_varnames


def test_ai_formatter_accepts_ref_prefix_parameter():
    formatter = SnapshotGenerator().ai_formatter

    assert "ref_prefix" in formatter.format.__code__.co_varnames
