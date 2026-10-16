#!/usr/bin/env python3
"""A lightweight standalone external text editor application for cross-application injection testing.

Runs as an independent external process (PID != Voice Flow test process) to prove
that Voice Flow pastes text reliably into standard third-party Windows applications
without relying on Notepad-specific controls or class names.
"""
import sys
import tkinter as tk
import time

def main():
    root = tk.Tk()
    root.title("External Text Editor - Test Target")
    root.geometry("400x300")

    text_widget = tk.Text(root, wrap="word", font=("Consolas", 11))
    text_widget.pack(expand=True, fill="both")
    text_widget.focus_set()

    # Print the native window handle to stdout so the test can target it
    root.update()
    hwnd = root.winfo_id()
    # On Windows, winfo_id() gives the HWND
    sys.stdout.write(f"HWND:{hwnd}\n")
    sys.stdout.flush()

    root.mainloop()

if __name__ == "__main__":
    main()
