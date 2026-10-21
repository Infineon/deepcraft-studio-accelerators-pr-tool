"""Interactive prompt for the long-description field."""

import os
import shlex
import subprocess
import sys
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
        handle.close()
        path.unlink(missing_ok=True)
    if body.endswith('\n'):
        body = body[:-1]
    return body.split('\n') if body else []


def _read_line(prompt: str) -> str | None:
    """Read one line. ``None`` means end of input, which must not be asked again."""
    try:
        return input(prompt)
    except EOFError:
        print()
        return None
    except KeyboardInterrupt:
        print()
        raise


def _queue_windows_console_text(text: str) -> bool:
    """Type *text* into the Windows console so the next ``input()`` can edit it."""
    import ctypes
    from ctypes import wintypes

    class _KeyEvent(ctypes.Structure):
        _fields_ = [
            ('bKeyDown', wintypes.BOOL),
            ('wRepeatCount', wintypes.WORD),
            ('wVirtualKeyCode', wintypes.WORD),
            ('wVirtualScanCode', wintypes.WORD),
            ('uChar', wintypes.WCHAR),
            ('dwControlKeyState', wintypes.DWORD),
        ]

    class _Event(ctypes.Union):
        _fields_ = [('KeyEvent', _KeyEvent)]

    class _InputRecord(ctypes.Structure):
        _fields_ = [('EventType', wintypes.WORD), ('Event', _Event)]

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    units = text.encode('utf-16-le')
    chars = [units[i:i + 2].decode('utf-16-le', 'surrogatepass') for i in range(0, len(units), 2)]
    records = (_InputRecord * (len(chars) * 2))()
    for index, char in enumerate(chars):
        for offset, key_down in ((0, True), (1, False)):
            record = records[index * 2 + offset]
            record.EventType = 0x0001
            record.Event.KeyEvent.bKeyDown = key_down
            record.Event.KeyEvent.wRepeatCount = 1
            record.Event.KeyEvent.uChar = char
    written = wintypes.DWORD()
    ok = kernel32.WriteConsoleInputW(handle, records, len(records), ctypes.byref(written))
    return bool(ok) and written.value == len(records)


def _queue_line_for_editing(text: str) -> bool:
    """Put *text* on the next input line. Return False when the terminal cannot do it."""
    if not text:
        return False
    try:
        if not sys.stdin.isatty():
            return False
        if os.name == 'nt':
            return _queue_windows_console_text(text)
        import readline
    except (ImportError, OSError, AttributeError, ValueError):
        return False
    readline.set_startup_hook(lambda: readline.insert_text(text))
    return True


def _read_prefilled(prompt: str, text: str) -> tuple[str | None, bool]:
    """Read a line that starts with *text*. Also returns whether *text* was placed."""
    prefilled = _queue_line_for_editing(text)
    if not prefilled:
        print(f'  {text}')
        print('  Press Enter to keep this line, or type a replacement.')
    try:
        return _read_line(prompt), prefilled
    finally:
        if prefilled and os.name != 'nt':
            import readline
            readline.set_startup_hook()


def _show_terminal_edit_hint() -> None:
    print(_separator('-'))
    print('  The current text is on the line below. Change it, then press Enter.')
    print(f'  Then type {_LONG_TEXT_END} to finish, or {_LONG_TEXT_EDIT} to open Notepad.')
    print(_separator('-'))


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


def _choose_entry_mode(*, has_current: bool = False) -> str:
    """Ask whether the text is kept, typed here, or opened in Notepad.

    Returns ``keep``, ``terminal``, or ``notepad``. ``keep`` is offered only
    when a saved value is already shown.
    """
    print(_separator('='))
    if has_current:
        print('  Choose how to update the long description.')
        print('  Enter  keep the current value')
        print('  1. Edit in this terminal')
        print('  2. Edit in Notepad')
    else:
        print('  Where do you want to write the long description?')
        print('  1. In this terminal')
        print('  2. In Notepad')
    print(f'  {_LONG_TEXT_END} and {_LONG_TEXT_EDIT} stay available either way.')
    print(_separator('-'))
    prompt = 'Choice (Enter, 1, or 2): ' if has_current else 'Choice (1 or 2): '
    retry = (
        'Press Enter to keep it, or type 1 for the terminal or 2 for Notepad. Please try again.'
        if has_current
        else 'Type 1 for the terminal or 2 for Notepad. Please try again.'
    )
    while True:
        answer = _read_line(prompt)
        if answer is None:
            raise EOFError
        answer = answer.strip().lower()
        if has_current and answer == '':
            return 'keep'
        if answer in ('1', 'terminal'):
            return 'terminal'
        if answer in ('2', 'notepad'):
            return 'notepad'
        _print_between_separators(retry)


