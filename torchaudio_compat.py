"""
torchaudio 2.4+ では set_audio_backend / get_audio_backend が削除されるが、
pyannote.audio 3.1 系が import 時に参照する。whisperx を import する前にこのモジュールを読み込む。

PyTorch 2.6+ では torch.load の既定が weights_only=True になり、
transformers / pyannote 等のチェックポイント読み込みで失敗することがある。
信頼できるソースのモデルのみを扱う前提で、weights_only=False に統一する。
"""
import torch

_torch_load_orig = torch.load


def _torch_load_weights_only_false(*args, **kwargs):
    kwargs["weights_only"] = False
    return _torch_load_orig(*args, **kwargs)


torch.load = _torch_load_weights_only_false

import torchaudio

if not hasattr(torchaudio, "set_audio_backend"):

    def _noop_set_audio_backend(*_args, **_kwargs):
        pass

    torchaudio.set_audio_backend = _noop_set_audio_backend

if not hasattr(torchaudio, "get_audio_backend"):

    def _default_get_audio_backend():
        return "soundfile"

    torchaudio.get_audio_backend = _default_get_audio_backend
