"""Native CF dictionary equality/lifetime and portable invalid-ref guards.

No permission prompt or application is launched by these tests.
"""
import ctypes
import sys
from unittest.mock import Mock

import pytest

from voice_flow.platform import macos_native as native


@pytest.mark.parametrize("pairs", [[], [(0, 2)], [(1, 0)]])
def test_null_objects_never_reach_cf_dictionary_create(monkeypatch, pairs):
    loader = Mock()
    monkeypatch.setattr(native, "_loader", loader)
    assert native.cf_dictionary(pairs) == 0
    loader.symbol.assert_not_called()
    loader.framework.assert_not_called()


@pytest.mark.parametrize("missing_kind", ["key", "value"])
def test_missing_callbacks_skip_native_call(monkeypatch, missing_kind):
    loader = Mock()
    monkeypatch.setattr(native, "_loader", loader)
    monkeypatch.setattr(native, "_cf", lambda: object())
    def missing(*args):
        raise ValueError("callback symbol unavailable")
    monkeypatch.setattr(native._CFDictionaryKeyCallBacks, "in_dll",
                        lambda *args: native._CFDictionaryKeyCallBacks())
    monkeypatch.setattr(native._CFDictionaryValueCallBacks, "in_dll",
                        lambda *args: native._CFDictionaryValueCallBacks())
    callback_type = (native._CFDictionaryKeyCallBacks if missing_kind == "key"
                     else native._CFDictionaryValueCallBacks)
    monkeypatch.setattr(callback_type, "in_dll", missing)
    assert native.cf_dictionary([(0x100000001, 0x100000002)]) == 0
    loader.symbol.assert_not_called()


def test_missing_cf_boolean_skips_ax_prompt_and_releases_key(monkeypatch):
    monkeypatch.setattr(native, "IS_MACOS", True)
    calls = []
    ax = Mock()
    dictionary = Mock(wraps=native.cf_dictionary)
    monkeypatch.setattr(native._loader, "symbol", lambda *args, **kwargs: ax)
    monkeypatch.setattr(native, "cfstring_from_python", lambda text: 0x100000001)
    monkeypatch.setattr(native, "cfbool", lambda value: 0)
    monkeypatch.setattr(native, "cf_dictionary", dictionary)
    monkeypatch.setattr(native, "cf_release", calls.append)
    assert native.accessibility_trusted(prompt=True) is False
    ax.assert_not_called()
    assert calls == [0x100000001]


def test_ax_pointer_width_and_owned_reference_cleanup(monkeypatch):
    monkeypatch.setattr(native, "IS_MACOS", True)
    calls = []
    options = 0x123456789AB
    ax = Mock(return_value=True)
    monkeypatch.setattr(native._loader, "symbol", lambda *args, **kwargs: ax)
    monkeypatch.setattr(native, "cfstring_from_python", lambda text: 0x100000001)
    monkeypatch.setattr(native, "cfbool", lambda value: 0x100000002)
    monkeypatch.setattr(native, "cf_dictionary", lambda pairs: options)
    monkeypatch.setattr(native, "cf_release", calls.append)
    assert native.accessibility_trusted(prompt=True) is True
    assert ax.argtypes == [ctypes.c_void_p]
    ax.assert_called_once_with(options)
    assert calls == [options, 0x100000001]


@pytest.mark.skipif(sys.platform != "darwin", reason="uses system CoreFoundation only")
def test_equal_content_distinct_cfstring_lookup_and_dictionary_retention():
    key_a = native.cfstring_from_python("APF dictionary equality regression key")
    key_b = native.cfstring_from_python("APF dictionary equality regression key")
    value = native.cfstring_from_python("APF retained dictionary value")
    dictionary = 0
    try:
        assert key_a and key_b and value
        assert key_a != key_b, "The regression needs two separately allocated CFStrings"
        dictionary = native.cf_dictionary([(key_a, value)])
        assert dictionary
        # The dictionary must own its contents after the caller releases them.
        native.cf_release(key_a)
        key_a = 0
        native.cf_release(value)
        value = 0
        lookup = native._loader.symbol("CoreFoundation", "CFDictionaryGetValue")
        lookup.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lookup.restype = ctypes.c_void_p
        retained_value = lookup(dictionary, key_b)
        assert retained_value
        assert native.cfstring_to_python(retained_value) == "APF retained dictionary value"
    finally:
        native.cf_release(dictionary)
        native.cf_release(key_a)
        native.cf_release(key_b)
        native.cf_release(value)
