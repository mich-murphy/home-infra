#!/usr/bin/env python3
"""systemd Type=notify/Watchdog entry point. Never background or invoke directly."""
from host_lifecycle import main

if __name__ == '__main__':
    main_args = __import__('sys').argv
    main_args[:] = [main_args[0], 'guard']
    main()
