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

On desktop, ytxt opens a ChatGPT browser draft by default. Enable the browser
helper once using the steps below. Use `--no-chatgpt` to download only.
Termux keeps downloading without opening ChatGPT.

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
- Prepares `~/.local/share/ytxt/browser/ytxt-chatgpt.user.js` for browser drafts.
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

## Default desktop behavior: a ChatGPT browser draft

```sh
# Download and prepare a browser draft with the transcript selected for upload.
ytxt 'VIDEO_URL'

# Explicit aliases for the default desktop handoff.
ytxt 'VIDEO_URL' --chatgpt
ytxt 'VIDEO_URL' --chatgpt-browser

# Download only.
ytxt 'VIDEO_URL' --no-chatgpt

# Choose a starter request or combine sources.
ytxt 'VIDEO_URL' --prompt-file ~/my-question.txt
ytxt 'VIDEO_URL_1' 'VIDEO_URL_2' --combine comparison.txt --prompt compare

# Reuse an existing file without downloading anything.
ytxt --chatgpt-file "$HOME/Downloads/ytxt/My transcript.txt"
```

After a successful desktop download, ytxt opens a new tab at `chatgpt.com` in
your default browser. Its browser helper fills an editable discussion prompt
and selects the transcript files in ChatGPT's upload control. **It never
presses Send.** Check that the attachments have finished uploading, add your
question, and send when ready. Termux continues downloading without launching
ChatGPT; the browser handoff currently requires a desktop browser.

With `--combine`, only the combined document is selected; otherwise all
successful transcripts and split parts are selected. Repeat `--chatgpt-file`
to include existing `.txt` files. The default request uses your editable
`discussion` template; `--prompt` or `--prompt-file` chooses another.
Browser prompts refer to attachments, since the website cannot read local
filesystem paths. The helper preserves an existing unsent text draft and asks
you to clear or save it before retrying.

### Enable the browser helper once

1. Install [Tampermonkey](https://www.tampermonkey.net/) in your desktop browser.
2. Run `ytxt --install-browser-helper` to print the installed userscript's path.
3. In Tampermonkey, create a new script, replace its contents with the complete
   contents of that file, save it, and enable it. Allow userscripts and access
   to `chatgpt.com` if the browser requests those permissions.
4. Sign in to your ChatGPT account at `https://chatgpt.com/` in that browser.
5. Run ytxt normally. If prompted by the script manager, allow the helper's
   connection to `127.0.0.1`.

The ytxt installer prepares this file automatically:

```text
~/.local/share/ytxt/browser/ytxt-chatgpt.user.js
```

It does not install browser add-ons or enable scripts for you. After an update
that changes the helper, replace the script's contents in Tampermonkey with
the updated installed file. `YTXT_HOME` changes the parent application folder.

If you are already signed in, a missing-control error does not mean you need
to sign in again. Helper versions before 0.4.1 used the same sign-in advice
for both a missing message box and a missing file input. Update ytxt with
`sh install.sh`, replace the script in Tampermonkey, save, reload ChatGPT,
and rerun your command. Updating the Python package alone does not update
the script saved inside Tampermonkey.

The helper recognizes several message-box layouts and attempts to open the
attachment menu when the file input is absent. If its notice asks you to open
the + / attachment menu, do so while the command is waiting. It waits up to
30 seconds for the message box and another 45 seconds for a document input,
then reports which control it could not find. If that still fails even
though manual uploads work, the helper needs another compatibility update.

### Handoff behavior and limitations

ytxt starts a short-lived server bound to `127.0.0.1` on a random port. A random
token authorizes that handoff. Prompt text and transcript contents travel
through this local connection, not through a URL query. The helper runs only
on `chatgpt.com` and activates only for ytxt's marked new-chat links. The
bridge serves the selected file contents, not arbitrary filesystem paths.

The command waits up to 30 seconds for the helper and up to another 180 seconds
for draft preparation, then closes its local server. A missing helper, sign-in
screen, or incompatible composer produces an error while retaining your files
and saved prompt. Retry using `--chatgpt-file`, or use `--no-chatgpt` to download
without the browser handoff. Total attached transcript content is limited to
16 MiB per handoff; ChatGPT can impose additional account limits.

This is a userscript integration with ChatGPT's web interface. Website changes
may require updating the helper. Tests cover draft filling and file selection
against a simulated composer and exercise the real local HTTP bridge. The
live signed-in ChatGPT interface still needs verification in your browser.
No ChatGPT desktop app is required.

### Optional native desktop-app target

```sh
ytxt 'VIDEO_URL' --chatgpt-app
```

`--chatgpt-app` requests a new local chat in the installed ChatGPT desktop app,
prefills an editable prompt, and opens the transcript directory as a workspace.
It lists local file references; automatic attachment chips are not implemented
for this native target. The app can read the referenced files after you send.

This uses OpenAI's documented `codex://new` link with `prompt` and `path`
parameters. It never submits the message. You can add attachments manually
before sending. ytxt does not guarantee synchronization of local desktop chats
into ordinary ChatGPT web history. See the
[official desktop-link documentation](https://learn.chatgpt.com/docs/reference/commands).

The app must be installed on the same computer and registered for `codex://`
links. On Linux, `xdg-open` and `xdg-mime` from `xdg-utils` are required. Check
the [Linux app requirements](https://learn.chatgpt.com/docs/linux/linux-app)
before installing; Ubuntu 22.04 is outside the currently listed supported
Ubuntu versions. The ytxt installer does not install the ChatGPT app or change
your operating system.

Both targets save `prompt.txt` and `draft.json` in a unique folder under
`~/.local/share/ytxt/drafts/` (or your `YTXT_HOME`). The manifest lists the files
and target. A failed handoff returns a nonzero status, prints the saved prompt
location, and retains the downloaded transcripts. An explicit native target
does not fall back to the browser.

Opening the actual Linux app still needs verification on a computer with it
installed. In earlier versions, `--chatgpt` selected the native target; use
`--chatgpt-app` for that behavior now.


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
node tests/browser_helper.test.cjs
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
messages, or call model APIs. The default desktop browser handoff fills a
draft and selects files for upload; `--chatgpt-app` passes draft text and local
file paths to the native app. Caption availability and YouTube rate limits still apply. See the
[upstream transcript API documentation](https://github.com/jdepoix/youtube-transcript-api)
and [Termux documentation](https://github.com/termux/termux-tools/blob/master/doc/termux.1.md.in)
for the underlying services and platform behavior.
