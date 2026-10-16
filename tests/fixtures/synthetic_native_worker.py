"""Standalone synthetic peer: no DLL, model, microphone, or application imports."""
import os
import sys
import time
import threading
from multiprocessing.connection import Connection


def guard(event, args):
    if event in ("subprocess.Popen", "socket.connect", "socket.bind", "ctypes.dlopen"):
        raise AssertionError("Synthetic worker external effect blocked")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0]).replace("/", "\\").lower()
        if "\\.voice_flow\\" in path or "ai-productivity-flow\\src\\" in path:
            raise AssertionError("Private/original reads blocked")
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            raise AssertionError("Synthetic worker file writes blocked")


sys.addaudithook(guard)
def watch_parent(connection):
    try:
        while True:
            connection.recv_bytes()
    except (EOFError, OSError):
        os._exit(0)


if os.name == "nt":
    from multiprocessing.connection import PipeConnection
    connection_type = PipeConnection
else:
    connection_type = Connection
lifetime = connection_type(int(sys.argv[2]), readable=True, writable=False)
threading.Thread(target=watch_parent, args=(lifetime,), daemon=True).start()
connection = connection_type(int(sys.argv[1]))
while True:
    request = connection.recv()
    op, values = request["op"], request["values"]
    if op in ("crash", "recognize"):
        os._exit(73)
    if op == "hang":
        time.sleep(30)
    response = {"id": request["id"], "generation": request["generation"], "value": values}
    if op == "late":
        time.sleep(0.3)
    if op == "shutdown":
        response["value"] = None
    connection.send(response)
    if op == "shutdown":
        break
    if op == "stop_reading":
        time.sleep(30)
connection.close()
