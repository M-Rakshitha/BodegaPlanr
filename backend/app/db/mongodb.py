from __future__ import annotations

import os
from functools import lru_cache

import certifi
from pymongo import MongoClient
from pymongo.collection import Collection


@lru_cache(maxsize=1)
def _client() -> MongoClient:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set in environment variables.")
    # certifi provides up-to-date CA certs; required on macOS Python 3.x
    return MongoClient(uri, tlsCAFile=certifi.where())


def _db():
    return _client()["bodegaplanr"]


def get_reports_col() -> Collection:
    return _db()["reports"]


def get_chunks_col() -> Collection:
    return _db()["chunks"]
