import os
import re
import json
import uuid
import requests
from urllib.parse import urlencode, parse_qs, urlparse, urlunparse

# Cache per M3U8 filtrati (key -> filtered M3U8 string)
_m3u8_cache = {}

TMDB_API_KEY = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJmNzc4ZmIxZTZlYzNmZWI0Mjc3NjI2ZmY3ODBjYmJlOSIsIm5iZiI6MTc2MjMzODYxMC4zNTgsInN1YiI6IjY5MGIyNzMyODljNzRlYTZmMjRiZDAzMCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.G3m-bKQsA9WRzqHAAuGtlOI3qN-CAxHLfLdyzzCh72k'

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Origin": "https://vixsrc.to",
    "Referer": "https://vixsrc.to/",
}

EMBED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

PLAYLIST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Origin": "https://vixsrc.to",
}


def extract_json_block(html: str, var_name: str):
    prefix = f"window.{var_name} = "
    start = html.find(prefix)
    if start == -1:
        print(f"[extract_json_block] window.{var_name} non trovato nel HTML")
        return None
    start += len(prefix)
    end = html.find(";", start)
    if end == -1:
        print(f"[extract_json_block] ';' non trovato dopo window.{var_name}")
        return None
    return html[start:end].strip()


def fetch_title(imdb_id: str, content_type: str, season=None, episode=None):
    if not TMDB_API_KEY:
        return None
    url = f"https://api.themoviedb.org/3/find/{imdb_id}"
    headers = {}
    params = {"external_source": "imdb_id"}
    if TMDB_API_KEY.startswith("ey"):
        headers = {"Authorization": f"Bearer {TMDB_API_KEY}"}
    else:
        params["api_key"] = TMDB_API_KEY
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if content_type == "movie":
            results = data.get("movie_results", [])
            if results:
                return results[0].get("title")
        else:
            results = data.get("tv_results", [])
            if results:
                name = results[0].get("name")
                if name and season is not None and episode is not None:
                    return f"{name} S{season:02d}E{episode:02d}"
                return name
    except Exception as e:
        print(f"[fetch_title] Errore: {e}")
    return None


def _warmup_session(session):
    try:
        print("[_warmup_session] Warming up sessione su vixsrc.to...")
        resp = session.get("https://vixsrc.to", timeout=15)
        print(f"[_warmup_session] Home status: {resp.status_code}, cookies: {session.cookies.get_dict()}")
    except Exception as e:
        print(f"[_warmup_session] Errore warm-up: {e}")


def filter_m3u8(m3u8_text):
    """Filtra il master M3U8: solo audio ita, solo variante video max resolution, niente sottotitoli."""
    lines = m3u8_text.splitlines()

    # Trova l'indice della variante con la massima risoluzione
    best_idx = -1
    best_height = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#EXT-X-STREAM-INF:"):
            m = re.search(r'RESOLUTION=(\d+)x(\d+)', stripped)
            if m:
                h = int(m.group(2))
                if h > best_height:
                    best_height = h
                    best_idx = i

    filtered = []
    skip_url = False  # True se la prossima riga URL va saltata
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Rimuovi sottotitoli
        if stripped.startswith("#EXT-X-MEDIA:TYPE=SUBTITLES"):
            continue
        # Mantieni SOLO audio italiano
        if stripped.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
            if 'LANGUAGE="ita"' in stripped:
                filtered.append(line)
            continue
        # Gestisci varianti video
        if stripped.startswith("#EXT-X-STREAM-INF:"):
            if i == best_idx:
                # Rimuovi AUDIO= e SUBTITLES= per evitare riferimenti a gruppi rimossi
                cleaned = re.sub(r',AUDIO="[^"]*"', '', stripped)
                cleaned = re.sub(r',SUBTITLES="[^"]*"', '', cleaned)
                filtered.append(cleaned)
                skip_url = False
            else:
                skip_url = True
            continue
        # Salta la riga URL se appartiene a una variante scartata
        if skip_url and stripped and not stripped.startswith("#"):
            skip_url = False
            continue
        filtered.append(line)
    return "\n".join(filtered)


