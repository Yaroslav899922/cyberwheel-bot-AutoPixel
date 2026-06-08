from __future__ import annotations

import argparse
import hashlib
import ipaddress
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
DEFAULT_DURATION = 24
MAX_DOWNLOAD_MB = 180
OUTPUT_DIR = Path(os.getenv("REELS_OUTPUT_DIR", "generated_reels"))
TMP_DIR = OUTPUT_DIR / "tmp"
ASSETS_DIR = OUTPUT_DIR / "assets"
ACCENT_BLUE = (0, 168, 255, 255)
WHITE = (255, 255, 255, 255)
SOFT_WHITE = (235, 241, 247, 255)
DARK_CARD = (10, 16, 24, 205)
DARK_CARD_STRONG = (5, 9, 14, 225)


@dataclass
class OverlaySpec:
    path: Path
    start: float
    end: float


class ReelGenerationError(RuntimeError):
    """Помилка генерації AutoPulse Reel."""


# ─────────────────────────────────────────────────────────────────────────────
# БАЗОВІ HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def is_url(value: str) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"}


def validate_public_video_url(video_url: str) -> None:
    """
    Мінімальний SSRF-захист для ручного MVP.

    Блокує localhost/private/link-local/reserved IP. Це важливо, якщо в майбутньому
    URL почнуть приходити не вручну від Ярослава, а з автоматичного джерела.
    """
    parsed = urlparse(video_url)
    if parsed.scheme not in {"http", "https"}:
        raise ReelGenerationError("Підтримуються тільки http/https URL для відео.")

    hostname = parsed.hostname
    if not hostname:
        raise ReelGenerationError("URL відео не містить hostname.")

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ReelGenerationError(f"Не вдалося визначити IP для host {hostname}: {exc}") from exc

    checked_ips = set()
    for address in addresses:
        ip_raw = address[4][0]
        if ip_raw in checked_ips:
            continue
        checked_ips.add(ip_raw)
        try:
            ip = ipaddress.ip_address(ip_raw)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ReelGenerationError(f"Небезпечний або приватний IP для відео URL: {hostname} -> {ip}")


