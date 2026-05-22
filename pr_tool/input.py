import argparse
import re
from argparse import ArgumentTypeError
from pathlib import Path
from typing import Callable

TITLE_MAX_LENGTH = 40
DESCRIPTION_MAX_LENGTH = 100
ALGORITHM = ['Classification', 'Regression', 'Object Detection']
SENSORS = [
    'Microphone',
    'Camera',
    'Radar',
    'Capacitive Sensing', 'Inductive Sensing',
    'Current', 'Voltage', 'Power',
    'Torque', 'RPM',
    'IMU', 'Vibration',
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


def input_str(name: str, max_len: int) -> str:
    prompt = f'{name} (max {max_len} characters): '
    while True:
        value = input(prompt).strip()
        if not value:
            print('Value cannot be empty, please try again.')
            continue
        if len(value) > max_len:
            print(f'Value is more than {max_len} characters, please try again.')
            continue
        return value


def confirm_new_value(value: str, kind: str) -> bool:
    """Ask the user to confirm using a value that is not in the suggested list."""
    while True:
        answer = input(
            f'"{value}" is not in the suggested {kind} list. Use it anyway? (y/n): '
        ).strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        print("Please answer 'y' or 'n'.")


def input_choice(name: str, choices: list[str]) -> str:
    """Prompt for exactly one value. The user can pick a number from the list,
    type one of the listed names, or enter a new name (which must be confirmed)."""
    choices_sub_list = '\n'.join(f'{i + 1}. {choice}' for i, choice in enumerate(choices))
    range_str = f'between 1 and {len(choices)}'
    prompt = (
        f'{name} - type a number {range_str} or enter a new name\n'
        f'{choices_sub_list}\n: '
    )
    while True:
        raw = input(prompt).strip()
        if not raw:
            print('Value cannot be empty, please try again.')
            continue
        if raw.isnumeric():
            n = int(raw)
            if n <= 0 or n > len(choices):
                print(f'Number {raw} is not {range_str}.')
                continue
            return choices[n - 1]
        if raw in choices:
            return raw
        if confirm_new_value(raw, name.lower()):
            return raw


def input_choices(name: str, choices: list[str]) -> list[str]:
    """Prompt for one or more values, comma-separated. Each value can be a
    number from the list, one of the listed names, or a new name (which must
    be confirmed individually)."""
    choices_sub_list = '\n'.join(f'{i + 1}. {choice}' for i, choice in enumerate(choices))
    range_str = f'between 1 and {len(choices)}'
    prompt = (
        f'{name}(s) - type one or more numbers {range_str} and/or names, '
        f'comma-separated\n{choices_sub_list}\n: '
    )
    while True:
        raw = input(prompt).strip()
        if not raw:
            print('Value cannot be empty, please try again.')
            continue
        tokens = [t.strip() for t in raw.split(',') if t.strip()]
        if not tokens:
            print('Value cannot be empty, please try again.')
            continue
        results: list[str] = []
        retry = False
        for token in tokens:
            if token.isnumeric():
                n = int(token)
                if n <= 0 or n > len(choices):
                    print(f'Number {token} is not {range_str}.')
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
            print(f'You must choose at least one {name.lower()}, please try again.')
            continue
        return deduped


class Input:
    def __init__(self) -> None:
        parser = argparse.ArgumentParser(description='Submit a project as a candidate DEEPCRAFT&trade; Studio Accelerator.')
        parser.add_argument('--path', required=True,
                            help='The root path of the project.')
        parser.add_argument('--name', default=None,
                            help='The name of the project, in CamelCase;  That name will also be the branch name;'
                                 'Default is the containing directory\'s name.')
        parser.add_argument('--override-metadata', action='store_true',
                            help='Override existing metadata.json file, if any, with meta-data options below.')
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
        args = parser.parse_args()
        self.project_path = Path(args.path).resolve()
        self.project_name = args.name or self.project_path.name
        if not re.fullmatch(r'(?:[A-Z][a-z]*)+', self.project_name):
            raise ValueError(f'Project name "{self.project_name}" is not CamelCase')
        self.metadata = dict(
            title=args.title or input_str('Project title', TITLE_MAX_LENGTH),
            description=args.description or input_str('Project description', DESCRIPTION_MAX_LENGTH),
            algorithm=args.algorithm or input_choice('Algorithm', ALGORITHM),
            sensors=args.sensor if args.sensor else input_choices('Sensor', SENSORS),
        ) if args.override_metadata or not (self.project_path / 'metadata.json').exists() else None
