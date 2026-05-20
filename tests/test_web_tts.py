"""Tests for TTS web routes."""

import os

from anti_fraud_explorer.config import settings
from anti_fraud_explorer.web.web import create_app


def test_tts_latest_returns_newest_file(tmp_path):
    original_cache_dir = settings.tts_cache_dir
    settings.tts_cache_dir = tmp_path
    try:
        older = tmp_path / ("a" * 64 + ".mp3")
        newer = tmp_path / ("b" * 64 + ".mp3")
        ignored = tmp_path / "latest.mp3"
        older.write_bytes(b"older-audio")
        newer.write_bytes(b"newer-audio")
        ignored.write_bytes(b"ignored")
        os.utime(older, (1, 1))
        os.utime(newer, (2, 2))

        client = create_app().test_client()
        response = client.get("/api/tts/latest")

        assert response.status_code == 200
        assert response.mimetype == "audio/mpeg"
        assert response.data == b"newer-audio"
    finally:
        settings.tts_cache_dir = original_cache_dir


def test_tts_latest_404_when_cache_is_empty(tmp_path):
    original_cache_dir = settings.tts_cache_dir
    settings.tts_cache_dir = tmp_path
    try:
        client = create_app().test_client()
        response = client.get("/api/tts/latest")

        assert response.status_code == 404
    finally:
        settings.tts_cache_dir = original_cache_dir
