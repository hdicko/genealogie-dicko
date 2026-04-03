#!/usr/bin/env python3
"""
API locale pour l'arbre généalogique Dicko.
Usage : python3 scripts/api_server.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from http.server import HTTPServer
from genealogie.handlers import GenealogieHandler

if __name__ == "__main__":
    port = 1315
    server = HTTPServer(("127.0.0.1", port), GenealogieHandler)
    print(f"🌳 API généalogie démarrée sur http://localhost:{port}")
    print(f"   PATCH  http://localhost:{port}/api/person/I1")
    print(f"   POST   http://localhost:{port}/api/photo/I1")
    print(f"   DELETE http://localhost:{port}/api/photo/I1")
    print("   Ctrl+C pour arrêter\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
