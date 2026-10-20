"""
Comprehensive Channel Taxonomy Re-Tagging Script
Tags all 91 channels in instance/iptv.db with precise Country, Genre, and Language metadata.
Also regenerates data/curated_fta_channels.m3u with standardized tvg-country and tvg-language attributes.
"""
import sys
import re
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
from app.models import Channel, Country, Genre, Language, channel_genres, channel_languages
from app.services.channel_service import ChannelService

COUNTRY_DEFINITIONS = {
    "US": "United States",
    "GB": "United Kingdom",
    "FR": "France",
    "DE": "Germany",
    "ES": "Spain",
    "IT": "Italy",
    "JP": "Japan",
    "IN": "India",
    "CN": "China",
    "RU": "Russia",
    "UA": "Ukraine",
    "PL": "Poland",
    "VN": "Vietnam",
    "TR": "Turkey",
    "SG": "Singapore",
    "AT": "Austria",
    "KR": "South Korea",
    "QA": "Qatar",
    "AE": "United Arab Emirates",
    "BR": "Brazil",
    "HU": "Hungary",
    "SK": "Slovakia",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "KZ": "Kazakhstan",
    "CI": "Ivory Coast",
    "LU": "Luxembourg",
    "BJ": "Benin",
    "IQ": "Iraq",
    "RO": "Romania",
    "KG": "Kyrgyzstan",
    "SD": "Sudan",
    "CZ": "Czech Republic",
    "AU": "Australia"
}

LANGUAGE_DEFINITIONS = {
    "eng": "English",
    "spa": "Spanish",
    "fra": "French",
    "deu": "German",
    "hin": "Hindi",
    "rus": "Russian",
    "ukr": "Ukrainian",
    "pol": "Polish",
    "jpn": "Japanese",
    "vie": "Vietnamese",
    "tur": "Turkish",
    "ara": "Arabic",
    "por": "Portuguese",
    "hun": "Hungarian",
    "slk": "Slovak",
    "cat": "Catalan",
    "zho": "Chinese",
    "kor": "Korean",
    "nld": "Dutch",
    "ces": "Czech",
    "kur": "Kurdish",
    "ron": "Romanian",
    "kir": "Kyrgyz",
    "kaz": "Kazakh",
    "tel": "Telugu",
    "ltz": "Luxembourgish",
    "ita": "Italian"
}

