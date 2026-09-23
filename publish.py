#!/usr/bin/env python3
"""
Quiddity publishing helper.

Creates correctly-formatted files in the right place so you never have to
hand-write front matter or remember the folder structure. Run it from
anywhere; it finds the site root next to this script.

Examples:
  python publish.py essay "On Stillness" --tags attention,silence
  python publish.py note "A short thought"
  python publish.py note                       (untitled fragment)
  python publish.py journal
  python publish.py photo "C:\\pics\\rain.jpg" "Rain on Taft Avenue" --place "Manila" --camera "35mm"
  python publish.py push                        (add + commit + push everything pending)

Add --publish to essay/note/journal/photo to also commit and push immediately
(only sensible when you're not going to edit the body afterwards, e.g. photos).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"


def yaml_str(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"Refusing to overwrite existing file: {path}")
        sys.exit(1)
    path.write_text(content, encoding="utf-8")
    print(f"Created {path.relative_to(ROOT)}")


def open_in_editor(path: Path):
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 - launches user's default app for .md
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"(Couldn't auto-open the file: {e}. Open it yourself at {path})")


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check)


def do_publish():
    print("\nPublishing...")
    git("add", "-A")
    result = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print("Nothing staged to commit.")
        return
    git("commit", "-m", f"Publish: {datetime.now():%Y-%m-%d %H:%M}")
    git("push")
    print("Pushed. GitHub Pages will rebuild in a minute or two.")


def cmd_essay(args):
    today = date.today().isoformat()
    slug = slugify(args.title)
    path = ROOT / "_posts" / "essays" / f"{today}-{slug}.md"
    lines = ["---", f"title: {yaml_str(args.title)}"]
    if args.description:
        lines.append(f"description: {yaml_str(args.description)}")
    if args.tags:
        tag_list = ", ".join(t.strip() for t in args.tags.split(","))
        lines.append(f"tags: [{tag_list}]")
    lines += ["---", "", "Start writing here.", ""]
    write_file(path, "\n".join(lines))
    if not args.no_open:
        open_in_editor(path)
    print("When you're done writing and have saved the file, run: python publish.py push")
    if args.publish:
        do_publish()


def cmd_note(args):
    today = date.today().isoformat()
    slug = slugify(args.title) if args.title else datetime.now().strftime("%H%M")
    path = ROOT / "_posts" / "notes" / f"{today}-{slug}.md"
    lines = ["---"]
    if args.title:
        lines.append(f"title: {yaml_str(args.title)}")
    if args.tags:
        tag_list = ", ".join(t.strip() for t in args.tags.split(","))
        lines.append(f"tags: [{tag_list}]")
    lines += ["---", "", "Start writing here.", ""]
    write_file(path, "\n".join(lines))
    if not args.no_open:
        open_in_editor(path)
    print("When you're done writing and have saved the file, run: python publish.py push")
    if args.publish:
        do_publish()


def cmd_journal(args):
    today = date.today().isoformat()
    slug = slugify(args.title) if args.title else "entry"
    path = ROOT / "_posts" / "journal" / f"{today}-{slug}.md"
    lines = ["---"]
    if args.title:
        lines.append(f"title: {yaml_str(args.title)}")
    lines += ["---", "", "Start writing here.", ""]
    write_file(path, "\n".join(lines))
    if not args.no_open:
        open_in_editor(path)
    print("When you're done writing and have saved the file, run: python publish.py push")
    if args.publish:
        do_publish()


def cmd_photo(args):
    src = Path(args.image).expanduser().resolve()
    if not src.exists():
        print(f"Image not found: {src}")
        sys.exit(1)

    today = date.today().isoformat()
    title = args.title or args.caption
    slug = slugify(title)
    ext = src.suffix.lower()
    dest_image = ROOT / "assets" / "photos" / f"{today}-{slug}{ext}"
    dest_image.parent.mkdir(parents=True, exist_ok=True)
    if dest_image.exists():
        print(f"Refusing to overwrite existing file: {dest_image}")
        sys.exit(1)
    shutil.copy2(src, dest_image)
    print(f"Copied photo to {dest_image.relative_to(ROOT)}")

    size_mb = dest_image.stat().st_size / (1024 * 1024)
    if size_mb > 5:
        print(f"Heads up: this file is {size_mb:.1f} MB. Consider resizing to "
              f"~2000px on the long edge so the site loads quickly.")

    md_path = ROOT / "_photos" / f"{today}-{slug}.md"
    alt = args.alt or args.caption
    lines = [
        "---",
        f"title: {yaml_str(title)}",
        f"date: {today}",
        f"image: /assets/photos/{dest_image.name}",
        f"alt: {yaml_str(alt)}",
        f"caption: {yaml_str(args.caption)}",
    ]
    if args.place:
        lines.append(f"place: {yaml_str(args.place)}")
    if args.camera:
        lines.append(f"camera: {yaml_str(args.camera)}")
    lines += ["---", "", ""]
    write_file(md_path, "\n".join(lines))

    if args.publish:
        do_publish()
    else:
        print("Run: python publish.py push   (to commit and go live)")


def cmd_push(args):
    if args.message:
        git("add", "-A")
        result = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
        if result.returncode == 0:
            print("Nothing staged to commit.")
            return
        git("commit", "-m", args.message)
        git("push")
        print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        do_publish()


def main():
    parser = argparse.ArgumentParser(description="Quiddity publishing helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("essay", help="Start a new essay")
    p.add_argument("title")
    p.add_argument("--description", help="One-line teaser shown under the title")
    p.add_argument("--tags", help="Comma-separated tags, e.g. attention,silence")
    p.add_argument("--no-open", action="store_true", help="Don't auto-open the file")
    p.add_argument("--publish", action="store_true", help="Also commit and push right away")
    p.set_defaults(func=cmd_essay)

    p = sub.add_parser("note", help="Start a new short fragment")
    p.add_argument("title", nargs="?", default=None)
    p.add_argument("--tags", help="Comma-separated tags")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--publish", action="store_true")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("journal", help="Start today's journal entry")
    p.add_argument("title", nargs="?", default=None)
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--publish", action="store_true")
    p.set_defaults(func=cmd_journal)

    p = sub.add_parser("photo", help="Add a photograph with a caption")
    p.add_argument("image", help="Path to the image file on your computer")
    p.add_argument("caption", help="Caption shown under the photo")
    p.add_argument("--title", help="Defaults to the caption if omitted")
    p.add_argument("--alt", help="Accessibility description; defaults to the caption")
    p.add_argument("--place", help="e.g. 'Manila' or 'Quezon City'")
    p.add_argument("--camera", help="e.g. 'Phone' or '35mm'")
    p.add_argument("--publish", action="store_true", help="Also commit and push right away")
    p.set_defaults(func=cmd_photo)

    p = sub.add_parser("push", help="Commit and push everything pending")
    p.add_argument("message", nargs="?", default=None, help="Custom commit message")
    p.set_defaults(func=cmd_push)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
