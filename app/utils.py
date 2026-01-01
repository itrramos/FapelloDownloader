"""
Utility functions for the FapelloDownloader web application.

These functions encapsulate the scraping and downloading logic needed
to fetch media from Fapello profiles.  They are derived from the
original desktop implementation but have been simplified for use in a
Flask server.

The primary entry point is :func:`download_all`, which takes a Fapello
page URL and downloads every media file into a target directory.  A
progress callback can be supplied to receive updates after each file
is saved.
"""

from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Optional, List, Callable

import requests
from bs4 import BeautifulSoup

# HTTP headers used when making requests to Fapello.  A desktop browser
# User‑Agent string is used to avoid blocks that some websites place on
# unknown clients.
HEADERS_FOR_REQUESTS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}


def get_fapello_files_number(url: str) -> int:
    """Return the number of media files available at the given Fapello URL.

    This function first tries to parse the number of media entries from the page
    text (which usually appears as "XX Media").  If that fails it falls back
    to counting links that match the URL pattern `/.../NN/`.

    Args:
        url: A Fapello page URL ending with a slash.

    Returns:
        An integer count of media files.  Returns 0 if no files are found or
        the page cannot be parsed.
    """
    try:
        page = requests.get(url, headers=HEADERS_FOR_REQUESTS, timeout=30)
    except Exception:
        return 0
    soup = BeautifulSoup(page.content, "lxml")

    # Attempt to extract the count from text like "123 Media"
    match = re.search(r"(\d+)\s*Media", soup.get_text())
    if match:
        return int(match.group(1))

    # Fallback: find all numbered links that lead to individual media pages
    pattern = re.compile(f"{re.escape(url)}(\d+)/")
    all_href_links = soup.find_all('a', href=pattern)

    max_number = 0
    for link in all_href_links:
        link_href = link.get('href').rstrip('/')
        link_href_numeric = link_href.split('/')[-1]
        if link_href_numeric.isnumeric():
            max_number = max(max_number, int(link_href_numeric))
    return max_number


def get_fapello_file_url(link: str) -> Tuple[Optional[str], Optional[str]]:
    """Return the direct media URL and file type for an individual media page.

    The returned ``file_type`` will be either ``"image"`` or ``"video"``
    depending on whether the page contains an ``<img>`` or ``<source>`` element.

    Args:
        link: A Fapello media page URL (e.g. ``https://fapello.com/model/123/``).

    Returns:
        A tuple ``(file_url, file_type)``.  If no media is found the tuple
        ``(None, None)`` is returned.
    """
    try:
        page = requests.get(link, headers=HEADERS_FOR_REQUESTS, timeout=30)
    except Exception:
        return None, None
    soup = BeautifulSoup(page.content, "lxml")
    file_element = soup.find("div", class_="flex justify-between items-center")
    if not file_element:
        return None, None
    try:
        # Videos use a <source> tag; images use <img>.
        if 'type="video/mp4' in str(file_element):
            file_tag = file_element.find("source")
            file_url = file_tag.get("src") if file_tag else None
            file_type = "video"
        else:
            img_tag = file_element.find("img")
            file_type = "image"
            file_url = None
            if img_tag:
                # Prefer the highest‑resolution image from srcset if available.
                srcset = img_tag.get("srcset") or img_tag.get("data-srcset")
                if srcset:
                    # srcset is a comma‑separated list of "URL width" entries.  Choose the URL
                    # from the last entry assuming it represents the largest width.
                    try:
                        candidates = [s.strip().split()[0] for s in srcset.split(',') if s.strip()]
                        if candidates:
                            file_url = candidates[-1]
                    except Exception:
                        file_url = None
                # Fallback to src attribute
                if not file_url:
                    file_url = img_tag.get("src")
        return (file_url, file_type) if file_url else (None, None)
    except Exception:
        return None, None


def prepare_filename(file_url: str, index: int, file_type: str) -> str:
    """Construct a friendly filename from the media URL and index."""
    # Use a part of the URL path to derive a stable base name.  Fapello URLs
    # typically contain the model username several segments up the path.  We
    # take the third component from the end (e.g. ``https://.../username/123/
    # something.jpg``) so that all files from the same model have the same
    # prefix.  Append the index and appropriate extension.
    segments = file_url.split("/")
    base_part = segments[-3] if len(segments) >= 3 else segments[-2] if len(segments) >= 2 else segments[-1]
    extension = ".mp4" if file_type == "video" else ".jpg"
    return f"{base_part}_{index}{extension}"


def download_single(base_url: str, target_dir: str, index: int, model_name: str) -> None:
    """Download a single media file.

    Args:
        base_url: The base URL of the Fapello page (ending with a slash).
        target_dir: The path where downloaded files will be stored.
        index: The media index (appended to ``base_url``).
        model_name: The username derived from the URL; used to filter files.
    """
    # Compose the full URL to the individual media page (e.g. .../0/, .../1/)
    link = f"{base_url}{index}"
    file_url, file_type = get_fapello_file_url(link)
    if not file_url or not file_type:
        return
    # Skip files that do not belong to the target model.  The file URL should contain
    # the model name; otherwise the media likely belongs to another user or is a
    # low‑resolution thumbnail.
    if model_name and model_name not in file_url:
        return
    filename = prepare_filename(file_url, index, file_type)
    dest_path = os.path.join(target_dir, filename)
    # Skip download if the file already exists
    if os.path.exists(dest_path):
        return
    try:
        with requests.get(file_url, headers=HEADERS_FOR_REQUESTS, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except Exception:
        # Ignore download errors for individual files
        return


def download_all(
    url: str,
    target_dir: str,
    max_workers: int = 4,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    """Download all media files from a Fapello page.

    This function orchestrates concurrent downloads and optionally reports
    progress via the supplied callback.

    Args:
        url: Fapello page URL (must end with a slash).
        target_dir: Directory where media files should be stored.
        max_workers: Number of threads to use for downloading.
        progress_cb: Optional callable that will be invoked after each file
            is downloaded.  It must accept three positional arguments:
            ``(model_name, current_count, total_count)``.

    Returns:
        The total number of files scheduled for download.  A value of zero
        indicates that either no media files were found or the page could
        not be parsed.
    """
    os.makedirs(target_dir, exist_ok=True)
    total_count = get_fapello_files_number(url)
    # Derive the model name from the URL (e.g. https://fapello.com/model-name/)
    parts = [p for p in url.split('/') if p]
    model_name = parts[-1] if parts and parts[-1] else (parts[-2] if len(parts) >= 2 else '')
    # Thread-safe counter for completed downloads
    current_count = 0
    counter_lock = threading.Lock()

    def download_wrapper(idx: int) -> None:
        nonlocal current_count
        # Download the individual file
        download_single(url, target_dir, idx, model_name)
        if progress_cb:
            # Safely increment the counter and report progress
            with counter_lock:
                current_count += 1
                current = current_count
            try:
                progress_cb(model_name, current, total_count)
            except Exception:
                # Ignore errors in the callback
                pass

    # Use threads rather than processes for better HTTP connection sharing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(download_wrapper, range(total_count)))
    return total_count