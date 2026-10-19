# ytxt

Download YouTube subtitles or automatically generated captions as documents
for discussion with ChatGPT. Works on desktop and Android through Termux.
No API key is needed.

```sh
ytxt 'https://youtu.be/dQw4w9WgXcQ'
```

Each text file includes its title, channel, source URL, caption language and
type, download date, and time range. Captions are joined into readable
paragraphs without rewriting their wording. A companion JSON file preserves
the original caption text and timing.

## Install on a desktop

Requires Git and Python 3.10–3.14. On Debian/Ubuntu:

```sh
sudo apt install git python3 python3-venv
git clone REPOSITORY_URL ytxt
cd ytxt
sh install.sh
```

Replace `REPOSITORY_URL` with this project's Git clone URL. The installer:

- Creates `~/Downloads/ytxt` for transcripts and download history.
- Installs Python dependencies in `~/.local/share/ytxt/venv`.
- Creates editable discussion templates in `~/.local/share/ytxt/templates`.
- Links the command into `~/.local/bin`, backing up any previous standalone
  script beside it.

If `~/.local/bin` is not on PATH, add this to `~/.bashrc` or your shell's
configuration, then open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Installation does not need `sudo` or change the system Python packages.

## Install on Android with Termux

Keep the clone and Python environment inside Termux's private home directory:

```sh
pkg update
pkg install git python python-pip
termux-setup-storage
git clone REPOSITORY_URL ytxt
cd ytxt
sh install.sh
```

Allow the Android storage permission when requested. The installer creates
`~/storage/downloads/ytxt`, which is inside Android's shared Downloads folder.
On a standard installation, its full path is:

```text
/data/data/com.termux/files/home/storage/downloads/ytxt/
```

The command is linked into `$PREFIX/bin`, already on Termux's PATH. The
installer also creates `~/bin/termux-url-opener`: share a video from YouTube
or your browser, select **Termux**, and ytxt downloads its captions. An existing
Share hook is backed up beside the hook before replacement; reinstalling
preserves those backups. Shared text may include a title alongside the URL.

If Android sharing does not launch Termux, check Termux's permission to display
over other apps. You can always run `ytxt 'VIDEO_URL'` in the terminal.

## Your ytxt folder

The desktop default is `~/Downloads/ytxt`; the Termux default is
`~/storage/downloads/ytxt`. The installer creates it before you download
anything. It contains:

```text
ytxt/
  Video title [video-id].txt       # Document for reading or attaching
  Video title [video-id].json      # Original captions, timing, and metadata
  .ytxt/history/                  # Records used to recognize saved downloads
```

Video IDs keep different videos with the same title separate. Different
language, formatting, section, splitting, or prompt options get a filename
suffix so their outputs can coexist. Long titles are shortened safely.

Choose a different folder for one command:

```sh
ytxt 'VIDEO_URL' --output-dir ~/Documents/transcripts
```

Or set a default in your shell configuration. Export it before running the
installer if you want the installer to initialize that folder:

```sh
export YTXT_OUTPUT_DIR="$HOME/Documents/ytxt"
sh install.sh
```

An explicit `--output-dir` takes precedence over `YTXT_OUTPUT_DIR`; both name
the exact destination, with no extra subfolder appended. `ytxt --init` can
create the folder and missing prompt templates again without downloading.

## Readable text, original lines, and timestamps

```sh
# Default: source header and readable paragraphs.
ytxt 'VIDEO_URL'

# Source header and one caption per line.
ytxt 'VIDEO_URL' --raw

# Timestamp each paragraph; combine with --raw to timestamp every caption.
ytxt 'VIDEO_URL' --timestamps
```

Paragraphs are grouped using caption timing and length. Wording, capitalization,
and punctuation are not corrected. Whitespace is normalized in readable
paragraphs; the JSON companion retains the original text.

Headers include a link to the start of the included caption range. English
captions are requested by default; manually created captions are preferred
over automatically generated captions in the same language:

