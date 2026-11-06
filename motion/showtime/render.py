#!/usr/bin/env python3
"""Render an existing capture with a pinned, separately installed Showtime checkout."""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys


SHOWTIME_COMMIT = "2bd4b44fcf47f9802233c4b6e33be61096b36428"


def prepare_inputs(showtime_root, capture, events, output, layout):
    root, capture, events, output = (
        Path(path).expanduser().resolve() for path in (showtime_root, capture, events, output)
    )
    for path in (capture, events):
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output must be a new .mp4 file")
    work = output.with_suffix(".showtime")
    destinations = [output, work, output.with_suffix(".quality.json"), output.with_suffix(".render.json")]
    if any(path.exists() for path in destinations):
        raise ValueError("Output or its work/report files already exist; choose a new output name")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != SHOWTIME_COMMIT:
        raise ValueError(f"Showtime must be checked out at {SHOWTIME_COMMIT}; found {head}")
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal", "--", "scripts", "profiles", "assets"],
        text=True,
    )
    if dirty.strip():
        raise ValueError("Showtime scripts, profiles or assets have local changes; use the clean pinned checkout")
    for name in ("compose_pilot.py", "showtime_doctor.py", "render_quality.py"):
        if not (root / "scripts" / name).is_file():
            raise ValueError(f"Missing Showtime script: {name}")
    profile_path = root / "profiles" / "telegram-product.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("path_base") != "config":
        raise ValueError("The pinned profile must resolve assets relative to its configuration")
    for section, key in (("device", "source"), ("device", "manifest"), ("background", "source"), ("tap", "sequence")):
        profile[section][key] = str((profile_path.parent / profile[section][key]).resolve())
    profile["layout"] = layout
    # Validate JSON before creating output files; upstream validates gesture timing and geometry.
    value = json.loads(events.read_text(encoding="utf-8"))
    if not isinstance(value, list) and not (isinstance(value, dict) and isinstance(value.get("events"), list)):
        raise ValueError("Events must be a JSON list or an object containing an events list")
    return root, capture, events, output, work, profile


def validate_capture(metadata, profile):
    videos = [item for item in metadata.get("streams", []) if item.get("codec_type") == "video"]
    if len(videos) != 1:
        raise ValueError("Capture must contain exactly one video stream")
    video = videos[0]
    duration = float(video.get("duration") or metadata.get("format", {}).get("duration", 0))
    width, height = video.get("width", 0), video.get("height", 0)
    if not math.isfinite(duration) or duration < 10 or width <= 0 or height <= 0:
        raise ValueError("Capture needs valid dimensions and at least 10 seconds of video")
    source_width, source_height = profile["device"]["source_size"]
    left, top, right, bottom = profile["device"]["screen_insets"]
    screen_ratio = (source_width - left - right) / (source_height - top - bottom)
    if abs((width / height) / screen_ratio - 1) > 0.01:
        raise ValueError("Capture aspect ratio does not match the phone screen. Supply a clean portrait recording; automatic cropping is refused")


def render(showtime_root, capture, events, output, layout="full"):
    root, capture, events, output, work, profile = prepare_inputs(showtime_root, capture, events, output, layout)
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(capture),
    ], text=True))
    validate_capture(metadata, profile)
    # Doctor checks local dependencies/assets only. Native recording is not part of this adapter.
    subprocess.run([sys.executable, str(root / "scripts/showtime_doctor.py")], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir()
    profile_path = work / "profile.json"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run([
        sys.executable, str(root / "scripts/compose_pilot.py"),
        "--config", str(profile_path), "--work-dir", str(work / "stage"),
        "render", "--capture", str(capture), "--events", str(events), "--output", str(output),
    ], check=True)
    subprocess.run([
        sys.executable, str(root / "scripts/render_quality.py"), str(output),
        "--report", str(output.with_suffix(".quality.json")),
    ], check=True)
    print(f"Rendered: {output}\nTechnical checks passed. Review motion, text and tap alignment before publication.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--showtime-root", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--layout", choices=("full", "crop-top", "crop-bottom"), default="full")
    args = parser.parse_args()
    try:
        render(args.showtime_root, args.capture, args.events, args.output, args.layout)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"showtime: {error}\n")


if __name__ == "__main__":
    main()
