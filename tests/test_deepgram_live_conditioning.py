import json
import queue
import threading
import time
import numpy as np
import pytest
from voice_flow.flux_stream import FluxStreamTranscriber, NovaStreamTranscriber
from voice_flow.storage import storage
from voice_flow.voice_enhance import LiveSpeechEnhancer

class Transport:
    def __init__(self, nova):
        self.nova=nova
        self.sent=[]
        self.incoming=queue.Queue()
        self.closed=threading.Event()
    def send(self, message):
        self.sent.append(message)
        if isinstance(message, str):
            if self.nova:
                self.incoming.put(json.dumps({'type':'Results','is_final':True,'start':0,'duration':2,'channel':{'alternatives':[{'transcript':'synthetic complete'}]}}))
                self.incoming.put(json.dumps({'type':'Metadata'}))
            else:
                self.incoming.put(json.dumps({'type':'TurnInfo','event':'EndOfTurn','trigger':'manual','turn_index':0,'transcript':'synthetic complete','audio_window_end':2}))
    def recv(self, timeout):
        try: return self.incoming.get(timeout=timeout)
        except queue.Empty: raise TimeoutError()
    def close(self): self.closed.set()

def replay(monkeypatch, kind, profile, rate=44100):
    reads=[]
    processed=[]
    class ObservedEnhancer(LiveSpeechEnhancer):
        def process(self, frame, sr=16000):
            processed.append((len(frame), sr))
            return super().process(frame, sr)
    monkeypatch.setattr('voice_flow.flux_stream.LiveSpeechEnhancer', ObservedEnhancer)
    selected=[profile]
    def setting(key, default=None):
        if key=='voice_flow_mic_profile':
            reads.append(key)
            return selected[0]
        return default
    monkeypatch.setattr(storage,'get_setting',setting)
    transport=Transport(kind=='nova')
    urls=[]
    monkeypatch.setattr('websockets.sync.client.connect',lambda url, **kwargs:(urls.append(url) or transport))
    monkeypatch.setattr('voice_flow.stt_engines._key_for',lambda provider:'synthetic')
    stream=(NovaStreamTranscriber if kind=='nova' else FluxStreamTranscriber)()
    stream.start_session(model_ref='deepgram/nova-3' if kind=='nova' else 'deepgram/flux-general-en')
    selected[0]='off' # settings are frozen at session start
    lengths=[1024]*12+[137]
    t=np.arange(sum(lengths))/rate
    audio=(.004*np.sin(2*np.pi*190*t)).astype(np.float32)
    before=audio.copy()
    offset=0
    for length in lengths:
        stream.submit_frame(audio[offset:offset+length,None],rate)
        offset+=length
    stream.end_session(deadline=time.monotonic()+1)
    assert stream.collect(timeout=2)=='synthetic complete'
    assert transport.closed.wait(1)
    np.testing.assert_array_equal(audio,before)
    assert not stream.had_failures()
    assert 'sample_rate='+str(rate) in urls[0]
    packets=[m for m in transport.sent if isinstance(m,bytes)]
    pcm=b''.join(packets)
    assert len(pcm)==audio.size*2
    assert processed == [(length, rate) for length in lengths]
    assert len(packets)==len(lengths) if kind=='nova' else all(len(p)==round(rate*.08)*2 for p in packets[:-1])
    return np.frombuffer(pcm,dtype='<i2'),audio,reads

@pytest.mark.parametrize('kind',['nova','flux'])
@pytest.mark.parametrize('rate',[16000,44100,48000])
def test_far_profile_conditions_successful_live_transport_once(monkeypatch,kind,rate):
    far,audio,reads=replay(monkeypatch,kind,'far',rate)
    off,_,off_reads=replay(monkeypatch,kind,'off',rate)
    assert np.sqrt(np.mean(far.astype(float)**2)) > 4*np.sqrt(np.mean(off.astype(float)**2))
    assert reads==off_reads==['voice_flow_mic_profile']
    np.testing.assert_array_equal(off,(audio*32767).astype('<i2'))
    assert np.max(np.abs(far.astype(float)))<=.95*32767+1
    again,_,_=replay(monkeypatch,kind,'far',rate)
    np.testing.assert_array_equal(far,again)


def test_unavailable_profile_setting_uses_safe_auto(monkeypatch):
    from voice_flow.flux_stream import _session_enhancer

    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic setting unavailable")

    monkeypatch.setattr(storage, "get_setting", unavailable)
    enhancer = _session_enhancer()
    assert enhancer.profile == "auto"
    assert np.isfinite(enhancer.process(np.ones(1024, dtype=np.float32) * 0.004, 16000)).all()


def test_nova_pcm_static_helper_retains_sanitization_and_scaling():
    frame = np.array([[0.25], [-0.5], [np.nan], [np.inf]], dtype=np.float32)
    mono, pcm = NovaStreamTranscriber._pcm(frame)
    np.testing.assert_array_equal(mono, [0.25, -0.5, 0.0, 0.0])
    np.testing.assert_array_equal(np.frombuffer(pcm, dtype="<i2"), [8191, -16383, 0, 0])
