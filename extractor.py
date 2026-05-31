import os
import re
import json
import requests
from urllib.parse import urlencode, parse_qs, urlparse, urlunparse

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

EMBED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

PLAYLIST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "it,en;q=0.9,ru;q=0.8,es;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def extract_json_block(html: str, var_name: str):
    """Estrae un blocco JSON assegnato a una variabile globale window.<var>."""
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
    """Recupera il titolo da TMDB tramite IMDB ID."""
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
        resp.raise_for_status()
    except Exception as e:
        print(f"[_resolve_stream] Errore API vixsrc.to con ID {id_val}: {e}")
        return None

    data = resp.json()
    print(f"[_resolve_stream] Risposta API: {json.dumps(data, indent=2)}")

    src = data.get("src")
    if not src:
        print(f"[_resolve_stream] Campo 'src' mancante nella risposta API")
        return None

    embed_path = src if src.startswith("/") else "/" + src
    embed_url = f"https://vixsrc.to{embed_path}"
    print(f"[_resolve_stream] Embed URL: {embed_url}")

    # 2. Pagina embed
    try:
        resp = session.get(embed_url, headers={**EMBED_HEADERS, "Referer": embed_url}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[_resolve_stream] Errore embed page: {e}")
        return None

    html = resp.text
    print(f"[_resolve_stream] HTML embed length: {len(html)}")

    # Estrae window.streams
    streams_block = extract_json_block(html, "streams")
    if not streams_block:
        print(f"[_resolve_stream] window.streams non trovato, abort")
        return None
    try:
        streams = json.loads(streams_block.replace("\\/", "/"))
        print(f"[_resolve_stream] Server trovati: {len(streams)}")
    except json.JSONDecodeError as e:
        print(f"[_resolve_stream] Errore parsing window.streams: {e}")
        return None

    chosen_server = None
    for s in streams:
        if s.get("active"):
            chosen_server = s
            break
    if not chosen_server:
        chosen_server = streams[0]
    server_url = chosen_server["url"]
    print(f"[_resolve_stream] Server scelto: {chosen_server.get('name')} -> {server_url}")

    # Estrae window.masterPlaylist
    master_block = extract_json_block(html, "masterPlaylist")
    if not master_block:
        print(f"[_resolve_stream] window.masterPlaylist non trovato, abort")
        return None
    token = re.search(r"'token':\s*'([^']+)'", master_block)
    expires = re.search(r"'expires':\s*'([^']+)'", master_block)
    asn = re.search(r"'asn':\s*'([^']*)'", master_block)
    print(f"[_resolve_stream] masterPlaylist -> token={token.group(1) if token else 'MISSING'}, expires={expires.group(1) if expires else 'MISSING'}, asn={asn.group(1) if asn else 'MISSING'}")
    if not token or not expires:
        print(f"[_resolve_stream] Token o expires mancanti, abort")
        return None

    params = {
        "token": token.group(1),
        "expires": expires.group(1),
        "asn": asn.group(1) if asn else "",
    }
    if "canPlayFHD=1" in embed_url:
        params["h"] = "1"
        print(f"[_resolve_stream] Aggiunto parametro h=1 (canPlayFHD)")

    parsed = urlparse(server_url)
    existing_qs = parse_qs(parsed.query)
    existing_qs.update({k: [v] for k, v in params.items()})
    new_query = urlencode(existing_qs, doseq=True)
    playlist_url = urlunparse(parsed._replace(query=new_query))
    print(f"[_resolve_stream] Playlist URL: {playlist_url}")

    # 3. Scarica il master M3U8
    try:
        resp = session.get(playlist_url, headers={**PLAYLIST_HEADERS, "Referer": embed_url}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[_resolve_stream] Errore download playlist: {e}")
        return None

    print(f"[_resolve_stream] Playlist status: {resp.status_code}, length: {len(resp.text)}")
    m3u8 = resp.text
    if not m3u8.startswith("#EXTM3U"):
        print(f"[_resolve_stream] Risposta playlist non e' un M3U8 valido (inizio: {resp.text[:200]})")
        return None

    # 4. Parsa il M3U8 per trovare la risoluzione massima
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
    for v in video_variants:
        print(f"  - {v['height']}p (bw={v['bandwidth']}) url={v['url']}")

    if not video_variants:
        print(f"[_resolve_stream] Nessuna variante video trovata nel M3U8")
        return None

    best = max(video_variants, key=lambda v: v["height"])
    print(f"[_resolve_stream] Variante scelta: {best['height']}p -> {best['url']}")

    display_title = f"{title} - {best['height']}p" if title else f"VixSrc {best['height']}p"

    stream_info = {
        "url": playlist_url,
        "title": display_title,
        "type": "hls",
        "behaviorHints": {
            "notWebReady": False,
            "proxyHeaders": {
                "request": {
                    "Referer": embed_url,
                    "User-Agent": DEFAULT_HEADERS["User-Agent"],
                }
            }
        }
    }
    print(f"[_resolve_stream] Stream finale: {json.dumps(stream_info, indent=2)}")
    return stream_info


def get_vixsrc_stream(imdb_id: str, content_type: str, season: int = None, episode: int = None):
    """
    Estrae lo stream da vixsrc.to per un dato contenuto.
    Ritorna un dict con url, title, behaviourHints oppure None.
    """
    print(f"[get_vixsrc_stream] Richiesta: imdb_id={imdb_id}, type={content_type}, season={season}, episode={episode}")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    title = fetch_title(imdb_id, content_type, season, episode)
    print(f"[get_vixsrc_stream] Titolo TMDB: {title}")

    print(f"[get_vixsrc_stream] Provo vixsrc con IMDB ID: {imdb_id}")
    stream = _resolve_stream(session, content_type, imdb_id, season, episode, title=title)
    if stream:
        print(f"[get_vixsrc_stream] Stream trovato con IMDB ID")
        return stream

    print(f"[get_vixsrc_stream] Nessuno stream trovato per {imdb_id}")
    return None
