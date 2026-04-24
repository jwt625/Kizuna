#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from collections import deque
from pathlib import Path

from PIL import Image


def connected_components(mask: list[list[bool]]) -> list[list[tuple[int, int]]]:
    height = len(mask)
    width = len(mask[0])
    seen = [[False] * width for _ in range(height)]
    components: list[list[tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue

            queue = deque([(y, x)])
            seen[y][x] = True
            pixels: list[tuple[int, int]] = []

            while queue:
                cy, cx = queue.popleft()
                pixels.append((cy, cx))

                for ny in range(max(0, cy - 1), min(height, cy + 2)):
                    for nx in range(max(0, cx - 1), min(width, cx + 2)):
                        if mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            queue.append((ny, nx))

            components.append(pixels)

    return components


def find_center_blob(mask: list[list[bool]]) -> tuple[tuple[float, float], float]:
    height = len(mask)
    width = len(mask[0])
    image_center = (height / 2.0, width / 2.0)
    best_score = None
    best_centroid = None
    best_radius = None

    for component in connected_components(mask):
        area = len(component)
        if area < 100:
            continue

        sum_y = sum(y for y, _ in component)
        sum_x = sum(x for _, x in component)
        centroid = (sum_y / area, sum_x / area)
        dist = math.hypot(centroid[0] - image_center[0], centroid[1] - image_center[1])

        ys = [y for y, _ in component]
        xs = [x for _, x in component]
        box_area = (max(ys) - min(ys) + 1) * (max(xs) - min(xs) + 1)
        fill_ratio = area / box_area
        score = dist - fill_ratio * 40.0

        if best_score is None or score < best_score:
            best_score = score
            best_centroid = centroid
            best_radius = math.sqrt(area / math.pi)

    if best_centroid is None or best_radius is None:
        raise RuntimeError("Could not find center dot.")

    return best_centroid, best_radius


def circular_median(values: list[float]) -> float:
    sin_sum = sum(math.sin(math.radians(value)) for value in values)
    cos_sum = sum(math.cos(math.radians(value)) for value in values)
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0


def estimate_spoke_angles(points: list[tuple[int, int]], center_xy: tuple[float, float]) -> list[float]:
    angles = []
    for y, x in points:
        dx = x - center_xy[0]
        dy = y - center_xy[1]
        angles.append((math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0)

    hist = [0] * 360
    for angle in angles:
        hist[min(359, int(angle))] += 1

    smooth = []
    kernel = [1, 2, 3, 2, 1]
    for i in range(360):
        total = 0
        for j, weight in enumerate(kernel):
            idx = i + j - 2
            if 0 <= idx < 360:
                total += hist[idx] * weight
        smooth.append(total)

    threshold = max(20, int(max(smooth) * 0.18))
    bands: list[tuple[int, int]] = []
    start = None
    for idx, value in enumerate(smooth):
        if value >= threshold and start is None:
            start = idx
        elif value < threshold and start is not None:
            bands.append((start, idx - 1))
            start = None
    if start is not None:
        bands.append((start, len(smooth) - 1))

    out = []
    for low, high in bands:
        band_angles = [angle for angle in angles if low <= angle < high + 1]
        if band_angles:
            out.append(circular_median(band_angles))

    out = sorted(out)
    if len(out) > 1 and (out[0] + 360.0 - out[-1]) < 4.0:
        merged = circular_median([out[0], out[-1]])
        out = [merged] + out[1:-1]

    return sorted(out)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def measure_spoke(
    points: list[tuple[int, int]],
    center_xy: tuple[float, float],
    angle_deg: float,
) -> tuple[float, list[float]]:
    theta = math.radians(angle_deg)
    ux, uy = math.cos(theta), math.sin(theta)

    along_values: list[float] = []
    across_values: list[float] = []

    for y, x in points:
        px = x - center_xy[0]
        py = y - center_xy[1]
        along = px * ux + py * uy
        across = abs(-px * uy + py * ux)
        if along > 0 and across < 16:
            along_values.append(along)
            across_values.append(across)

    endpoint = percentile(along_values, 99.8)
    bins = [0.0] * (int(endpoint) + 3)

    for along, across in zip(along_values, across_values):
        idx = min(len(bins) - 1, max(0, int(round(along))))
        bins[idx] = max(bins[idx], across)

    smooth = [0.0] * len(bins)
    for i, value in enumerate(bins):
        total = value * 2
        weight = 2
        if i > 0:
            total += bins[i - 1]
            weight += 1
        if i + 1 < len(bins):
            total += bins[i + 1]
            weight += 1
        smooth[i] = total / weight

    narrow = [value for value in smooth if 0 < value < 8]
    body_width = max(1.0, percentile(narrow, 50.0)) if narrow else 2.0
    tick_threshold = max(7.5, body_width * 2.2)

    ticks: list[float] = []
    start = None
    for idx, value in enumerate(smooth):
        is_tick = value > tick_threshold
        if is_tick and start is None:
            start = idx
        elif not is_tick and start is not None:
            center = (start + idx - 1) / 2.0
            if 20 < center < endpoint - 8:
                ticks.append(center)
            start = None

    return endpoint, ticks


def svg_line(x1: float, y1: float, x2: float, y2: float, width: float) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="black" stroke-width="{width:.2f}" stroke-linecap="square" />'
    )


def convert_png_to_svg(input_path: Path, output_path: Path, threshold: int) -> None:
    image = Image.open(input_path).convert("L")
    width, height = image.size
    pixels = image.load()
    mask = [[pixels[x, y] < threshold for x in range(width)] for y in range(height)]

    center_rc, center_radius = find_center_blob(mask)
    center_xy = (center_rc[1], center_rc[0])
    gap_radius = center_radius + 10.5
    min_tick_radius = center_radius + 48.0

    points: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x]:
                continue
            if math.hypot(x - center_xy[0], y - center_xy[1]) > center_radius + 12:
                points.append((y, x))

    angles = estimate_spoke_angles(points, center_xy)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<g fill="none" stroke="black" stroke-linecap="square">',
    ]

    for angle in angles:
        endpoint, tick_positions = measure_spoke(points, center_xy, angle)
        theta = math.radians(angle)
        ux, uy = math.cos(theta), math.sin(theta)
        px, py = -uy, ux

        start_x = center_xy[0] + ux * gap_radius
        start_y = center_xy[1] + uy * gap_radius
        end_x = center_xy[0] + ux * endpoint
        end_y = center_xy[1] + uy * endpoint
        lines.append(svg_line(start_x, start_y, end_x, end_y, 5.5))

        filtered_ticks = [tick for tick in tick_positions if tick >= min_tick_radius]
        for tick in filtered_ticks + [endpoint]:
            tx = center_xy[0] + ux * tick
            ty = center_xy[1] + uy * tick
            half = 11.5
            lines.append(
                svg_line(
                    tx - px * half,
                    ty - py * half,
                    tx + px * half,
                    ty + py * half,
                    5.5,
                )
            )

    lines.append(
        f'<circle cx="{center_xy[0]:.2f}" cy="{center_xy[1]:.2f}" r="{center_radius + 1.5:.2f}" fill="black" />'
    )
    lines.append("</g>")
    lines.append("</svg>")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a radial line PNG to a simple SVG.")
    parser.add_argument("input", type=Path, help="Input PNG path")
    parser.add_argument("output", type=Path, nargs="?", help="Output SVG path")
    parser.add_argument("--threshold", type=int, default=180, help="Dark pixel threshold")
    args = parser.parse_args()

    output = args.output or args.input.with_suffix(".svg")
    convert_png_to_svg(args.input, output, args.threshold)


if __name__ == "__main__":
    main()
