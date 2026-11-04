"""Interactive prompt for the long-description field."""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import constants
from metadata.long_description import (
    looks_like_html,
    looks_like_markdown,
    normalize_long_description,
    validate_long_description,
)
from metadata.prompts import _separator


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


_BOX_CHARS = set('┌┐└┘├┤│─ ')
_RULE = '----'
_NOTEPAD_MARKER = '[ LONG DESCRIPTION ] - Write it below'
_NOTEPAD_HEADER = (
    '[ INSTRUCTIONS ]',
    _RULE,
    'Plain text, Markdown, or HTML are accepted.',
    'Headings and images are not accepted.',
    _RULE,
    'Markdown may contain lists, **bold**, *italic*, [links](url),',
    'and line breaks. It is converted to HTML once saved.',
    _RULE,
    'HTML may use <p></p>, <br>, <ul></ul>, <ol></ol>, <li></li>,',
    '<strong></strong>, <em></em>, <a href="..."></a>.',
    '======',
    _NOTEPAD_MARKER,
)


_HEADER_SIGNATURES = (
    'enter the long description below',
    'write the long description beside the colon',
    'write the long description after the colon',
    'write it below',
    'plain text, markdown, or html are accepted',
    'markdown may contain lists',
    'is converted to html',
    'headings and images are not accepted',
    'lines inside this box are not saved',
    'lines inside this box are ignored',
    'lines that belong to this header are not saved',
    'the lines above the marker are not saved',
    'the lines above are not saved',
    'html may use <p></p>',
    '<strong></strong>, <em></em>, <a href=',
)


