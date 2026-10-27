"""Offline SDK and image checks: no API billing, database writes or publishing.

Run: python -m unittest discover -s tests -v
"""

import importlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from google import genai
from google.genai import types
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DependencyCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(patch.dict(os.environ, {
            "GOOGLE_API_KEY": "offline-test-key",
            "GEMINI_API_KEY": "",
            "GOOGLE_GENAI_USE_VERTEXAI": "false",
        }))
        cls.enterClassContext(patch("dotenv.load_dotenv", return_value=False))
        cls.enterClassContext(patch.object(
            socket.socket, "connect", side_effect=AssertionError("Network disabled")
        ))
        cls.enterClassContext(patch("nltk.download", return_value=True))
        cls.brain = importlib.import_module("brain")
        cls.addClassCleanup(cls.brain.client.close)
        cls.weekly = importlib.import_module("weekly_digest")
        cls.parser = importlib.import_module("auto_parser")
        cls.reels = importlib.import_module("reels_generator")

    def use_sdk(self, replies):
        pending = iter(replies)
        self.requests = []

        def handle(request):
            self.requests.append(request)
            status, text = next(pending)
            if status != 200:
                return httpx.Response(status, json={
                    "error": {"code": status, "message": "offline error"}
                })
            return httpx.Response(200, json={
                "candidates": [{
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "finishReason": "STOP",
                }]
            })

        client = genai.Client(
            api_key="offline-test-key",
            http_options=types.HttpOptions(
                client_args={"transport": httpx.MockTransport(handle)},
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.addCleanup(client.close)
        self.enterContext(patch.object(self.brain, "client", client))

    def test_summary_uses_real_sdk_and_preserves_ukrainian_html(self):
        self.use_sdk([(200, "[TITLE]: Новини Škoda\n📌 Суть: Нова Octavia.\n"
                       "💡 Вердикт Агента Софії: Гарний вибір.\n"
                       "[QUESTION]: Яку модель оберете?")])
        result = self.brain.summarize_text("Тестова стаття", "News")
        self.assertIn("[TITLE]: Новини Škoda", result)
        self.assertIn("<b>Octavia</b>", result)
        self.assertIn("<blockquote expandable>", result)
        self.assertIn("<i>Яку модель оберете?</i>", result)
        request = self.requests[0]
        self.assertIn("gemini-flash-lite-latest:generateContent", request.url.path)
        body = json.loads(request.content)
        self.assertIn("Тестова стаття", body["contents"][0]["parts"][0]["text"])

    def test_summary_model_fallback(self):
        self.use_sdk([(400, ""), (200, "[TITLE]: Новина\nСуть: Текст")])
        self.assertIn("[TITLE]: Новина", self.brain.summarize_text("text", "title"))
        self.assertEqual(len(self.requests), 2)
        self.assertIn("gemini-3.1-flash-lite-preview", self.requests[1].url.path)

    def test_summary_keeps_failure_result(self):
        self.use_sdk([(400, ""), (400, ""), (400, "")])
        self.assertEqual(self.brain.summarize_text("text", "title"), "⚠️ Помилка ШІ.")
        self.assertEqual(len(self.requests), 3)

    def test_weekly_selection(self):
        headlines = [{"title": f"Новина {i}", "url": f"https://example.invalid/{i}"}
                     for i in range(1, 8)]
        selection = [{"index": i, "why": "Важливо для України"} for i in range(1, 8)]
        self.use_sdk([(200, json.dumps(selection, ensure_ascii=False))])
        result = self.weekly.pick_top7_with_gemini(headlines)
        self.assertEqual([item["url"] for item in result],
                         [item["url"] for item in headlines])
        self.assertEqual(result[0]["why"], "Важливо для України")

    def test_weekly_verdict(self):
        self.use_sdk([(200, "**Тиждень змін.**")])
        self.assertEqual(self.weekly.get_weekly_verdict([{"title": "Новина"}]),
                         "Тиждень змін.")

    def test_evening_message_without_publishing(self):
        self.use_sdk([(200, "Спокійної ночі зі Škoda.")])
        with patch.object(self.parser, "was_task_done_today", return_value=False), \
             patch.object(self.parser, "mark_task_done") as mark, \
             patch.object(self.parser.telegram_bot, "send_telegram_message",
                          return_value=True) as send:
            self.parser.send_evening_message()
        self.assertIn("Спокійної ночі зі Škoda.", send.call_args.kwargs["text"])
        mark.assert_called_once_with(self.parser.EVENING_DATE_KEY)
        self.assertEqual(len(self.requests), 1)

    def test_all_overlay_types_preserve_png_dimensions_and_transparency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                self.reels.create_title_overlay("Новини Škoda в Україні", root / "title.png"),
                self.reels.create_fact_overlay("Новий електромобіль", root / "fact.png"),
                self.reels.create_watermark_overlay(root / "watermark.png"),
            ]
            for path in paths:
                with self.subTest(path=path.name), Image.open(path) as image:
                    image.load()
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, (1080, 1920))
                    self.assertEqual(image.mode, "RGBA")
                    alpha = image.getchannel("A")
                    self.assertEqual(alpha.getextrema()[0], 0)
                    self.assertGreater(alpha.getextrema()[1], 0)

    def test_newspaper_image_dimensions_with_updated_pillow(self):
        from newspaper import images
        buffer = io.BytesIO()
        Image.new("RGB", (320, 240)).save(buffer, format="PNG")
        raw = io.BytesIO(buffer.getvalue())
        raw._connection = None
        response = type("Response", (), {
            "raw": raw, "headers": {"Content-Type": "image/png"}
        })()
        with patch.object(images.requests, "get", return_value=response):
            self.assertEqual(images.fetch_image_dimension("https://example.invalid/photo.png", "offline-test"),
                             (320, 240))

    def test_xbm_redos_inputs_are_rejected_within_timeout(self):
        # GHSA-xgh8-jp6q-p5x8: test public Image.open and streaming Parser paths.
        # A child process bounds runtime even if a vulnerable version is installed.
        code = """
import io
from PIL import Image, ImageFile, UnidentifiedImageError
control = io.BytesIO()
Image.new('1', (8, 1)).save(control, format='XBM')
with Image.open(io.BytesIO(control.getvalue())) as image:
    image.load()
    assert image.size == (8, 1)
for newline in (b'\\r', b'\\n'):
    data = b''.join(b'#define' + b' ' * 60 + name + newline
                    for name in (b'_width 1', b'_height 1', b'_x_hot 1', b'_y_hot 1'))
    data += newline * 59 + b'_bits'
    data = data.ljust(512, b'A')
    try:
        Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, ValueError):
        pass
    else:
        raise AssertionError('Malformed XBM accepted')
    parser = ImageFile.Parser()
    try:
        parser.feed(data)
    except ValueError:
        pass
    assert parser.image is None
print('XBM control and both malformed variants passed')
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("both malformed variants passed", result.stdout)

    def test_mcidas_short_stride_cannot_load_past_file(self):
        # CVE-2026-54058: a tiny file must not map a much wider image row.
        code = """
import struct
import tempfile
from pathlib import Path
from PIL import Image
words = [0] * 64
words[1] = 4
words[8] = 1
words[9] = 1024
words[10] = 1
words[14] = 1
words[33] = 256
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'short-stride.area'
    path.write_bytes(struct.pack('!64i', *words) + b'\\0A')
    with Image.open(path) as image:
        try:
            image.load()
        except (OSError, ValueError):
            pass
        else:
            raise AssertionError('Image exceeds file-backed storage')
print('Short-stride McIdas input rejected')
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Short-stride McIdas input rejected", result.stdout)


if __name__ == "__main__":
    unittest.main()
