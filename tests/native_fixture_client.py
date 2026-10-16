"""Test-only fake DLL-backed child domain seam; never starts a native process."""
import ctypes
import importlib.util
from pathlib import Path
from voice_flow import nemotron_abi, nemotron_engine


class DomainClient:
    def __init__(self, engine, dll, *, opened=False):
        spec = importlib.util.spec_from_file_location(
            "fixture_native_owner", Path(nemotron_engine.__file__).with_name("nemotron_native_worker.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.abi = nemotron_abi
        self.owner = module.NativeOwner()
        self.owner.dll = dll
        self.owner.recognizers[engine.rec_handle.value] = ctypes.c_void_p(engine.rec_handle.value)
        if opened:
            self.owner.streams[42] = (ctypes.c_void_p(42), None, (), engine.rec_handle.value)
        self.calls = []

    def call(self, op, **values):
        self.calls.append((op, values.copy()))
        return self.owner.dispatch(op, values)

    def close(self):
        self.owner.dispatch("shutdown", {})


def bind_native(engine, dll, *, opened=False):
    engine._native = DomainClient(engine, dll, opened=opened)
    engine._native_call = engine._native.call
    engine.fatal_error = None
    engine.metadata = getattr(engine, "metadata", {})
    engine.spec = getattr(engine, "spec", None) or {"default_language": "en"}
    return engine
