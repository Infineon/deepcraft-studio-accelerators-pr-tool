import argparse
import shutil
from argparse import ArgumentTypeError
from pathlib import Path
from typing import Callable

import constants
from target_repo import get_target_repo
from image_selector import get_available_images, get_available_tags, select_image
from project_layouts import get_project_layout


TITLE_MAX_LENGTH = 40
DESCRIPTION_MAX_LENGTH = 100
ALGORITHM = ['Classification', 'Regression', 'Object Detection']
SENSORS = [
    'Microphone',
    'Camera',
    'IMU', 'Vibration',
    'Radar',
    'Capacitive Sensing', 'Inductive Sensing',
    'Current', 'Voltage', 'Power',
    'Torque', 'RPM',
    'DPS',
    'Other',
]


def arg_validator(max_len: int) -> Callable[[str], str]:
    def validate_arg(value: str) -> str:
        if not value:
            raise ArgumentTypeError('Value is empty')
        if len(value) > max_len:
            raise ArgumentTypeError(f'Value is more than {max_len} characters')
        return value

    return validate_arg


def _separator(char: str) -> str:
    """Return a horizontal rule sized to the current terminal width.

    Used to visually separate one prompt from the next, so repeated prompts
    (after empty/invalid input) don't blur together.
    """
    width = shutil.get_terminal_size((80, 24)).columns
    return char * width


