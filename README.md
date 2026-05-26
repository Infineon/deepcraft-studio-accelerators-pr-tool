# DEEPCRAFT&trade; Studio Accelerators – Pull Request Tool

This repository contains the `pr_tool`, a Python command-line utility that lets
DEEPCRAFT&trade; Studio users contribute their projects as candidate DEEPCRAFT&trade; 
Studio Accelerator to the
[Infineon/deepcraft-studio-accelerators](https://github.com/Infineon/deepcraft-studio-accelerators)
repository.

The tool wraps `git` and the GitHub CLI (`gh`) to automate the entire workflow:
authentication, forking, cloning, branching, committing, pushing in size-safe
chunks, and opening the pull request in the browser.

## Repository contents

```
deepcraft-studio-accelerators-pr-tool/
├── .gitignore
├── README.md              <- you are here
└── pr_tool/               <- the tool itself (entry point + modules)
    ├── README.md          <- end-user usage instructions
    ├── pr_tool.py         <- main script / entry point
    ├── cli.py             <- thin wrapper around `git` and `gh` subprocess calls
    ├── constants.py       <- repo name, base repo, branch, ignored dirs, etc.
    ├── input.py           <- argparse + interactive prompts for project metadata
    ├── image_selector.py  <- picks the best-matching image for a project
    ├── images.json        <- catalog of candidate project images and their tags
    ├── utils.py           <- helpers (file grouping for 2 GB push limit, etc.)
    └── validation.py      <- checks the project directory structure
```

### Module overview

| File | Responsibility |
| --- | --- |
| `pr_tool.py` | Orchestrates the whole flow: parse args, confirm metadata (with redo/abort support), authenticate, fork, clone, branch, commit, push, create/open PR. |
| `cli.py` | `Cli` class that invokes `git` / `gh` via `subprocess.run`, prints commands and outputs, and enforces a minimum `git` version. |
| `constants.py` | Centralized configuration: target repo (`Infineon/deepcraft-studio-accelerators`), main branch, local `.git_deepcraft` directory, and directories that must be excluded from commits (`Models`, `PreprocessorTrack`). |
| `input.py` | `Input` class that parses CLI arguments (`--path`, `--name`, `--title`, `--description`, `--algorithm`, `--sensor`, `--tag`, `--image`, `--override-metadata`) and falls back to interactive prompts. Validates that the project name is CamelCase. Calls `image_selector` to populate `thumbnail_image_id` / `main_image_id` in the generated metadata. Tag values are used only for image selection and are **not** persisted to `metadata.json`. After metadata is collected, the user is asked to confirm, redo (with previous values as defaults), or abort. |
| `image_selector.py` | Loads the image catalog &mdash; **remote first** from `REMOTE_IMAGES_URL` (a hardcoded GitHub raw URL), falling back to the local `images.json` if the remote fetch fails; the catalog is cached per process via `@functools.cache`. On a successful fetch, mirrors the remote payload to the local file when they differ, so the local copy self-heals after accidental edits (remote is the source of truth). `get_available_tags()` returns the union of tags from the loaded catalog. `select_image()` returns the `name` of the catalog image whose tags best match a list of input tags (case-insensitive). Falls back to `DEFAULT_IMAGE` (`deepcraft.webp`) when no catalog is available, no tags are provided, or no image shares any tag. |
| `images.json` | JSON array of `{name, tags, link}` objects. Used by `image_selector.py` as the **local fallback** when the remote catalog cannot be fetched, and to populate the interactive Tag prompt's suggested list. Kept in sync with the remote catalog automatically on every successful fetch. |
| `utils.py` | `group_files()` splits the change set into chunks below GitHub's 2 GB per-push limit, plus a small `handle_readonly` helper used when cleaning up the working tree. |
| `validation.py` | `validate_project_structure()` ensures the project folder contains the required items (`<name>.improj`, `Data/`, `README.md`) and nothing outside the allowed set. |

## Requirements

* Python 3.10+
* git 2.43+ (git 2.16.2+ on Windows is also accepted because the tool will
  run `update-git-for-windows` automatically)
* GitHub CLI (`gh`) installed and on `PATH`
* A GitHub account

## Usage (quick reference)

End-user instructions live in [`pr_tool/README.md`](pr_tool/README.md). In
short, from the `pr_tool/` directory:

```bash
python ./pr_tool.py --path <project-path>
```

Run `python ./pr_tool.py --help` to see all flags.

## Making changes to the tool

The tool is a small, dependency-free Python project. Working on it should be
straightforward:

### 1. Clone and set up

```bash
git clone https://github.com/<your-org>/deepcraft-studio-accelerators-pr-tool.git
cd deepcraft-studio-accelerators-pr-tool
```

A virtual environment is recommended but not required since the tool currently
has no third-party dependencies (it only uses the Python standard library plus
the external `git` and `gh` binaries):

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Where to make your change

Pick the module that owns the behavior you want to change:

* **New CLI flag or interactive prompt** &rarr; `pr_tool/input.py`
* **Change which repo / branch / ignored directories are used** &rarr; `pr_tool/constants.py`
* **Change a `git` / `gh` invocation, error handling, or version check** &rarr; `pr_tool/cli.py`
* **Change the required / allowed project layout** &rarr; `pr_tool/validation.py`
* **Change push chunking or filesystem helpers** &rarr; `pr_tool/utils.py`
* **Add or update the catalog of project images** &rarr; the canonical catalog lives at `REMOTE_IMAGES_URL` (see `pr_tool/image_selector.py`); the local `pr_tool/images.json` is a fallback that is auto-refreshed from the remote on every successful run. Update the canonical (remote) copy first; the local copy follows automatically.
* **Change the remote catalog URL or the selection algorithm** &rarr; `pr_tool/image_selector.py`
* **Change the overall fork / clone / commit / PR sequence** &rarr; `pr_tool/pr_tool.py`

Keep the runtime dependency surface minimal. If a change really needs a
third-party package, add a `requirements.txt` in the same PR and document it
here.

### 3. Test locally

Because the tool talks to GitHub, it's easiest to validate changes against
your own fork of `Infineon/deepcraft-studio-accelerators`:

1. Temporarily point `BASE_REPO_OWNER` in `pr_tool/constants.py` at your own
   GitHub user/org so you don't open PRs against Infineon while testing.
2. Prepare a small DEEPCRAFT&trade; Studio project on disk that satisfies the
   layout enforced by `validate_project_structure()` (at minimum
   `<Name>.improj`, `Data/`, `README.md`).
3. From `pr_tool/`, run:

   ```bash
   python ./pr_tool.py --path <path-to-test-project>
   ```

4. Verify the expected branch, commits, and pull request appear on your test
   repo.
5. Revert `constants.py` before committing.

The tool prints every `git` and `gh` command it runs (see
`Cli.run` in `cli.py`), which is the primary debugging aid.

### 4. Submit a pull request

1. Create a feature branch.
2. Commit focused, descriptive changes.
3. Open a pull request against `main` of this repository describing what you
   changed and how you tested it.

## License

See the upstream
[Infineon/deepcraft-studio-accelerators](https://github.com/Infineon/deepcraft-studio-accelerators)
repository for licensing of the Accelerator content this tool helps publish.
