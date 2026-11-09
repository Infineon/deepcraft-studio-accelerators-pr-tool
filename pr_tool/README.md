# DEEPCRAFT&trade; Pull Request Tool

A small Python command-line utility for opening pull requests against Infineon
DEEPCRAFT&trade; GitHub repositories:

* [Infineon/deepcraft-studio-accelerators](https://github.com/Infineon/deepcraft-studio-accelerators) (`--repo accelerators`)
* [Infineon/deepcraft-model-zoo-for-psoc](https://github.com/Infineon/deepcraft-model-zoo-for-psoc) (`--repo model-zoo-psoc`)
* [Infineon/deepcraft-model-zoo-for-aurix](https://github.com/Infineon/deepcraft-model-zoo-for-aurix) (`--repo model-zoo-aurix`) — **metadata file only**; the tool does not fork, push, or open a pull request

The tool wraps `git` and the bundled GitHub CLI (`pr_tool/gh.exe`) to automate the whole workflow
for you:

1. Authenticates using your GitHub account.
2. Forks the selected Infineon repository to your account (or syncs an existing fork).
3. Creates / switches to a branch named after your project.
4. Commits and pushes your project's files (splitting large change sets into
   chunks under GitHub's ~2 GB per-push limit and about 2,500 files per
   commit, so large Data folders stay reliable).
5. Opens the resulting pull request in your browser.

The same command can also be used to **update** an existing pull request &ndash;
just re-run it after making changes to your project.

## Requirements

* **Python 3.10** or newer
* **git 2.43** or newer
  * On Windows, git 2.16.2+ is also accepted &mdash; the tool will run
    `update-git-for-windows` automatically to bring it up to date.
* **GitHub CLI** (`gh`) &mdash; the copy **bundled** as `pr_tool/gh.exe` is used
  when present; otherwise `gh` on your `PATH`. Each binary has its own login
  (install from [cli.github.com](https://cli.github.com/) if needed).
* A **GitHub account**

No additional Python packages are required &mdash; the tool only uses the
standard library.

On startup the tool checks GitHub and updates itself to the latest published
copy, unless you pass `--no-update` or you are running from a git checkout
(use `git pull` in that case). A failed update does not stop the run.

Project image names and tags are read from **`pr_tool/images.json` only**
(shipped with the tool). The catalog is not downloaded from the network.

## Target repositories (`--repo`)

| `--repo` value | GitHub repository | Project layout |
| --- | --- | --- |
| `accelerators` | `Infineon/deepcraft-studio-accelerators` | `accelerator_layout` (DEEPCRAFT&trade; Studio, below) |
| `model-zoo-psoc` | `Infineon/deepcraft-model-zoo-for-psoc` | `model_zoo_psoc_layout` (README + metadata only) |
| `model-zoo-aurix` | `Infineon/deepcraft-model-zoo-for-aurix` | `metadata_only_layout` (metadata-only target: writes `metadata.json`; no publish) |

Every publishing layout requires **`README.md`** and **`metadata.json`** at the project root.
A metadata-only target (currently `model-zoo-aurix`) only writes `metadata.json` and does not publish.

The `--repo` argument is **required** on every run.

## Project layout requirements (`--repo accelerators`)

Before running the tool for **accelerators**, make sure your project directory has the following
layout. The tool validates this before doing anything.

**Required items** (must be present at the project root):

* `README.md`
* `metadata.json`
* `<ProjectName>.improj`
* `Data/`

**Allowed items** (optional, may be present):

* `*.im*` files (other DEEPCRAFT&trade; Studio files)
* `Models/`
* `PreprocessorTrack/`
* `Resources/`
* `Tools/`
* `Units/`

Anything else at the project root will cause the tool to fail with a clear
error message (see [Local git and Python environments](#local-git-and-python-environments)).
Folder and file names are **case-sensitive** and must match exactly
(e.g. `Models/`, not `models/`; `Data/`, not `data/`).
The `Models/` and `PreprocessorTrack/` directories are tracked
in your project but are **not** pushed to GitHub.

The project name **defaults to the project folder's name** and is used as
both the **branch name** and the **PR title prefix** on GitHub (e.g.
`Accelerator MyAudioClassifier`). It must be in **CamelCase**, e.g.
`MyAudioClassifier`. You can override it with `--name <CamelCaseName>` if
the folder name doesn't match the desired project name.

## Project layout requirements (`--repo model-zoo-psoc`)

For the [Model Zoo for PSOC&trade;](https://github.com/Infineon/deepcraft-model-zoo-for-psoc),
the project folder must include **`README.md`** and **`metadata.json`** at its
root. Other files and folders at the root are allowed (for example deployment
code, HEX files, or model assets).

The project name defaults to the project folder name and is used as the
**branch name** on GitHub (for example `ArcFace`, `Yolov8nPose`, or
`EfficientNetV2-S`). The pull request title is `Model Zoo PSOC <project name>`.
It must be safe for a **local folder name and a Git branch**:
letters, digits, `.`, `_`, and `-` are allowed; it must start and end with a
letter or digit; **spaces are not allowed** (and characters such as `\ / : * ? "
< > | ~ ^ [` are rejected).

## Metadata-only targets

A metadata-only target writes `metadata.json` in the folder you pass with `--path` and then stops. It does not fork the repository, push files, or open a pull request. `README.md` is optional. The project name defaults to the folder name and must be folder- and branch-safe (same rules as Model Zoo for PSOC&trade;).

This behavior comes from the target setting, not from a particular repository. `model-zoo-aurix` is the metadata-only target today. Another repository added later with the same setting follows this path automatically; its `metadata.json` fields come from its own schema.

### Model Zoo for AURIX&trade; (`--repo model-zoo-aurix`)

The file matches metadata already published in the [Model Zoo for AURIX&trade;](https://github.com/Infineon/deepcraft-model-zoo-for-aurix):

* `algorithm` is chosen from the list (it is not read from an `.improj` file).
* `kit` / `device` use the AURIX&trade; and TRAVEO&trade; boards from the model zoo. Device is derived from the selected kit.
* `type` is stored as one entry, `Model Development, Model Deployment` (both are selected by default; press Enter to keep them). `workflow` is the matching pair of ML workflow values.
* `brand` defaults to DEEPCRAFT&trade; (press Enter to keep it). A brand already saved in `metadata.json` is offered instead.
* `videos` is optional and is stored after `brand_url`. Press Enter to leave it empty, or type `1` to add one video.
* `links` are filled automatically: a Model Zoo link (with heading) and a GitHub link to `.../tree/main/<project name>` (label and URL only).

```bash
python ./pr_tool.py --repo model-zoo-aurix --path C:\Projects\KeywordDetection
```

## Local git and Python environments

Your project folder may already be a git repo or contain a Python virtual
environment. That is fine: local git data, virtualenvs, and typical Python
cache folders are **not** uploaded. With `--repo accelerators`, they are also
ignored when the tool checks the project root layout.

## Usage

From the directory containing `pr_tool.py`, run:

```bash
python ./pr_tool.py --repo <target> --path <project-path>
```

`<target>` is `accelerators` or `model-zoo-psoc`. `<project-path>` is the
root of your project folder.

The first time you run the tool you will be:

1. Prompted to authenticate with GitHub in your browser (only once &ndash;
   credentials are then cached by `gh`).
2. Shown a **project summary**, then the **main steps**. A metadata-only target
   lists one step, create/review metadata.json. The other targets list that step
   and a second step, create pull request. Each step starts with its own header,
   such as "Step 1 of 2: Create/review metadata.json", in the same white-rule
   header style as the other sections. Without colour (`NO_COLOR` or no terminal) it is plain text. Choose **Yes** to continue or **Abort**.
3. Asked for **metadata** (unless `metadata.json` already exists and you did
   not pass `--override-metadata`). A few fields can be set via CLI flags on
   the first pass; the rest are prompted interactively. Each field you are asked
   shows its place among the questions, such as `(4/15)`, beside the field name.
   Fields the tool fills in automatically are not numbered and not counted: the
   workflow, the copied main image, the project links, the algorithm (unless you
   re-edit it), a domain or device that follows the sensors or kit, and, for an Object Detection or Image Classification project, the sensors and kit. The total
   is worked out from the answers so far, so it can drop once a derived field is
   reached; for example, choosing a microphone removes the domain question.

When metadata is ready, the tool shows a preview and asks:

* **y** &ndash; save `metadata.json`. For a target that opens a pull request, the
  tool then shows a submission summary (target, repository, path, branch),
  names the steps that follow (fork and sync, push, create and open the pull
  request), and asks "Proceed with pull request?" as a y/n menu. Declining keeps the
  saved file and does not fork, push, or open a pull request. A metadata-only
  target stops after saving, with no further question.
* **n** &ndash; modify the metadata (previous values are kept as defaults).
* **a** &ndash; abort without saving.

When the push completes, the tool creates or reuses the pull request (retrying
and using the GitHub API when ``gh pr create`` struggles with very large
diffs), waits until GitHub exposes it (up to about 5 minutes), then opens it
in the browser and prints the PR URL. If creating the pull request still fails, it
opens the GitHub compare page so you can click **Create pull request**, and
also prints fork/repo links plus the compare URL.

When the pull request was just created and the metadata contains values that
are not in the tool's lists, the tool posts a review comment on it. The comment
opens with a bold **NEW VALUES DETECTED** heading and the sentence
"The metadata file of this project contains new values to be reviewed."
Below that, each new catalog entry (a sensor, kit, use case, and so on) and
each new project image is a list line. A new partner is called out in its own
highlighted block. Re-running against an open pull request does not post that
comment again. `pr_comment.py` builds the lines and posts the comment, using
the same `gh` calls as the rest of the tool.

### Interactive metadata

Suggested values for list fields (sensors, domain, kit, …) come from the
DEEPCRAFT&trade; AI Hub catalog. Prompt order matches the metadata schema for
your selected `--repo`. In a terminal, field names in the prompts are shown in green capitals, and a list field's `(s)` is shown as `(S)` in the same style. The metadata.json overview shows its keys in green but in lower case, as they appear in the file. The `====` rule that starts each field prompt stays white. Rules inside a field, such as the ones around a warning or the Notepad confirmation, are grey. The `Current value:` label and retry messages are shown in yellow. Keys you type, the numbers in a choice list, and the field counter such as `(4/15)`, are shown in cyan. `Tag(s)` and `Image` in the project-image prompts are capitals without green. Under the metadata step header, a `Color Code:` line names each colour, and magenta marks other highlighted items such as the `metadata.json` name in the overview heading. Set `NO_COLOR` to turn colour off. The saved file stays plain text. When a field already has a saved value, that value is shown above the input. Enter is listed there and keeps it. Text, metric, and choice prompts then list the same two choices: `1` modifies the current value, which places it on the input line for editing, and `2` types a new value. On a numbered list, that edit line shows the list numbers (`1, 2`) rather than the names. A saved value that is not in the list stays as text. Anything else is refused, so a stray keystroke cannot replace the saved value. On a choice prompt, a number from the list is typed only after `1` or `2`. A metric with no saved value lists Enter as the way to skip it.

| Topic | Behaviour |
| --- | --- |
| **Long description** | The prompt asks for more than one sentence, preferably below 2000 characters. Choose `1` for plain text of any length in the terminal, entered without line breaks, or `2` to open Notepad for plain text, Markdown, or HTML. Notepad opens with a short instruction note labeled [ INSTRUCTIONS ]. Short lines separate its sections. It ends with [ LONG DESCRIPTION ] - Write it below, and the description is written on the following lines. Those instruction lines are not saved, including when some of them are deleted; the remaining text is the description. Press Enter to confirm the text, type `1` to change it in the terminal, or type `2` to open it in Notepad. After plain text, the text you typed is left on the input row. A saved value is shown first. Enter is listed with the other choices and keeps it, `1` replaces it with plain text, and `2` modifies it in Notepad. Headings and images are not accepted. **Plain text** is stored without line breaks. **Markdown** from Notepad is converted to HTML and stored without line breaks. **Text HTML** from Notepad must use the tags in [Long description tags](#long-description-tags). Straight `"` in the text is stored as curly quotes, and HTML attributes use single quotes, so the value stays valid inside `metadata.json`. |
| **Sensors, domain, use case** | Select from the lists the tool shows. Sensors are grouped under their domain, each domain as a column with its sensors listed below it. A domain with more than four sensors continues in the next column, three or four sensors each. A new value is accepted only if none of the listed options fits, and only after you confirm it. Domain follows the sensors: see **Sensors → domain** below. Use cases follow the selected application: see **Application → use case and image** below. |
| **Application → use case and image** | The use-case list, and the project-image names and tags, are limited to the selected application. Smart Home does not offer traffic use cases, and Wearables does not offer industrial images. Several applications show the combined list. The use-case list and the project-image names and tags are limited again by the selected domain, which follows the sensors. Audio does not offer gesture or touch use cases, and a microphone with Smart Home keeps the sound use cases and the audio image tags (`microphone`, `voice`) without radar or camera tags. Several domains show the combined list. When nothing fits both, the list follows the domain. Room and setting images are not tied to a sensor, so they drop out once a domain is selected. Other, or an application or domain with no mapping, skips that side of the filter. A use case already saved in metadata.json stays the current value, including one that is not in the suggested list, and Enter keeps it. An Object Detection project always offers the Object Detection use case, and an Image Classification project always offers Image Classification, even when the filters would leave them out. |
| **Sensors → domain** | When every selected sensor belongs to one domain, that domain is set automatically. Microphone alone is Audio. Camera or TOF camera, including both together, is Vision. Radar, gas, and pressure map to the domain of the same name. UWB, WiFi, and Bluetooth are Radar. Other, or a custom sensor, leaves the full domain list open. Capacitive and inductive sensing are Touch. Current, voltage, and power are Electrical Signals. Temperature and humidity are Temperature and Humidity. IMU, accelerometer, gyroscope, magnetometer, Hall sensor, vibration, torque, RPM, and speed are Motion and Vibration. DPS is Pressure, with the other pressure sensor: Infineon DPS310 and DPS368 are digital barometric pressure sensors. Sensors from different domains select every one of those domains, with no further prompt. |
| **Other choices** (kit, device, …) | Pick by number from the AI Hub list, or type a custom value (one confirmation). These prompts show the same reminder as sensors, domain, and use case: enter a new value only if none of the listed options fits. Custom text is title-cased (`smart home` → `Smart Home`). **Application**, **project type**, and **algorithm** must be chosen from the list, so they do not show that reminder. |
| **Kit → device** | Device is derived from kit(s) and is not asked again when you re-edit metadata. A custom kit name still prompts for device. |
| **Type → workflow** | Pick one or both types (`1,2`); workflow is set automatically. |
| **Brand** | Infineon, a listed partner, or **New Brand/Partner** (custom image + URL). Model Zoo for AURIX&trade; defaults to DEEPCRAFT&trade;. |
| **Links** | Filled automatically (accelerators: Studio + GitHub; model-zoo PSOC&trade;: GitHub; model-zoo AURIX&trade;: Model Zoo + GitHub). |
| **Videos** | Optional. One entry, with `title`, `description`, and a **single-video** `link` (YouTube, Vimeo, Dailymotion, Wistia, Loom, or a direct video file). Title and description are stored as one line. The title is at most 40 characters and the description at most 300. A straight `"` becomes a curly quote so the value stays valid inside `metadata.json`. The prompts use the same layout as the other fields. Press Enter to leave the field empty, or type `1` to add a video. A saved video is kept with Enter, `1` modifies it, and `2` removes it. On the video link, 3 attempts return to this prompt. An empty entry and a rejected link each count as one attempt. An empty `videos` value is left out of `metadata.json`. YouTube playlists, other collections, and regular web pages are rejected. A link with a start time, such as `?t=42` or `#t=30s`, is accepted and saved as typed. An existing `metadata.json` with no `videos` field keeps that omission until you choose to modify the metadata. Modifying the metadata asks for the video together with the other fields. More than one saved video must be replaced by one video or left empty. |
| **Image** | Auto-pick from `images.json` by tags, or choose interactively. `--image` / `--tag` skip the prompt. |
| **Accelerators only** | First pass: `algorithm` from `{Project}.improj` `<ProjectType>`; for `ObjectDetection` / `ImageClassification` also auto-sets `sensors=Camera`, `domain=Vision`, and Edge kit/device. After the metadata overview, choose **n** to re-edit every field (including those defaults). |
| **Model zoo PSOC&trade; only** | `metrics` optional (fixed labels, you enter values). `videos` optional. |
| **Model zoo AURIX&trade; only** | Metadata file only (no pull request). `algorithm` is prompted. Kits and devices are the AURIX&trade;/TRAVEO&trade; boards. `type` is one combined value. `brand` defaults to DEEPCRAFT&trade;. `videos` optional. No `metrics`. |

All fields are required except **videos** (all three targets) and **metrics** on `model-zoo-psoc`. `model-zoo-aurix` does not include metrics. HTML in the long description is optional. Whatever form you enter is stored without line breaks.

### Long description tags

Plain text with none of this markup is stored as plain text. Markdown is converted into the same tags. Images, media, scripts, comments, and any attribute other than `href` are rejected.

| Tag | Use | Status |
| --- | --- | --- |
| `p` | Paragraph | Accepted |
| `br` | Line break | Accepted |
| `h1`–`h6` | Headings. Markdown `#` headings use the same code | Implemented, turned off |
| `ul`, `ol`, `li` | Lists | Accepted |
| `strong`, `b` | Bold | Accepted |
| `em`, `i` | Italic | Accepted |
| `a` | Link. The only allowed attribute is `href` (`http`, `https`, `mailto`, `#fragment`, or a root-relative path) | Accepted |
| `blockquote` | Quotation | Accepted |
| `code` | Inline code | Accepted |
| `pre` | Code block, together with `code` | Accepted |
| `hr` | Horizontal rule | Accepted |

If **`metadata.json` already exists**, the tool loads it first: missing fields
are prompted; values not in the AI Hub–based suggested lists show a warning.
It is common for new projects to use values that are not yet in the catalog,
and a new partner always shows here, as "a new partner, not one of the known
brands". The brand image must be a `.webp` file name, such as `acme.webp`. You
can continue, edit `metadata.json`, or re-run with `--override-metadata`.

### Updating an existing pull request

To push new changes to a pull request you already opened, **just re-run the
exact same command on the same project folder**:

```bash
python ./pr_tool.py --repo <target> --path <project-path>
```

What happens under the hood:

1. The branch name is taken from the project name (which defaults to the
   project folder's name), so a second run resolves to the same branch as the
   first run.
2. The tool sees that branch already exists on your fork and switches to it
   instead of creating a new one. Commit messages change from `Add files` /
   `Add chunk N of M` to `Modify files` / `Modify chunk N of M` on subsequent
   runs.
3. Only the diff against your previous push is committed and pushed (file
   additions, modifications, and deletions are all handled).
4. If a pull request is already **open** for that branch, the tool simply
   **opens it in your browser** &ndash; no new PR is created.

Things to watch out for:

* **Don't rename the project folder between runs** (or, if you must, pass
  `--name <SameCamelCaseName>` explicitly). Otherwise the tool will use a
  different branch and open a **new** pull request alongside the old one.
* **If the pull request was closed or merged on GitHub**, the next run asks
  whether to keep the existing fork branch or reset it and start fresh from
  the current upstream `main`. Keeping the branch is the safe choice when you
  want to preserve its history; resetting it is useful when you want a clean
  PR without old branch history. An **open** PR is left alone and just opened
  in the browser.
* **Changing metadata on a subsequent run** &ndash; edit `metadata.json`
  directly and re-run (changes are pushed like any other file), or use
  `--override-metadata` to regenerate it interactively.

### The `.git_deepcraft` folder

While the tool runs it creates a working directory next to your project:

```
<project-path>/..
├── <ProjectName>/              <- your DEEPCRAFT&trade; Studio project
└── .git_deepcraft/
    └── <repo-key>/             <- e.g. accelerators, model-zoo-psoc
        └── <ProjectName>/      <- git metadata for this project's PR
```

This folder is the tool's separate **git directory** &mdash; it stores all of
git's bookkeeping (objects, refs, branches, remote configuration) for the
pull request, **without** placing a `.git` folder inside your project itself.
That keeps your project directory clean and avoids interfering with any
existing version control you may have there.

Each project uses `.git_deepcraft/<repo-key>/<ProjectName>/`. If you run the
tool for several projects at the same time, each keeps its own subfolder until
that run finishes.

**What happens if you delete it?**

* **After a run:** the tool removes this project's scratch folder and, when
  nothing else is using `.git_deepcraft`, removes the whole `.git_deepcraft`
  directory. The next run recreates it by cloning your fork freshly.
* **Between runs:** deleting it manually is harmless for the same reason.
* **During a run:** the current run will fail, because git can no longer find
  its metadata. Simply re-run the command &mdash; the folder will be
  recreated from scratch.
* **Your pull request is not affected.** All commits already live on GitHub
  (in your fork and on the PR). `.git_deepcraft` is purely local scratch
  space; deleting it never loses any work that has been pushed.

### Common options

| Option | Description |
| --- | --- |
| `--repo <target>` | **Required.** `accelerators` or `model-zoo-psoc` (see table above). |
| `--path <project-path>` | **Required.** Root directory of your project. |
| `--name <CamelCaseName>` | Override the project name (defaults to the directory name). Also becomes the branch name on GitHub. |
| `--title <text>` | Project title (max 40 characters). |
| `--description <text>` | Short project description (max 100 characters). |
| `--sensor <name>` | Target sensor. Run `--help` to see the suggested list. Can be passed multiple times (e.g. `--sensor Microphone --sensor Camera`) to specify more than one sensor. |
| `--image <name>` | Image name to use directly (e.g. `Audio.webp`). Skips the tag-based auto-selection and the interactive image prompt. |
| `--tag <tag>` | Tag used to auto-pick a project image. Can be passed multiple times (e.g. `--tag audio --tag "smart home"`). Skips the interactive image prompt but not the auto-selection step. Not saved to `metadata.json`. |
| `--override-metadata` | Regenerate `metadata.json` from the options above even if one already exists. |
| `--no-update` | Skip the startup check for a newer version of this tool. |
| `--verbose`, `-v` | Print every `git`/`gh` command and captured output (default is short progress lines only). |

For the complete list of options, run:

```bash
python ./pr_tool.py --help
```

### Example

Single sensor:

```bash
python ./pr_tool.py \
  --repo accelerators \
  --path C:\Projects\MyAudioClassifier \
  --title "My audio classifier" \
  --description "Detects three types of household sounds" \
  --sensor Microphone
```

With a specific image (skips the image prompt entirely):

```bash
python ./pr_tool.py \
  --repo accelerators \
  --path C:\Projects\MyMultiModalDetector \
  --title "Multi-modal detector" \
  --description "Combines audio and motion signals" \
  --sensor Microphone \
  --sensor IMU \
  --image Motion.webp
```

With tags for auto-selection (skips the image prompt, auto-picks the best
match):

```bash
python ./pr_tool.py \
  --repo accelerators \
  --path C:\Projects\MyMultiModalDetector \
  --title "Multi-modal detector" \
  --description "Combines audio and motion signals" \
  --sensor Microphone \
  --sensor IMU \
  --tag audio \
  --tag motion
```

Model Zoo for PSOC&trade;:

```bash
python ./pr_tool.py \
  --repo model-zoo-psoc \
  --path C:\Projects\ArcFace \
  --title "ArcFace" \
  --description "Face recognition model for PSOC&trade;" \
  --sensor Camera
```

## Troubleshooting

* **`git version 2.43 or newer is required`** &mdash; install / update git
  from [git-scm.com](https://git-scm.com/). On Windows, the tool will try
  `update-git-for-windows` first.
* **`GitHub CLI (gh) not found`** &mdash; make sure `gh.exe` is present in the
  `pr_tool/` folder next to `pr_tool.py`, or install the GitHub CLI from
  [cli.github.com](https://cli.github.com/) and add it to your `PATH`. At
  startup the tool prints which `gh` binary it is using.
* **`Project name "..." is not CamelCase`** &mdash; with `--repo accelerators`,
  rename the project directory (or pass `--name`) to CamelCase (e.g.
  `MyAudioClassifier`).
* **Invalid project name (Model Zoo)** &mdash; with `--repo model-zoo-psoc`, the
  name must be folder- and branch-safe: no spaces; use letters, digits, `.`,
  `_`, or `-`; start and end with a letter or digit (e.g. `EfficientNetV2-S`).
* **`Items {...} are missing` / `not allowed in project's root directory`**
  &mdash; adjust your project root so it matches the layout described in
  [Project layout requirements](#project-layout-requirements-repo-accelerators)
  (`--repo accelerators` only). Git and Python artefacts are excluded; see
  [Local git and Python environments](#local-git-and-python-environments).
* **Authentication issues** &mdash; the tool prefers bundled `pr_tool/gh.exe`
  (each `gh` binary keeps its own login).
  Run `gh auth status` with the same binary shown at startup. If you are logged
  in but missing permissions, the tool runs `gh auth refresh` for the
  `workflow` scope instead of asking for a full login when possible. If the
  token is invalid, run `gh auth login -h github.com` for that binary.
* **Your fork is out of sync** &mdash; the tool tries to sync your fork's
  `main` with Infineon. If that fails, it asks before deleting and recreating
  the entire fork (which would remove all other branches on that fork). It will
  also prompt to grant the `delete_repo` scope when recreation is confirmed.

By default the tool prints short progress lines, a simple progress bar while
staging/pushing, and an animated status spinner during long waits (clone,
branch switch, scanning large folders). For full command output, run with
`--verbose` (or `-v`); that prints every `git` and `gh` command and is the
first place to look when something goes wrong.