def _kept_value(default: str) -> str | None:
    """Return the saved text when it is still valid."""
    error = validate_long_description(default)
    if error:
        _print_between_separators(
            f'Previous value is not valid: {_retry_message(error)}',
        )
        return None
    return normalize_long_description(default)


def input_html_text(
    name: str,
    max_len: int | None = None,
    default: str | None = None,
) -> str:
    """Collect multiline plain text, Markdown, or text HTML (no images).

    The stored value is one line. Newlines matter only while Markdown is read.
    The user chooses the terminal or Notepad, including when a value is already saved.
    ``END`` on its own line finishes. ``EDIT`` opens the whole text in Notepad.
    """
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    current_block = ''
    if default:
        shown = '\n'.join(f'  {line}' for line in default.splitlines() or [''])
        current_block = (
            f'  Current value:\n'
            f'{shown}\n'
            f'{bottom_sep}\n'
        )
    limit_line = f' (max {max_len} characters)' if max_len is not None else ''
    print(
        f'{top_sep}\n'
        f'{name}{limit_line}\n'
        f'{bottom_sep}\n'
        f'{current_block}'
        f'  The terminal can change only the line you are typing.\n'
        f'  To change the text, go to a new line, type {_LONG_TEXT_EDIT}, and press Enter.\n'
        f'  That opens the whole text in Notepad. Change it, save, and close Notepad.\n'
        f'  When you are finished, go to a new line, type {_LONG_TEXT_END}, and press Enter.\n'
        f'\n'
        f'  Plain text is stored as one line.\n'
        f'  Markdown (lists, **bold**, *italic*, [links](url)) is converted to HTML.\n'
        f'  Headings and images are not accepted.\n'
        f'  HTML may use <p></p>, <br>, <ul></ul>, <ol></ol>, <li></li>, '
        f'<strong></strong>, <em></em>, <a href="..."></a>.\n'
        f'{bottom_sep}'
    )
    lines: list[str] = []
    started = False
    mode = _choose_entry_mode(has_current=bool(default))
    if mode == 'keep' and default:
        kept = _kept_value(default)
        if kept is not None:
            return kept
        mode = 'terminal'
    if mode == 'notepad':
        source = (default.splitlines() or ['']) if default else lines
        opened = _load_from_editor(source)
        if opened is not None:
            lines = opened
            started = True
    pending: list[str] = []
    if mode == 'terminal' and default:
        pending = default.splitlines() or ['']
        started = True
        _show_terminal_edit_hint()
    while True:
        prompt = f'{len(lines) + 1}> '
        prefilled = False
        if pending:
            line, prefilled = _read_prefilled(prompt, pending[0])
        else:
            line = _read_line(prompt)
        if line is None:
            line = _LONG_TEXT_END
            end_of_input = True
        else:
            end_of_input = False
        command = line.strip().upper()
        if command == _LONG_TEXT_EDIT:
            source = lines + pending if started or not default else default.splitlines() or ['']
            edited = _load_from_editor(source)
            if edited is not None:
                lines[:] = edited
                pending.clear()
                started = True
            continue
        if command == _LONG_TEXT_END:
            lines.extend(pending)
            pending.clear()
            raw = '\n'.join(lines)
            error = validate_long_description(raw)
            if error:
                if end_of_input:
                    raise EOFError
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
                if end_of_input:
                    raise EOFError
                _print_between_separators('Value cannot be empty. Please try again.')
                continue
            if max_len is not None and len(value) > max_len:
                if end_of_input:
                    raise EOFError
                _print_between_separators(
                    f'Value is more than {max_len} characters. Please try again.',
                )
                continue
            return value
        if pending:
            saved = pending.pop(0)
            if line.strip():
                lines.append(line.rstrip())
            elif not prefilled:
                lines.append(saved)
            continue
        lines.append(line.rstrip())
        started = True
