"""
Flask application for FapelloDownloader.

This web service exposes endpoints to download media from Fapello profiles,
monitor download progress, and manage a history of completed downloads.

Key features:

* A landing page with a form to submit a Fapello URL and choose the number
  of concurrent downloads (1–60).  Submitting the form starts an
  asynchronous download task.
* Real‑time progress updates are exposed via JSON and displayed on a
  progress page.  When the download completes a ZIP archive of the
  downloaded files becomes available for download.
* A history view lists previously downloaded models, with controls to
  delete individual entries, multiple selections or the entire history.
* Duplicate downloads are detected; the user is prompted to confirm or
  cancel if the model has already been downloaded.

The application stores downloaded media and ZIP archives under the
``/downloads`` directory inside the container.  When deployed via
Docker Compose this directory is mapped to a persistent volume on the
host (``/DATA/AppData/FapelloDownloader/data``), ensuring files are
preserved across container restarts.
"""

from __future__ import annotations

import os
import json
import threading
import zipfile
from typing import Dict, Any, List

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    jsonify,
)

from utils import download_all

app = Flask(
    __name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates')
)

# Location for downloads inside the container.  This is mapped to a host
# directory via docker-compose.
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', '/downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Path to the history file.  A JSON list of objects with keys
# ``model`` and ``zip``.  Each entry corresponds to a completed download.
HISTORY_FILE = os.path.join(DOWNLOAD_DIR, 'history.json')

# Global dictionary used to track download progress.  Keys are model names
# and values are dictionaries with keys: ``current``, ``total``, ``status``
# and ``zip_path``.
progress_data: Dict[str, Dict[str, Any]] = {}


def read_history() -> List[Dict[str, str]]:
    """Return the download history as a list of entries.

    Each entry has the form ``{"model": <model_name>, "zip": <zip_filename>}``.
    If the history file does not exist an empty list is returned.
    """
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def write_history(history: List[Dict[str, str]]) -> None:
    """Persist the download history to disk."""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
    except Exception:
        # Silently ignore errors writing history
        pass


def add_history_entry(model_name: str, zip_filename: str) -> None:
    """Add a new entry to the history file."""
    history = read_history()
    history.append({'model': model_name, 'zip': zip_filename})
    write_history(history)


def start_download_task(url: str, model_name: str, target_dir: str, workers: int) -> None:
    """Spawn a background thread to download all media and build a zip archive.

    The progress of the download is recorded in the global ``progress_data``.
    When the download completes the ZIP archive is stored and a history
    entry is written.

    Args:
        url: The Fapello page URL ending with a slash.
        model_name: The username derived from the URL.
        target_dir: Directory where media files will be stored.
        workers: Maximum number of concurrent download workers.
    """
    # Initialise progress tracking
    progress_data[model_name] = {
        'current': 0,
        'total': 0,
        'status': 'downloading',
        'zip_path': '',
    }

    def progress_cb(model: str, current: int, total: int) -> None:
        # Update the progress data for the given model.  Assign the total only
        # when it is nonzero; this allows the front end to display a
        # placeholder until the count is known.
        progress_data[model]['current'] = current
        progress_data[model]['total'] = total

    # Perform downloads and zipping in a worker thread
    def worker() -> None:
        # Download all media files and capture the total count
        total = download_all(url, target_dir, max_workers=workers, progress_cb=progress_cb)
        # Ensure the final values are set even if no progress callback was invoked
        progress_data[model_name]['total'] = total
        # Build ZIP archive
        zip_name = f"{model_name}.zip"
        zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(target_dir):
                for filename in files:
                    abs_path = os.path.join(root, filename)
                    # Use only the filename inside the archive to avoid nested paths
                    zf.write(abs_path, arcname=filename)
        # Update progress data to reflect completion
        progress_data[model_name]['status'] = 'done'
        progress_data[model_name]['zip_path'] = zip_path
        # Record history entry
        add_history_entry(model_name, zip_name)

    threading.Thread(target=worker, daemon=True).start()


@app.route('/', methods=['GET'])
def index() -> str:
    """Render the home page with optional message feedback."""
    message = request.args.get('message')
    return render_template('index.html', message=message)


