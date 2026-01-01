# Fapello Downloader for ZimaOS / Docker

## Overview

This repository packages the open‑source **Fapello Downloader** as a lightweight
Docker application with a simple web interface for [ZimaOS](https://www.zimaspace.com/).
The original project – written by [Djdefrag](https://github.com/Djdefrag) –
provides a desktop GUI for batch downloading images and videos from
public pages on [Fapello.com](https://fapello.com/).  This adaptation replaces
the desktop GUI with a browser‑based form, allowing you to deploy the
downloader on your ZimaOS server and access it from any device on your
network.

The app works by scraping the target Fapello page, enumerating all available
media, downloading each file concurrently and then packaging the results into a
zip archive for easy retrieval.  All downloaded files are stored on the host
in the persistent `/DATA/AppData/FapelloDownloader/data` directory so they are
retained between container restarts.

![alt text](https://lh3.googleusercontent.com/sitesv/AAzXCkfpY_GndtUG9NjWE6Voug6bOCsP7t6vXodo-Bb9TiseW4Cvkxf8LOPA39YBUOO6UNyb2YbeeuprSHLmj1UAMADSjfG6zMV7iYx1J7diuvtQ0o6rtbGZ_69roE1iS_1wWUtVpTiHVazitSpfRmQ5AG4HyNXIxv_YgHGp39D5TYWmOY3oRwprLBIQSM8JeF7MyUQXN0xE9a0qFVy57wjuDDttOevW9fMpbgZnvqs=w1280)

## Features

### Core functionality

* 📦 **Web‑based interface** – open a modern, responsive form at `/` and paste
  any public Fapello page to start a batch download.  The interface uses
  a colourful purple‑to‑orange gradient theme inspired by modern app design.
* ⚡ **Parallel downloads** – multiple images and videos are downloaded
  concurrently for better performance.  You can choose how many
  simultaneous downloads (1–60) should run when scraping a page.  The
  default of 15 balances speed and network usage.
* 💾 **Persistent storage** – media are saved under
  `/DATA/AppData/FapelloDownloader/data` on the host and exposed via a
  `volumes` mount in `docker-compose.yml`, so files survive container restarts.
* 🧰 **Self‑contained container** – the Docker image is built from a minimal
  Python base and contains all dependencies required to run the application.
* 🛠️ **ZimaOS metadata** – the compose file includes the `x-casaos` block so
  the app can be added to your ZimaOS app store and launched with one click.

### Quality‑of‑life improvements

* 🔄 **Real‑time progress tracking** – after submitting a URL you’re taken
  to a progress page that displays a live counter (`Downloading X / Y`)
  and progress bar.  When the download finishes a ZIP archive becomes
  available to download.
* 🗂️ **Download history** – completed downloads are recorded and listed on
  the History page.  You can redownload an entry, remove individual
  entries, select multiple entries for deletion or clear the entire
  history.  Attempting to download a model that’s already in the history
  prompts you to confirm or cancel the operation.

These enhancements make it easy to manage multiple downloads and avoid
unintentional duplicates while providing visibility into long‑running tasks.

## Quick Start

Follow these steps to build and run the container on your ZimaOS or any
Docker‑enabled system.  The only requirement is a recent version of Docker
and Docker Compose.

1. **Create the data directory**.  On your ZimaOS host run:

   ```bash
   mkdir -p /DATA/AppData/FapelloDownloader/data
   ```

2. **Build the image and start the service**.  From within this repository
   directory run the following command:

   ```bash
   docker compose up -d
   ```

   Docker will build the image from the provided `Dockerfile`, install
   dependencies from `requirements.txt` and launch the container.  It
   exposes the web interface on port **8089** by default.  You can change the
   published port by editing the `ports` section in
   `docker-compose.yml`.

3. **Access the web interface**.  Open a browser and navigate to

   ```
   http://<your-zimaos-host>:8089/
   ```

   Replace `<your-zimaos-host>` with the IP or hostname of your server.  Paste
   a Fapello page URL into the form and press **Download**.  The server
   will gather all available media, compress them into a zip file and
   automatically start a download in your browser.  All files are also
   stored under `/DATA/AppData/FapelloDownloader/data/<model_name>` on your
   server for later access.

## File Structure

This repository contains the following key files:

| Path | Purpose |
| --- | --- |
| `Dockerfile` | Builds a minimal Python image, installs dependencies and starts the Flask web server. |
| `docker-compose.yml` | Defines the service, port mapping, volume mounts and ZimaOS metadata via `x-casaos`. |
| `requirements.txt` | Declares Python dependencies (Flask, Requests, BeautifulSoup4, lxml). |
| `app/utils.py` | Contains functions to scrape Fapello pages and download individual media files. |
| `app/app.py` | Flask entry point exposing routes for the form, download, progress polling and history management. |
| `app/templates/index.html` | Landing page where you paste a Fapello URL and choose concurrency. |
| `app/templates/progress.html` | Displays live progress and a download link when ready. |
| `app/templates/confirm.html` | Warning page shown when attempting to redownload a model already in the history. |
| `app/templates/history.html` | Lists completed downloads and provides deletion controls. |
| `README.md` | This documentation. |

## Notes and Limitations

* **Supported content**: This downloader only works with publicly accessible
  Fapello pages.  Private or paywalled content is not supported.
* **Download duration**: Large pages with many media items can take a long
  time to download.  During the download the web page will be waiting
  for the server to respond.  Closing the tab cancels the download in your
  browser but the server will continue processing in the background.
* **NSFW content**: Fapello hosts adult material.  Ensure you comply with
  your local laws and only download material you are legally permitted to
  access.
* **License**: The original Fapello Downloader is distributed under the MIT
  licence.  See `LICENSE` and `LICENSE.txt` in this repository for details.

## Acknowledgements

This project packages and adapts
[Fapello Downloader](https://github.com/Djdefrag/Fapello.Downloader) by
**Djdefrag** for use on ZimaOS.  All credit for the underlying scraping logic
goes to the original author.  The containerisation and web interface were
created solely to simplify deployment on self‑hosted environments.  If you
find this useful please consider supporting the upstream project.