# Explicit mapping overrides for high precision
CHANNEL_METADATA_MAP = {
    # Original 13 channels
    "France 24 English": {"country": "FR", "genres": ["News"], "languages": ["eng"]},
    "DW English": {"country": "DE", "genres": ["News"], "languages": ["eng"]},
    "NASA TV Public": {"country": "US", "genres": ["Science"], "languages": ["eng"]},
    "NHK World Japan": {"country": "JP", "genres": ["News"], "languages": ["eng"]},
    "Euronews English": {"country": "FR", "genres": ["News"], "languages": ["eng"]},
    "Al Jazeera English": {"country": "QA", "genres": ["News"], "languages": ["eng"]},
    "Red Bull TV": {"country": "AT", "genres": ["Sports"], "languages": ["eng"]},
    "Bloomberg TV": {"country": "US", "genres": ["Business", "News"], "languages": ["eng"]},
    "TV5Monde Info": {"country": "FR", "genres": ["News", "General"], "languages": ["fra"]},
    "Arirang TV": {"country": "KR", "genres": ["Culture", "News"], "languages": ["eng"]},
    "CGTN English": {"country": "CN", "genres": ["News"], "languages": ["eng"]},
    "RAI News 24": {"country": "IT", "genres": ["News"], "languages": ["ita"]},
    "DW Deutsch": {"country": "DE", "genres": ["News", "Culture"], "languages": ["deu"]},

    # News
    "3CatInfo": {"country": "ES", "genres": ["News"], "languages": ["cat", "spa"]},
    "4 SiDES TV": {"country": "IN", "genres": ["News"], "languages": ["eng"]},
    "4TV News": {"country": "IN", "genres": ["News"], "languages": ["tel", "hin"]},
    "6 TV Telugu": {"country": "IN", "genres": ["News"], "languages": ["tel"]},

    # Documentary
    "30A Loomered TV": {"country": "US", "genres": ["Documentary"], "languages": ["eng"]},
    "365 days TV": {"country": "RU", "genres": ["Documentary"], "languages": ["rus"]},
    "Adventure Earth": {"country": "DE", "genres": ["Documentary"], "languages": ["eng", "deu"]},
    "Al Arabiya Programs": {"country": "AE", "genres": ["Documentary"], "languages": ["ara"]},
    "American Heroes Channel": {"country": "US", "genres": ["Documentary"], "languages": ["eng"]},
    "Animal Planet (United States)": {"country": "US", "genres": ["Documentary"], "languages": ["eng"]},
    "Animal Planet Latin America": {"country": "US", "genres": ["Documentary"], "languages": ["spa"]},

    # Science
    ".sci-fi": {"country": "RU", "genres": ["Science"], "languages": ["rus"]},
    "Can Tho TV 2": {"country": "VN", "genres": ["Science", "Education"], "languages": ["vie"]},
    "Discovery Science Latin America": {"country": "US", "genres": ["Science"], "languages": ["spa"]},
    "Eko TV": {"country": "UA", "genres": ["Science"], "languages": ["ukr"]},
    "Ozone TV": {"country": "HU", "genres": ["Science"], "languages": ["hun"]},
    "Wonder": {"country": "GB", "genres": ["Science", "Documentary"], "languages": ["eng"]},

    # Music
    "3ABN Praise Him Music Network": {"country": "US", "genres": ["Music"], "languages": ["eng"]},
    "4ever Music": {"country": "UA", "genres": ["Music"], "languages": ["ukr"]},
    "4 Fun Dance": {"country": "PL", "genres": ["Music"], "languages": ["pol"]},
    "4 Fun TV": {"country": "PL", "genres": ["Music"], "languages": ["pol"]},
    "9X Jalwa": {"country": "IN", "genres": ["Music"], "languages": ["hin"]},

    # Classic
    "3Cat Plats bruts": {"country": "ES", "genres": ["Classic", "Comedy"], "languages": ["cat"]},
    "ARTFLIX Movie Classics": {"country": "US", "genres": ["Classic", "Movies"], "languages": ["eng"]},
    "Bollywood Film": {"country": "RO", "genres": ["Classic", "Movies"], "languages": ["hin", "ron"]},
    "BRIDGE Classic": {"country": "RU", "genres": ["Classic", "Music"], "languages": ["rus"]},
    "CCTV-Nostalgia Theater": {"country": "CN", "genres": ["Classic"], "languages": ["zho"]},

    # Movies
    "24 Hour Free Movies": {"country": "US", "genres": ["Movies"], "languages": ["eng"]},
    "4ever Cinema": {"country": "UA", "genres": ["Movies"], "languages": ["ukr"]},
    "30A TV Classic Movies": {"country": "US", "genres": ["Movies", "Classic"], "languages": ["eng"]},
    "312 Kino": {"country": "KG", "genres": ["Movies"], "languages": ["rus", "kir"]},
    "&TV International": {"country": "IN", "genres": ["Movies", "Entertainment"], "languages": ["hin"]},

    # Sports
    "30A Golf Kingdom": {"country": "US", "genres": ["Sports"], "languages": ["eng"]},
    "A Spor SD": {"country": "TR", "genres": ["Sports"], "languages": ["tur"]},
    "ACC Digital Network": {"country": "US", "genres": ["Sports"], "languages": ["eng"]},
    "ACC Network": {"country": "US", "genres": ["Sports"], "languages": ["eng"]},
    "Arena4": {"country": "HU", "genres": ["Sports"], "languages": ["hun"]},
    "Arena Sport 1": {"country": "SK", "genres": ["Sports"], "languages": ["slk"]},

    # Animation
    "ADN TV+": {"country": "FR", "genres": ["Animation"], "languages": ["fra"]},
    "Aniplus Asia": {"country": "SG", "genres": ["Animation"], "languages": ["eng", "jpn"]},
    "Cartoon Classics": {"country": "PL", "genres": ["Animation"], "languages": ["eng"]},
    "Cartoon Network Asia": {"country": "SG", "genres": ["Animation", "Kids"], "languages": ["eng"]},
    "Cartoon Network CEE Czech Republic": {"country": "CZ", "genres": ["Animation", "Kids"], "languages": ["ces"]},
    "Cartoon Network CEE Ukraine": {"country": "UA", "genres": ["Animation", "Kids"], "languages": ["ukr"]},

    # Kids
    "3ABN Kids": {"country": "US", "genres": ["Kids"], "languages": ["eng"]},
    "ADO TV": {"country": "BJ", "genres": ["Kids"], "languages": ["fra"]},
    "Afarin Baxcha": {"country": "IQ", "genres": ["Kids"], "languages": ["kur"]},
    "Afarin TV [Not 24/7]": {"country": "IQ", "genres": ["Kids"], "languages": ["kur"]},
    "Baby Shark TV": {"country": "US", "genres": ["Kids"], "languages": ["eng"]},
    "BabyFirst": {"country": "US", "genres": ["Kids"], "languages": ["eng"]},
    "BabyFirst Spanish": {"country": "US", "genres": ["Kids"], "languages": ["spa"]},

    # Weather
    "3Cat Cameres del temps": {"country": "ES", "genres": ["Weather"], "languages": ["cat"]},
    "AccuWeather NOW": {"country": "US", "genres": ["Weather", "News"], "languages": ["eng"]},
    "Fox Weather": {"country": "US", "genres": ["Weather", "News"], "languages": ["eng"]},
    "Meteonews": {"country": "CH", "genres": ["Weather"], "languages": ["fra", "deu"]},
    "Sky News Weather": {"country": "GB", "genres": ["Weather", "News"], "languages": ["eng"]},
    "Weathernews": {"country": "JP", "genres": ["Weather"], "languages": ["jpn"]},
    "WeatherSpy (Australia)": {"country": "AU", "genres": ["Weather"], "languages": ["eng"]},

    # Culture
    "Abai TV": {"country": "KZ", "genres": ["Culture"], "languages": ["kaz", "rus"]},
    "Afroculture TV": {"country": "CI", "genres": ["Culture"], "languages": ["fra"]},
    "Andy Haryana": {"country": "IN", "genres": ["Culture"], "languages": ["hin"]},
    "apart TV": {"country": "LU", "genres": ["Culture"], "languages": ["fra", "ltz"]},
    "ART (Russia)": {"country": "RU", "genres": ["Culture"], "languages": ["rus"]},
    "Arte 1": {"country": "BR", "genres": ["Culture"], "languages": ["por"]},
    "BX Arts": {"country": "US", "genres": ["Culture"], "languages": ["eng"]},

    # Education
    "AgroCanal": {"country": "BR", "genres": ["Education"], "languages": ["por"]},
    "Al Alamiya 2": {"country": "SD", "genres": ["Education"], "languages": ["ara"]},
    "Al Hiwar TV [Not 24/7]": {"country": "GB", "genres": ["Education", "News"], "languages": ["ara"]},
    "ARD-alpha": {"country": "DE", "genres": ["Education"], "languages": ["deu"]},

    # Auto
    "30A We Love Cars": {"country": "US", "genres": ["Auto"], "languages": ["eng"]},
    "Avto24": {"country": "RU", "genres": ["Auto"], "languages": ["rus"]},
    "Choppertown": {"country": "US", "genres": ["Auto"], "languages": ["eng"]},
    "City Eden AutoGid [Not 24/7]": {"country": "RU", "genres": ["Auto"], "languages": ["rus"]},
    "Discovery Turbo Latin America": {"country": "US", "genres": ["Auto"], "languages": ["spa"]},
    "Fierro a Fondo TV": {"country": "US", "genres": ["Auto"], "languages": ["spa"]},
    "InTrouble": {"country": "NL", "genres": ["Auto", "Sports"], "languages": ["eng", "nld"]},

    # Comedy
    "30A Ridiculous TV": {"country": "US", "genres": ["Comedy"], "languages": ["eng"]},
    "Anger Management Channel": {"country": "US", "genres": ["Comedy"], "languages": ["eng"]}
}