def _resolve_stream(session, content_type, id_val, season, episode, title=None):
    if content_type == "series":
        api_url = f"https://vixsrc.to/api/tv/{id_val}/{season}/{episode}"
        referer = f"https://vixsrc.to/tv/{id_val}/{season}/{episode}"
    else:
        api_url = f"https://vixsrc.to/api/movie/{id_val}"
        referer = f"https://vixsrc.to/movie/{id_val}"

    print(f"[_resolve_stream] API URL: {api_url}")

    try:
        resp = session.get(api_url, headers={"Referer": referer}, timeout=15)
        print(f"[_resolve_stream] API status: {resp.status_code}")
        resp.raise_for_status()
    except Exception as e:
        print(f"[_resolve_stream] Errore API vixsrc.to con ID {id_val}: {e}")
        return []

    try:
        data = resp.json()
    except Exception as e:
        print(f"[_resolve_stream] Errore parsing JSON risposta API: {e}")
        print(f"[_resolve_stream] Body grezzo: {resp.text[:500]}")
        return []

    print(f"[_resolve_stream] Risposta API: {json.dumps(data, indent=2)}")

    src = data.get("src")
    if not src:
        print(f"[_resolve_stream] Campo 'src' mancante nella risposta API")
        return []

    embed_path = src if src.startswith("/") else "/" + src
    embed_url = f"https://vixsrc.to{embed_path}"
    print(f"[_resolve_stream] Embed URL: {embed_url}")

    try:
        resp = session.get(embed_url, headers={**EMBED_HEADERS, "Referer": embed_url}, timeout=15)
        print(f"[_resolve_stream] Embed status: {resp.status_code}")
        resp.raise_for_status()
    except Exception as e:
        print(f"[_resolve_stream] Errore embed page: {e}")
        return []

    html = resp.text
    print(f"[_resolve_stream] HTML embed length: {len(html)}")

    streams_block = extract_json_block(html, "streams")
    if not streams_block:
        print(f"[_resolve_stream] window.streams non trovato, abort")
        return []
    try:
        streams = json.loads(streams_block.replace("\\/", "/"))
        print(f"[_resolve_stream] Server trovati: {len(streams)}")
    except json.JSONDecodeError as e:
        print(f"[_resolve_stream] Errore parsing window.streams: {e}")
        return []

    master_block = extract_json_block(html, "masterPlaylist")
    if not master_block:
        print(f"[_resolve_stream] window.masterPlaylist non trovato, abort")
        return []
    token = re.search(r"'token':\s*'([^']+)'", master_block)
    expires = re.search(r"'expires':\s*'([^']+)'", master_block)
    asn = re.search(r"'asn':\s*'([^']*)'", master_block)
    mp_url_match = re.search(r"url:\s*'([^']+)'", master_block)
    print(f"[_resolve_stream] masterPlaylist -> token={token.group(1) if token else 'MISSING'}, expires={expires.group(1) if expires else 'MISSING'}, asn={asn.group(1) if asn else 'MISSING'}, url={mp_url_match.group(1) if mp_url_match else 'MISSING'}")
    if not token or not expires:
        print(f"[_resolve_stream] Token o expires mancanti, abort")
        return []

    # Use masterPlaylist.url as base (like the browser does), not window.streams URLs
    playlist_base = mp_url_match.group(1) if mp_url_match else streams[0]["url"].split("?")[0]
    print(f"[_resolve_stream] Playlist base URL: {playlist_base}")

    # Extract lang from embed URL (browser uses the same lang as the embed page)
    embed_parsed = parse_qs(urlparse(embed_url).query)
    lang = embed_parsed.get("lang", ["en"])[0]

    base_params = {
        "token": token.group(1),
        "expires": expires.group(1),
        "lang": lang,
    }
    asn_val = asn.group(1) if asn else ""
    if asn_val:
        base_params["asn"] = asn_val
    if "canPlayFHD=1" in embed_url:
        base_params["h"] = "1"
    print(f"[_resolve_stream] Base params: {base_params}")

    stream_list = []
    seen_urls = set()
    for s in streams:
        server_name = s.get("name", "VixSrc")

        # Build clean playlist URL exactly like the browser:
        # masterPlaylist.url + masterPlaylist.params + h + lang
        # NO server-specific params (ub=1, ab=1) — those are only for HEAD health checks
        params = dict(base_params)

        new_query = urlencode(params, doseq=True)
        playlist_url = f"{playlist_base}?{new_query}"

        # Deduplicate: if same URL already returned, skip
        if playlist_url in seen_urls:
            print(f"[_resolve_stream] URL duplicato per {server_name}, skip")
            continue
        seen_urls.add(playlist_url)

        print(f"[_resolve_stream] Provo server: {server_name} -> {playlist_url}")

        try:
            resp = session.get(playlist_url, headers={**PLAYLIST_HEADERS, "Referer": embed_url}, timeout=15)
            print(f"[_resolve_stream] Playlist status: {resp.status_code}")
            resp.raise_for_status()
        except Exception as e:
            print(f"[_resolve_stream] Errore download playlist per {server_name}: {e}")
            continue

        m3u8 = resp.text
        print(f"[_resolve_stream] Playlist length: {len(m3u8)}")
        if not m3u8.startswith("#EXTM3U"):
            preview = m3u8[:200] if len(m3u8) > 200 else m3u8
            print(f"[_resolve_stream] Risposta playlist non e' un M3U8 valido (inizio: {preview})")
            continue

        video_variants = []
        lines = m3u8.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                bandwidth_match = re.search(r'BANDWIDTH=(\d+)', line)
                resolution_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                bandwidth = int(bandwidth_match.group(1)) if bandwidth_match else 0
                height = int(resolution_match.group(2)) if resolution_match else 0
                i += 1
                url = lines[i].strip() if i < len(lines) else None
                video_variants.append({"bandwidth": bandwidth, "height": height, "url": url})
            i += 1

        print(f"[_resolve_stream] Varianti video trovate: {len(video_variants)}")
        # Filtra il M3U8 per rimuovere sottotitoli (causano blocco parser Stremio)
        filtered_m3u8 = filter_m3u8(m3u8)
        print(f"[_resolve_stream] M3U8 filtrato: {len(filtered_m3u8)} chars (da {len(m3u8)})")

        # Trova la qualita migliore per il titolo
        best_height = 0
        for line in m3u8.splitlines():
            if line.startswith("#EXT-X-STREAM-INF:"):
                m = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                if m:
                    best_height = max(best_height, int(m.group(2)))

        display_title = f"{title} - {server_name} {best_height}p" if title else f"{server_name} {best_height}p"

        # Salva M3U8 filtrato in cache e restituisci URL al nostro endpoint
        cache_key = str(uuid.uuid4())[:12]
        _m3u8_cache[cache_key] = filtered_m3u8
        print(f"[_resolve_stream] M3U8 cached with key: {cache_key}")

        stream_info = {
            "url": f"/m3u8/{cache_key}.m3u8",
            "title": display_title,
            "type": "hls",
            "behaviorHints": {
                "notWebReady": False,
            }
        }
        print(f"[_resolve_stream] Stream finale: {json.dumps(stream_info, indent=2)}")
        stream_list.append(stream_info)

    return stream_list


def get_vixsrc_stream(imdb_id: str, content_type: str, season: int = None, episode: int = None):
    print(f"[get_vixsrc_stream] Richiesta: imdb_id={imdb_id}, type={content_type}, season={season}, episode={episode}")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    _warmup_session(session)

    title = fetch_title(imdb_id, content_type, season, episode)
    print(f"[get_vixsrc_stream] Titolo TMDB: {title}")

    print(f"[get_vixsrc_stream] Provo vixsrc con IMDB ID: {imdb_id}")
    streams = _resolve_stream(session, content_type, imdb_id, season, episode, title=title)
    if streams:
        print(f"[get_vixsrc_stream] Trovati {len(streams)} stream con IMDB ID")
        return streams

    print(f"[get_vixsrc_stream] Nessuno stream trovato per {imdb_id}")
    return []