```sh
ytxt 'VIDEO_URL' --languages es en
```

Put URLs before `--languages`, which accepts multiple language codes.

## Extract a section or split a long video

```sh
# Include captions overlapping minutes 12 through 20.
ytxt 'VIDEO_URL' --start 12:00 --end 20:00 --timestamps

# Produce numbered parts with at most 2,000 transcript words each.
ytxt 'VIDEO_URL' --split-words 2000 --timestamps
```

Times accept seconds, `MM:SS`, or `HH:MM:SS`, including fractional seconds.
The start is inclusive and the end is exclusive. Captions overlapping the
requested interval are included whole, so the document may extend slightly
past those boundaries. The JSON companion keeps the full fetched transcript.

Every split part repeats the source information and identifies its part number
and caption time range. The word limit applies to transcript text, excluding
headers and prompts. A caption longer than the limit is split at word
boundaries; portions keep the original caption's timing.

## Download several videos and compare them

```sh
ytxt 'VIDEO_URL_1' 'VIDEO_URL_2'
ytxt 'VIDEO_URL_1' 'VIDEO_URL_2' --combine comparison.txt --prompt compare
```

A relative combined filename is placed inside your ytxt folder. Individual
documents and their JSON companions are still saved. Combined documents retain
each source's header and all split parts in order.

For a list of videos, create a text file with one URL or video ID per line.
Blank lines and lines starting with `#` are ignored:

```sh
ytxt --batch links.txt
ytxt --batch links.txt --combine comparison.txt --prompt compare
```

Full watch URLs, shortened URLs, Shorts, live and embed URLs, and bare video IDs
are accepted. Duplicate IDs in one invocation are processed once. Quote URLs
so shell characters such as `&` stay part of the URL.

If one video fails, other videos continue. A combined document includes the
successful downloads; the command still returns a nonzero status if any item
failed.

## History and refreshing downloads

```sh
ytxt --history
ytxt 'VIDEO_URL' --refresh
```

Repeating a successful request with the same options skips network requests
when its files are present and unchanged. Deleting a file makes that request
download again. Edited saved files are preserved unless you explicitly use
`--refresh`, which redownloads and replaces them.

History is local to each output folder. Keep `.ytxt/history` with your
transcripts if you move the folder. Older files downloaded before this feature
are left in place and are not automatically imported. Refreshing a video whose
title changed can leave its older files in place.

## Editable discussion prompts

```sh
ytxt 'VIDEO_URL' --prompt discussion
ytxt 'VIDEO_URL_1' 'VIDEO_URL_2' --combine comparison.txt --prompt compare
ytxt 'VIDEO_URL' --prompt-file ~/my-discussion-request.txt
```

Prompts are optional and included in the text documents for you to give to
ChatGPT. They do not trigger any AI requests. Edit these files to change the
built-in requests:

```text
~/.local/share/ytxt/templates/discussion.txt
~/.local/share/ytxt/templates/compare.txt
```

The installer creates missing templates and preserves your edits on updates.
Standard Python installations that bypass the shell installer can also use
the packaged templates, or run `ytxt --init` to create editable copies.

## Prepare a ChatGPT desktop-app draft

```sh
ytxt 'VIDEO_URL' --chatgpt
ytxt 'VIDEO_URL' --chatgpt --prompt-file ~/my-question.txt
ytxt 'VIDEO_URL_1' 'VIDEO_URL_2' --combine comparison.txt --chatgpt --prompt compare

# Reuse an existing file without downloading anything.
ytxt --chatgpt --chatgpt-file "$HOME/Downloads/ytxt/My transcript.txt"
```

`--chatgpt` requests a new local chat in the ChatGPT desktop app, prefills an
editable discussion prompt, and opens the transcript directory as its workspace.
The prompt lists the selected local transcript files for the app to read when
you send it. With `--combine`, only the combined document is referenced; otherwise
all successful transcripts and split parts are listed. Repeat `--chatgpt-file`
to include several existing `.txt` files. The default prompt uses your editable
`discussion` template; `--prompt` or `--prompt-file` chooses another.