def get_or_create_country(code: str, name: str) -> Country:
    country = Country.query.get(code)
    if not country:
        country = Country(code=code, name=name)
        db.session.add(country)
        db.session.flush()
    return country


def get_or_create_genre(genre_name: str) -> Genre:
    slug = genre_name.strip().lower().replace(" ", "-").replace("&", "and")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    genre = Genre.query.filter_by(slug=slug).first()
    if not genre:
        genre = Genre(slug=slug, name=genre_name.strip().title())
        db.session.add(genre)
        db.session.flush()
    return genre


def get_or_create_language(code: str, name: str) -> Language:
    lang = Language.query.get(code)
    if not lang:
        lang = Language(code=code, name=name)
        db.session.add(lang)
        db.session.flush()
    return lang


def retag_database():
    """Update all channels in SQLite database with verified taxonomies."""
    app = create_app()
    with app.app_context():
        # Pre-seed taxonomy models
        for code, name in COUNTRY_DEFINITIONS.items():
            get_or_create_country(code, name)
        for code, name in LANGUAGE_DEFINITIONS.items():
            get_or_create_language(code, name)
        db.session.commit()

        channels = Channel.query.all()
        tagged_count = 0

        for ch in channels:
            meta = CHANNEL_METADATA_MAP.get(ch.name)
            if not meta:
                # Fallback: parse from external_id
                ext = ch.external_id or ""
                c_m = re.search(r'\.([a-z]{2})(?:@[a-zA-Z0-9]+)?$', ext)
                raw_c = c_m.group(1).upper() if c_m else "US"
                c_code = "GB" if raw_c == "UK" else raw_c
                meta = {
                    "country": c_code,
                    "genres": [g.name for g in ch.genres] or ["General"],
                    "languages": ["eng"]
                }

            # 1. Update Country
            c_code = meta["country"]
            c_name = COUNTRY_DEFINITIONS.get(c_code, c_code)
            country_obj = get_or_create_country(c_code, c_name)
            ch.country_code = country_obj.code
            ch.country = country_obj

            # 2. Update Genres
            genre_objs = []
            for g_name in meta["genres"]:
                g_obj = get_or_create_genre(g_name)
                if g_obj not in genre_objs:
                    genre_objs.append(g_obj)
            ch.genres = genre_objs

            # 3. Update Languages
            lang_objs = []
            for l_code in meta["languages"]:
                l_name = LANGUAGE_DEFINITIONS.get(l_code, l_code.capitalize())
                l_obj = get_or_create_language(l_code, l_name)
                if l_obj not in lang_objs:
                    lang_objs.append(l_obj)
            ch.languages = lang_objs

            tagged_count += 1

        db.session.commit()
        ChannelService.invalidate_filter_cache()
        print(f"Successfully re-tagged {tagged_count} channels in database.")


