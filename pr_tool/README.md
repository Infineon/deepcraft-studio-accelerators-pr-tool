## Create and update a Pull Request for a candidate starter model

Minimum requirement are:
* python 3.10
* git 2.43 (or git 2.16.2 that will self-update itself to the latest)
* GitHub account

The tool will authenticate using your GitHub account, fork https://github.com/Infineon/deepcraft-starter-models to your account, and prepare the pull request.
Once ready, it will open the pull request in your browser.
It can also be used to update the pull request.

From the path of `pr_tool.py`, run:

`python .\pr_tool.py --path <project-path>`

where `<project-path>` is the root path of the project.

For more options, run

`python .\pr_tool.py --help`