def safe_slug(text: str, max_length: int = 72) -> str:
    """Безпечна назва файлу з підтримкою українських літер."""
    cleaned = re.sub(r"[^\w\s.-]", "", str(text), flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "-", cleaned.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip(".-_")
    if not cleaned:
        cleaned = "autopulse-reel"
    return cleaned[:max_length].strip(".-_") or "autopulse-reel"


def parse_facts(facts: str | Iterable[str] | None) -> list[str]:
    """Приймає список або рядок через кому/крапку з комою/pipe і повертає факти."""
    if not facts:
        return []

    if isinstance(facts, str):
        raw_items = re.split(r"[,;|\n]+", facts)
    else:
        raw_items = []
        for item in facts:
            if item:
                raw_items.extend(re.split(r"[,;|\n]+", str(item)))

    result = []
    for item in raw_items:
        item = re.sub(r"\s+", " ", item).strip()
        if item:
            result.append(item)
    return result


def resolve_ffmpeg() -> str:
    """Повертає шлях до FFmpeg: imageio-ffmpeg або системний ffmpeg."""
    try:
        import imageio_ffmpeg  # type: ignore

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg and Path(ffmpeg).exists():
            return ffmpeg
    except Exception:
        pass

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    raise ReelGenerationError(
        "FFmpeg не знайдено. Додай imageio-ffmpeg у requirements.txt або встанови ffmpeg на сервері."
    )


def resolve_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    """Шукає ffprobe поруч із ffmpeg або в PATH."""
    if ffmpeg_path:
        ffmpeg = Path(ffmpeg_path)
        candidates = []
        if sys.platform.startswith("win"):
            candidates.append(ffmpeg.with_name("ffprobe.exe"))
        candidates.append(ffmpeg.with_name("ffprobe"))
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    return shutil.which("ffprobe")


def run_command(args: list[str], timeout: int = 360) -> subprocess.CompletedProcess:
    process = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if process.returncode != 0:
        cmd_preview = " ".join(str(a) for a in args[:8])
        raise ReelGenerationError(
            f"Команда завершилась з помилкою {process.returncode}: {cmd_preview}\n"
            f"STDERR:\n{process.stderr[-2500:]}"
        )
    return process


# ─────────────────────────────────────────────────────────────────────────────
# ЗАВАНТАЖЕННЯ ТА ПРОБА ВІДЕО
# ─────────────────────────────────────────────────────────────────────────────

def download_video(video_url: str, tmp_dir: Path | None = None, max_mb: int = MAX_DOWNLOAD_MB) -> Path:
    """Завантажує відео з прямого HTTP/HTTPS URL у тимчасову папку."""
    validate_public_video_url(video_url)

    tmp_dir = tmp_dir or TMP_DIR
    tmp_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(video_url)
    url_hash = hashlib.sha1(video_url.encode("utf-8")).hexdigest()[:12]
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".mkv", ".m4v"}:
        suffix = ".mp4"

    target = tmp_dir / f"source_{url_hash}{suffix}"
    partial_target = target.with_suffix(target.suffix + ".part")

    if target.exists() and target.stat().st_size > 0:
        return target

    if partial_target.exists():
        partial_target.unlink()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        )
    }

    max_bytes = max_mb * 1024 * 1024
    downloaded = 0

    try:
        current_url = video_url
        response = None
        for _ in range(6):
            validate_public_video_url(current_url)
            response = requests.get(current_url, headers=headers, stream=True, timeout=30, allow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise ReelGenerationError("Відео URL повернув redirect без Location header.")
                current_url = urljoin(current_url, location)
                continue
            break
        else:
            raise ReelGenerationError("Забагато redirect-ів під час завантаження відео.")

        if response is None:
            raise ReelGenerationError("Не вдалося відкрити відео URL.")

        with response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "text/html" in content_type:
                raise ReelGenerationError(
                    "URL повернув HTML-сторінку, а не відеофайл. Для MVP потрібне пряме посилання на .mp4/.mov/.webm."
                )

            with partial_target.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise ReelGenerationError(f"Відео більше {max_mb} MB — зупиняю завантаження.")
                    file.write(chunk)

        if partial_target.stat().st_size == 0:
            raise ReelGenerationError("Завантажений відеофайл порожній.")

        partial_target.replace(target)
        return target

    except requests.RequestException as exc:
        if partial_target.exists():
            partial_target.unlink()
        raise ReelGenerationError(f"Не вдалося завантажити відео: {exc}") from exc
    except Exception:
        if partial_target.exists():
            partial_target.unlink()
        raise


def resolve_video_source(video_source: str, tmp_dir: Path | None = None) -> Path:
    if is_url(video_source):
        return download_video(video_source, tmp_dir=tmp_dir)

    path = Path(video_source)
    if not path.exists() or not path.is_file():
        raise ReelGenerationError(f"Відеофайл не знайдено: {video_source}")
    return path


def probe_duration(video_path: Path, ffmpeg_path: str | None = None) -> float | None:
    ffprobe = resolve_ffprobe(ffmpeg_path)
    if not ffprobe:
        return None

    try:
        result = run_command(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            timeout=60,
        )
        value = result.stdout.strip()
        return float(value) if value else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ШРИФТИ ТА ГРАФІКА
# ─────────────────────────────────────────────────────────────────────────────

def find_font(bold: bool = False) -> str | None:
    env_key = "REEL_FONT_BOLD_PATH" if bold else "REEL_FONT_PATH"
    env_path = os.getenv(env_key)
    if env_path and Path(env_path).exists():
        return env_path

    candidates = []

    if sys.platform.startswith("win"):
        if bold:
            candidates.extend([
                r"C:\Windows\Fonts\arialbd.ttf",
                r"C:\Windows\Fonts\segoeuib.ttf",
            ])
        candidates.extend([
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
        ])

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ])

    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ])

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    return None


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_path = find_font(bold=bold)
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text).split()
    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        width, _ = measure_text(draw, candidate, font)
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_rounded_rectangle(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def create_title_overlay(title: str, output_path: str | Path, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT) -> Path:
    """Створює прозорий PNG із верхнім заголовком AutoPulse."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    label_font = load_font(34, bold=True)
    title_font = load_font(62, bold=True)

    x = 64
    y = 72
    card_w = width - 128
    padding_x = 34
    padding_y = 26

    title_text = str(title).strip()
    if len(title_text) > 92:
        title_text = title_text[:89].rstrip() + "..."
    title_lines = wrap_text(draw, title_text.upper(), title_font, card_w - padding_x * 2)
    title_lines = title_lines[:3]

    label = "AUTOPULSE NEWS"
    line_gap = 14
    label_w, label_h = measure_text(draw, label, label_font)
    label_box_w = min(card_w - padding_x * 2, label_w + 44)
    title_h = sum(measure_text(draw, line, title_font)[1] for line in title_lines)
    title_h += max(0, len(title_lines) - 1) * line_gap
    card_h = padding_y * 2 + label_h + 20 + title_h

    draw_rounded_rectangle(
        draw,
        (x, y, x + card_w, y + card_h),
        radius=34,
        fill=DARK_CARD_STRONG,
        outline=(255, 255, 255, 35),
        width=2,
    )

    draw.rounded_rectangle((x + padding_x, y + padding_y, x + padding_x + label_box_w, y + padding_y + 46), radius=23, fill=ACCENT_BLUE)
    draw.text((x + padding_x + 22, y + padding_y + 5), label, font=label_font, fill=(4, 12, 18, 255))

    text_y = y + padding_y + 66
    for line in title_lines:
        draw.text((x + padding_x, text_y), line, font=title_font, fill=WHITE)
        _, line_h = measure_text(draw, line, title_font)
        text_y += line_h + line_gap

    image.save(output_path)
    return output_path


def create_fact_overlay(
    fact: str,
    output_path: str | Path,
    index: int = 1,
    total: int = 3,
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
) -> Path:
    """Створює нижню картку з одним коротким фактом/субтитром."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    badge_font = load_font(34, bold=True)
    fact_font = load_font(58, bold=True)

    x = 72
    y = 1290
    card_w = width - 144
    padding_x = 34
    padding_y = 30

    fact_text = str(fact).strip()
    if len(fact_text) > 88:
        fact_text = fact_text[:85].rstrip() + "..."

    fact_lines = wrap_text(draw, fact_text, fact_font, card_w - padding_x * 2)
    fact_lines = fact_lines[:3]
    line_gap = 13
    text_h = sum(measure_text(draw, line, fact_font)[1] for line in fact_lines)
    text_h += max(0, len(fact_lines) - 1) * line_gap
    card_h = padding_y * 2 + 52 + 20 + text_h

    draw_rounded_rectangle(
        draw,
        (x, y, x + card_w, y + card_h),
        radius=34,
        fill=DARK_CARD,
        outline=(255, 255, 255, 30),
        width=2,
    )

    badge = f"{index}/{total}"
    draw.rounded_rectangle((x + padding_x, y + padding_y, x + padding_x + 96, y + padding_y + 52), radius=25, fill=ACCENT_BLUE)
    draw.text((x + padding_x + 22, y + padding_y + 6), badge, font=badge_font, fill=(3, 11, 18, 255))

    small_label = "КОРОТКО"
    draw.text((x + padding_x + 122, y + padding_y + 6), small_label, font=badge_font, fill=SOFT_WHITE)

    text_y = y + padding_y + 76
    for line in fact_lines:
        draw.text((x + padding_x, text_y), line, font=fact_font, fill=WHITE)
        _, line_h = measure_text(draw, line, fact_font)
        text_y += line_h + line_gap

    image.save(output_path)
    return output_path


def create_watermark_overlay(output_path: str | Path, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    font = load_font(34, bold=True)
    text = "AutoPulse"
    text_w, text_h = measure_text(draw, text, font)
    x = width - text_w - 74
    y = height - text_h - 74

    draw_rounded_rectangle(
        draw,
        (x - 24, y - 12, x + text_w + 24, y + text_h + 18),
        radius=22,
        fill=(5, 10, 16, 160),
        outline=(255, 255, 255, 25),
        width=1,
    )
    draw.text((x, y), "Auto", font=font, fill=WHITE)
    auto_w, _ = measure_text(draw, "Auto", font)
    draw.text((x + auto_w, y), "Pulse", font=font, fill=ACCENT_BLUE)

    image.save(output_path)
    return output_path


def build_overlays(title: str, facts: list[str], tmp_dir: Path, duration: float) -> list[OverlaySpec]:
    tmp_dir.mkdir(parents=True, exist_ok=True)

    overlays: list[OverlaySpec] = []

    title_path = create_title_overlay(title, tmp_dir / "title_overlay.png")
    overlays.append(OverlaySpec(title_path, 0.0, duration))

    clean_facts = facts[:3]
    if not clean_facts:
        clean_facts = ["Коротко про головне", "Без води та зайвих слів", "Більше — в AutoPulse"]

    usable_start = 3.0
    usable_end = max(duration - 2.0, usable_start + len(clean_facts))
    slot = max(2.5, (usable_end - usable_start) / len(clean_facts))

    for idx, fact in enumerate(clean_facts, start=1):
        start = usable_start + (idx - 1) * slot
        end = min(duration, start + slot + 0.35)
        fact_path = create_fact_overlay(fact, tmp_dir / f"fact_{idx}.png", index=idx, total=len(clean_facts))
        overlays.append(OverlaySpec(fact_path, start, end))

    watermark_path = create_watermark_overlay(tmp_dir / "watermark.png")
    overlays.append(OverlaySpec(watermark_path, 0.0, duration))

    return overlays


# ─────────────────────────────────────────────────────────────────────────────
# ВІДЕОРЕНДЕР
# ─────────────────────────────────────────────────────────────────────────────

def find_music_file() -> Path | None:
    env_music = os.getenv("REEL_MUSIC_PATH")
    candidates = []
    if env_music:
        candidates.append(Path(env_music))
    candidates.extend([
        ASSETS_DIR / "reel_music.mp3",
        Path("assets") / "reel_music.mp3",
    ])

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def render_vertical_reel(
    input_video: Path,
    output_path: Path,
    overlays: list[OverlaySpec],
    duration: float,
    start: float = 0.0,
    music_path: Path | None = None,
) -> Path:
    ffmpeg = resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{max(0.0, start):.2f}",
        "-t",
        f"{duration:.2f}",
        "-i",
        str(input_video),
    ]

    for overlay in overlays:
        cmd.extend(["-loop", "1", "-t", f"{duration:.2f}", "-i", str(overlay.path)])

    music_input_index = None
    if music_path:
        music_input_index = 1 + len(overlays)
        cmd.extend(["-stream_loop", "-1", "-i", str(music_path)])

    filter_parts = [
        (
            f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},boxblur=20:1,"
            "eq=brightness=-0.24:saturation=0.85,setsar=1[bg]"
        ),
        (
            "[0:v]scale=1020:1280:force_original_aspect_ratio=decrease,"
            "setsar=1[fg]"
        ),
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base]",
    ]

    current = "base"
    for idx, overlay in enumerate(overlays, start=1):
        out_label = f"v{idx}"
        start_expr = max(0.0, overlay.start)
        end_expr = max(start_expr + 0.1, overlay.end)
        filter_parts.append(
            f"[{current}][{idx}:v]overlay=0:0:enable='between(t,{start_expr:.2f},{end_expr:.2f})'[{out_label}]"
        )
        current = out_label

    filter_parts.append(f"[{current}]format=yuv420p[vout]")

    if music_input_index is not None:
        filter_parts.append(
            f"[{music_input_index}:a]volume=0.10,atrim=0:{duration:.2f},asetpts=PTS-STARTPTS[aout]"
        )

    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "[vout]"])

    if music_input_index is not None:
        cmd.extend(["-map", "[aout]"])
    else:
        cmd.append("-an")

    cmd.extend([
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_path),
    ])

    run_command(cmd, timeout=540)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ReelGenerationError("FFmpeg завершився без помилки, але MP4 не створено.")

    return output_path


