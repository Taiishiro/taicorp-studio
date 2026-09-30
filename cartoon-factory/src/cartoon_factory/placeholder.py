"""Dessins « placeholder » façon crayon, générés avec Pillow, sans GPU.

Ils servent au mode `--backend placeholder` : tester tout le pipeline
(cache, animation, voix, montage) sur une machine sans ComfyUI, et montrer un
rendu de bout en bout. Le style vise le cahier des charges : papier crème,
traits tremblés, aplats doux, décor minimal, personnage simple.

Le contenu est choisi par mots-clés sur la description visuelle (ciel, soleil,
lumière, molécules, nuit…) : ce n'est pas de la génération, c'est un croquis.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PAPER = (250, 246, 236)
PENCIL = (70, 62, 58)
SKY = (176, 212, 240)
SKY_DEEP = (120, 170, 225)
SUN = (252, 214, 110)
GRASS = (184, 220, 160)
NIGHT = (52, 60, 110)
ORANGE = (250, 168, 110)
WHITE = (255, 255, 255)

RAINBOW = [(240, 120, 120), (250, 180, 110), (250, 225, 130), (170, 215, 150),
           (140, 190, 235), (150, 140, 210)]


def _hex(color: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) != 6:
        return fallback
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def _wobble(points: list[tuple[float, float]], rnd: random.Random, amp: float = 2.0):
    return [(x + rnd.uniform(-amp, amp), y + rnd.uniform(-amp, amp)) for x, y in points]


def _crayon_line(draw: ImageDraw.ImageDraw, pts, rnd: random.Random, color=PENCIL, width=4):
    """Trait tremblé : deux passes légèrement décalées, comme un crayon gras."""
    for pass_ in range(2):
        jitter = _wobble(pts, rnd, amp=1.5 + pass_)
        draw.line(jitter, fill=color, width=width, joint="curve")


def _crayon_circle(draw, cx, cy, r, rnd, fill, outline=PENCIL, width=4, segments=40):
    pts = [(cx + r * math.cos(2 * math.pi * i / segments),
            cy + r * math.sin(2 * math.pi * i / segments)) for i in range(segments + 1)]
    pts = _wobble(pts, rnd, amp=r * 0.03)
    draw.polygon(pts, fill=fill)
    _crayon_line(draw, pts, rnd, color=outline, width=width)


def _paper(width: int, height: int, rnd: random.Random) -> Image.Image:
    img = Image.new("RGB", (width, height), PAPER)
    px = img.load()
    # Grain de papier très léger (bruit ponctuel)
    for _ in range(width * height // 40):
        x, y = rnd.randrange(width), rnd.randrange(height)
        r, g, b = px[x, y]
        d = rnd.randint(-10, 6)
        px[x, y] = (max(0, r + d), max(0, g + d), max(0, b + d))
    return img


def _vertical_gradient(img: Image.Image, top, bottom, y0: int, y1: int) -> None:
    draw = ImageDraw.Draw(img)
    h = max(1, y1 - y0)
    for y in range(y0, y1):
        t = (y - y0) / h
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line([(0, y), (img.width, y)], fill=c)


def _character(draw, rnd, cx, cy, scale, body_color, accent, expression="smile"):
    """Personnage rond très simple : tête, corps, bras, yeux, bouche."""
    head_r = 46 * scale
    body_w, body_h = 70 * scale, 90 * scale
    # Corps (ovale)
    body = [cx - body_w, cy, cx + body_w, cy + body_h * 2]
    draw.ellipse(body, fill=body_color)
    _crayon_line(draw, [(cx - body_w, cy + body_h), (cx - body_w * 0.9, cy + body_h * 1.8),
                        (cx, cy + body_h * 2), (cx + body_w * 0.9, cy + body_h * 1.8),
                        (cx + body_w, cy + body_h)], rnd, width=int(4 * scale) + 1)
    # Bras levés
    _crayon_line(draw, [(cx - body_w, cy + body_h * 0.6), (cx - body_w * 1.8, cy - head_r * 0.4)],
                 rnd, width=int(5 * scale) + 1)
    _crayon_line(draw, [(cx + body_w, cy + body_h * 0.6), (cx + body_w * 1.8, cy - head_r * 0.2)],
                 rnd, width=int(5 * scale) + 1)
    # Tête
    _crayon_circle(draw, cx, cy - head_r * 0.6, head_r, rnd, fill=accent, width=int(4 * scale) + 1)
    # Yeux
    for dx in (-0.35, 0.35):
        ex, ey = cx + dx * head_r, cy - head_r * 0.75
        draw.ellipse([ex - 5 * scale, ey - 6 * scale, ex + 5 * scale, ey + 6 * scale], fill=PENCIL)
    # Bouche
    m = head_r * 0.35
    if expression == "surprised":
        draw.ellipse([cx - m * 0.4, cy - head_r * 0.35, cx + m * 0.4, cy - head_r * 0.05],
                     fill=PENCIL)
    else:
        pts = [(cx - m + m * i / 6, cy - head_r * 0.3 + math.sin(math.pi * i / 6) * m * 0.5)
               for i in range(7)]
        _crayon_line(draw, pts, rnd, width=int(3 * scale) + 1)


def _text(draw, xy, text, size, color=PENCIL, anchor="mm"):
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    draw.text(xy, text, fill=color, font=font, anchor=anchor)


def draw_keyframe(out_path: str | Path, *, width: int, height: int, visual: str,
                  seed: int, characters: list[dict] | None = None, variant: int = 0,
                  label: str = "") -> Path:
    """Génère un dessin clé placeholder à partir d'une description visuelle.

    `variant` (0 ou 1) décale légèrement la pose : ToonCrafter interpole entre
    les deux. `characters` = liste de dicts {name, palette}.
    """
    rnd = random.Random(seed * 31 + variant)
    v = visual.lower()
    img = _paper(width, height, rnd)
    draw = ImageDraw.Draw(img)
    W, H = width, height
    horizon = int(H * 0.72)

    def has(*keys: str) -> bool:
        # Mots entiers uniquement : « delighted » ne doit pas allumer « light ».
        return any(re.search(rf"\b{k}", v) for k in keys)

    night = has("nuit", "night", "étoile", "star", "lune", "moon")
    sunset = has("coucher", "sunset", "orange", "rouge", "soir")
    space = has("espace", "space", "planète", "planet", "univers")
    molecules = has("molécule", "molecule", "particule", "particle", "air")
    prism = has("arc-en-ciel", "rainbow", "prisme", "prism", "couleurs", "colors", "spectre",
                "spectrum")
    rays = has("rayon", "ray", "lumière", "light", "faisceau", "beam")
    sun = has("soleil", "sun") or sunset or rays

    # ── Ciel / fond ──────────────────────────────────────────────────────────
    if space:
        _vertical_gradient(img, (30, 30, 60), NIGHT, 0, H)
        for _ in range(80):
            x, y = rnd.randrange(W), rnd.randrange(H)
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=WHITE)
        # Terre en bas
        _crayon_circle(draw, W * 0.5, H * 1.35, H * 0.7, rnd, fill=SKY_DEEP, width=6)
        _crayon_circle(draw, W * 0.5, H * 1.35, H * 0.62, rnd, fill=GRASS, outline=SKY_DEEP,
                       width=3)
    elif night:
        _vertical_gradient(img, NIGHT, (90, 100, 160), 0, horizon)
        for _ in range(60):
            x, y = rnd.randrange(W), rnd.randrange(horizon)
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=WHITE)
        _crayon_circle(draw, W * 0.8, H * 0.2, H * 0.08, rnd, fill=(250, 240, 200), width=3)
    elif sunset:
        _vertical_gradient(img, SKY_DEEP, ORANGE, 0, horizon)
    else:
        _vertical_gradient(img, SKY_DEEP, SKY, 0, horizon)

    # ── Sol ──────────────────────────────────────────────────────────────────
    if not space:
        draw.rectangle([0, horizon, W, H], fill=GRASS)
        hill = [(x, horizon + 18 * math.sin(x / W * math.pi * 2 + rnd.random()))
                for x in range(0, W + 40, 40)]
        _crayon_line(draw, hill, rnd, width=5)

    # ── Soleil et rayons ─────────────────────────────────────────────────────
    if sun and not night:
        sx, sy, sr = W * 0.82, H * 0.2, H * 0.1
        if rays:
            for i in range(14):
                a = 2 * math.pi * i / 14 + variant * 0.1
                _crayon_line(draw, [(sx + math.cos(a) * sr * 1.3, sy + math.sin(a) * sr * 1.3),
                                    (sx + math.cos(a) * sr * (2.2 + rnd.random()),
                                     sy + math.sin(a) * sr * (2.2 + rnd.random()))],
                             rnd, color=(240, 190, 90), width=5)
        _crayon_circle(draw, sx, sy, sr, rnd, fill=SUN, width=5)

    # ── Molécules d'air qui diffusent la lumière ─────────────────────────────
    if molecules:
        for _ in range(28):
            x = rnd.uniform(W * 0.1, W * 0.9)
            y = rnd.uniform(H * 0.1, horizon - 30)
            r = rnd.uniform(9, 16)
            _crayon_circle(draw, x, y, r, rnd, fill=(200, 225, 250), width=2, segments=18)
        if rays:  # petits éclats bleus rebondissant dans tous les sens
            for _ in range(18):
                x, y = rnd.uniform(W * 0.2, W * 0.8), rnd.uniform(H * 0.1, horizon - 40)
                a = rnd.uniform(0, 2 * math.pi)
                _crayon_line(draw, [(x, y), (x + math.cos(a) * 40, y + math.sin(a) * 40)],
                             rnd, color=(90, 140, 230), width=3)

    # ── Prisme / arc-en-ciel ─────────────────────────────────────────────────
    if prism:
        cx, cy = W * 0.5, horizon
        for i, col in enumerate(RAINBOW):
            r = H * 0.55 - i * 16
            pts = [(cx + r * math.cos(math.pi + math.pi * t / 60),
                    cy + r * math.sin(math.pi + math.pi * t / 60)) for t in range(61)]
            _crayon_line(draw, pts, rnd, color=col, width=14)

    # ── Personnages ──────────────────────────────────────────────────────────
    chars = characters or []
    n = len(chars)
    for i, ch in enumerate(chars):
        pal = ch.get("palette", {})
        body = _hex(pal.get("body", ""), (250, 205, 120))
        accent = _hex(pal.get("skin", ""), (252, 228, 200))
        cx = W * (0.5 if n == 1 else 0.3 + 0.4 * i / max(1, n - 1))
        cy = horizon - 120 + variant * 6  # variante = léger mouvement
        expr = "surprised" if ("surpris" in v or "étonn" in v or "?" in visual) else "smile"
        _character(draw, rnd, cx, cy, 1.0, body, accent, expr)

    # Étiquette discrète (id du plan) — utile pour la vérification visuelle
    if label:
        _text(draw, (W - 12, H - 10), label, max(14, H // 40), color=(120, 110, 100), anchor="rd")

    img = img.filter(ImageFilter.GaussianBlur(0.6))  # adoucit les traits, effet papier
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def draw_title_card(out_path: str | Path, *, width: int, height: int, title: str,
                    subtitle: str = "", seed: int = 7) -> Path:
    """Carte-titre simple (question de l'épisode) sur fond papier."""
    rnd = random.Random(seed)
    img = _paper(width, height, rnd)
    draw = ImageDraw.Draw(img)
    _crayon_circle(draw, width * 0.5, height * 0.5, height * 0.42, rnd, fill=SKY, width=6)
    _text(draw, (width / 2, height * 0.47), title, max(20, height // 14))
    if subtitle:
        _text(draw, (width / 2, height * 0.62), subtitle, max(14, height // 26),
              color=(110, 100, 95))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