@app.route('/download', methods=['POST'])
def download_route() -> Any:
    """Handle submission of the download form.

    This route validates the user input, checks if the model has been
    downloaded previously and either prompts for confirmation or starts a
    new background download task and redirects to the progress page.
    """
    url_input = request.form.get('url', '').strip()
    workers_input = request.form.get('workers', '15').strip()
    confirm_flag = request.form.get('confirm', '')  # Non-empty if user confirmed re-download
    # Validate URL
    if not url_input or 'fapello.com' not in url_input:
        return render_template('index.html', message='Please enter a valid Fapello URL starting with https://fapello.com/')
    # Ensure URL ends with a slash
    if not url_input.endswith('/'):
        url_input += '/'
    # Derive model name from the URL path
    parts = [p for p in url_input.split('/') if p]
    if not parts:
        return render_template('index.html', message='The provided URL is incomplete. Please enter a full Fapello page URL.')
    model_name = parts[-1] if parts[-1] else (parts[-2] if len(parts) >= 2 else '')
    target_dir = os.path.join(DOWNLOAD_DIR, model_name)
    # Clamp worker count to [1, 60]
    try:
        workers = int(workers_input)
    except ValueError:
        workers = 15
    workers = max(1, min(60, workers))
    # If the model already exists in history and user has not confirmed, prompt for confirmation
    history = read_history()
    if any(entry['model'] == model_name for entry in history) and not confirm_flag:
        # Render a confirmation page with hidden form fields to carry the user inputs
        return render_template(
            'confirm.html',
            model=model_name,
            url=url_input,
            workers=workers
        )
    # Start the download task
    start_download_task(url_input, model_name, target_dir, workers)
    return redirect(url_for('progress_page', model=model_name))


@app.route('/progress/<model>', methods=['GET'])
def progress_page(model: str) -> str:
    """Render the progress page for the specified model."""
    return render_template('progress.html', model=model)


@app.route('/progress_data/<model>', methods=['GET'])
def progress_json(model: str) -> Any:
    """Return JSON with current progress for the specified model."""
    data = progress_data.get(model)
    if not data:
        # If no progress data exists return a default placeholder
        return jsonify({'current': 0, 'total': 0, 'status': 'unknown'})
    return jsonify({
        'current': data.get('current', 0),
        'total': data.get('total', 0),
        'status': data.get('status', ''),
    })


@app.route('/download-file/<model>', methods=['GET'])
def download_file(model: str) -> Any:
    """Return the completed ZIP archive for the given model, if available."""
    data = progress_data.get(model)
    if not data or data.get('status') != 'done':
        return 'File not ready', 404
    zip_path = data.get('zip_path')
    if not zip_path or not os.path.exists(zip_path):
        return 'File not found', 404
    return send_file(zip_path, as_attachment=True, download_name=os.path.basename(zip_path))


@app.route('/history', methods=['GET', 'POST'])
def history_page() -> Any:
    """Display and manage the download history."""
    history = read_history()
    if request.method == 'POST':
        action = request.form.get('action')
        # Determine which entries have been selected for deletion (if any)
        selected = request.form.getlist('selected')  # list of model names
        if action == 'delete_selected':
            # Delete selected entries
            for model in selected:
                # Remove files and directories
                dir_path = os.path.join(DOWNLOAD_DIR, model)
                zip_file = f"{model}.zip"
                zip_path = os.path.join(DOWNLOAD_DIR, zip_file)
                try:
                    if os.path.isdir(dir_path):
                        import shutil
                        shutil.rmtree(dir_path, ignore_errors=True)
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except Exception:
                    pass
            # Filter history
            history = [entry for entry in history if entry['model'] not in selected]
            write_history(history)
        elif action == 'delete_all':
            # Delete all entries and all associated files
            for entry in history:
                model = entry['model']
                dir_path = os.path.join(DOWNLOAD_DIR, model)
                zip_path = os.path.join(DOWNLOAD_DIR, f"{model}.zip")
                try:
                    if os.path.isdir(dir_path):
                        import shutil
                        shutil.rmtree(dir_path, ignore_errors=True)
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except Exception:
                    pass
            history = []
            write_history(history)
        # Redirect back to GET after POST
        return redirect(url_for('history_page'))
    return render_template('history.html', history=history)


if __name__ == '__main__':
    # Run the development server when invoked directly.  In production the
    # Dockerfile will run ``flask run`` instead.
    port = int(os.environ.get('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, debug=False)