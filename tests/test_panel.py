import pytest

from flycodex.panel import render_panel


def test_panel_has_fixed_rgb_dimensions():
    image = render_panel(1, 5)

    assert image.mode == "RGB"
    assert image.size == (320, 180)


def test_panel_reflects_distinct_result_counts():
    assert render_panel(1, 5).tobytes() != render_panel(2, 5).tobytes()


def test_panel_has_no_failure_color_when_every_test_passes():
    assert (192, 82, 73) not in render_panel(5, 5).get_flattened_data()


def test_panel_has_no_passing_color_when_no_test_passes():
    assert (73, 170, 111) not in render_panel(0, 5).get_flattened_data()


def test_panel_reflects_busy_and_missing_result_states():
    settled = render_panel(1, 5)

    assert settled.tobytes() != render_panel(1, 5, busy=True).tobytes()
    assert settled.tobytes() != render_panel(1, 5, has_result=False).tobytes()


@pytest.mark.parametrize("passed,total", [(-1, 5), (6, 5), (0, 0)])
def test_panel_rejects_invalid_test_counts(passed, total):
    with pytest.raises(ValueError, match="counts"):
        render_panel(passed, total)
