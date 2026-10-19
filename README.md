# ytxt

Download a YouTube video's subtitles or automatically generated captions as a
plain text file to give to ChatGPT for discussion. No API key is needed.

This project brings the original desktop script from `~/.local/bin/ytxt` into
one installable Python package for desktop and Android/Termux. The default
command stays the same:

```sh
ytxt 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
```

On desktop, the transcript is saved as `~/Downloads/<video title>.txt`; Termux
uses Android's shared Downloads folder. Files have one caption per line and
no timestamps. English captions are requested by default. Manually
created captions are preferred over automatically generated captions in the
same language. Repeating a download with the same title overwrites that file.

## Install on a desktop

Requires Git and Python 3.10–3.14. On Debian/Ubuntu:

```sh
sudo apt install git python3 python3-venv
```

Replace `REPOSITORY_URL` below with this project's Git clone URL:

```sh
git clone REPOSITORY_URL ytxt
cd ytxt
sh install.sh
```

The installer creates a private environment at `~/.local/share/ytxt/venv` and
links the command into `~/.local/bin`. If that folder is not already in your
PATH, add this line to your shell configuration (for example `~/.bashrc`):

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Open a new terminal after changing PATH. An existing standalone `ytxt` command
is backed up next to the command before replacement. Installation does not
need `sudo` and does not install packages into the system Python.

## Install on Android with Termux

Run these commands inside Termux. Keep the repository and its Python
environment in Termux's private home directory:

```sh
pkg update
pkg install git python python-pip
termux-setup-storage
git clone REPOSITORY_URL ytxt
cd ytxt
sh install.sh
```

Allow the Android storage permission requested by `termux-setup-storage`.
The command is linked into Termux's `$PREFIX/bin`, which is already on PATH.
Transcripts default to `~/storage/downloads`, Termux's link to Android's shared
Download folder, so other Android apps can open and share them:

```sh
ytxt 'https://youtu.be/dQw4w9WgXcQ'
```

On a standard Termux installation, this is
`/data/data/com.termux/files/home/storage/downloads/`.

If shared storage is unavailable, `ytxt` asks you to run `termux-setup-storage`.
You can also choose another directory with `--output-dir`, or set a persistent
preference in `~/.bashrc` (or the configuration file for your shell):

```sh
export YTXT_OUTPUT_DIR="$HOME/storage/downloads/transcripts"
```

## Usage

```sh
# Full URLs, shortened URLs, Shorts, live, embed URLs, and video IDs work.
ytxt 'https://youtu.be/dQw4w9WgXcQ'
ytxt dQw4w9WgXcQ

# Choose the destination for one invocation.
ytxt 'https://youtu.be/dQw4w9WgXcQ' -d ~/Documents/transcripts

# Request Spanish captions, falling back to English.
ytxt 'https://youtu.be/dQw4w9WgXcQ' --languages es en

ytxt --help
ytxt --version
```

Quote URLs so that shell characters such as `&` stay part of the URL.
`--output-dir` overrides `YTXT_OUTPUT_DIR`, which overrides the device default
(`~/Downloads` on desktop, `~/storage/downloads` in Termux).
The output directory is created as needed. If the title cannot be fetched, the
video ID is used as the filename. Unsafe filename characters are replaced.

This downloads existing captions; it does not transcribe audio or send anything
to ChatGPT. Videos without accessible captions cannot be downloaded. YouTube
can also block or rate-limit requests. Errors are printed to stderr with a
nonzero exit code. See the
[upstream transcript API documentation](https://github.com/jdepoix/youtube-transcript-api)
for supported caption behavior and service limitations.

## Update any device

From that device's clone:

```sh
git pull --ff-only
sh install.sh
```

The source and Python dependency declaration live in Git. Each device has its
own installed environment and output-directory preference. Downloaded
transcripts and virtual environments are not part of the source backup.

## Develop and sync changes

Use an editable installation on a device where you develop:

```sh
sh install.sh --dev
```

Changes to `src/ytxt/` then take effect immediately. Keep the clone in place.
After changing dependencies in `pyproject.toml`, rerun `sh install.sh --dev`.
Tests use Python's built-in test runner and mock YouTube requests:

```sh
~/.local/share/ytxt/venv/bin/python -m unittest discover -s tests -v
```

Make changes in a branch, run the tests, then commit and push to the shared
remote. Pull those changes on other devices and rerun the installer. GitHub
Actions runs the tests on pushes and pull requests.

```sh
git switch -c feature/my-change
# Edit the files and run the tests.
git add src tests pyproject.toml README.md install.sh .gitignore .github
git commit -m "Describe the change"
git push -u origin feature/my-change
```

The current package version is in `src/ytxt/__init__.py`. The CLI lives in
`src/ytxt/cli.py`; installation and dependencies are defined by `pyproject.toml`.

## Connect the local repository to GitHub

After creating an empty repository on GitHub, connect this local repository
and push its commits:

```sh
git remote add origin REPOSITORY_URL
git push -u origin main
```

Use the real remote URL in place of `REPOSITORY_URL`. Once pushed, new devices
can use the clone-and-install instructions above.

If starting from a copy of these files without Git history, first run
`git init -b main`, `git add .`, and
`git commit -m "Import ytxt with desktop and Termux installation"`.

## Installer overrides

`PYTHON` selects the Python executable. `YTXT_HOME` changes the application
directory (the installer puts `venv/` inside it); `YTXT_BIN_DIR` changes where
the command link is placed. Use the same overrides when reinstalling or
updating. For example:

```sh
PYTHON=python3.12 sh install.sh
```

Alternatively, install using standard Python tooling in an existing virtual
environment with `python -m pip install .`, or `python -m pip install -e .`
for development.
