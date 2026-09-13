"""Der Dateinamensvorschlag aus dem gelesenen Text.

Die Beispieltexte stammen aus Mias echten Briefen, durch denselben Weg
geschickt, den ein Beleg nimmt: Seite als Bild gerendert, durch Tesseract,
Konfidenzfilter. Deshalb stehen hier auch die OCR-Fehler drin (``fur`` statt
``für``, Logo-Reste am Zeilenanfang). Ein Test auf sauberem Text würde genau
die Fälle nicht prüfen, an denen die Regeln scheitern.
"""

from datetime import date

from src import namen

HEUTE = date(2026, 9, 10)


# --- Datum --------------------------------------------------------------


def test_datum_bevorzugt_das_beschriftete():
    """``Datum 03.08.2026`` schlägt jedes andere Datum auf dem Blatt.

    Auf dem Anschreiben der Hansestadt steht zuerst ``Ihre Nachricht vom:
    03.08.2026 15:05:26``, und in anderen Briefen stehen dort Fristen und
    Vertragstermine. Nur das ausgezeichnete ist das Briefdatum.
    """
    text = "Ihre Nachricht vom: 01.07.2026 15:05:26\nDatum 03.08.2026\nSehr geehrte Frau"
    assert namen.datum_finden(text, HEUTE) == date(2026, 8, 3)


def test_datum_nimmt_die_alleinstehende_zeile():
    text = "Philipp Grünwald\nIm Apfelgarten 75c\n10.02.2025\nSergej Klein"
    assert namen.datum_finden(text, HEUTE) == date(2025, 2, 10)


def test_datum_im_fliesstext_ist_die_letzte_wahl():
    """Ohne besseres Datum zählt der Fließtext, aber nur dann.

    In der Kündigung steht das Briefdatum am Rand und der Vertragsbeginn
    mitten im Satz. Wäre der Fließtext gleichwertig, hieße die Datei nach dem
    Tag, an dem Mias Vater angefangen hat zu arbeiten.
    """
    text = "Kündigung des Arbeitsverhältnisses vom 01.08.2024\nzum 12.02.2025"
    assert namen.datum_finden(text, HEUTE) == date(2025, 2, 12)


def test_datum_als_wort():
    assert namen.datum_finden("Hamburg, 19. Mai 2026", HEUTE) == date(2026, 5, 19)


def test_datum_in_der_zukunft_faellt_raus():
    """Ein Briefdatum liegt nie in der Zukunft.

    Auf Formularen stehen Maßnahmezeiträume, die Jahre nach vorn reichen
    (``bis 31.07.2028``). Ohne die Grenze hieße die Schweigepflichtentbindung
    nach ihrem Enddatum.
    """
    text = "vom 01.08.2025 bis 31.07.2028"
    assert namen.datum_finden(text, HEUTE) == date(2025, 8, 1)


def test_datum_unmoegliches_wird_uebergangen():
    """Der 31. Februar ist ein OCR-Fehler, kein Datum."""
    assert namen.datum_finden("31.02.2026\n05.03.2026", HEUTE) == date(2026, 3, 5)


def test_ohne_datum_kein_datum():
    assert namen.datum_finden("Ein Blatt ganz ohne Zahlen", HEUTE) is None


# --- Absender -----------------------------------------------------------


def test_absender_aus_dem_briefkopf():
    text = "HANSESTADT\nBUXTEHUDE\nHansestadt Buxtehude Postfach 1555 21605 Buxtehude"
    assert namen.absender_finden(text) == "Hansestadt Buxtehude"


def test_absender_ohne_die_anhaengende_adresse():
    """Briefkopf und Anschriftfeld landen bei OCR in einer Zeile."""
    text = "Sparkasse Harburg-Buxtehude Sand 2 21073 Hamburg"
    assert namen.absender_finden(text) == "Sparkasse Harburg-Buxtehude"


def test_absender_hinter_dem_logo():
    """Aus einem Logo macht Tesseract ``ees`` oder ``C d ® B)``."""
    assert namen.absender_finden("ees Bundesagentur für Arbeit") == "Bundesagentur für Arbeit"


def test_absender_erkennt_verlorenen_umlaut():
    """Tesseract liest ``für`` regelmäßig als ``fur``.

    Ohne die entschärfte Schreibweise im Muster hätte die Fahrtkostenerklärung
    keinen Absender bekommen, obwohl er groß im Kopf steht.
    """
    assert namen.absender_finden("ca ae Bundesagentur fur Arbeit") == "Bundesagentur fur Arbeit"


def test_absender_ignoriert_den_empfaenger():
    """Weiter unten steht Mia selbst, und die ist kein Absender.

    In einer Ablage, die komplett ihr gehört, sagt ihr eigener Name im
    Dateinamen nichts aus.
    """
    text = "\n".join(["Zeile"] * 30 + ["Krankenkasse IKK gesund plus"])
    assert namen.absender_finden(text) == ""


# --- Betreff ------------------------------------------------------------


def test_betreff_steht_ueber_der_anrede():
    """DIN 5008: der Betreff steht direkt über der Anrede.

    Diese Stelle trägt weiter als jedes Schlüsselwort. ``Anpassung Ihrer
    Zugangsdaten für pushTAN`` enthält keines und ist trotzdem der Betreff.
    """
    text = "12.04.2026\nAnpassung Ihrer Zugangsdaten für pushTAN\nSehr geehrter Herr Grünwald,"
    assert namen.betreff_finden(text) == "Anpassung Ihrer Zugangsdaten für pushTAN"


