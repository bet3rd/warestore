import pytest

from warestore.presentation.account_manager.ui.theme.accent import (
    ACCENT_PRESETS,
    DEFAULT_ACCENT,
    accent_shades,
    normalize_accent,
    render_qss,
)


def test_default_accent_keeps_the_hand_tuned_red():
    s = accent_shades(DEFAULT_ACCENT)
    assert s.base == "#880808"
    assert s.hover == "#a00a0a"
    assert s.pressed == "#660606"
    assert s.disabled_bg == "#3a1616"
    assert s.disabled_text == "#6a3030"
    assert s.border == "#aa1010"
    assert s.bright == "#cc4444"
    assert s.bright_hover == "#e46060"
    assert s.sel_bg == "#261a1a"
    assert s.sel_border == "#cc1111"
    assert s.on_accent == "#ffffff"


def test_presets_start_with_the_default():
    assert ACCENT_PRESETS[0][1] == DEFAULT_ACCENT
    assert len({hx for _, hx in ACCENT_PRESETS}) == len(ACCENT_PRESETS)


@pytest.mark.parametrize("_name,hx", ACCENT_PRESETS)
def test_every_preset_derives_valid_shades(_name, hx):
    s = accent_shades(hx)
    for value in vars(s).values():
        assert value.startswith("#") and len(value) == 7


def test_derived_shades_order_by_lightness():
    s = accent_shades("#1f5fa8")

    def lum(hx):
        r, g, b = (int(hx[i : i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    assert lum(s.pressed) < lum(s.base) < lum(s.hover)
    assert lum(s.disabled_bg) < lum(s.base)
    assert lum(s.bright) > lum(s.base)


def test_text_on_accent_flips_dark_for_light_colors():
    assert accent_shades("#1f5fa8").on_accent == "#ffffff"
    assert accent_shades("#f5e6a0").on_accent != "#ffffff"


def test_achromatic_accent_does_not_crash():
    s = accent_shades("#808080")
    assert s.base == "#808080"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("#1F5FA8", "#1f5fa8"),
        ("1f5fa8", "#1f5fa8"),
        ("#f80", "#ff8800"),
        ("  #1f5fa8 ", "#1f5fa8"),
        ("nope", DEFAULT_ACCENT),
        ("", DEFAULT_ACCENT),
        (None, DEFAULT_ACCENT),
        (123, DEFAULT_ACCENT),
    ],
)
def test_normalize_accent(raw, expected):
    assert normalize_accent(raw) == expected


def test_render_qss_substitutes_tokens():
    template = "QPushButton { background: @accent; color: @on-accent; }\nQ:hover { background: @accent-hover; }"
    out = render_qss(template, accent_shades(DEFAULT_ACCENT))
    assert out == "QPushButton { background: #880808; color: #ffffff; }\nQ:hover { background: #a00a0a; }"


def test_render_qss_rejects_unknown_tokens():
    with pytest.raises(KeyError):
        render_qss("x { color: @accent-bogus; }", accent_shades(DEFAULT_ACCENT))


def test_shipped_qss_has_no_hardcoded_accent_left():
    from warestore.presentation.account_manager.ui.theme.styles import QSS_TEMPLATE

    for old in ("#880808", "#a00a0a", "#660606", "#3a1616", "#6a3030", "#aa1010"):
        assert old not in QSS_TEMPLATE.lower()
    assert "@accent" in QSS_TEMPLATE
