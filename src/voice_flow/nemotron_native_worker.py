"""Standalone native ASR owner. No application/package initializer imports."""
from __future__ import annotations
import ctypes
import os
from multiprocessing.connection import Connection
from pathlib import Path
import sys
import threading

# -I omits the script directory: add only our sibling pure ABI definitions.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nemotron_abi as abi

MAX_AUDIO_BYTES = 64 * 1024 * 1024
MAX_STREAM_DRAIN_RESULTS = 4096


class NativeOwner:
    def __init__(self):
        self.dll = None
        self.recognizers = {}
        self.streams = {}
        self.serial = 0

    def token(self, table, value):
        self.serial += 1
        table[self.serial] = value
        return self.serial

    def options(self, values):
        opts = self.dll.nemo_speech_asr_recognition_options_default()
        opts.enable_automatic_punctuation = True
        refs = []
        if values.get("streaming"):
            opts.interim_results = False
        language = values.get("language")
        if language:
            if not isinstance(language, str) or len(language) > 32:
                raise ValueError("invalid language")
            encoded = language.encode("utf-8")
            opts.language_code = encoded
            refs.append(encoded)
        vocabulary = values.get("vocabulary", ())
        if not isinstance(vocabulary, (list, tuple)) or len(vocabulary) > 4096:
            raise ValueError("invalid vocabulary")
        refs.extend(abi._attach_speech_context(opts, vocabulary))
        return opts, refs

    def audio(self, values):
        data, count, rate = values["audio"], values["count"], values["rate"]
        if (not isinstance(data, bytes) or not isinstance(count, int) or count < 0
                or len(data) != count * 4 or len(data) > MAX_AUDIO_BYTES
                or not isinstance(rate, int) or not 1 <= rate <= 384000):
            raise ValueError("invalid float32 audio")
        return (ctypes.c_float * count).from_buffer_copy(data), count, rate

    def result(self, handle, status, final=True):
        if status != 0 or not handle.value:
            return {"status": status, "result": None}
        try:
            text = self.dll.nemo_speech_asr_result_transcript(handle, 0)
            is_final = self.dll.nemo_speech_asr_result_is_final(handle) if not final else True
            return {"status": status, "result": {"text": bytes(text or b""), "final": bool(is_final)}}
        finally:
            self.dll.nemo_speech_asr_result_destroy(handle)

    def recognize_streaming(self, handle, opts, refs, audio, count, rate):
        """Whole recording through the warmed cache-aware path; no partial success."""
        stream = ctypes.c_void_p()
        finalized = []
        final_count = 0
        pending_interim = False

        def drain():
            nonlocal final_count, pending_interim
            # A broken native producer must not loop forever. Overflow fails
            # the entire request; it never publishes a truncated transcript.
            for _ in range(MAX_STREAM_DRAIN_RESULTS):
                result = ctypes.c_void_p()
                status = self.dll.nemo_speech_asr_stream_next(stream, ctypes.byref(result))
                if status != 0:
                    if result.value:
                        self.dll.nemo_speech_asr_result_destroy(result)
                    return status
                value = self.result(result, status, final=False)["result"]
                if value is None:
                    return 0
                if value["final"]:
                    final_count += 1
                    pending_interim = False
                    text = value["text"].strip()
                    if text:
                        finalized.append(text)
                elif value["text"].strip():
                    pending_interim = True
            return -1

        try:
            status = self.dll.nemo_speech_asr_streaming_recognize(handle, ctypes.byref(opts), ctypes.byref(stream))
            if status != 0 or not stream.value:
                return {"status": status or -1, "result": None}
            block = max(1, rate * 160 // 1000)
            for offset in range(0, count, block):
                length = min(block, count - offset)
                samples = ctypes.cast(ctypes.byref(audio, offset * ctypes.sizeof(ctypes.c_float)),
                                      ctypes.POINTER(ctypes.c_float))
                status = self.dll.nemo_speech_asr_stream_push_f32(stream, samples, length, rate)
                if status == 0:
                    status = drain()
                if status != 0:
                    return {"status": status, "result": None}
            before_finish_finals = final_count
            status = self.dll.nemo_speech_asr_stream_finish(stream)
            if status == 0:
                status = drain()
            if status != 0 or final_count == before_finish_finals or pending_interim:
                return {"status": status or -1, "result": None}
            return {"status": 0, "result": {"text": b" ".join(finalized), "final": True}}
        finally:
            # opts and refs remain local/retained through native close, even
            # when setup returned a partial handle or decoding raised.
            if stream.value:
                self.dll.nemo_speech_asr_stream_close(stream)

    def dispatch(self, op, values):
        if op == "create":
            if self.dll is None:
                self.dll = abi.load_dll(values["dll_path"])
            backend = abi._BackendConfig(size=ctypes.sizeof(abi._BackendConfig), gpu=-1)
            model = abi._ModelConfig(size=ctypes.sizeof(abi._ModelConfig),
                                     path=values["model_path"].encode("utf-8"), name=None)
            config = abi._RecognizerConfig(size=ctypes.sizeof(abi._RecognizerConfig),
                                           backend=ctypes.pointer(backend), model=ctypes.pointer(model))
            handle = ctypes.c_void_p()
            status = self.dll.nemo_speech_asr_create(ctypes.byref(config), ctypes.byref(handle))
            return {"status": status, "handle": self.token(self.recognizers, handle) if status == 0 and handle.value else 0}
        if op == "shutdown":
            for token in tuple(self.streams):
                self.dispatch("stream_close", {"handle": token})
            for token in tuple(self.recognizers):
                self.dispatch("recognizer_close", {"handle": token})
            return None
        if op == "recognizer_close":
            for token, record in tuple(self.streams.items()):
                if record[3] == values["handle"]:
                    self.dispatch("stream_close", {"handle": token})
            handle = self.recognizers.pop(values["handle"], None)
            if handle is not None:
                self.dll.nemo_speech_asr_destroy(handle)
            return None
        if op == "stream_close":
            record = self.streams.pop(values["handle"], None)
            if record is not None:
                self.dll.nemo_speech_asr_stream_close(record[0])
            return None
        if op in ("stream_open", "recognize", "warm"):
            handle = self.recognizers[values["handle"]]
            if any(record[3] == values["handle"] for record in self.streams.values()):
                return {"status": -1, "busy": True, "result": None, "handle": 0}
            opts, refs = self.options(values)
            if op == "recognize":
                audio, count, rate = self.audio(values)
                if values.get("streaming") is True:
                    return self.recognize_streaming(handle, opts, refs, audio, count, rate)
                result = ctypes.c_void_p()
                status = self.dll.nemo_speech_asr_recognize_f32(handle, ctypes.byref(opts), audio, count, rate, ctypes.byref(result))
                return self.result(result, status)
            stream = ctypes.c_void_p()
            status = self.dll.nemo_speech_asr_streaming_recognize(handle, ctypes.byref(opts), ctypes.byref(stream))
            if status != 0 or not stream.value:
                # Native setup may return an allocated partial stream on error.
                # opts/refs remain alive until this close completes.
                if stream.value:
                    self.dll.nemo_speech_asr_stream_close(stream)
                return {"status": status, "handle": 0} if op == "stream_open" else {"status": status}
            if op == "stream_open":
                return {"status": status, "handle": self.token(self.streams, (stream, opts, refs, values["handle"]))}
            try:
                silence = (ctypes.c_float * 16000)()
                status = self.dll.nemo_speech_asr_stream_push_f32(stream, silence, 16000, 16000)
                if status == 0:
                    while True:
                        result = ctypes.c_void_p()
                        nxt = self.dll.nemo_speech_asr_stream_next(stream, ctypes.byref(result))
                        if nxt != 0 or not result.value:
                            break
                        self.dll.nemo_speech_asr_result_destroy(result)
                return {"status": status}
            finally:
                self.dll.nemo_speech_asr_stream_close(stream)
        if op in ("stream_push_next", "stream_finish", "stream_next"):
            stream = self.streams[values["handle"]][0]
            if op == "stream_push_next":
                audio, count, rate = self.audio(values)
                status = self.dll.nemo_speech_asr_stream_push_f32(stream, audio, count, rate)
                if status != 0:
                    return {"status": status, "result": None, "push_failed": True}
            elif op == "stream_finish":
                return {"status": self.dll.nemo_speech_asr_stream_finish(stream)}
            result = ctypes.c_void_p()
            status = self.dll.nemo_speech_asr_stream_next(stream, ctypes.byref(result))
            return self.result(result, status, final=False)
        raise ValueError("operation not allowed")


def serve(connection):
    owner = NativeOwner()
    generation = None
    try:
        while True:
            request = connection.recv()
            if generation is None:
                generation = request["generation"]
            if generation != request["generation"]:
                raise ValueError("wrong generation")
            response = {"id": request["id"], "generation": generation}
            try:
                response["value"] = owner.dispatch(request["op"], request["values"])
            except MemoryError:
                response["protocol_error"] = True
                response["failure_code"] = "memory_error"
            except (KeyError, TypeError, ValueError):
                response["protocol_error"] = True
                response["failure_code"] = "invalid_request"
            except Exception:
                # Only fixed codes leave diagnostics; never exception strings,
                # native text, audio, paths, language or vocabulary options.
                response["protocol_error"] = True
                response["failure_code"] = "native_call_error"
            connection.send(response)
            if request["op"] == "shutdown":
                break
    except (EOFError, OSError):
        pass
    finally:
        connection.close()


def watch_parent(connection):
    """EOF is independent of the RPC thread, even while native inference hangs."""
    try:
        while True:
            connection.recv_bytes()
    except (EOFError, OSError):
        os._exit(0)


if __name__ == "__main__":
    if os.name == "nt":
        from multiprocessing.connection import PipeConnection
        connection_type = PipeConnection
    else:
        connection_type = Connection
    lifetime = connection_type(int(sys.argv[2]), readable=True, writable=False)
    threading.Thread(target=watch_parent, args=(lifetime,), daemon=True).start()
    serve(connection_type(int(sys.argv[1])))
