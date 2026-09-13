"""The sole visual observation supplied to the neural policy."""

from PIL import Image, ImageDraw


WIDTH = 320
HEIGHT = 180


def render_panel(
    passed: int, total: int, busy: bool = False, has_result: bool = True
) -> Image.Image:
    """Render the fixed 320×180 RGB task-state panel.

    The panel uses filled areas and brightness only.  Human-readable labels
    belong around the image so they cannot become a second policy input.
    """
    if (
        isinstance(passed, bool)
        or isinstance(total, bool)
        or not isinstance(passed, int)
        or not isinstance(total, int)
        or total <= 0
        or not 0 <= passed <= total
    ):
        raise ValueError("invalid passed/total counts")

    image = Image.new("RGB", (WIDTH, HEIGHT), (239, 242, 245))
    draw = ImageDraw.Draw(image)
    margin, gap = 12, 8
    panel_width = (WIDTH - 2 * margin - 2 * gap) // 3
    top, bottom = 24, HEIGHT - 24

    regions = [
        (margin, top, margin + panel_width, bottom),
        (margin + panel_width + gap, top, margin + 2 * panel_width + gap, bottom),
        (margin + 2 * (panel_width + gap), top, WIDTH - margin, bottom),
    ]
    for box in regions:
        draw.rectangle(box, fill=(211, 218, 226))

    # Codex activity: a bright, fully-filled region while a turn is active.
    draw.rectangle(regions[0], fill=(54, 123, 178) if busy else (127, 161, 187))
    # Whether an external evaluation result is currently available.
    draw.rectangle(regions[1], fill=(65, 159, 110) if has_result else (158, 169, 180))

    # Test status: passing and failing areas share the fixed third region.
    left, top, right, bottom = regions[2]
    passed_end = left + round((right - left + 1) * passed / total) - 1
    if passed:
        draw.rectangle((left, top, passed_end, bottom), fill=(73, 170, 111))
    if passed_end < right:
        draw.rectangle((passed_end + 1, top, right, bottom), fill=(192, 82, 73))
    return image
