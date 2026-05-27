# DEEPCRAFT&trade; Studio Accelerators – Pull Request Tool

A small Python command-line utility that lets DEEPCRAFT&trade; Studio users
contribute their projects as candidate Accelerators (Starter Models) to the
[Infineon/deepcraft-studio-accelerators](https://github.com/Infineon/deepcraft-studio-accelerators)
repository.

The tool wraps `git` and the GitHub CLI (`gh`) to automate the whole workflow
for you:

1. Authenticates using your GitHub account.
2. Forks `Infineon/deepcraft-studio-accelerators` to your account (or syncs an
   existing fork).
3. Creates / switches to a branch named after your project.
4. Commits and pushes your project's files (splitting large change sets into
   chunks below GitHub's 2 GB per-push limit).
5. Opens the resulting pull request in your browser.

The same command can also be used to **update** an existing pull request &ndash;
just re-run it after making changes to your project.

## Requirements

* **Python 3.10** or newer
* **git 2.43** or newer
  * On Windows, git 2.16.2+ is also accepted &mdash; the tool will run
    `update-git-for-windows` automatically to bring it up to date.
* **GitHub CLI** (`gh`) installed and available on your `PATH`
  &ndash; see [cli.github.com](https://cli.github.com/)
* A **GitHub account**

No additional Python packages are required &mdash; the tool only uses the
standard library.

## Project layout requirements

Before running the tool, make sure your project directory has the following
layout. The tool validates this before doing anything.

**Required items** (must be present at the project root):

* `<ProjectName>.improj`
* `Data/`
* `README.md`

**Allowed items** (optional, may be present):

* `*.im*` files (other DEEPCRAFT&trade; Studio files)
* `metadata.json`
* `Models/`
* `PreprocessorTrack/`
* `Resources/`
* `Tools/`
* `Units/`

Anything else at the project root will cause the tool to fail with a clear
error message. The `Models/` and `PreprocessorTrack/` directories are tracked
in your project but are **not** pushed to GitHub.

The project name **defaults to the project folder's name** and is used as
both the **branch name** and the **PR title prefix** on GitHub (e.g.
`Accelerator MyAudioClassifier`). It must be in **CamelCase**, e.g.
`MyAudioClassifier`. You can override it with `--name <CamelCaseName>` if
the folder name doesn't match the desired project name.

## Usage

From the directory containing `pr_tool.py`, run:

```bash
python ./pr_tool.py --path <project-path>
```

where `<project-path>` is the absolute or relative path to the root of your
DEEPCRAFT&trade; Studio project.

The first time you run the tool you will be:

1. Prompted to authenticate with GitHub in your browser (only once &ndash;
   credentials are then cached by `gh`).
2. Asked for project metadata (title, description, algorithm, sensors, and
   a project image) unless a `metadata.json` already exists in the project,
   or you pass these as CLI flags.

Once all metadata is collected (or loaded from an existing file), the tool
shows a summary and asks you to confirm before continuing:

* **y** (yes) &ndash; accept and proceed.
* **n** (redo) &ndash; restart metadata input. Every field is prompted again
  but the previous values are shown as defaults, so you can press Enter to
  keep a field and only retype the ones you want to change.
* **a** (abort) &ndash; exit immediately without writing anything.

When the push completes, your default browser opens the pull request page on
`Infineon/deepcraft-studio-accelerators` so you can review and submit it.

### Interactive metadata prompts

When the tool needs metadata it does not have, it asks you for it on the
command line. The prompts behave as follows:

* **Title and description** &ndash; free-form text with a maximum length.
  Empty input is rejected and the prompt repeats until you provide a value
  that fits within the limit.
* **Algorithm** &ndash; pick exactly one option by typing its number from
  the displayed list, or type a custom name. If you type something that is
  not in the suggested list, the tool asks you to confirm before using it.
* **Sensors** &ndash; pick one or more options by typing a comma-separated
  list of numbers and/or names (for example `1, 3, MyCustomSensor`). Each
  custom name is confirmed individually, and duplicates are removed
  automatically. At least one sensor must be selected.
* **Project image** &ndash; choose between two methods:
  1. **Auto-select based on tags** &ndash; pick one or more domain tags
     (for example `smart home`, `audio`, `automotive`) and the tool selects
     the image whose tags best match. If nothing matches, `deepcraft.webp`
     is used as default.
  2. **Pick from available images** &ndash; the tool shows a link to the
     [image repository](https://github.com/Reyev123/ai-hub-default-images)
     where you can preview the images, and then lets you choose one by
     number or name from the catalog.

  The selected image name is written to the `thumbnail_image_id` and
  `main_image_id` fields of `metadata.json`. You can also skip this prompt
  entirely by passing `--image <name>` or `--tag <tag>` on the command
  line.


### Updating an existing pull request

To push new changes to a pull request you already opened, **just re-run the
exact same command on the same project folder**:

```bash
python ./pr_tool.py --path <project-path>
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
4. If a pull request is already open for that branch, the tool simply
   **reopens it in your browser** &ndash; no new PR is created.

Things to watch out for:

* **Don't rename the project folder between runs** (or, if you must, pass
  `--name <SameCamelCaseName>` explicitly). Otherwise the tool will use a
  different branch and open a **new** pull request alongside the old one.
* **If the pull request was closed on GitHub**, the next run will not reopen
  it &ndash; it creates a fresh pull request on the same branch.
* **Changing metadata on a subsequent run.** The tool never modifies an
  existing `metadata.json`, so you have two options:
  * Edit `metadata.json` directly in your project and re-run the tool &ndash;
    the modified file is committed and pushed like any other change.
  * Or pass `--override-metadata` together with the new values (or let the
    tool prompt you interactively) to have the tool regenerate the file for
    you.

### The `.git_deepcraft` folder

While the tool runs it creates a working directory next to your project:

```
<project-path>/..
├── <ProjectName>/         <- your DEEPCRAFT&trade; Studio project
└── .git_deepcraft/
    └── <ProjectName>/     <- git metadata for this project's PR
```

This folder is the tool's separate **git directory** &mdash; it stores all of
git's bookkeeping (objects, refs, branches, remote configuration) for the
pull request, **without** placing a `.git` folder inside your project itself.
That keeps your project directory clean and avoids interfering with any
existing version control you may have there.

Each project gets its own subfolder under `.git_deepcraft/`, so you can
maintain pull requests for several projects in parallel without conflicts.

**What happens if you delete it?**

* **Between runs:** nothing bad. The tool already deletes the folder at the
  end of every successful run, and recreates it at the start of the next one
  by cloning your fork freshly. Deleting it manually is harmless.
* **During a run:** the current run will fail, because git can no longer find
  its metadata. Simply re-run the command &mdash; the folder will be
  recreated from scratch.
* **Your pull request is not affected.** All commits already live on GitHub
  (in your fork and on the PR). `.git_deepcraft` is purely local scratch
  space; deleting it never loses any work that has been pushed.

### Common options

| Option | Description |
| --- | --- |
| `--path <project-path>` | **Required.** Root directory of your project. |
| `--name <CamelCaseName>` | Override the project name (defaults to the directory name). Also becomes the branch name on GitHub. |
| `--title <text>` | Project title (max 40 characters). |
| `--description <text>` | Short project description (max 100 characters). |
| `--algorithm <name>` | Supervised learning algorithm. Suggested values: `Classification`, `Regression`, `Object Detection`. |
| `--sensor <name>` | Target sensor. Run `--help` to see the suggested list. Can be passed multiple times (e.g. `--sensor Microphone --sensor Camera`) to specify more than one sensor. |
| `--image <name>` | Image name to use directly (e.g. `Audio.png`). Skips the tag-based auto-selection and the interactive image prompt. |
| `--tag <tag>` | Tag used to auto-pick a project image. Can be passed multiple times (e.g. `--tag audio --tag "smart home"`). Skips the interactive image prompt but not the auto-selection step. Not saved to `metadata.json`. |
| `--override-metadata` | Regenerate `metadata.json` from the options above even if one already exists. |

For the complete list of options, run:

```bash
python ./pr_tool.py --help
```

### Example

Single sensor:

```bash
python ./pr_tool.py \
  --path C:\Projects\MyAudioClassifier \
  --title "My audio classifier" \
  --description "Detects three types of household sounds" \
  --algorithm Classification \
  --sensor Microphone
```

With a specific image (skips the image prompt entirely):

```bash
python ./pr_tool.py \
  --path C:\Projects\MyMultiModalDetector \
  --title "Multi-modal detector" \
  --description "Combines audio and motion signals" \
  --algorithm Classification \
  --sensor Microphone \
  --sensor IMU \
  --image Motion.png
```

With tags for auto-selection (skips the image prompt, auto-picks the best
match):

```bash
python ./pr_tool.py \
  --path C:\Projects\MyMultiModalDetector \
  --title "Multi-modal detector" \
  --description "Combines audio and motion signals" \
  --algorithm Classification \
  --sensor Microphone \
  --sensor IMU \
  --tag audio \
  --tag motion
```

## Troubleshooting

* **`git version 2.43 or newer is required`** &mdash; install / update git
  from [git-scm.com](https://git-scm.com/). On Windows, the tool will try
  `update-git-for-windows` first.
* **`gh: command not found`** &mdash; install the GitHub CLI from
  [cli.github.com](https://cli.github.com/) and make sure it's on your
  `PATH`.
* **`Project name "..." is not CamelCase`** &mdash; rename the project
  directory (or pass `--name`) so it uses CamelCase, e.g.
  `MyAudioClassifier`.
* **`Items {...} are missing` / `not allowed in project's root directory`**
  &mdash; adjust your project root so it matches the layout described in
  [Project layout requirements](#project-layout-requirements).
* **Authentication issues** &mdash; run `gh auth status` to inspect the
  current state, or `gh auth login` to start fresh. The tool requires the
  `workflow` scope.
* **Your fork is out of sync** &mdash; the tool can recreate your fork
  automatically; it will prompt you to grant the `delete_repo` scope first.

The tool prints every `git` and `gh` command it runs, so the console output
is the first place to look when something goes wrong.
