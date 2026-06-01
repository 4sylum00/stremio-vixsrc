import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from extractor import get_vixsrc_stream, _m3u8_cache

app = Flask(__name__)
CORS(app)

MANIFEST = {
    "id": "org.vixsrc.stremio",
    "version": "1.0.0",
    "name": "VixSrc",
    "description": "Addon Stremio per VixSrc",
    "logo": "https://vixsrc.to/favicon.ico",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": [],
    "behaviorHints": {
        "configurable": True,
        "configurationRequired": False
    }
}

@app.route("/manifest.json")
def manifest():
    return jsonify(MANIFEST)

@app.route("/stream/<type>/<path:id>.json")
def stream(type, id):
    print(f"\n[SERVER] ========================================")
    print(f"[SERVER] Nuova richiesta: type={type}, id={id}")
    print(f"[SERVER] User-Agent: {request.headers.get('User-Agent', 'N/A')}")
    parts = id.split(":")
    imdb_id = parts[0]
    season = int(parts[1]) if len(parts) > 1 else None
    episode = int(parts[2]) if len(parts) > 2 else None

    content_type = "series" if type == "series" else "movie"
    print(f"[SERVER] Parsed: imdb_id={imdb_id}, content_type={content_type}, season={season}, episode={episode}")

    try:
        streams = get_vixsrc_stream(imdb_id, content_type, season, episode)
        if streams:
            print(f"[SERVER] Trovati {len(streams)} stream:")
            # Converti URL relative /m3u8/ in assolute
            base = request.host_url.rstrip("/")
            for s in streams:
                url = s["url"]
                if url.startswith("/m3u8/"):
                    s["url"] = f"{base}{url}"
                print(f"  - title: {s['title']}")
                print(f"    url: {s['url'][:120]}...")
            response = {"streams": streams}
            print(f"[SERVER] Response: {json.dumps(response, indent=2)}")
            return jsonify(response)
        else:
            print(f"[SERVER] Nessuno stream trovato per {imdb_id}")
    except Exception as e:
        print(f"[SERVER] ERRORE durante get_vixsrc_stream: {e}")
        import traceback
        traceback.print_exc()

    print(f"[SERVER] Returning empty streams")
    return jsonify({"streams": []})

@app.route("/test/movie/<imdb_id>")
def test_movie(imdb_id):
    print(f"\n[SERVER] TEST movie: {imdb_id}")
    try:
        streams = get_vixsrc_stream(imdb_id, "movie")
        if streams:
            return jsonify({"found": True, "streams": streams})
        return jsonify({"found": False, "error": "Nessuno stream trovato"}), 200
    except Exception as e:
        import traceback
        return jsonify({"found": False, "error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/test/series/<imdb_id>/<int:season>/<int:episode>")
def test_series(imdb_id, season, episode):
    print(f"\n[SERVER] TEST series: {imdb_id} S{season}E{episode}")
    try:
        streams = get_vixsrc_stream(imdb_id, "series", season, episode)
        if streams:
            return jsonify({"found": True, "streams": streams})
        return jsonify({"found": False, "error": "Nessuno stream trovato"}), 200
    except Exception as e:
        import traceback
        return jsonify({"found": False, "error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/m3u8/<key>.m3u8")
def serve_m3u8(key):
    m3u8 = _m3u8_cache.get(key)
    if not m3u8:
        print(f"[SERVER] M3U8 cache miss for key: {key}")
        return jsonify({"error": "Not found"}), 404
    print(f"[SERVER] Serving M3U8 for key: {key} ({len(m3u8)} chars)")
    return Response(m3u8, mimetype="application/vnd.apple.mpegurl")

@app.route("/")
def home():
    return f"""
    <h1>VixSrc Stremio Addon</h1>
    <p>Installa in Stremio: <code>http://{request.host}/manifest.json</code></p>
    <p>Test film: <code>/test/movie/tt0137523</code></p>
    <p>Test serie: <code>/test/series/tt0944947/1/1</code></p>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
