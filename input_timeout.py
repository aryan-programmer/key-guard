# https://github.com/johejo/inputimeout/blob/master/inputimeout/inputimeout.py
import sys

DEFAULT_TIMEOUT = 30.0
INTERVAL = 0.05

SP = " "
CR = "\r"
LF = "\n"
CRLF = CR + LF


class InputTimeoutOccurred(Exception):
    pass


def echo(string):
    sys.stdout.write(string)
    sys.stdout.flush()


def posix_input_timeout(prompt="", timeout=DEFAULT_TIMEOUT):
    echo(prompt)
    flush_input()
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ)
    events = sel.select(timeout)

    if events:
        key, _ = events[0]
        return key.fileobj.readline().rstrip(LF)
    else:
        echo(LF)
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
        raise InputTimeoutOccurred


def win_input_timeout(prompt="", timeout=DEFAULT_TIMEOUT):
    echo(prompt)
    begin = time.monotonic()
    end = begin + timeout
    line = ""

    while time.monotonic() < end:
        if msvcrt.kbhit():
            c = msvcrt.getwche()
            if c in (CR, LF):
                echo(CRLF)
                return line
            if c == "\003":
                raise KeyboardInterrupt
            if c == "\b":
                line = line[:-1]
                cover = SP * len(prompt + line + SP)
                echo("".join([CR, cover, CR, prompt, line]))
            else:
                line += c
        time.sleep(INTERVAL)

    echo(CRLF)
    raise InputTimeoutOccurred


def flush_input():
    try:
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        import sys, termios  # for linux/unix

        termios.tcflush(sys.stdin, termios.TCIOFLUSH)


try:
    import msvcrt

except ImportError:
    import selectors
    import termios

    input_timeout = posix_input_timeout

else:
    import time

    input_timeout = win_input_timeout
