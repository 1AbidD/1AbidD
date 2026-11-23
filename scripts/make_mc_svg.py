#!/usr/bin/env python3
"""Generate an animated floating Minecraft avatar SVG with base64 PNG embedding."""

from __future__ import annotations

import argparse
import base64
import io
import struct
import urllib.error
import urllib.request
import zlib
from pathlib import Path

# Set your real Minecraft Java username here, or place a local skin at skin.png.
MC_USERNAME = "abdzki"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "assets" / "mc-avatar.svg"
DEFAULT_SKIN_CANDIDATES = (ROOT / "skin.png", ROOT / "assets" / "skin.png")


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _encode_rgba_png(width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )


def build_placeholder_png(scale: int = 8) -> bytes:
    """Create a 16x32 pixel-art purple space astronaut placeholder as PNG bytes."""
    palette = {
        ".": (0, 0, 0, 0),
        "H": (26, 30, 58, 255),
        "M": (42, 48, 86, 255),
        "V": (160, 32, 240, 255),
        "C": (34, 211, 238, 255),
        "W": (241, 245, 249, 255),
        "P": (124, 58, 237, 255),
        "D": (17, 22, 43, 255),
        "B": (76, 29, 149, 255),
    }
    sprite = [
        "....HHHHHHHH....",
        "....HMMMMMMH....",
        "....HMWWWWWH....",
        "....HMVVVVVH....",
        "....HMVCCVVH....",
        "....HMVVVVVH....",
        "....HMMMMMMH....",
        "....HHHHHHHH....",
        "PPPPPPPPPPPPPPPP",
        "PMMMHDDDDDDHMMMP",
        "PMMMHDWPPWDHMMMP",
        "PMMMHDPCCPDHMMMP",
        "PMMMHDPPPPDHMMMP",
        "PBBBHDDDDDDHBBBP",
        "PBBBHMMMMMMHBBBP",
        "PBBBHDDDDDDHBBBP",
        "PBBBHMMMMMMHBBBP",
        "PMMMHDDDDDDHMMMP",
        "PMMMHDDDDDDHMMMP",
        "....HHHHHHHH....",
        "....HMMMMMMH....",
        "....HMD..DMH....",
        "....HMD..DMH....",
        "....HMD..DMH....",
        "....HPD..DPH....",
        "....HPD..DPH....",
        "....HMD..DMH....",
        "....HMD..DMH....",
        "....HBB..BBH....",
        "....HBB..BBH....",
        "....HDD..DDH....",
        "....HDD..DDH....",
    ]
    h = len(sprite)
    w = len(sprite[0])
    pixels: list[list[tuple[int, int, int, int]]] = []
    for y in range(h):
        row = []
        for x in range(w):
            color = palette[sprite[y][x]]
            row.extend([color] * scale)
        for _ in range(scale):
            pixels.append(row)
    return _encode_rgba_png(w * scale, h * scale, pixels)


