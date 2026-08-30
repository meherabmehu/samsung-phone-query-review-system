"""Tests for the GSMArena parser (offline, on saved HTML) and normalizers."""
from __future__ import annotations

from app.scraper.parser import (
    extract_battery_mah,
    extract_display_size_inches,
    extract_main_camera_mp,
    extract_price_usd,
    extract_ram_gb,
    extract_weight_g,
    parse_phone_page,
)

SAMPLE_HTML = """
<html><body>
<h1 class="specs-phone-name-title">Samsung Galaxy S23</h1>
<div id="specs-list">
<table>
  <tr><th rowspan="3">Launch</th><td class="ttl">Announced</td><td class="nfo">2023, February 01</td></tr>
  <tr><td class="ttl">Status</td><td class="nfo">Available. Released 2023, February 17</td></tr>
</table>
<table>
  <tr><th rowspan="4">Display</th><td class="ttl">Type</td><td class="nfo">Dynamic AMOLED 2X</td></tr>
  <tr><td class="ttl">Size</td><td class="nfo">6.1 inches, 90.1 cm2</td></tr>
  <tr><td class="ttl">Resolution</td><td class="nfo">1080 x 2340 pixels</td></tr>
</table>
<table>
  <tr><th rowspan="2">Battery</th><td class="ttl">Type</td><td class="nfo">Li-Ion 3900 mAh</td></tr>
  <tr><td class="ttl">Charging</td><td class="nfo">25W wired</td></tr>
</table>
<table>
  <tr><th rowspan="2">Main Camera</th><td class="ttl">Triple</td><td class="nfo">50 MP, f/1.8, 24mm (wide)</td></tr>
  <tr><td class="ttl">Video</td><td class="nfo">8K@24fps</td></tr>
</table>
<table>
  <tr><th rowspan="1">Memory</th><td class="ttl">Internal</td><td class="nfo">128GB 8GB RAM, 256GB 8GB RAM</td></tr>
</table>
<table>
  <tr><th rowspan="1">Body</th><td class="ttl">Weight</td><td class="nfo">168 g (5.93 oz)</td></tr>
</table>
<table>
  <tr><th rowspan="1">Misc</th><td class="ttl">Price</td><td class="nfo">$ 799.00 / £ 699.00</td></tr>
</table>
</div>
</body></html>
"""


def test_parse_phone_page_basic():
    parsed = parse_phone_page(SAMPLE_HTML, slug="samsung_galaxy_s23-12082.php")
    assert parsed["name"] == "Samsung Galaxy S23"
    assert parsed["announced"] == "2023, February 01"
    assert parsed["battery_capacity_mah"] == 3900
    assert parsed["display_size_inches"] == 6.1
    assert parsed["main_camera_mp"] == 50.0
    assert parsed["ram_gb"] == 8.0
    assert parsed["weight_g"] == 168
    assert parsed["price_usd"] == 799.0
    assert len(parsed["specs"]) >= 9


def test_parse_missing_fields_are_none_or_not_available():
    html = '<html><body><div id="specs-list"></div></body></html>'
    parsed = parse_phone_page(html, slug="unknown")
    assert parsed["name"] == "unknown"
    assert parsed["announced"] == "Not available"
    assert parsed["released"] == "Not available"
    assert parsed["battery_capacity_mah"] is None
    assert parsed["display_size_inches"] is None
    assert parsed["main_camera_mp"] is None
    assert parsed["ram_gb"] is None
    assert parsed["weight_g"] is None
    assert parsed["price_usd"] is None
    assert parsed["specs"] == []


def test_multiline_spec_continuation_rows_are_joined():
    html = """
    <div id="specs-list"><table>
      <tr><th rowspan="2">Body</th><td class="ttl">SIM</td><td class="nfo">Nano-SIM</td></tr>
      <tr><td class="ttl"></td><td class="nfo">IP68 water resistant</td></tr>
    </table></div>
    """
    parsed = parse_phone_page(html, slug="x")
    sim = next(s for s in parsed["specs"] if s["key"] == "SIM")
    assert "IP68" in sim["value"]


def test_numeric_extractors():
    assert extract_battery_mah("Li-Ion 3900 mAh") == 3900
    assert extract_battery_mah("no battery here") is None
    assert extract_display_size_inches("6.8 inches, 114.7 cm2") == 6.8
    assert extract_display_size_inches("n/a") is None
    assert extract_main_camera_mp("200 MP, f/1.7, wide") == 200.0
    assert extract_main_camera_mp("no camera") is None
    assert extract_ram_gb("128GB 8GB RAM, 256GB 12GB RAM") == 12.0
    assert extract_ram_gb("128GB storage") is None
    assert extract_weight_g("168 g (5.93 oz)") == 168
    assert extract_weight_g("n/a") is None
    assert extract_price_usd("$ 1,199.00 / £ 1,099") == 1199.0
    assert extract_price_usd("About 190 EUR") is None
