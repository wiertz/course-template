import argparse
import shutil
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import yaml
from babel.dates import format_date
from watchdog.events import RegexMatchingEventHandler
from watchdog.observers import Observer

# Resolve paths relative to package
PKG = Path(__file__).parent
TEMPLATE = PKG / "templates" / "default.html"
ASSETS = PKG / "assets"
SKELETON = PKG / "skeleton"

# Resolve paths for content based on working dir 
SRC_PATH = Path(".")
DST_PATH = SRC_PATH / "_site"
TMP_DIR = SRC_PATH / "_tmp"
COURSE_YAML = SRC_PATH / "course.yaml"
DEPLOY_YAML = SRC_PATH / "deploy.yaml"

# Set language from metadata (default to German)
LANG = yaml.safe_load(COURSE_YAML.read_text()).get("lang", "de") if COURSE_YAML.exists() else "de"


def is_ignored_path(path: Path) -> bool:
    return any(part.startswith(("_", ".")) for part in path.parts)


def build_page(src: Path, dst: Path, base: str, extra_flags: list[str] | None = None) -> None:
    extra_flags = extra_flags or []

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pandoc",
            str(src),
            "--template",
            str(TEMPLATE),
            "--metadata-file",
            str(COURSE_YAML),
            "--metadata",
            f"base:{base}",
            "--citeproc",
            "--output",
            str(dst),
            *extra_flags,
        ],
        check=True,
    )


def collect_listing(path: Path) -> list[dict]:
    entries = [
        (meta_file.parent, yaml.safe_load(meta_file.read_text(encoding="UTF-8")))
        for meta_file in path.glob("*/index.yaml")
    ]
    entries.sort(key=lambda x: x[1].get("date", date(2100, 1, 1)))
    return [
        {
            "title": meta.get("title", "N/A"),
            "date": format_date(meta["date"], format="EE, dd. MMMM", locale=LANG)
            if meta.get("date")
            else None,
            "time": meta.get("time"),
            "description": meta.get("description"),
            "url": "/" + str(folder.relative_to(SRC_PATH) / "index.html"),
        }
        for folder, meta in entries
    ]


def write_listing(path: Path) -> Path:
    out = TMP_DIR / f"{path.name}.yaml"
    out.write_text(
        yaml.dump({"listing": collect_listing(path)}, allow_unicode=True),
        encoding="UTF-8",
    )
    return out


def is_out_of_date(dst, sources) -> bool:
    if not dst.exists():
        return True
    dst_mtime = dst.stat().st_mtime
    return any(s.stat().st_mtime > dst_mtime for s in sources)


def sync_tree(src_dir: Path, dst_dir: Path, exclude_ext=None) -> None:
    exclude_ext = exclude_ext or []
    for src in src_dir.rglob("*"):
        if src.is_dir() or src.suffix in exclude_ext or is_ignored_path(src):
            continue
        dst = dst_dir / src.relative_to(src_dir)
        if is_out_of_date(dst, [src]):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def build(base: str = "") -> None:
    print("Building")

    # If the previous build used a different base, URLs in generated pages
    # are stale. Force clean rebuild in that case or if no marker exists.
    base_marker = DST_PATH / ".base"
    prev_base = base_marker.read_text() if base_marker.exists() else None
    if prev_base != base:
        clean()

    deps = [COURSE_YAML, TEMPLATE]

    for src in SRC_PATH.rglob("*.md"):
        if is_ignored_path(src):
            continue
        rel = src.relative_to(SRC_PATH)
        dst = (DST_PATH / rel).with_suffix(".html")
        page_deps = list(deps)
        flags = []

        meta_file = src.with_suffix(".yaml")
        if meta_file.exists():
            flags += ["--metadata-file", str(meta_file)]
            page_deps.append(meta_file)

        if src.name == "listing.md":
            dst = dst.with_name("index.html")
            listing_deps = list(src.parent.glob("*/index.*"))
            page_deps += listing_deps
            flags += ["--metadata-file", str(write_listing(src.parent))]

        if is_out_of_date(dst, [src, *page_deps]):
            build_page(src, dst, base, extra_flags=flags)

    sync_tree(SRC_PATH, DST_PATH, exclude_ext=[".md", ".yaml", ".yml", ".json"])
    sync_tree(ASSETS, DST_PATH / "assets")

    DST_PATH.mkdir(parents=True, exist_ok=True)
    base_marker.write_text(base)

    print("Finished building")


def serve():
    print("Serving")
    build()
    subprocess.run(
        [sys.executable, "-m", "http.server", "8000", "-d", str(DST_PATH)], check=True
    )


def clean():
    print("Cleaning")
    shutil.rmtree(DST_PATH, ignore_errors=True)


class RebuildHandler(RegexMatchingEventHandler):
    def __init__(self, delay=0.3):
        super().__init__(
            ignore_regexes=[
                r".*/[._].*",  # any path component starting with _ or .
                r".*~$",       # editor backups (file~)
            ],
            ignore_directories=True,
        )
        self.delay = delay
        self._timer = None
        self._lock = threading.Lock()

    def _trigger(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self._run)
            self._timer.start()

    def _run(self):
        try:
            build()
        except Exception as e:
            print(f"Build failed: {e}")

    def on_any_event(self, event):
        print(event.event_type, event.src_path)
        self._trigger()


def watch():
    build()
    handler = RebuildHandler()
    observer = Observer()

    # Watch course content (changes to template require manual rebuild)
    observer.schedule(handler, str(SRC_PATH), recursive=True)
    observer.start()

    print("Watching for changes. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def deploy():
    print("Deploying")
    if not DEPLOY_YAML.exists():
        sys.exit("deploy.yaml missing — cp deploy.example.yaml deploy.yaml")
    cfg = yaml.safe_load(DEPLOY_YAML.read_text()) or {}
    build(cfg.get("deploy_base", ""))
    subprocess.run(
        ["rsync", "-az", "--delete", f"{DST_PATH}/" + "/", cfg["deploy_target"]],
        check=True,
    )


def init():
    if COURSE_YAML.exists():
        sys.exit("course.yaml already exists — there is already a course.")
    shutil.copytree(SKELETON, Path("."), dirs_exist_ok=True)
    print("Kurs angelegt.")


def main():

    tasks = {
        "init": init,
        "build": build,
        "serve": serve,
        "clean": clean,
        "watch": watch,
        "deploy": deploy,
    }

    parser = argparse.ArgumentParser(
        prog="course", description="Makes the course website"
    )
    parser.add_argument("task", choices=tasks.keys())
    args = parser.parse_args()
    task = args.task
    if not task == "init" and not COURSE_YAML.exists():
        sys.exit("course.yaml does not exist – run `course init` to create a new course in the current directory.")

    TMP_DIR.mkdir(exist_ok=True, parents=True)
    try:
        tasks[task]()
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
