"""Synthetic speech worker for soft-deadline tests: no DLL, model or audio device.

Speaks the NativeASRClient pipe protocol. ``recognize`` (the whole-recording
decode) is slow, so a short caller deadline always expires while it runs;
``stream_push_next`` can be slowed with SLOW_WORKER_PUSH_SECONDS. Every result
is a final transcript so the stream path completes normally.
"""
import os
import sys
import threading
import time
from multiprocessing.connection import Connection

RECOGNIZE_SECONDS = float(os.environ.get("SLOW_WORKER_RECOGNIZE_SECONDS", "0.4"))
PUSH_SECONDS = float(os.environ.get("SLOW_WORKER_PUSH_SECONDS", "0.002"))


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
streams = {}
serial = 0
while True:
    request = connection.recv()
    op, values = request["op"], request["values"]
    value = None
    if op == "create":
        value = {"status": 0, "handle": 1}
    elif op == "warm":
        value = {"status": 0}
    elif op == "stream_open":
        serial += 1
        streams[serial] = {"pushed": 0, "finished": False, "emitted": False}
        value = {"status": 0, "handle": serial}
    elif op == "stream_push_next":
        time.sleep(PUSH_SECONDS)
        streams[values["handle"]]["pushed"] += values.get("count", 0)
        value = {"status": 1, "result": None}
    elif op == "stream_finish":
        streams[values["handle"]]["finished"] = True
        value = {"status": 0}
    elif op == "stream_next":
        stream = streams[values["handle"]]
        if stream["finished"] and not stream["emitted"]:
            stream["emitted"] = True
            value = {"status": 0, "result": {"text": b"stream text.", "final": True}}
        else:
            value = {"status": 1, "result": None}
    elif op == "stream_close":
        streams.pop(values["handle"], None)
    elif op == "recognize":
        time.sleep(RECOGNIZE_SECONDS)
        value = {"status": 0, "result": {"text": b"whole recording text.", "final": True}}
    response = {"id": request["id"], "generation": request["generation"], "value": value}
    connection.send(response)
    if op == "shutdown":
        break
connection.close()