def _is_box_border(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= _BOX_CHARS


def _is_header_instruction(line: str) -> bool:
    """True for an instruction line, a box border, or a leftover piece of either."""
    stripped = line.strip()
    if (
        stripped == _RULE
        or (stripped and set(stripped) == {'='})
        or _is_box_border(stripped)
        or stripped[:1] in '┌┐└┘├┤│'
    ):
        return True
    folded = stripped.strip('│').strip().lower()
    if folded in {'instructions', '[ instructions ]', 'long description'}:
        return True
    if folded.startswith('[ long description ]'):
        return True
    if folded.startswith('-----') and ('below' in folded or 'do not delete' in folded):
        return True
    return any(signature in folded for signature in _HEADER_SIGNATURES)


def _strip_notepad_header(body: str) -> str:
    """Keep the user's text and drop the instruction note, even when part of it is deleted."""
    lines = body.split('\n')
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == _NOTEPAD_MARKER or stripped.lower().startswith('[ long description ]'):
            return '\n'.join(lines[index + 1:])
    kept = [line for line in lines if not _is_header_instruction(line)]
    while kept and not kept[0].strip():
        del kept[0]
    return '\n'.join(kept)


def _read_notepad_body(body: str) -> list[str]:
    """Return the description lines, without the Notepad header."""
    if body.endswith('\n'):
        body = body[:-1]
    text = _strip_notepad_header(body)
    if text.endswith('\n'):
        text = text[:-1]
    return text.split('\n') if text else []


def _open_notepad(lines: list[str]) -> list[str] | None:
    """Open Notepad once. ``None`` means it could not be started."""
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
        handle.write('\n'.join(_NOTEPAD_HEADER))
        handle.write('\n')
        if lines:
            handle.write('\n'.join(lines))
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
    return _read_notepad_body(body)


def _edit_long_text(lines: list[str]) -> list[str] | None:
    """Open the whole description in an editor so any line can be changed.

    Returns the new lines, or ``None`` when no editor could be started.
    Header lines are ignored, including when the user deletes some of them.
    Ctrl+C closes the editor and aborts the tool.
    """
    return _open_notepad(lines)


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


def _is_plain_text(text: str) -> bool:
    """True when the terminal can accept *text* without treating it as markup."""
    return not looks_like_html(text) and not looks_like_markdown(text)


def _load_from_editor(lines: list[str]) -> list[str] | None:
    """Open Notepad with the current text. Return the saved lines, or ``None``."""
    edited = _edit_long_text(lines)
    if edited is None:
        _print_between_separators(
            'Could not open Notepad. Set the EDITOR variable. Please try again.',
        )
        return None
    return edited


def _choice(key: str, text: str) -> str:
    """One menu row. Numbers use the same ``1.`` form as the other prompts."""
    label = 'Enter' if key == 'Enter' else f'{key}.'
    return f'  {label}'.ljust(12) + text


def _choose_entry_mode(*, has_current: bool = False) -> str:
    """Ask whether the text is kept, typed here, or opened in Notepad.

    Returns ``keep``, ``terminal``, or ``notepad``. ``keep`` is offered only
    when a saved value is already shown.
    """
    if has_current:
        print('  Choose an option:')
        print(_choice('Enter', 'Keep the current value'))
        print(_choice('1', 'Replace it with plain text in this terminal, without line breaks'))
        print(_choice('2', 'Modify it in Notepad'))
    else:
        print('  Choose an option:')
        print(_choice('1', 'Plain text in this terminal, without line breaks'))
        print(_choice('2', 'Notepad for plain text, Markdown, or HTML'))
    print(_separator('-'))
    prompt = ': '
    retry = (
        'Press Enter to keep it, or type 1 for the terminal or 2 for Notepad. Please try again.'
        if has_current
        else 'Type 1 for the terminal or 2 for Notepad. Please try again.'
    )
    while True:
        answer = _read_line(prompt)
        if answer is None:
            raise EOFError
        answer = answer.strip()
        if has_current and answer == '':
            return 'keep'
        if answer == '1':
            return 'terminal'
        if answer == '2':
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


def _read_plain_line(seed: str) -> str | None:
    """Read one line of plain text. ``None`` means end of input."""
    print('  Plain text of any length. Markdown and HTML are not accepted here.')
    print(_separator('-'))
    if not seed:
        return _read_line(': ')
    line, prefilled = _read_prefilled(': ', seed)
    if line is None:
        return None
    if not line.strip() and not prefilled:
        return seed
    return line.rstrip()


def _confirm_or_modify(lines: list[str], mode: str) -> str:
    """Return ``confirm``, ``modify``, or ``notepad``.

    ``notepad`` is offered after plain text, so the same line can be continued
    in Notepad.
    """
    print(_separator('='))
    if mode == 'notepad':
        print(f'{constants.ICON_SUCCESS} Loaded {len(lines)} line(s) from Notepad:')
        _show_long_text_lines(lines)
        print(_separator('-'))
    print(_choice('Enter', 'Confirm this text'))
    if mode == 'terminal':
        print(_choice('1', 'Modify it in this terminal'))
        print(_choice('2', 'Continue in Notepad'))
        retry = (
            'Press Enter to confirm, type 1 to modify in this terminal, '
            'or type 2 to continue in Notepad. Please try again.'
        )
    else:
        print(_choice('1', 'Modify it in Notepad'))
        retry = 'Press Enter to confirm, or type 1 to modify in Notepad. Please try again.'
    print(_separator('-'))
    while True:
        answer = _read_line(': ')
        if answer is None:
            raise EOFError
        answer = answer.strip()
        if answer == '':
            return 'confirm'
        if answer == '1':
            return 'modify'
        if mode == 'terminal' and answer == '2':
            return 'notepad'
        _print_between_separators(retry)


def _stored_value(raw: str, max_len: int | None) -> tuple[str | None, str | None]:
    """Return ``(value, error)``. Exactly one of the two is set."""
    error = validate_long_description(raw)
    if error:
        return None, error
    value = normalize_long_description(raw)
    if not value:
        return None, 'Value cannot be empty'
    if max_len is not None and len(value) > max_len:
        return None, f'Value is more than {max_len} characters'
    return value, None


def input_html_text(
    name: str,
    max_len: int | None = None,
    default: str | None = None,
) -> str:
    """Collect a long description.

    The terminal accepts plain text of any length, without line breaks.
    Notepad accepts plain text, Markdown, or HTML. Enter confirms the text.
    ``1`` changes it in the terminal, and ``2`` opens Notepad. Markdown from
    Notepad is stored as HTML.
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
    note = 'use more than one sentence, preferably below 2000 characters'
    if max_len is not None:
        limit_line = f' (max {max_len} characters; {note})'
    else:
        limit_line = f' ({note})'
    print(
        f'{top_sep}\n'
        f'{name}{limit_line}\n'
        f'{bottom_sep}\n'
        f'{current_block}'.rstrip('\n')
    )
    mode = _choose_entry_mode(has_current=bool(default))
    if mode == 'keep' and default:
        kept = _kept_value(default)
        if kept is not None:
            return kept
        mode = 'terminal' if _is_plain_text(default) else 'notepad'
    draft = default.splitlines() if default else []
    while True:
        if mode == 'terminal':
            seed = ''
            if draft and _is_plain_text('\n'.join(draft)):
                seed = ' '.join(line.strip() for line in draft if line.strip())
            entered = _read_plain_line(seed)
            if entered is None:
                raise EOFError
            lines = [entered]
            raw = entered
            if not raw.strip():
                _print_between_separators('Value cannot be empty. Please try again.')
                continue
            if not _is_plain_text(raw):
                _print_between_separators(
                    'The terminal accepts plain text only. '
                    'Use Notepad for Markdown or HTML. Please try again.',
                )
                draft = [raw]
                mode = _choose_entry_mode(has_current=False)
                continue
        else:
            opened = _load_from_editor(draft)
            if opened is None:
                continue
            lines = opened
            raw = '\n'.join(lines)
        value, error = _stored_value(raw, max_len)
        if error or value is None:
            print('  Text:')
            _show_long_text_lines(lines)
            _print_between_separators(_retry_message(error or 'Value cannot be empty'))
            draft = lines
            continue
        action = _confirm_or_modify(lines, mode)
        if action == 'confirm':
            return value
        if action == 'notepad':
            mode = 'notepad'
        draft = lines
