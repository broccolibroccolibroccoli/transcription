"""
torchaudio 2.4+ では set_audio_backend / get_audio_backend が削除されるが、
pyannote.audio 3.1 系が import 時に参照する。whisperx を import する前にこのモジュールを読み込む。
PyTorch 2.6+ の torch.load(weights_only=True) で pickle に含まれる型を許可する。
"""
import torch
from typing import Any

torch.serialization.add_safe_globals([Any])

try:
    from omegaconf import DictConfig, ListConfig
    from omegaconf.base import ContainerMetadata

    torch.serialization.add_safe_globals(
        [ListConfig, DictConfig, ContainerMetadata]
    )
except Exception:
    pass

import torchaudio

if not hasattr(torchaudio, "set_audio_backend"):

    def _noop_set_audio_backend(*_args, **_kwargs):
        pass

    torchaudio.set_audio_backend = _noop_set_audio_backend

if not hasattr(torchaudio, "get_audio_backend"):

    def _default_get_audio_backend():
        return "soundfile"

    torchaudio.get_audio_backend = _default_get_audio_backend
