"""Interactive prompt for the long-description field."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import constants
from metadata.long_description import normalize_long_description, validate_long_description
from metadata.prompts import _separator


_LONG_TEXT_END = 'END'
_LONG_TEXT_EDIT = 'EDIT'


def _print_between_separators(message: str) -> None:
    """Print a message between a ===== line and a ----- line."""
    print(_separator('='))
    print(f'{constants.ICON_WARNING} {message}')
    print(_separator('-'))


def _retry_message(error: str) -> str:
    text = error.strip()
    if text:
        text = text[0].upper() + text[1:]
    if not text.endswith('.'):
        text += '.'
    return f'{text} Please try again.'


def _show_long_text_lines(lines: list[str]) -> None:
    if not lines:
        print('  (no lines yet)')
        return
    for index, line in enumerate(lines, start=1):
        print(f'  {index}| {line}')


def _stop_editor(process: subprocess.Popen | None) -> None:
    """Close an editor left open after Ctrl+C."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    except OSError:
        return


def _wait_for_editor(process: subprocess.Popen) -> None:
    """Wait in short steps so Ctrl+C is delivered while a GUI editor is open.

    On Windows a wait with no timeout blocks inside the system call, so Ctrl+C
    is held until the editor closes and then aborts with the saved text lost.
    """
    while process.poll() is None:
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue


def _edit_long_text(lines: list[str]) -> list[str] | None:
    """Open the whole description in an editor so any line can be changed.

    Returns the new lines, or ``None`` when no editor could be started.
    The terminal itself can change only the line currently being typed.
    Ctrl+C closes the editor and aborts the tool.
    """
    editor = os.environ.get('EDITOR') or os.environ.get('VISUAL')
    if not editor and os.name == 'nt':
        editor = 'notepad'
    if not editor:
        return None
    handle = tempfile.NamedTemporaryFile(
        'w', suffix='.txt', delete=False, encoding='utf-8', newline='\n',
    )
    path = Path(handle.name)
    process: subprocess.Popen | None = None
    try:
        handle.write('\n'.join(lines))
        if lines:
            handle.write('\n')
        handle.close()
        command = shlex.split(editor, posix=(os.name != 'nt'))
        process = subprocess.Popen([*command, str(path)])
        _wait_for_editor(process)
        body = path.read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    except KeyboardInterrupt:
        _stop_editor(process)
        raise
    except OSError:
        _stop_editor(process)
        return None
    finally:
        path.unlink(missing_ok=True)
    if body.endswith('\n'):
        body = body[:-1]
    return body.split('\n') if body else []


def _read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return _LONG_TEXT_END
    except KeyboardInterrupt:
        print()
        raise


def _show_loaded_lines(lines: list[str]) -> None:
    print(_separator('='))
    print(f'{constants.ICON_SUCCESS} Loaded {len(lines)} line(s) from the editor:')
    _show_long_text_lines(lines)
    print(_separator('-'))
    print(f'  Type {_LONG_TEXT_END} on its own line when this text is finished.')
    print(f'  Type {_LONG_TEXT_EDIT} on its own line to open Notepad again.')
    print(_separator('-'))


def _load_from_editor(lines: list[str]) -> list[str] | None:
    """Open Notepad with the current text. Return the saved lines, or ``None``."""
    edited = _edit_long_text(lines)
    if edited is None:
        _print_between_separators(
            'Could not open Notepad. Set the EDITOR variable, or keep typing. Please try again.',
        )
        return None
    _show_loaded_lines(edited)
    return edited


def _choose_entry_mode() -> str:
    """Ask whether the first draft is typed here or started in Notepad."""
    print(_separator('='))
    print('  Where do you want to write the long description?')
    print('  1. In this terminal')
    print('  2. In Notepad')
    print(f'  {_LONG_TEXT_END} and {_LONG_TEXT_EDIT} stay available either way.')
    print(_separator('-'))
    while True:
        answer = _read_line('Choice (1 or 2): ').strip().lower()
        if answer in ('1', 'terminal'):
            return 'terminal'
        if answer in ('2', 'notepad'):
            return 'notepad'
        _print_between_separators(
            'Type 1 for the terminal or 2 for Notepad. Please try again.',
        )


def input_html_text(
    name: str,
    max_len: int | None = None,
    default: str | None = None,
) -> str:
    """Collect multiline plain text, Markdown, or text HTML (no images).

    The stored value is one line. Newlines matter only while Markdown is read.
    The first time, the user chooses the terminal or Notepad.
    ``END`` on its own line finishes. ``EDIT`` opens the whole text in Notepad.
    """
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = (
        '  Press Enter on the first line to keep the previous value.\n' if default else ''
    )
    limit_line = f' (max {max_len} characters)' if max_len is not None else ''
    print(
        f'{top_sep}\n'
        f'{name}{limit_line}\n'
        f'{bottom_sep}\n'
        f'{default_line}'
        f'  The terminal can change only the line you are typing.\n'
        f'  To change the text, go to a new line, type {_LONG_TEXT_EDIT}, and press Enter.\n'
        f'  That opens the whole text in Notepad. Change it, save, and close Notepad.\n'
        f'  When you are finished, go to a new line, type {_LONG_TEXT_END}, and press Enter.\n'
        f'\n'
        f'  Plain text is stored as one line.\n'
        f'  Markdown (lists, **bold**, *italic*, [links](url)) is converted to HTML.\n'
        f'  Headings and images are not accepted.\n'
        f'  HTML may use <p>, <br>, <ul>, <ol>, <li>, <strong>, <em>, <a href="...">.\n'
        f'{bottom_sep}'
    )
    lines: list[str] = []
    if not default and _choose_entry_mode() == 'notepad':
        opened = _load_from_editor(lines)
        if opened is not None:
            lines = opened
    first = True
    while True:
        line = _read_line(f'{len(lines) + 1}> ')
        command = line.strip().upper()
        if first and default and line.strip() == '':
            error = validate_long_description(default)
            if error:
                _print_between_separators(
                    f'Previous value is not valid: {_retry_message(error)}',
                )
                first = False
                continue
            return normalize_long_description(default)
        first = False
        if command == _LONG_TEXT_EDIT:
            edited = _load_from_editor(lines)
            if edited is not None:
                lines[:] = edited
            continue
        if command == _LONG_TEXT_END:
            raw = '\n'.join(lines)
            error = validate_long_description(raw)
            if error:
                print('  Text so far:')
                _show_long_text_lines(lines)
                _print_between_separators(_retry_message(error))
                print(
                    f'  Type {_LONG_TEXT_EDIT} on its own line to change the text, '
                    f'then {_LONG_TEXT_END} when it is fixed.'
                )
                continue
            value = normalize_long_description(raw)
            if not value:
                _print_between_separators('Value cannot be empty. Please try again.')
                continue
            if max_len is not None and len(value) > max_len:
                _print_between_separators(
                    f'Value is more than {max_len} characters. Please try again.',
                )
                continue
            return value
        lines.append(line.rstrip())
