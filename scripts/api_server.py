#!/usr/bin/env python3
"""
API locale pour l'arbre généalogique Dicko.
Usage : python3 scripts/api_server.py
"""
# Note 1: sys.path.insert(0, ...) ensures the 'genealogie' package located in
# the same directory as this script (scripts/) is importable regardless of the
# working directory from which Python is invoked.
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Note 2: http.server.HTTPServer is Python's built-in single-threaded HTTP
# server. It is adequate for local development use (one developer, low load)
# but should never be exposed to the public internet.
from http.server import HTTPServer
from genealogie.handlers import GenealogieHandler

if __name__ == "__main__":
    # Note 3: Binding to 127.0.0.1 (loopback) rather than 0.0.0.0 ensures the
    # server only accepts connections from the local machine. Binding to 0.0.0.0
    # would expose it on all network interfaces including LAN and Wi-Fi.
    port = 1315
    server = HTTPServer(("127.0.0.1", port), GenealogieHandler)
    print(f"🌳 API généalogie démarrée sur http://localhost:{port}")
    print(f"   PATCH  http://localhost:{port}/api/person/I1")
    print(f"   POST   http://localhost:{port}/api/photo/I1")
    print(f"   DELETE http://localhost:{port}/api/photo/I1")
    print("   Ctrl+C pour arrêter\n")
    try:
        # Note 4: serve_forever() runs a select() loop, dispatching each
        # incoming request to GenealogieHandler.handle_one_request() in the
        # same thread. For this single-user local tool, no threading is needed.
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
