#!/usr/bin/env python3
"""
Quiddity publishing helper.

  python publish.py admin
      Opens a local page in your browser where you can write new posts, edit
      or delete existing ones, edit the About page and the site's text, and
      publish — all without touching files.

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
import binascii
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
from urllib.parse import parse_qs, unquote, urlsplit

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

ROOT = Path(__file__).resolve().parent
ADMIN_DIR = ROOT / "admin"
ASSETS_DIR = ROOT / "assets"
PHOTO_DIR = ASSETS_DIR / "photos"
CONTENT_JSON = ROOT / "_data" / "content.json"
ABOUT_MD = ROOT / "about.md"
CONFIG_YML = ROOT / "_config.yml"

SECTIONS = {
    "essay": ROOT / "_posts" / "essays",
    "note": ROOT / "_posts" / "notes",
    "journal": ROOT / "_posts" / "journal",
    "photo": ROOT / "_photos",
}
KIND_LABEL = {"essay": "essay", "note": "note", "journal": "journal entry", "photo": "photo"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
MAX_REQUEST_BYTES = 60 * 1024 * 1024

DEFAULT_CONTENT = {
    "home": {
        "title": "On the thoughts",
        "title_em": "that shape our being.",
        "intro": "I'm vent. This is where I think slowly, in essays, fragments, and photographs, "
                 "about attention, identity, and the beauty of things we walk past.",
    },
    "ledes": {
        "essays": "Longer pieces, written slowly and revised often.",
        "notes": "Fragments. Things half-thought, kept anyway.",
        "journal": "Dated, unedited, mostly for myself.",
        "photographs": "What I saw when I was paying attention.",
        "tags": "Threads that run through the writing.",
    },
    "instagram": "yourhandle",
}

IDENTITY_HELP = (
    "Git doesn't know who you are on this computer yet, so it can't save anything to publish. "
    "Run these two commands once in a terminal (use the email on your GitHub account), "
    "then publish again:\n"
    'git config --global user.name "vent"\n'
    'git config --global user.email "you@example.com"'
)


class PublishError(Exception):
    pass


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"


def yaml_str(value: str) -> str:
    # A JSON string is also a valid YAML double-quoted scalar, escapes and all.
    return json.dumps(str(value), ensure_ascii=False)


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_new_file(path: Path, content: str) -> Path:
    if path.exists():
        raise PublishError(f"There's already a file called {path.name} — try a different title.")
    write_text(path, content)
    return path


def split_tags(tags) -> list:
    if isinstance(tags, list):
        items = tags
    else:
        items = (tags or "").split(",")
    return [t.strip() for t in items if str(t).strip()]


def open_in_editor(path: Path):
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 - launches the user's default app for .md
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"(Couldn't auto-open the file: {e}. Open it yourself at {path})")


def check_image_name(name: str) -> str:
    ext = Path(name or "").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise PublishError(
            f"{ext} files can't be shown on the web reliably. Use a JPG, PNG, WEBP, GIF or AVIF "
            "(on iPhone, HEIC photos can be exported as JPG)."
        )
    return ext


# ---------------------------------------------------------------------------
# Front matter: read, edit, and write without disturbing fields we don't touch
# ---------------------------------------------------------------------------

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*$\n?", re.S | re.M)
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):(?:\s+(.*)|\s*)$")


def parse_scalar(raw: str):
    s = raw.strip()
    if not s or s.startswith("#"):
        return ""
    if s[0] == '"':
        end = s.rfind('"')
        try:
            return json.loads(s[: end + 1]) if end > 0 else s[1:]
        except json.JSONDecodeError:
            return s[1:end] if end > 0 else s[1:]
    if s[0] == "'":
        out, i = [], 1
        while i < len(s):
            if s[i] == "'":
                if s[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                break
            out.append(s[i])
            i += 1
        return "".join(out)
    if s[0] == "[":
        inner = s[1:s.rfind("]")] if "]" in s else s[1:]
        parts, buf, quote = [], "", None
        for ch in inner:
            if quote:
                buf += ch
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                buf += ch
            elif ch == ",":
                parts.append(buf)
                buf = ""
            else:
                buf += ch
        parts.append(buf)
        return [parse_scalar(p) for p in parts if p.strip()]
    return re.sub(r"\s+#.*$", "", s).strip()


def entry_value(entry):
    raw = entry["raw"]
    if raw in (">", ">-", ">+", "|", "|-", "|+") and entry["extra"]:
        lines = [line.strip() for line in entry["extra"]]
        return (" " if raw.startswith(">") else "\n").join(lines).strip()
    return parse_scalar(raw)


def parse_front_matter(fm: str) -> list:
    entries = []
    lines = fm.rstrip("\n").split("\n") if fm.strip() else []
    for line in lines:
        m = KEY_RE.match(line)
        if m:
            entries.append({"key": m.group(1), "raw": (m.group(2) or "").strip(), "line": line, "extra": []})
        elif line[:1] in (" ", "\t") and entries and entries[-1]["key"]:
            entries[-1]["extra"].append(line)
        else:
            entries.append({"key": None, "raw": line, "line": line, "extra": []})
    return entries


def read_doc(path: Path):
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    m = FM_RE.match(text)
    if not m:
        return [], text
    return parse_front_matter(m.group(1)), text[m.end():]


def get_field(entries, key, default=""):
    for e in entries:
        if e["key"] == key:
            return entry_value(e)
    return default


def format_value(value):
    if isinstance(value, list):
        return "[" + ", ".join(
            t if re.fullmatch(r"\w[\w .-]*", t) else yaml_str(t) for t in value
        ) + "]"
    return yaml_str(value)


def set_field(entries, key, value):
    empty = value is None or value == "" or value == []
    for i, e in enumerate(entries):
        if e["key"] != key:
            continue
        if empty:
            del entries[i]
        elif entry_value(e) != value:
            formatted = format_value(value)
            entries[i] = {"key": key, "raw": formatted, "line": f"{key}: {formatted}", "extra": []}
        return
    if not empty:
        formatted = format_value(value)
        entries.append({"key": key, "raw": formatted, "line": f"{key}: {formatted}", "extra": []})


def write_doc(path: Path, entries, body: str):
    lines = ["---"]
    for e in entries:
        lines.append(e["line"])
        lines.extend(e["extra"])
    lines.append("---")
    body = (body or "").replace("\r\n", "\n").strip("\n").rstrip()
    write_text(path, "\n".join(lines) + "\n" + ("\n" + body + "\n" if body else ""))


def excerpt_of(body: str, limit=110) -> str:
    text = re.sub(r"<[^>]+>|[*_`#>]|\{%.*?%\}", "", body or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Git / publishing
# ---------------------------------------------------------------------------

def git_run(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def explain_git_error(output: str) -> str:
    low = output.lower()
    if "tell me who you are" in low or "unable to auto-detect email" in low:
        return IDENTITY_HELP
    if ("authentication failed" in low or "could not read username" in low
            or "permission denied" in low or "invalid username or token" in low):
        return ("GitHub rejected the login. Open a terminal in the quiddity folder and run "
                "`git push` once — it should ask you to sign in — then publish again here.")
    if "rejected" in low and ("fetch first" in low or "non-fast-forward" in low):
        return ("GitHub has changes this computer doesn't have yet (maybe from editing on github.com). "
                "Run `git pull` in the quiddity folder, then publish again.")
    if "could not resolve host" in low or "unable to access" in low:
        return "Couldn't reach GitHub — check your internet connection, then publish again."
    return output.strip() or "Git failed without saying why."


def git_ok(*args) -> str:
    r = git_run(*args)
    if r.returncode != 0:
        raise PublishError(explain_git_error((r.stderr or "") + "\n" + (r.stdout or "")))
    return r.stdout


def git_status() -> dict:
    name = git_run("config", "user.name").stdout.strip()
    email = git_run("config", "user.email").stdout.strip()
    porcelain = git_run("-c", "core.quotepath=false", "status", "--porcelain").stdout
    pending = [line[3:].strip().strip('"') for line in porcelain.splitlines() if line.strip()]
    ahead_run = git_run("rev-list", "--count", "@{u}..HEAD")
    ahead_out = ahead_run.stdout.strip()
    ahead = int(ahead_out) if ahead_run.returncode == 0 and ahead_out.isdigit() else 0
    return {"identity_ok": bool(name and email), "pending": pending, "ahead": ahead}


def publish(message: str = None) -> str:
    """Commit everything pending (if anything) and push. Raises PublishError with a readable reason."""
    status = git_status()
    if status["pending"]:
        if not status["identity_ok"]:
            raise PublishError(IDENTITY_HELP)
        git_ok("add", "-A")
        git_ok("commit", "-m", message or f"Update site: {datetime.now():%Y-%m-%d %H:%M}")
    elif status["ahead"] == 0:
        return "Nothing to publish — everything is already live."
    git_ok("push")
    return "Published. The live site updates in a minute or two."


# ---------------------------------------------------------------------------
# Creating content — shared by the CLI and the admin page
# ---------------------------------------------------------------------------

def _new_doc(path: Path, fields: dict, body: str) -> Path:
    if path.exists():
        raise PublishError(f"There's already a file called {path.name} — try a different title.")
    entries = []
    for key, value in fields.items():
        set_field(entries, key, value)
    write_doc(path, entries, body)
    return path


def build_essay(title, description="", tags="", body="") -> Path:
    if not (title or "").strip():
        raise PublishError("An essay needs a title.")
    path = SECTIONS["essay"] / f"{date.today().isoformat()}-{slugify(title)}.md"
    fields = {"title": title.strip(), "description": (description or "").strip(), "tags": split_tags(tags)}
    return _new_doc(path, fields, body or "Start writing here.")


def build_note(title="", tags="", body="") -> Path:
    title = (title or "").strip()
    slug = slugify(title) if title else datetime.now().strftime("%H%M")
    path = SECTIONS["note"] / f"{date.today().isoformat()}-{slug}.md"
    return _new_doc(path, {"title": title, "tags": split_tags(tags)}, body or "Start writing here.")


def build_journal(title="", body="") -> Path:
    title = (title or "").strip()
    slug = slugify(title) if title else "entry"
    path = SECTIONS["journal"] / f"{date.today().isoformat()}-{slug}.md"
    return _new_doc(path, {"title": title}, body or "Start writing here.")


def _photo_doc(today, slug, title, caption, alt, place, camera, body, image_rel) -> Path:
    fields = {
        "title": title, "date": today, "image": image_rel, "alt": alt,
        "caption": caption, "place": place, "camera": camera,
    }
    path = SECTIONS["photo"] / f"{today}-{slug}.md"
    if path.exists():
        raise PublishError(f"There's already a photo called {path.name} — try a different title.")
    entries = []
    for key, value in fields.items():
        if key == "date":
            entries.append({"key": "date", "raw": value, "line": f"date: {value}", "extra": []})
        else:
            set_field(entries, key, (value or "").strip())
    write_doc(path, entries, body)
    return path


def build_photo_from_path(image_path, caption, title="", alt="", place="", camera="", body="") -> Path:
    if not (caption or "").strip():
        raise PublishError("A photo needs a caption.")
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        raise PublishError(f"Image not found: {src}")
    ext = check_image_name(src.name)

    today = date.today().isoformat()
    title = (title or "").strip() or caption.strip()
    slug = slugify(title)
    dest_image = PHOTO_DIR / f"{today}-{slug}{ext}"
    if dest_image.exists():
        raise PublishError(f"There's already an image called {dest_image.name} — try a different title.")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_image)

    size_mb = dest_image.stat().st_size / (1024 * 1024)
    if size_mb > 5:
        print(f"Heads up: {dest_image.name} is {size_mb:.1f} MB. Consider resizing to "
              f"~2000px on the long edge so the site loads quickly.")

    return _photo_doc(today, slug, title, caption.strip(), alt or caption, place, camera, body,
                      f"/assets/photos/{dest_image.name}")


def build_photo_from_bytes(image_bytes, image_name, caption, title="", alt="", place="", camera="", body="") -> Path:
    if not (caption or "").strip():
        raise PublishError("A photo needs a caption.")
    if not image_bytes:
        raise PublishError("Choose a photo first.")
    ext = check_image_name(image_name)

    today = date.today().isoformat()
    title = (title or "").strip() or caption.strip()
    slug = slugify(title)
    dest_image = PHOTO_DIR / f"{today}-{slug}{ext}"
    if dest_image.exists():
        raise PublishError(f"There's already an image called {dest_image.name} — try a different title.")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    dest_image.write_bytes(image_bytes)

    return _photo_doc(today, slug, title, caption.strip(), alt or caption, place, camera, body,
                      f"/assets/photos/{dest_image.name}")


# ---------------------------------------------------------------------------
# Listing, editing, and deleting existing content
# ---------------------------------------------------------------------------

def resolve_item(item_id: str):
    """Map an id like '_posts/notes/2026-09-30-x.md' to (kind, path) — only inside the content folders."""
    try:
        path = (ROOT / (item_id or "")).resolve()
    except (OSError, ValueError):
        raise PublishError("That item doesn't exist.")
    for kind, folder in SECTIONS.items():
        if path.parent == folder.resolve() and path.suffix == ".md" and path.is_file():
            return kind, path
    raise PublishError("That item doesn't exist (it may have been deleted already).")


def item_summary(kind: str, path: Path) -> dict:
    entries, body = read_doc(path)
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(.*)", path.stem)
    return {
        "id": rel(path),
        "kind": kind,
        "title": str(get_field(entries, "title") or ""),
        "date": str(get_field(entries, "date") or (m.group(1) if m else "")),
        "excerpt": excerpt_of(get_field(entries, "caption") or body),
        "image": str(get_field(entries, "image") or ""),
    }


def list_items() -> list:
    items = []
    for kind, folder in SECTIONS.items():
        if folder.is_dir():
            items += [item_summary(kind, p) for p in folder.glob("*.md")]
    return sorted(items, key=lambda i: (i["date"], i["id"]), reverse=True)


def get_item(item_id: str) -> dict:
    kind, path = resolve_item(item_id)
    entries, body = read_doc(path)
    fields = {key: str(get_field(entries, key) or "")
              for key in ("title", "description", "caption", "place", "camera", "alt", "image")}
    tags = get_field(entries, "tags", [])
    fields["tags"] = ", ".join(tags) if isinstance(tags, list) else str(tags or "")
    fields["body"] = body.strip("\n")
    return {"ok": True, "id": rel(path), "kind": kind, "fields": fields}


def photo_image_path(image_url: str):
    """Local file for an /assets/photos/... URL, or None if it points anywhere else."""
    if not image_url or not image_url.startswith("/assets/photos/"):
        return None
    path = (ROOT / image_url.lstrip("/")).resolve()
    return path if path.parent == PHOTO_DIR.resolve() else None


def image_in_use(image_url: str, ignore: Path = None) -> bool:
    for p in SECTIONS["photo"].glob("*.md"):
        if ignore is not None and p.resolve() == ignore.resolve():
            continue
        if get_field(read_doc(p)[0], "image") == image_url:
            return True
    return False


def update_item(payload: dict) -> Path:
    kind, path = resolve_item(payload.get("id", ""))
    entries, _ = read_doc(path)
    title = (payload.get("title") or "").strip()

    if kind == "essay":
        if not title:
            raise PublishError("An essay needs a title.")
        set_field(entries, "title", title)
        set_field(entries, "description", (payload.get("description") or "").strip())
        set_field(entries, "tags", split_tags(payload.get("tags")))
    elif kind == "note":
        set_field(entries, "title", title)
        set_field(entries, "tags", split_tags(payload.get("tags")))
    elif kind == "journal":
        set_field(entries, "title", title)
    elif kind == "photo":
        caption = (payload.get("caption") or "").strip()
        if not caption:
            raise PublishError("A photo needs a caption.")
        set_field(entries, "title", title or caption)
        set_field(entries, "caption", caption)
        set_field(entries, "alt", (payload.get("alt") or "").strip() or caption)
        set_field(entries, "place", (payload.get("place") or "").strip())
        set_field(entries, "camera", (payload.get("camera") or "").strip())
        image_bytes = decode_image(payload)
        if image_bytes:
            ext = check_image_name(payload.get("image_name", ""))
            old_url = str(get_field(entries, "image") or "")
            old_file = photo_image_path(old_url)
            dest = PHOTO_DIR / f"{old_file.stem if old_file else path.stem}{ext}"
            PHOTO_DIR.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(image_bytes)
            new_url = f"/assets/photos/{dest.name}"
            set_field(entries, "image", new_url)
            if old_file and old_file != dest.resolve() and old_file.exists() and not image_in_use(old_url, ignore=path):
                old_file.unlink()

    write_doc(path, entries, payload.get("body") or "")
    return path


def delete_item(item_id: str):
    kind, path = resolve_item(item_id)
    entries, _ = read_doc(path)
    label = str(get_field(entries, "title") or path.stem)
    image_url = str(get_field(entries, "image") or "") if kind == "photo" else ""
    path.unlink()
    image_file = photo_image_path(image_url)
    if image_file and image_file.exists() and not image_in_use(image_url):
        image_file.unlink()
    return kind, path, label


def decode_image(payload: dict) -> bytes:
    data = payload.get("image_data") or ""
    if not data:
        return b""
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise PublishError("That image couldn't be read — try choosing it again.")


# ---------------------------------------------------------------------------
# Site text: home page, section subtitles, About page, tagline, Instagram
# ---------------------------------------------------------------------------

def load_content() -> dict:
    content = json.loads(json.dumps(DEFAULT_CONTENT))
    if CONTENT_JSON.is_file():
        saved = json.loads(CONTENT_JSON.read_text(encoding="utf-8-sig"))
        for key, value in saved.items():
            if isinstance(value, dict) and isinstance(content.get(key), dict):
                content[key].update(value)
            else:
                content[key] = value
    return content


def config_value(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:(.*(?:\n[ \t]+.*)*)", text, re.M)
    if not m:
        return ""
    first, *rest = m.group(1).split("\n")
    return str(entry_value({"raw": first.strip(), "extra": rest}) or "")


def set_config_value(text: str, key: str, value: str) -> str:
    line = f"{key}: {yaml_str(value)}"
    pattern = re.compile(rf"^{re.escape(key)}:.*(?:\n[ \t]+.*)*$", re.M)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    return text.rstrip("\n") + "\n" + line + "\n"


def get_site() -> dict:
    content = load_content()
    about_entries, about_body = read_doc(ABOUT_MD)
    config = CONFIG_YML.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    return {
        "ok": True,
        "home_title": content["home"]["title"],
        "home_title_em": content["home"]["title_em"],
        "home_intro": content["home"]["intro"],
        **{f"lede_{k}": v for k, v in content["ledes"].items()},
        "instagram": content.get("instagram", ""),
        "about_title": str(get_field(about_entries, "title") or "About"),
        "about_body": about_body.strip("\n"),
        "tagline": config_value(config, "tagline"),
        "description": config_value(config, "description"),
    }


def save_site(payload: dict):
    def text(key):
        return (payload.get(key) or "").strip()

    if not text("tagline"):
        raise PublishError("The tagline can't be empty.")
    if not text("about_title"):
        raise PublishError("The About page needs a title.")

    content = load_content()
    content["home"].update(title=text("home_title"), title_em=text("home_title_em"),
                           intro=(payload.get("home_intro") or "").strip())
    for key in content["ledes"]:
        content["ledes"][key] = text(f"lede_{key}")
    content["instagram"] = text("instagram").lstrip("@")
    write_text(CONTENT_JSON, json.dumps(content, indent=2, ensure_ascii=False) + "\n")

    entries, _ = read_doc(ABOUT_MD)
    set_field(entries, "title", text("about_title"))
    write_doc(ABOUT_MD, entries, payload.get("about_body") or "")

    config = CONFIG_YML.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    updated = config
    for key in ("tagline", "description"):
        if config_value(updated, key) != text(key):
            updated = set_config_value(updated, key, text(key))
    if updated != config:
        write_text(CONFIG_YML, updated)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def _cli_guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except PublishError as e:
        print(str(e))
        sys.exit(1)


def _cli_created(path, args, open_file=True):
    print(f"Created {rel(path)}")
    if open_file and not getattr(args, "no_open", False):
        open_in_editor(path)
    if args.publish:
        print(_cli_guard(publish))
    else:
        print("When you're ready, run: python publish.py push")


def cmd_essay(args):
    _cli_created(_cli_guard(build_essay, args.title, args.description or "", args.tags or ""), args)


def cmd_note(args):
    _cli_created(_cli_guard(build_note, args.title or "", args.tags or ""), args)


def cmd_journal(args):
    _cli_created(_cli_guard(build_journal, args.title or ""), args)


def cmd_photo(args):
    path = _cli_guard(build_photo_from_path, args.image, args.caption,
                      args.title or "", args.alt or "", args.place or "", args.camera or "")
    _cli_created(path, args, open_file=False)


def cmd_push(args):
    print(_cli_guard(publish, args.message))


# ---------------------------------------------------------------------------
# Local admin server
# ---------------------------------------------------------------------------

class AdminHandler(BaseHTTPRequestHandler):
    server_version = "QuiddityAdmin"

    def log_message(self, fmt, *a):
        pass

    # -- plumbing --------------------------------------------------------

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self) -> bool:
        # Blocks DNS-rebinding: only answer requests addressed to this machine.
        return self.headers.get("Host", "") in self.server.allowed_hosts

    def _post_ok(self) -> bool:
        # Blocks other websites open in your browser from quietly posting here: they'd
        # send a foreign Origin, and a JSON content type forces a CORS preflight we never approve.
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in self.server.allowed_hosts}:
            return False
        return self.headers.get("Content-Type", "").split(";")[0].strip() == "application/json"

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_REQUEST_BYTES:
            raise PublishError("That's too large to upload — try a smaller image (under ~40 MB).")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise PublishError("The request was garbled — try again.")
        if not isinstance(data, dict):
            raise PublishError("The request was garbled — try again.")
        return data

    def _changed(self, path, payload, message):
        result = {"ok": True, "path": rel(path) if path.exists() else path.relative_to(ROOT).as_posix()}
        if payload.get("publish"):
            try:
                result["message"] = publish(message)
                result["published"] = True
            except PublishError as e:
                result["published"] = False
                result["publish_error"] = str(e)
        return result

    # -- routes ----------------------------------------------------------

    def do_GET(self):
        if not self._host_ok():
            self.send_error(403)
            return
        url = urlsplit(self.path)
        path = unquote(url.path)
        try:
            if path in ("/", "/index.html"):
                self._send_file(ADMIN_DIR / "index.html")
            elif path == "/admin/app.js":
                self._send_file(ADMIN_DIR / "app.js")
            elif path.startswith("/assets/"):
                target = (ROOT / path.lstrip("/")).resolve()
                if ASSETS_DIR.resolve() in target.parents:
                    self._send_file(target)
                else:
                    self.send_error(404)
            elif path == "/api/status":
                self._send_json(200, {"ok": True, **git_status()})
            elif path == "/api/items":
                self._send_json(200, {"ok": True, "items": list_items()})
            elif path == "/api/item":
                self._send_json(200, get_item(parse_qs(url.query).get("id", [""])[0]))
            elif path == "/api/site":
                self._send_json(200, get_site())
            else:
                self.send_error(404)
        except PublishError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"Something went wrong: {e}"})

    def do_POST(self):
        if not self._host_ok() or not self._post_ok():
            self._send_json(403, {"ok": False, "error": "Request blocked."})
            return
        route = urlsplit(self.path).path
        try:
            payload = self._read_json()
            get = payload.get
            if route == "/api/essay":
                path = build_essay(get("title", ""), get("description", ""), get("tags", ""), get("body", ""))
                result = self._changed(path, payload, f"Add essay: {get('title', '').strip()}")
            elif route == "/api/note":
                path = build_note(get("title", ""), get("tags", ""), get("body", ""))
                result = self._changed(path, payload, f"Add note: {get('title', '').strip() or path.stem}")
            elif route == "/api/journal":
                path = build_journal(get("title", ""), get("body", ""))
                result = self._changed(path, payload, f"Add journal entry: {path.stem}")
            elif route == "/api/photo":
                path = build_photo_from_bytes(
                    decode_image(payload), get("image_name", ""), get("caption", ""), get("title", ""),
                    get("alt", ""), get("place", ""), get("camera", ""), get("body", ""))
                result = self._changed(path, payload, f"Add photo: {get('title', '').strip() or get('caption', '').strip()}")
            elif route == "/api/item/update":
                path = update_item(payload)
                kind, _ = resolve_item(rel(path))
                result = self._changed(path, payload, f"Edit {KIND_LABEL[kind]}: {get('title', '').strip() or path.stem}")
            elif route == "/api/item/delete":
                kind, path, label = delete_item(get("id", ""))
                result = self._changed(path, payload, f"Delete {KIND_LABEL[kind]}: {label}")
            elif route == "/api/site":
                save_site(payload)
                result = self._changed(CONTENT_JSON, payload, "Update site text")
            elif route == "/api/publish":
                result = {"ok": True, "message": publish(get("message") or None)}
            else:
                self._send_json(404, {"ok": False, "error": "Unknown action."})
                return
            self._send_json(200, result)
        except PublishError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"Something went wrong: {e}"})


def cmd_admin(args):
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AdminHandler)
    server.allowed_hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Quiddity admin running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Quiddity publishing helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("admin", help="Open the site editor in your browser")
    p.add_argument("--port", type=int, default=8971)
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser window")
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