def retag_m3u_file():
    """Rewrite data/curated_fta_channels.m3u with explicit tvg-country and tvg-language attributes."""
    m3u_path = BASE_DIR / "data" / "curated_fta_channels.m3u"
    if not m3u_path.exists():
        print("Curated playlist not found.")
        return

    content = m3u_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = ["#EXTM3U"]
    current_extinf = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#EXTM3U"):
            continue

        if stripped.startswith("#EXTINF:"):
            # Extract channel title after last comma
            comma_idx = stripped.rfind(",")
            title = stripped[comma_idx + 1:].strip() if comma_idx != -1 else ""

            meta = CHANNEL_METADATA_MAP.get(title)
            country = meta["country"] if meta else "US"
            lang = meta["languages"][0] if meta and meta["languages"] else "eng"
            group = meta["genres"][0] if meta and meta["genres"] else "General"

            # Parse existing attributes
            id_m = re.search(r'tvg-id="([^"]*)"', stripped)
            name_m = re.search(r'tvg-name="([^"]*)"', stripped)
            logo_m = re.search(r'tvg-logo="([^"]*)"', stripped)

            tvg_id = id_m.group(1) if id_m else ""
            tvg_name = name_m.group(1) if name_m else title
            logo_part = f' tvg-logo="{logo_m.group(1)}"' if logo_m else ""

            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}"{logo_part} tvg-country="{country}" tvg-language="{lang}" group-title="{group}",{title}'
            current_extinf = extinf
        elif not stripped.startswith("#") and current_extinf:
            new_lines.append(current_extinf)
            new_lines.append(stripped)
            current_extinf = None

    m3u_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Successfully re-tagged {len(new_lines) // 2} streams in {m3u_path}.")


if __name__ == "__main__":
    retag_database()
    retag_m3u_file()