def test_betreff_ueber_mehrere_zeilen():
    """Ein langer Betreff bricht um, und die untere Hälfte allein ergibt Unsinn.

    Ohne das Sammeln hieß die Meldebescheinigung ``Bundesmeldegesetz (BMG)``.
    """
    text = (
        "Datum 03.08.2026\n"
        "Meldebescheinigung gemäß § 18 Absatz 1\n"
        "Bundesmeldegesetz (BMG)\n"
        "Sehr geehrte Frau Grünwald,"
    )
    assert (
        namen.betreff_finden(text)
        == "Meldebescheinigung gemäß § 18 Absatz 1 Bundesmeldegesetz (BMG)"
    )


def test_betreff_nicht_aus_dem_adressfeld():
    """Ein privater Brief hat oft keine Betreffzeile.

    Über der Anrede steht dann die Anschrift des Empfängers, und aus Mias
    Vater-Kündigung wurde ``2025-02-10 MAXEDV Beratung GmbH Boytinstraße``.
    Lieber kein Betreff als eine Straße im Dateinamen.
    """
    text = "Sergej Klein\nMAXEDV Beratung GmbH\nBoytinstraße 25\n22143 Hamburg\nSehr geehrter Herr,"
    assert namen.betreff_finden(text) == ""


def test_betreff_ohne_anrede_aus_der_ueberschrift():
    """Formulare haben keine Anrede, sondern eine Überschrift."""
    text = "Bundesagentur für Arbeit\nSchweigepflichtentbindung - Teilhabe am Arbeitsleben\n§ 112"
    assert namen.betreff_finden(text) == "Schweigepflichtentbindung"


def test_betreff_stutzt_die_formularueberschrift():
    """Überschrift und Erklärtext stehen in derselben Zeile.

    Auf der Wohnungsgeberbestätigung folgt direkt hinter dem Titel das
    Kleingedruckte, ohne Umbruch. Der Titel ist der Betreff.
    """
    text = (
        "Wohnungsgeberbestätigung Ab dem 01.11.2015 muss der Wohnungsgeber jedem "
        "Meldepflichtigen eine Bestätigung aushändigen"
    )
    assert namen.betreff_finden(text) == "Wohnungsgeberbestätigung"


def test_betreff_nimmt_kein_fliesstextwort():
    """Nach der Anrede steht Fließtext, und der enthält Betreffwörter.

    ``hiermit kündige ich das Arbeitsverhältnis`` ist kein Betreff, nur ein
    Satz mit dem Wort darin.
    """
    text = "Sehr geehrter Herr Klein,\nhiermit kündige ich das bestehende Arbeitsverhältnis"
    assert namen.betreff_finden(text) == ""


def test_betreff_ohne_prädikat():
    """Ein Betreff ist ein Nominalausdruck, kein Satz."""
    assert namen.betreff_finden("Diese Bestätigung gilt für folgende Personen") == ""


# --- Der fertige Name ---------------------------------------------------


def test_name_setzt_sich_aus_drei_teilen_zusammen():
    text = "Datum 03.08.2026\nHansestadt Buxtehude Postfach 1555\nMeldebescheinigung gemäß § 18\nSehr geehrte Frau"
    assert namen.name_bauen(text, ".pdf", HEUTE) == (
        "2026-08-03 Hansestadt Buxtehude Meldebescheinigung gemäß § 18.pdf"
    )


def test_name_ohne_betreff_ist_kein_name():
    """Ein Vorschlag, der nur aus einem Datum besteht, wird nur weggetippt."""
    assert namen.name_bauen("Datum 03.08.2026\nHansestadt Buxtehude", ".pdf", HEUTE) == ""


def test_name_kommt_auch_ohne_absender_zustande():
    """Die Teile sind einzeln optional, sonst fängt der Name mit einem Leerzeichen an."""
    text = "Schweigepflichtsentbindung\nNeu Wulmstorf den 21.02.2025"
    assert namen.name_bauen(text, ".jpg", HEUTE) == "2025-02-21 Schweigepflichtsentbindung.jpg"


def test_name_enthaelt_keine_pfadzeichen():
    """Ein Schrägstrich aus dem Text würde den Zielordner verlassen."""
    text = "Bescheid Az 12/2026 Widerspruch\nSehr geehrte Frau\nDatum 03.08.2026"
    assert "/" not in namen.name_bauen(text, ".pdf", HEUTE)


def test_name_ist_gedeckelt():
    """Manche Dateisysteme geben bei 255 Bytes auf."""
    lang = "Bescheid " + "sehr langer Betreff " * 20
    ergebnis = namen.name_bauen(f"Datum 03.08.2026\n{lang}\nSehr geehrte Frau", ".pdf", HEUTE)
    assert len(ergebnis) <= 115


def test_leerer_text_gibt_keinen_vorschlag():
    """Ohne OCR gibt es nichts zu lesen, und dann eben keinen Vorschlag."""
    assert namen.name_bauen("", ".pdf", HEUTE) == ""
    assert namen.vorschlagen("") == {"datum": "", "absender": "", "betreff": ""}
