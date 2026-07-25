"""Test script to inspect exact Win32 mouse message codes on middle click."""

from pynput import mouse

def win32_filter(msg, data):
    print(f"Mouse msg: {hex(msg)}")
    if msg in (0x0207, 0x0208, 0x00A7, 0x00A8, 0x0209, 0x00A9):
        print(f"--> BLOCKING middle click msg: {hex(msg)}")
        return False
    return True

listener = mouse.Listener(win32_event_filter=win32_filter, suppress=True)
listener.start()
print("Listening... Click middle scroll button now!")
listener.join()
