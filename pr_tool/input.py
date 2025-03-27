import argparse
import re
from argparse import ArgumentTypeError
from pathlib import Path
from typing import Callable

TITLE_MAX_LENGTH = 40
DESCRIPTION_MAX_LENGTH = 100
ALGORITHM = ['Classification', 'Regression']
SENSORS = [
    'Microphone', 'IVS-Infineon Vibration Sensor',
    'Camera',
    'Radar',
    'Capacitive Sensing', 'Inductive Sensing',
    'Current', 'Voltage', 'Power',
    'Torque', 'RPM',
    'IMU', 'Vibration',
    'Other',
]


def arg_validator(max_len: int) -> Callable[[str], str]:
    def validate_arg(value: str) -> str:
        if not value:
            raise ArgumentTypeError(f'Value is empty')
        if len(value) > max_len:
            raise ArgumentTypeError(f'Value is more than {max_len} characters')
        return value

    return validate_arg


def input_str(name: str, max_len: int) -> str:
    value = input(f'{name} (max {max_len} characters): ')
    return arg_validator(max_len)(value)


def input_choice(name: str, choices: list[str], default_idx: int = 0) -> str:
    choices_sub_list = '\n'.join([f'{i + 1}. {choice} {"(default)" if default_idx == i else ""}' for i, choice in enumerate(choices)])
    range_str = f'between 1 to {len(choices)}'
    prompt = f'{name} - type {range_str} or enter a new name\n{choices_sub_list}\n: '
    while True:
        choice = input(prompt)
        if not choice:
            return choices[default_idx]
        if choice.isnumeric():
            if int(choice) <= 0 or int(choice) > len(choices):
                print(f'Number {choice} is not {range_str}')
                continue
            return choices[int(choice) - 1]
        else:
            return choice


class Input:
    def __init__(self) -> None:
        parser = argparse.ArgumentParser(description='Submit a project as a candidate Starter Model.')
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
                              help='The supervised learning algorithm of the project; Default is Classification.')
        metadata.add_argument('--sensor', choices=SENSORS, default=None,
                              help='The target sensor of the project; Default is Other.')
        args = parser.parse_args()
        self.project_path = Path(args.path).resolve()
        self.project_name = args.name or self.project_path.name
        if not re.fullmatch(r'(?:[A-Z][a-z]*)+', self.project_name):
            raise ValueError(f'Project name "{self.project_name}" is not CamelCase')
        self.metadata = dict(
            title=args.title or input_str('Project title', TITLE_MAX_LENGTH),
            description=args.description or input_str('Project description', DESCRIPTION_MAX_LENGTH),
            algorithm=args.algorithm or input_choice('Algorithm', ALGORITHM),
            sensors=[args.sensor or input_choice('Sensor', SENSORS, default_idx=len(SENSORS) - 1)],
        ) if args.override_metadata or not (self.project_path / 'metadata.json').exists() else None
