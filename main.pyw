"""
FGOA Windows GUI Launcher (Console-less .pyw entry point)
Double-clicking this file runs pythonw.exe without opening any command prompt.
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import main

if __name__ == "__main__":
    main.main()
