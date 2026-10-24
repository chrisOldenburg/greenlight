#!/usr/bin/env python3
"""python3 gen_covers.py albums.txt
albums.txt: ein Spotify-Link (oder spotify:album:ID / spotify:playlist:ID) pro Zeile, # = Kommentar
Erzeugt: covers/*.jpg, dashboard.yaml, nfc_automation.yaml"""
import json, re, sys, urllib.parse, urllib.request
from pathlib import Path

PLAYER = "media_player.schlafzimmer"
COLUMNS = 4
COVER_DIR = Path("covers")             # später nach /config/www/covers/ kopieren

def oembed(url):
    api = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe="")
    with urllib.request.urlopen(api, timeout=15) as r:
        return json.load(r)

def main(path):
    COVER_DIR.mkdir(exist_ok=True)
    out = ["type: grid", f"columns: {COLUMNS}", "square: true", "cards:"]
    mapping = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.search(r"(album|playlist)[/:]([A-Za-z0-9]+)", line)
        if not m:
            print("Übersprungen:", line)
            continue
        kind, aid = m.groups()
        link = f"https://open.spotify.com/{kind}/{aid}"
        data = oembed(link)
        title = data.get("title", aid).replace("\n", " ")
        urllib.request.urlretrieve(data["thumbnail_url"], COVER_DIR / f"{aid}.jpg")
        print("OK:", title)
        mapping.append((link, title))
        out += [
            "  - type: picture",
            f"    image: /local/covers/{aid}.jpg",
            f"    alt_text: {json.dumps(title, ensure_ascii=False)}",
            "    tap_action:",
            "      action: perform-action",
            "      perform_action: media_player.play_media",
            "      target:",
            f"        entity_id: {PLAYER}",
            "      data:",
            "        media_content_type: music",
            f"        media_content_id: {link}",
        ]
    # Steuerung (Play/Pause, Zurück/Vor, Lautstärke) als Standard-Tile-Karte über dem Cover-Grid
    stack = [
        "type: vertical-stack",
        "cards:",
        "  - type: tile",
        f"    entity: {PLAYER}",
        "    vertical: false",
        "    features_position: bottom",
        "    features:",
        "      - type: media-player-playback-controls",
        "      - type: media-player-volume-slider",
        "  - " + out[0],
    ] + ["    " + l for l in out[1:]]
    Path("dashboard.yaml").write_text("\n".join(stack) + "\n", encoding="utf-8")
    print("dashboard.yaml geschrieben")

    auto = [
        "alias: Kinder-Album per NFC",
        "mode: restart",
        "triggers:",
        "  - trigger: tag",
        "actions:",
        "  - variables:",
        "      albums:",
    ]
    for i, (link, title) in enumerate(mapping, 1):
        auto.append(f'        "TAG-ID-{i}": "{link}"  # {title}')
    auto += [
        "  - condition: template",
        '    value_template: "{{ trigger.tag_id in albums }}"',
        "  - action: media_player.play_media",
        "    target:",
        f"      entity_id: {PLAYER}",
        "    data:",
        "      media_content_type: music",
        '      media_content_id: "{{ albums[trigger.tag_id] }}"',
    ]
    Path("nfc_automation.yaml").write_text("\n".join(auto) + "\n", encoding="utf-8")
    print("nfc_automation.yaml geschrieben")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Aufruf: python3 gen_covers.py albums.txt")
    main(sys.argv[1])