def render_skin_sheet_if_possible(png_bytes: bytes) -> bytes:
    """If Pillow is installed and input is a 64x64 or 64x32 MC skin sheet, render front sprite."""
    try:
        from PIL import Image
    except ImportError:
        return png_bytes

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if img.size not in ((64, 64), (64, 32)):
        return png_bytes

    canvas = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    # Base layers: head, body, right arm, right leg, left arm, left leg
    canvas.paste(img.crop((8, 8, 16, 16)), (4, 0))
    canvas.paste(img.crop((20, 20, 28, 32)), (4, 8))
    canvas.paste(img.crop((44, 20, 48, 32)), (0, 8))
    canvas.paste(img.crop((4, 20, 8, 32)), (4, 20))
    if img.size == (64, 64):
        canvas.paste(img.crop((36, 52, 40, 64)), (12, 8))
        canvas.paste(img.crop((20, 52, 24, 64)), (8, 20))
        overlays = [
            ((40, 8, 48, 16), (4, 0)),
            ((20, 36, 28, 48), (4, 8)),
            ((44, 36, 48, 48), (0, 8)),
            ((52, 52, 56, 64), (12, 8)),
            ((4, 36, 8, 48), (4, 20)),
            ((4, 52, 8, 64), (8, 20)),
        ]
        for crop_box, dest in overlays:
            part = img.crop(crop_box)
            canvas.alpha_composite(part, dest)
    else:
        canvas.paste(img.crop((44, 20, 48, 32)).transpose(Image.FLIP_LEFT_RIGHT), (12, 8))
        canvas.paste(img.crop((4, 20, 8, 32)).transpose(Image.FLIP_LEFT_RIGHT), (8, 20))
        canvas.alpha_composite(img.crop((40, 8, 48, 16)), (4, 0))

    scaled = canvas.resize((128, 256), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    scaled.save(buf, format="PNG")
    return buf.getvalue()


def fetch_mc_png(username: str) -> bytes:
    urls = [
        f"https://mc-heads.net/body/{username}/240",
        f"https://mc-heads.net/avatar/{username}/180",
    ]
    last_err: Exception | None = None
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "1AbidD-profile-generator"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if data.startswith(b"\x89PNG"):
                    return data
        except (urllib.error.URLError, TimeoutError) as err:
            last_err = err
    raise RuntimeError(f"Could not fetch Minecraft render for '{username}': {last_err}")


def load_avatar_png(username: str, skin_path: Path | None) -> tuple[bytes, str]:
    if skin_path is not None:
        if not skin_path.is_file():
            raise FileNotFoundError(f"Local skin file not found: {skin_path}")
        return render_skin_sheet_if_possible(skin_path.read_bytes()), f"SKIN // {skin_path.name.upper()}"

    if username and username != "CHANGE_ME":
        return fetch_mc_png(username), f"UNIT // {username.upper()}"

    for candidate in DEFAULT_SKIN_CANDIDATES:
        if candidate.is_file():
            return render_skin_sheet_if_possible(candidate.read_bytes()), f"SKIN // {candidate.name.upper()}"

    return build_placeholder_png(), "SKIN PLACEHOLDER // CHANGE_ME"


def build_mc_svg(png_bytes: bytes, status_label: str) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"
    safe_label = (
        status_label.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 240 290" width="240" height="290" role="img" aria-label="Floating Minecraft character avatar">
  <defs>
    <linearGradient id="mcBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#060914"/>
      <stop offset="100%" stop-color="#110d26"/>
    </linearGradient>
    <radialGradient id="mcAura" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#a020f0" stop-opacity="0.48"/>
      <stop offset="55%" stop-color="#7c3aed" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#060914" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="mcBorder" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.7"/>
      <stop offset="50%" stop-color="#7c3aed" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#a020f0" stop-opacity="0.8"/>
    </linearGradient>
    <clipPath id="mcClip">
      <polygon points="16,4 224,4 236,16 236,274 224,286 16,286 4,274 4,16"/>
    </clipPath>
  </defs>
  <style>
    .mc-float {{ animation: mcFloat 4.2s ease-in-out infinite; }}
    .mc-aura {{ animation: auraPulse 3.8s ease-in-out infinite; transform-origin: 120px 148px; }}
    .mc-shadow {{ animation: shadowPulse 4.2s ease-in-out infinite; transform-origin: 120px 242px; }}
    .p1 {{ animation: rise 3.4s linear infinite; }}
    .p2 {{ animation: rise 4.1s linear 0.8s infinite; }}
    .p3 {{ animation: rise 3.7s linear 1.6s infinite; }}
    .p4 {{ animation: rise 4.5s linear 2.2s infinite; }}
    .p5 {{ animation: rise 3.2s linear 0.4s infinite; }}
    .p6 {{ animation: rise 4.8s linear 1.2s infinite; }}
    @keyframes mcFloat {{
      0%, 100% {{ transform: translateY(0px); }}
      50% {{ transform: translateY(-10px); }}
    }}
    @keyframes auraPulse {{
      0%, 100% {{ opacity: 0.65; transform: scale(0.95); }}
      50% {{ opacity: 1; transform: scale(1.07); }}
    }}
    @keyframes shadowPulse {{
      0%, 100% {{ opacity: 0.55; transform: scaleX(1); }}
      50% {{ opacity: 0.28; transform: scaleX(0.78); }}
    }}
    @keyframes rise {{
      0% {{ transform: translateY(0px); opacity: 0; }}
      15% {{ opacity: 0.95; }}
      80% {{ opacity: 0.7; }}
      100% {{ transform: translateY(-170px); opacity: 0; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .mc-float, .mc-aura, .mc-shadow, .p1, .p2, .p3, .p4, .p5, .p6 {{ animation: none; }}
    }}
  </style>

  <g clip-path="url(#mcClip)">
    <rect width="240" height="290" fill="url(#mcBg)"/>
    <circle cx="34" cy="48" r="1.1" fill="#e2e8f0" opacity="0.65"/>
    <circle cx="204" cy="64" r="1.2" fill="#e2e8f0" opacity="0.55"/>
    <circle cx="52" cy="222" r="1" fill="#cbd5e1" opacity="0.5"/>
    <circle cx="196" cy="214" r="1.1" fill="#cbd5e1" opacity="0.6"/>

    <ellipse class="mc-aura" cx="120" cy="148" rx="84" ry="88" fill="url(#mcAura)"/>
    <ellipse class="mc-shadow" cx="120" cy="242" rx="44" ry="9" fill="#a020f0" opacity="0.38"/>

    <!-- Rising pixel particles -->
    <rect class="p1" x="48" y="236" width="5" height="5" fill="#c084fc"/>
    <rect class="p2" x="78" y="248" width="4" height="4" fill="#a020f0"/>
    <rect class="p3" x="156" y="242" width="5" height="5" fill="#22d3ee"/>
    <rect class="p4" x="184" y="234" width="4" height="4" fill="#c084fc"/>
    <rect class="p5" x="108" y="252" width="3" height="3" fill="#e9d5ff"/>
    <rect class="p6" x="136" y="250" width="4" height="4" fill="#7c3aed"/>

    <g class="mc-float">
      <image x="66" y="42" width="108" height="196" preserveAspectRatio="xMidYMid meet" style="image-rendering:pixelated" href="{data_uri}" xlink:href="{data_uri}"/>
    </g>

    <g font-family="ui-monospace, 'SFMono-Regular', Consolas, monospace" font-size="9.5" letter-spacing="1">
      <text x="18" y="24" fill="#94a3b8">CREW // AVATAR</text>
      <rect x="206" y="17" width="6" height="6" fill="#22d3ee"/>
      <line x1="18" y1="258" x2="222" y2="258" stroke="#7c3aed" stroke-width="1" opacity="0.5"/>
      <text x="120" y="274" text-anchor="middle" fill="#c4b5fd">{safe_label}</text>
    </g>
  </g>

  <polygon points="16,4 224,4 236,16 236,274 224,286 16,286 4,274 4,16" fill="none" stroke="url(#mcBorder)" stroke-width="1.5"/>
  <polyline points="4,34 4,16 16,4 36,4" fill="none" stroke="#22d3ee" stroke-width="2"/>
  <polyline points="204,286 224,286 236,274 236,256" fill="none" stroke="#a020f0" stroke-width="2"/>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate animated Minecraft avatar SVG.")
    parser.add_argument("--username", default=MC_USERNAME, help="Minecraft Java username (default: MC_USERNAME)")
    parser.add_argument("--skin", type=Path, default=None, help="Path to a local skin PNG or avatar PNG")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output SVG path")
    args = parser.parse_args()

    png_bytes, status_label = load_avatar_png(args.username, args.skin)
    svg = build_mc_svg(png_bytes, status_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {args.output} ({len(svg.encode('utf-8'))} bytes) [{status_label}]")


if __name__ == "__main__":
    main()