def _format_choices(choices: list[str]) -> str:
    """Render a numbered list of choices as a compact multi-column block.

    The number of columns is sized to the current terminal width. Items are
    laid out column-major, so reading top-to-bottom and then left-to-right
    preserves the original (e.g. alphabetical) order of ``choices``.
    """
    n = len(choices)
    if n == 0:
        return ''
    number_width = len(str(n))
    entries = [f'{i + 1:>{number_width}}. {choice}' for i, choice in enumerate(choices)]
    col_width = max(len(e) for e in entries) + constants.COLUMN_PADDING
    term_width = shutil.get_terminal_size((80, 24)).columns
    num_cols = max(1, term_width // col_width)
    num_rows = (n + num_cols - 1) // num_cols
    rows: list[str] = []
    for row in range(num_rows):
        cells = []
        for col in range(num_cols):
            idx = col * num_rows + row
            if idx < n:
                cells.append(entries[idx].ljust(col_width))
        rows.append(''.join(cells).rstrip())
    return '\n'.join(rows)


def input_str(name: str, max_len: int, default: str | None = None) -> str:
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    prompt = (
        f'{top_sep}\n'
        f'{name} (max {max_len} characters)\n'
        f'{default_line}'
        f'{bottom_sep}\n: '
    )
    while True:
        value = input(prompt).strip()
        if not value and default:
            return default
        if not value:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        if len(value) > max_len:
            print(f'{constants.ICON_WARNING} Value is more than {max_len} characters, please try again.')
            continue
        return value


def confirm(question: str) -> bool:
    """Ask a yes/no question; loop until the user types y/yes or n/no."""
    while True:
        answer = input(f'{question} (y/n): ').strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        print(f"{constants.ICON_WARNING} Please answer 'y' or 'n'.")


def confirm_metadata() -> str:
    """Ask the user to approve, redo, or abort metadata.

    Returns ``'yes'``, ``'no'`` (redo), or ``'abort'``.
    """
    while True:
        answer = input(
            'Proceed with this metadata? (y = yes / n = redo / a = abort): '
        ).strip().lower()
        if answer in ('y', 'yes'):
            return 'yes'
        if answer in ('n', 'no'):
            return 'no'
        if answer in ('a', 'abort'):
            return 'abort'
        print(f"{constants.ICON_WARNING} Please answer 'y', 'n', or 'a'.")


def confirm_new_value(value: str, kind: str) -> bool:
    """Ask the user to confirm using a value that is not in the suggested list."""
    return confirm(f'"{value}" is not in the suggested {kind} list. Use it anyway?')


def input_choice(name: str, choices: list[str], default: str | None = None) -> str:
    """Prompt for exactly one value. The user can pick a number from the list,
    type one of the listed names, or enter a new name (which must be confirmed)."""
    choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    prompt = (
        f'{top_sep}\n'
        f'{name} - type a number {range_str} or enter a new name\n'
        f'{default_line}'
        f'{choices_sub_list}\n'
        f'{bottom_sep}\n: '
    )
    while True:
        raw = input(prompt).strip()
        if not raw and default:
            return default
        if not raw:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        if raw.isnumeric():
            n = int(raw)
            if n <= 0 or n > len(choices):
                print(f'{constants.ICON_WARNING} Number {raw} is not {range_str}.')
                continue
            return choices[n - 1]
        if raw in choices:
            return raw
        if confirm_new_value(raw, name.lower()):
            return raw


def input_choices(name: str, choices: list[str],
                  default: list[str] | None = None) -> list[str]:
    """Prompt for one or more values, comma-separated. Each value can be a
    number from the list, one of the listed names, or a new name (which must
    be confirmed individually)."""
    choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = (f'>>> Press Enter to keep: {", ".join(default)}\n'
                    if default else '')
    prompt = (
        f'{top_sep}\n'
        f'{name}(s) - type one or more numbers {range_str} and/or names, '
        f'comma-separated\n{default_line}{choices_sub_list}\n'
        f'{bottom_sep}\n: '
    )
    while True:
        raw = input(prompt).strip()
        if not raw and default:
            return list(default)
        if not raw:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        tokens = [t.strip() for t in raw.split(',') if t.strip()]
        if not tokens:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        results: list[str] = []
        retry = False
        for token in tokens:
            if token.isnumeric():
                n = int(token)
                if n <= 0 or n > len(choices):
                    print(f'{constants.ICON_WARNING} Number {token} is not {range_str}.')
                    retry = True
                    break
                results.append(choices[n - 1])
            elif token in choices:
                results.append(token)
            elif confirm_new_value(token, name.lower()):
                results.append(token)
        if retry:
            continue
        # Preserve user order, drop duplicates
        deduped = list(dict.fromkeys(results))
        if not deduped:
            print(f'{constants.ICON_WARNING} You must choose at least one {name.lower()}, please try again.')
            continue
        return deduped


class Input:
    def __init__(self) -> None:
        repo_choices = ', '.join(f'{key} ({cfg.repo_name})' for key, cfg in constants.TARGET_REPOS.items())
        parser = argparse.ArgumentParser(
            description=f'Submit a project to an Infineon {constants.DEEPCRAFT} GitHub repository.',
        )
        parser.add_argument(
            '--repo', required=True, choices=sorted(constants.TARGET_REPOS),
            metavar='TARGET',
            help=f'Target repository. Choices: {repo_choices}',
        )
        parser.add_argument('--path', required=True,
                            help='The root path of the project.')
        parser.add_argument('--name', default=None,
                            help='The name of the project, in CamelCase;  That name will also be the branch name;'
                                 'Default is the containing directory\'s name.')
        parser.add_argument('--override-metadata', action='store_true',
                            help='Override existing metadata.json file, if any, with meta-data options below.')
        parser.add_argument('--verbose', '-v', action='store_true',
                            help='Print every git/gh command and captured output (for debugging).')
        metadata = parser.add_argument_group('Project meta-data')
        metadata.add_argument('--title', type=arg_validator(TITLE_MAX_LENGTH), default=None,
                              help=f'The title of the project; Max {TITLE_MAX_LENGTH} characters.')
        metadata.add_argument('--description', type=arg_validator(DESCRIPTION_MAX_LENGTH), default=None,
                              help=f'The description of the project; Max {DESCRIPTION_MAX_LENGTH} characters.')
        metadata.add_argument('--algorithm', choices=ALGORITHM, default=None,
                              help='The supervised learning algorithm of the project.')
        metadata.add_argument('--sensor', choices=SENSORS, default=None, action='append',
                              help='The target sensor of the project. Pass --sensor multiple '
                                   'times to specify more than one sensor.')
        metadata.add_argument('--tag', default=None, action='append',
                              help='Tag used to auto-pick a project image from images.json. '
                                   'Pass --tag multiple times to specify more than one tag.')
        metadata.add_argument('--image', default=None,
                              help='Image name to use directly (e.g. "Audio.png"). '
                                   'Skips the tag-based auto-selection.')
        self._args = args = parser.parse_args()
        self.verbose = args.verbose
        self.repo_key = args.repo
        self.target_repo = get_target_repo(args.repo)
        self.project_path = Path(args.path).resolve()
        self.project_name = args.name or self.project_path.name
        get_project_layout(self.target_repo.project_layout).validate_project_name(
            self.project_name,
        )
        if args.override_metadata or not (self.project_path / 'metadata.json').exists():
            self.metadata = self.collect_metadata()
        else:
            self.metadata = None

    def collect_metadata(self, *, use_cli_args: bool = True,
                         previous: dict | None = None) -> dict:
        """Build a fresh metadata dict by combining CLI flags with prompts.

        When ``use_cli_args`` is True (the default for the initial run), values
        supplied via CLI flags are reused and only the missing fields are
        prompted for. When False (used after the user rejects the proposed
        metadata) every field is prompted for, but the previously entered
        values are shown as defaults so the user can press Enter to keep them.

        ``previous`` is the metadata dict from the last attempt (if any). Its
        values are used as defaults in the interactive prompts so the user only
        needs to retype the fields they want to change.
        """
        args = self._args
        prev = previous or {}
        title_arg = args.title if use_cli_args else None
        description_arg = args.description if use_cli_args else None
        algorithm_arg = args.algorithm if use_cli_args else None
        sensor_arg = args.sensor if use_cli_args else None
        tag_arg = args.tag if use_cli_args else None
        image_arg = args.image if use_cli_args else None
        metadata = dict(
            title=title_arg or input_str(
                'Project title', TITLE_MAX_LENGTH,
                default=prev.get('title')),
            description=description_arg or input_str(
                'Project description', DESCRIPTION_MAX_LENGTH,
                default=prev.get('description')),
            algorithm=algorithm_arg or input_choice(
                'Algorithm', ALGORITHM,
                default=prev.get('algorithm')),
            sensors=(sensor_arg if sensor_arg
                     else input_choices('Sensor', SENSORS,
                                        default=prev.get('sensors'))),
        )
        prev_image = prev.get('thumbnail_image_id')
        selected_image = self._select_image_interactive(
            image_arg=image_arg, tag_arg=tag_arg, default=prev_image,
        )
        metadata['thumbnail_image_id'] = selected_image
        metadata['main_image_id'] = selected_image
        return metadata


    @staticmethod
    def _select_image_interactive(
        *, image_arg: str | None, tag_arg: list[str] | None,
        default: str | None = None,
    ) -> str:
        """Let the user choose between auto-selecting an image based on tags
        or picking one manually from the catalog.

        If ``--image`` was provided via CLI, it is used directly.
        If ``--tag`` was provided via CLI, auto-selection runs without prompting.
        Otherwise the user is asked interactively.
        """
        if image_arg:
            return image_arg
        if tag_arg:
            return select_image(tag_arg)
        available_images = get_available_images()
        top_sep = _separator('=')
        bottom_sep = _separator('-')
        default_line = (f'>>> Press Enter to keep: {default}\n'
                        if default else '')
        prompt = (
            f'{top_sep}\n'
            f'Project image - choose how to set the project image\n'
            f'{default_line}'
            f'  1. Auto-select based on tags\n'
            f'  2. Pick from available images\n'
            f'{bottom_sep}\n: '
        )
        while True:
            choice = input(prompt).strip()
            if not choice and default:
                return default
            if choice == '1':
                available_tags = get_available_tags()
                if available_tags:
                    tags = input_choices('Tag', available_tags)
                else:
                    tags = []
                return select_image(tags)
            if choice == '2':
                if not available_images:
                    print(f'{constants.ICON_WARNING} No images available in the catalog.')
                    continue
                print(f'\n{constants.ICON_INFO} Pick an image file name from the catalog list below.\n')
                return input_choice('Image', available_images)
            print(f'{constants.ICON_WARNING} Please type 1 or 2.')
