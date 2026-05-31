import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request
from flask_cors import CORS
from extractor import get_vixsrc_stream

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
    # Stremio invia ID nel formato: tt1234567 per film
    # tt1234567:1:1 per serie (id:season:episode)
    parts = id.split(":")
    imdb_id = parts[0]
    season = int(parts[1]) if len(parts) > 1 else None
    episode = int(parts[2]) if len(parts) > 2 else None

    content_type = "series" if type == "series" else "movie"

    stream_data = get_vixsrc_stream(imdb_id, content_type, season, episode)
    if stream_data:
        return jsonify({"streams": [stream_data]})
    return jsonify({"streams": []})

@app.route("/")
def home():
    return f"""
    <h1>VixSrc Stremio Addon</h1>
    <p>Installa in Stremio: <code>http://{request.host}/manifest.json</code></p>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port, debug=False)
