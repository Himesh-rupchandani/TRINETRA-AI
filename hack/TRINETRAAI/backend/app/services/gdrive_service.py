"""
Google Drive video ingestion for the multi-video analysis feature.

Only *shareable* ("Anyone with the link") Drive files are supported — the user
is never asked for Google credentials and no OAuth token is stored. A link
that is private, deleted, quota-blocked or not a video fails with a clear,
actionable message instead of silently producing an empty analysis.

Download strategy (Drive has several redirect shapes, none of them stable):
  1. Extract the file id from any of the documented URL layouts.
  2. HEAD/GET ``https://drive.usercontent.google.com/download?id=…&export=download``
     which is the endpoint Drive itself redirects to today.
  3. If Drive answers with the HTML "virus scan warning" interstitial, parse the
     hidden form fields and re-POST them (this is the supported large-file flow).
  4. Fall back to the legacy ``https://drive.google.com/uc?export=download&id=…``.
Anything that still returns HTML is treated as "not accessible".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import httpx

from ..core.config import settings
from ..core.logging_config import logger

DRIVE_HOSTS = {
    "drive.google.com",
    "www.drive.google.com",
    "docs.google.com",
    "drive.usercontent.google.com",
}

_FILE_ID_PATTERNS = (
    re.compile(r"/file/d/([a-zA-Z0-9_-]{10,})"),
    re.compile(r"/document/d/([a-zA-Z0-9_-]{10,})"),
    re.compile(r"/d/([a-zA-Z0-9_-]{10,})"),
)

USERCONTENT_URL = "https://drive.usercontent.google.com/download"
LEGACY_URL = "https://drive.google.com/uc"

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


class DriveError(Exception):
    """Raised for every user-facing Google Drive failure (message is shown in the UI)."""


@dataclass
class DriveLink:
    file_id: str
    normalized_url: str


@dataclass
class DriveFileInfo:
    file_id: str
    file_name: Optional[str]
    size_bytes: Optional[int]
    content_type: Optional[str]
    accessible: bool
    reason: Optional[str] = None


class _ConfirmFormParser(HTMLParser):
    """Pull the hidden inputs out of Drive's 'can't scan for viruses' page."""

    def __init__(self) -> None:
        super().__init__()
        self.action: Optional[str] = None
        self.fields: Dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "form" and self.action is None:
            self.action = a.get("action")
        elif tag == "input" and a.get("name"):
            self.fields[a["name"]] = a.get("value", "")


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def parse_drive_url(url: str) -> DriveLink:
    """
    Validate a Google Drive share URL and extract its file id.

    Raises DriveError with a human-readable message for anything unusable.
    """
    raw = (url or "").strip()
    if not raw:
        raise DriveError("Paste a Google Drive share link first.")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except Exception:
        raise DriveError("That does not look like a valid URL.")

    host = (parsed.hostname or "").lower()
    if host not in DRIVE_HOSTS:
        raise DriveError(
            f"'{host or raw}' is not a Google Drive link. "
            "Use a drive.google.com share link, or upload the file directly."
        )

    file_id: Optional[str] = None
    for pattern in _FILE_ID_PATTERNS:
        m = pattern.search(parsed.path)
        if m:
            file_id = m.group(1)
            break
    if not file_id:
        qs = parse_qs(parsed.query or "")
        for key in ("id", "docid"):
            if qs.get(key):
                file_id = qs[key][0]
                break
    if not file_id:
        raise DriveError(
            "Could not find a file id in that link. Use the 'Share → Copy link' "
            "URL of a single file (https://drive.google.com/file/d/FILE_ID/view)."
        )
    if "/folders/" in parsed.path:
        raise DriveError("That link points to a Drive *folder*. Share the individual video file instead.")

    return DriveLink(
        file_id=file_id,
        normalized_url=f"https://drive.google.com/file/d/{file_id}/view",
    )


# ---------------------------------------------------------------------------
# Reachability probe (no download)
# ---------------------------------------------------------------------------

def _filename_from_disposition(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    m = re.search(r"filename\*=UTF-8''([^;]+)", value)
    if m:
        from urllib.parse import unquote

        return unquote(m.group(1)).strip('"')
    m = re.search(r'filename="?([^";]+)"?', value)
    return m.group(1).strip() if m else None


def probe(url: str, timeout: float = 20.0) -> DriveFileInfo:
    """
    Check whether a Drive link points at a downloadable file, without
    transferring the body. Never raises for access problems — the outcome is
    reported in ``accessible`` / ``reason`` so the UI can show it verbatim.
    """
    link = parse_drive_url(url)  # may raise DriveError for malformed links
    params = {"id": link.file_id, "export": "download"}
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            with client.stream("GET", USERCONTENT_URL, params=params) as resp:
                ctype = (resp.headers.get("content-type") or "").lower()
                name = _filename_from_disposition(resp.headers.get("content-disposition"))
                size = resp.headers.get("content-length")
                if resp.status_code == 404:
                    return DriveFileInfo(link.file_id, None, None, ctype, False,
                                         "Google Drive says this file does not exist (404).")
                if resp.status_code == 403:
                    return DriveFileInfo(link.file_id, None, None, ctype, False,
                                         "Access denied. Set the file's sharing to "
                                         "'Anyone with the link — Viewer'.")
                if "text/html" in ctype:
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > 200_000:
                            break
                    text = body.decode("utf-8", "ignore")
                    if "confirm" in text and "download" in text.lower():
                        # Large-file interstitial: the file IS reachable.
                        parser = _ConfirmFormParser()
                        parser.feed(text)
                        return DriveFileInfo(
                            link.file_id,
                            _guess_name_from_html(text) or name,
                            None, "video/*", True, None,
                        )
                    return DriveFileInfo(
                        link.file_id, None, None, ctype, False,
                        "This Drive file is not publicly shared. Open it in Drive, choose "
                        "'Share', and set access to 'Anyone with the link'.",
                    )
                return DriveFileInfo(
                    link.file_id,
                    name,
                    int(size) if size and size.isdigit() else None,
                    ctype,
                    True,
                    None,
                )
    except httpx.HTTPError as exc:
        return DriveFileInfo(link.file_id, None, None, None, False,
                             f"Could not reach Google Drive: {exc}")


def _guess_name_from_html(text: str) -> Optional[str]:
    m = re.search(r"<span class=\"uc-name-size\"><a[^>]*>([^<]+)</a>", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"<title>([^<]+)</title>", text)
    if m:
        return m.group(1).replace(" - Google Drive", "").strip() or None
    return None


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download(url: str, dest_dir: Path, timeout: float = 60.0,
             max_bytes: Optional[int] = None) -> Tuple[Path, str]:
    """
    Download a shared Drive video into ``dest_dir``.

    Returns (path, resolved_file_name). Raises DriveError with a message that
    is safe to display to the user.
    """
    link = parse_drive_url(url)
    max_bytes = max_bytes or int(getattr(settings, "MAX_UPLOAD_SIZE_MB", 250)) * 1024 * 1024
    dest_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        try:
            resp = _open_download(client, link.file_id)
        except DriveError:
            raise
        except httpx.HTTPError as exc:
            # No network, DNS failure, TLS reset, timeout… The operator gets a
            # sentence they can act on instead of a 500.
            raise DriveError(
                "Could not reach Google Drive from this server "
                f"({type(exc).__name__}). Check the server's internet access, or "
                "download the video and upload the file directly."
            )
        ctype = (resp.headers.get("content-type") or "").lower()
        name = _filename_from_disposition(resp.headers.get("content-disposition"))

        if "text/html" in ctype:
            resp.close()
            raise DriveError(
                "Google Drive returned a web page instead of the video. The file is "
                "most likely private — set sharing to 'Anyone with the link', or "
                "upload the file directly."
            )

        file_name = name or f"gdrive_{link.file_id}.mp4"
        suffix = Path(file_name).suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            if ctype.startswith("video/"):
                file_name = f"{Path(file_name).stem or link.file_id}.mp4"
            else:
                resp.close()
                raise DriveError(
                    f"'{file_name}' is not a supported video "
                    f"({', '.join(sorted(VIDEO_SUFFIXES))})."
                )

        target = _unique_path(dest_dir, file_name)
        written = 0
        try:
            with target.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 512):
                    written += len(chunk)
                    if written > max_bytes:
                        raise DriveError(
                            f"Video exceeds the {max_bytes // (1024 * 1024)} MB limit."
                        )
                    fh.write(chunk)
        except DriveError:
            target.unlink(missing_ok=True)
            raise
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise DriveError(f"Download from Google Drive failed: {exc}")
        finally:
            resp.close()

        if written == 0:
            target.unlink(missing_ok=True)
            raise DriveError("Google Drive returned an empty file.")

    logger.info(f"[GDRIVE] Downloaded {file_name} ({written} bytes) from {link.normalized_url}")
    return target, file_name


def _open_download(client: httpx.Client, file_id: str) -> httpx.Response:
    """Open a streaming response for a Drive file, handling the confirm page."""
    params = {"id": file_id, "export": "download"}
    req = client.build_request("GET", USERCONTENT_URL, params=params)
    resp = client.send(req, stream=True)
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" not in ctype:
        return resp

    # Virus-scan interstitial → replay its form.
    body = resp.read()
    resp.close()
    text = body.decode("utf-8", "ignore")
    parser = _ConfirmFormParser()
    parser.feed(text)
    if parser.action and parser.fields:
        req = client.build_request("GET", parser.action, params=parser.fields)
        confirmed = client.send(req, stream=True)
        if "text/html" not in (confirmed.headers.get("content-type") or "").lower():
            return confirmed
        confirmed.close()

    # Legacy endpoint as a last resort.
    req = client.build_request(
        "GET", LEGACY_URL, params={"id": file_id, "export": "download", "confirm": "t"}
    )
    return client.send(req, stream=True)


def _unique_path(directory: Path, file_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("._") or "gdrive_video.mp4"
    target = directory / safe[:120]
    if not target.exists():
        return target
    stem, ext = target.stem, target.suffix
    i = 2
    while (directory / f"{stem}_{i}{ext}").exists():
        i += 1
    return directory / f"{stem}_{i}{ext}"