def create_review_caption(title: str, source_url: str | None = None) -> str:
    caption = "🎬 AutoPulse Reel готовий до перевірки\n\n"
    caption += str(title).strip()
    if source_url:
        caption += f"\n\nДжерело: {source_url}"
    caption += "\n\nЯкщо виглядає добре — можна публікувати у Facebook/Reels вручну."
    return caption


def create_reel_from_video(
    video_source: str,
    title: str,
    facts: str | Iterable[str] | None = None,
    source_url: str | None = None,
    output_dir: str | Path | None = None,
    duration: int | float = DEFAULT_DURATION,
    start: int | float = 0,
    send_telegram: bool = False,
) -> Path:
    """
    Основна функція MVP.

    Бере реальне відео, робить вертикальний AutoPulse Reel і, якщо потрібно,
    надсилає MP4 у Telegram на ручну перевірку.
    """
    ensure_dirs()

    output_root = Path(output_dir) if output_dir else OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)

    slug = safe_slug(title)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    session_dir = TMP_DIR / f"{stamp}_{slug[:38]}"
    session_dir.mkdir(parents=True, exist_ok=True)

    source_path = resolve_video_source(video_source, tmp_dir=session_dir)
    ffmpeg = resolve_ffmpeg()
    source_duration = probe_duration(source_path, ffmpeg)

    start_seconds = max(0.0, float(start))
    target_duration = max(4.0, min(float(duration), 45.0))

    if source_duration is not None:
        if start_seconds >= max(0.0, source_duration - 0.5):
            raise ReelGenerationError(
                f"Параметр start={start_seconds:.1f}s виходить за межі відео тривалістю {source_duration:.1f}s."
            )
        available_duration = max(0.1, source_duration - start_seconds)
        target_duration = min(target_duration, available_duration)

    clean_facts = parse_facts(facts)
    overlays = build_overlays(title=title, facts=clean_facts, tmp_dir=session_dir, duration=target_duration)

    music_path = find_music_file()
    output_path = output_root / f"{stamp}_{slug}.mp4"

    render_vertical_reel(
        input_video=source_path,
        output_path=output_path,
        overlays=overlays,
        duration=target_duration,
        start=start_seconds,
        music_path=music_path,
    )

    print(f"✅ Reel створено: {output_path}")

    if send_telegram:
        try:
            import telegram_bot

            caption = create_review_caption(title=title, source_url=source_url)
            telegram_bot.send_telegram_video(output_path, caption=caption)
        except Exception as exc:
            print(f"⚠️ Reel створено, але не вдалося надіслати в Telegram: {type(exc).__name__}: {exc}")

    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI ДЛЯ РУЧНОГО ТЕСТУ