The draft uses OpenAI's documented `codex://new` desktop link with `prompt` and
`path` parameters. It never submits the message. File references are provided
as local workspace context: **automatic attachment chips are not implemented**.
You can add attachments manually before sending. This opens a local desktop
chat; ytxt does not guarantee synchronization into ordinary ChatGPT web history.
See the [official desktop-link documentation](https://learn.chatgpt.com/docs/reference/commands).

The app must be installed on the same computer and registered for `codex://`
links. On Linux, `xdg-open` and `xdg-mime` from `xdg-utils` are required.
Check the [Linux app requirements](https://learn.chatgpt.com/docs/linux/linux-app)
before installing: Ubuntu 22.04 is outside the currently listed supported
Ubuntu versions. The ytxt installer does not install the ChatGPT app or change
your operating system. This desktop handoff is unavailable inside Termux.

Every request also saves `prompt.txt` and `draft.json` in a unique folder under
`~/.local/share/ytxt/drafts/` (or your `YTXT_HOME`). The manifest lists the files
and desktop link. If the app cannot be launched, ytxt returns a nonzero status,
prints the saved prompt location, and keeps your transcripts. It does not
silently open a browser or submit the prompt through an API.

Tests verify draft preparation and launcher behavior with mocks. Opening and
prefilling the actual Linux app, and any future attachment automation, still
need verification on a computer with the app installed.

## Update and develop across devices

On each device, from its clone:

```sh
git pull --ff-only
sh install.sh
```

For development, install in editable mode:

```sh
sh install.sh --dev
```

Changes to `src/ytxt/` then take effect immediately; keep the clone in place.
Rerun the editable installer after changing dependencies or package metadata.
To update an editable installation, use `sh install.sh --dev` after pulling.

Run the tests with the installed environment:

```sh
~/.local/share/ytxt/venv/bin/python -m unittest discover -s tests -v
```

Tests mock YouTube requests and exercise rendering, history, batch handling,
folder creation, and Share-hook installation. GitHub Actions tests the package
on Python 3.10 and 3.14. Android behavior is simulated in tests; actual phone
permissions and sharing must also be checked on the device.

Make changes in a branch, run the tests, commit, and push. Pull those commits
on other devices and rerun their installer. Git backs up the source and
packaged default templates. Downloaded transcripts, history, installed
environments, and personal template edits remain local to each device.

## Connect the local repository to GitHub

Create an empty repository on GitHub, then connect and push:

```sh
git remote add origin REPOSITORY_URL
git push -u origin main
```

If starting from a copy without Git history, first run `git init -b main`,
`git add .`, and `git commit -m "Import ytxt"`.

## Installer overrides

`PYTHON` selects the Python executable. `YTXT_HOME` changes the application
directory containing `venv/` and `templates/`. `YTXT_BIN_DIR` changes where the
command link is placed. `YTXT_OUTPUT_DIR` selects the transcript folder.
Use absolute paths and the same overrides when reinstalling. Persist
`YTXT_HOME` and `YTXT_OUTPUT_DIR` in your shell configuration when customized.

```sh
PYTHON=python3.12 sh install.sh
```

You can also install into an existing virtual environment with
`python -m pip install .` or `python -m pip install -e .`, then run `ytxt --init`.
On Termux, `ytxt --install-share-hook` installs or repairs the Share hook.

ytxt downloads existing captions; it does not transcribe audio, submit chat
messages, or call model APIs. `--chatgpt` passes draft text and local file paths
to the installed desktop app. Caption availability and YouTube rate limits still apply. See the
[upstream transcript API documentation](https://github.com/jdepoix/youtube-transcript-api)
and [Termux documentation](https://github.com/termux/termux-tools/blob/master/doc/termux.1.md.in)
for the underlying services and platform behavior.
