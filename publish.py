#!/usr/bin/env python3
"""
Quiddity publishing helper.

Two ways to use it:

  python publish.py admin
      Opens a local page in your browser with an Essay/Note/Journal/Photo
      form. Fill it in, hit Save. This is the easiest way to add content.

  python publish.py essay "Title"
  python publish.py note ["Title"]
  python publish.py journal
  python publish.py photo <path-to-image> "caption"
      Command-line equivalents. Each creates the file and opens it in your
      default editor so you can write the body, then:

  python publish.py push
      Commits and pushes everything pending.

Run `python publish.py --help` or `python publish.py <command> --help` for
the full option list.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PublishError(Exception):
    pass


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"


def yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_new_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PublishError(f"Refusing to overwrite existing file: {path}")
    path.write_text(content, encoding="utf-8")
    return path


def open_in_editor(path: Path):
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 - launches the user's default app for .md
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"(Couldn't auto-open the file: {e}. Open it yourself at {path})")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True)


def has_staged_changes() -> bool:
    git("add", "-A")
    result = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
    return result.returncode != 0


def do_publish(message: str = None) -> bool:
    if not has_staged_changes():
        return False
    git("commit", "-m", message or f"Publish: {datetime.now():%Y-%m-%d %H:%M}")
    git("push")
    return True


# ---------------------------------------------------------------------------
# Content builders — shared by the CLI commands and the admin server.
# ---------------------------------------------------------------------------

def build_essay(title, description="", tags="", body="") -> Path:
    if not title or not title.strip():
        raise PublishError("An essay needs a title.")
    today = date.today().isoformat()
    path = ROOT / "_posts" / "essays" / f"{today}-{slugify(title)}.md"
    lines = ["---", f"title: {yaml_str(title)}"]
    if description:
        lines.append(f"description: {yaml_str(description)}")
    if tags:
        tag_list = ", ".join(t.strip() for t in tags.split(",") if t.strip())
        if tag_list:
            lines.append(f"tags: [{tag_list}]")
    lines += ["---", "", (body or "Start writing here.").strip(), ""]
    return write_new_file(path, "\n".join(lines))


def build_note(title="", tags="", body="") -> Path:
    today = date.today().isoformat()
    slug = slugify(title) if title else datetime.now().strftime("%H%M")
    path = ROOT / "_posts" / "notes" / f"{today}-{slug}.md"
    lines = ["---"]
    if title:
        lines.append(f"title: {yaml_str(title)}")
    if tags:
        tag_list = ", ".join(t.strip() for t in tags.split(",") if t.strip())
        if tag_list:
            lines.append(f"tags: [{tag_list}]")
    lines += ["---", "", (body or "Start writing here.").strip(), ""]
    return write_new_file(path, "\n".join(lines))


def build_journal(title="", body="") -> Path:
    today = date.today().isoformat()
    slug = slugify(title) if title else "entry"
    path = ROOT / "_posts" / "journal" / f"{today}-{slug}.md"
    lines = ["---"]
    if title:
        lines.append(f"title: {yaml_str(title)}")
    lines += ["---", "", (body or "Start writing here.").strip(), ""]
    return write_new_file(path, "\n".join(lines))


def _photo_md(today, slug, title, caption, alt, place, camera, body, image_rel):
    lines = [
        "---",
        f"title: {yaml_str(title)}",
        f"date: {today}",
        f"image: {image_rel}",
        f"alt: {yaml_str(alt)}",
        f"caption: {yaml_str(caption)}",
    ]
    if place:
        lines.append(f"place: {yaml_str(place)}")
    if camera:
        lines.append(f"camera: {yaml_str(camera)}")
    lines += ["---", "", (body or "").strip(), ""]
    md_path = ROOT / "_photos" / f"{today}-{slug}.md"
    return write_new_file(md_path, "\n".join(lines))


def build_photo_from_path(image_path, caption, title="", alt="", place="", camera="", body="") -> Path:
    if not caption or not caption.strip():
        raise PublishError("A photo needs a caption.")
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        raise PublishError(f"Image not found: {src}")

    today = date.today().isoformat()
    title = title or caption
    slug = slugify(title)
    dest_image = ROOT / "assets" / "photos" / f"{today}-{slug}{src.suffix.lower()}"
    dest_image.parent.mkdir(parents=True, exist_ok=True)
    if dest_image.exists():
        raise PublishError(f"Refusing to overwrite existing file: {dest_image}")
    shutil.copy2(src, dest_image)

    size_mb = dest_image.stat().st_size / (1024 * 1024)
    if size_mb > 5:
        print(f"Heads up: {dest_image.name} is {size_mb:.1f} MB. Consider resizing to "
              f"~2000px on the long edge so the site loads quickly.")

    return _photo_md(today, slug, title, caption, alt or caption, place, camera, body,
                      f"/assets/photos/{dest_image.name}")


def build_photo_from_bytes(image_bytes, image_name, caption, title="", alt="", place="", camera="", body="") -> Path:
    if not caption or not caption.strip():
        raise PublishError("A photo needs a caption.")
    if not image_bytes:
        raise PublishError("No image data received.")

    today = date.today().isoformat()
    title = title or caption
    slug = slugify(title)
    ext = Path(image_name or "").suffix.lower() or ".jpg"
    dest_image = ROOT / "assets" / "photos" / f"{today}-{slug}{ext}"
    dest_image.parent.mkdir(parents=True, exist_ok=True)
    if dest_image.exists():
        raise PublishError(f"Refusing to overwrite existing file: {dest_image}")
    dest_image.write_bytes(image_bytes)

    return _photo_md(today, slug, title, caption, alt or caption, place, camera, body,
                      f"/assets/photos/{dest_image.name}")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def _cli_guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except PublishError as e:
        print(str(e))
        sys.exit(1)


def cmd_essay(args):
    path = _cli_guard(build_essay, args.title, args.description or "", args.tags or "")
    print(f"Created {path.relative_to(ROOT)}")
    if not args.no_open:
        open_in_editor(path)
    if args.publish:
        if do_publish():
            print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        print("When you're done writing and have saved the file, run: python publish.py push")


def cmd_note(args):
    path = _cli_guard(build_note, args.title or "", args.tags or "")
    print(f"Created {path.relative_to(ROOT)}")
    if not args.no_open:
        open_in_editor(path)
    if args.publish:
        if do_publish():
            print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        print("When you're done writing and have saved the file, run: python publish.py push")


def cmd_journal(args):
    path = _cli_guard(build_journal, args.title or "")
    print(f"Created {path.relative_to(ROOT)}")
    if not args.no_open:
        open_in_editor(path)
    if args.publish:
        if do_publish():
            print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        print("When you're done writing and have saved the file, run: python publish.py push")


def cmd_photo(args):
    path = _cli_guard(
        build_photo_from_path, args.image, args.caption,
        args.title or "", args.alt or "", args.place or "", args.camera or "",
    )
    print(f"Created {path.relative_to(ROOT)}")
    if args.publish:
        if do_publish():
            print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        print("Run: python publish.py push   (to commit and go live)")


def cmd_push(args):
    if do_publish(args.message):
        print("Pushed. GitHub Pages will rebuild in a minute or two.")
    else:
        print("Nothing staged to commit.")


# ---------------------------------------------------------------------------
# Local admin server
# ---------------------------------------------------------------------------

ADMIN_DIR = ROOT / "admin"


class AdminHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass  # keep the terminal quiet; errors still print via send_error

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send_file(ADMIN_DIR / "index.html")
        elif self.path == "/admin/app.js":
            self._send_file(ADMIN_DIR / "app.js")
        elif self.path.startswith("/assets/"):
            self._send_file(ROOT / self.path.lstrip("/"))
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Malformed request."})
            return

        kind = self.path[len("/api/"):]
        try:
            if kind == "essay":
                path = build_essay(payload.get("title", ""), payload.get("description", ""),
                                    payload.get("tags", ""), payload.get("body", ""))
            elif kind == "note":
                path = build_note(payload.get("title", ""), payload.get("tags", ""),
                                   payload.get("body", ""))
            elif kind == "journal":
                path = build_journal(payload.get("title", ""), payload.get("body", ""))
            elif kind == "photo":
                image_data = payload.get("image_data", "")
                image_bytes = base64.b64decode(image_data) if image_data else b""
                path = build_photo_from_bytes(
                    image_bytes, payload.get("image_name", ""), payload.get("caption", ""),
                    payload.get("title", ""), payload.get("alt", ""),
                    payload.get("place", ""), payload.get("camera", ""), payload.get("body", ""),
                )
            else:
                self._send_json(404, {"ok": False, "error": "Unknown endpoint."})
                return
        except PublishError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"Unexpected error: {e}"})
            return

        published = False
        if payload.get("publish"):
            try:
                published = do_publish()
            except subprocess.CalledProcessError as e:
                self._send_json(200, {
                    "ok": True, "path": str(path.relative_to(ROOT)),
                    "published": False, "error": f"Saved, but publish failed: {e}",
                })
                return

        self._send_json(200, {
            "ok": True,
            "path": str(path.relative_to(ROOT)),
            "published": published,
        })


def cmd_admin(args):
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AdminHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Quiddity admin running at {url}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Quiddity publishing helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("admin", help="Open the local Add page in your browser")
    p.add_argument("--port", type=int, default=8971)
    p.set_defaults(func=cmd_admin)

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