# ─────────────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AutoPulse Reels MVP: video source → vertical MP4 → optional Telegram review."
    )
    parser.add_argument("--video", required=True, help="Локальний файл або прямий URL на відео (.mp4/.mov/.webm).")
    parser.add_argument("--title", required=True, help="Заголовок ролика.")
    parser.add_argument("--facts", default="", help="2-3 факти через кому, крапку з комою або |.")
    parser.add_argument("--fact", action="append", default=[], help="Окремий факт. Можна вказати кілька разів.")
    parser.add_argument("--source-url", default="", help="Посилання на джерело для caption у Telegram.")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Тривалість ролика, секунд. За замовчуванням 24.")
    parser.add_argument("--start", type=float, default=0.0, help="З якої секунди почати нарізку.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Папка для готових MP4.")
    parser.add_argument("--send-telegram", action="store_true", help="Надіслати готовий MP4 у Telegram на перевірку.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    facts = []
    facts.extend(parse_facts(args.facts))
    facts.extend(parse_facts(args.fact))

    try:
        create_reel_from_video(
            video_source=args.video,
            title=args.title,
            facts=facts,
            source_url=args.source_url or None,
            output_dir=args.output_dir,
            duration=args.duration,
            start=args.start,
            send_telegram=args.send_telegram,
        )
        return 0
    except ReelGenerationError as exc:
        print(f"❌ ReelGenerationError: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n⏹️ Скасовано користувачем.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
