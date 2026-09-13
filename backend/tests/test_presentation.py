"""Tests fuer Anzeige-Aufbereitung und Icons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.categories import BY_KEY, CATEGORIES, Field
from src.icons import available, icon
from src.presenter import _relative_or_text, build_card, format_value


def _row(value=None, text=None, unit=None):  # type: ignore[no-untyped-def]
    return {"value": value, "text_value": text, "unit": unit}


# --- Icons ---------------------------------------------------------------


def test_icon_renders_svg() -> None:
    markup = str(icon("heart"))
    assert markup.startswith("<svg")
    assert 'stroke-width="1.5"' in markup
    assert 'aria-hidden="true"' in markup


def test_icon_unknown_is_empty() -> None:
    assert str(icon("gibtsnicht")) == ""


def test_every_category_icon_exists() -> None:
    """Verhindert eine leere Kachel, wenn jemand einen Icon-Namen vertippt."""
    names = available()
    for cat in CATEGORIES:
        assert cat.icon in names, f"Icon fehlt: {cat.icon}"


# --- Kategorien ----------------------------------------------------------


def test_each_category_has_exactly_one_lead() -> None:
    """Kern der Design-Entscheidung: eingeklappt genau eine Zahl."""
    for cat in CATEGORIES:
        leads = [f for f in cat.fields if f.lead]
        assert len(leads) == 1, f"{cat.key} hat {len(leads)} Leitwerte"


def test_lead_and_caption_not_in_details() -> None:
    for cat in CATEGORIES:
        detail_keys = {f.key for f in cat.details}
        assert cat.lead.key not in detail_keys
        if cat.caption:
            assert cat.caption.key not in detail_keys


# --- Formatierung --------------------------------------------------------


def test_format_number_with_unit() -> None:
    out = format_value(Field("gewicht", "Gewicht"), _row(value=89.5, unit="kg"))
    assert out["display"] == "89.5 kg"
    assert out["empty"] is False


def test_format_integer_has_no_decimal() -> None:
    out = format_value(Field("gaeste", "Gäste"), _row(value=40.0))
    assert out["display"] == "40"


def test_format_missing_row_is_empty() -> None:
    out = format_value(Field("weg", "Weg"), None)
    assert out["empty"] is True


def test_trend_down_is_positive_signal() -> None:
    """Abnehmen ist 'down' und wird gruen gezeigt, nicht als Minuszahl."""
    out = format_value(Field("delta", "", trend=True), _row(value=-1.0, unit="kg"))
    assert out["trend"] == "down"
    assert out["display"] == "1.0 kg", "Vorzeichen steckt im Pfeil, nicht im Text"


def test_trend_up() -> None:
    out = format_value(Field("delta", "", trend=True), _row(value=0.8, unit="kg"))
    assert out["trend"] == "up"


def test_relative_dates() -> None:
    now = datetime.now(UTC)
    assert _relative_or_text(now.isoformat()) == "heute"
    assert _relative_or_text((now - timedelta(days=1)).isoformat()) == "gestern"
    assert _relative_or_text((now - timedelta(days=3)).isoformat()) == "vor 3 Tagen"
    assert _relative_or_text((now - timedelta(days=21)).isoformat()) == "vor 3 Wochen"


def test_plain_text_passes_through() -> None:
    assert _relative_or_text("Laila Kommt zu uns") == "Laila Kommt zu uns"


def test_empty_text_is_empty() -> None:
    assert _relative_or_text(None) == ""


# --- Karten --------------------------------------------------------------


def test_build_card_splits_lead_and_details() -> None:
    cat = BY_KEY["gesundheit"]
    latest = {
        "gewicht": _row(value=89.5, unit="kg"),
        "gewicht_delta": _row(value=-1.0, unit="kg"),
        "ernaehrung_eintraege": _row(value=38.0),
    }
    card = build_card(cat, latest)

    assert card["lead"]["display"] == "89.5 kg"
    assert card["caption"]["trend"] == "down"
    assert card["has_data"] is True
    detail_keys = [d["key"] for d in card["details"]]
    assert "gewicht" not in detail_keys
    assert "ernaehrung_eintraege" in detail_keys


def test_build_card_without_data() -> None:
    card = build_card(BY_KEY["homelab"], {})
    assert card["has_data"] is False
    assert card["details"] == []
