"""Opciones de descarga como datos puros (sin variables de tkinter)."""
from dataclasses import dataclass

LOSSY_CODECS = ("mp3", "aac", "opus")
LOSSLESS_CODECS = ("flac", "wav", "alac")

SUPPORTED_SAMPLE_RATES = {
    "mp3": [32000, 44100, 48000],
    "aac": [44100, 48000],
    "opus": [48000],
}


@dataclass(frozen=True)
class DownloadSettings:
    codec: str = "mp3"
    bitrate: str = "192"
    bit_depth: str = "16"
    sample_rate: str = "44100"
    channels: str = "stereo"          # stereo | mono | multichannel
    normalization: str = "off"        # off | lufs_14 | lufs_23 | custom
    custom_lufs_i: str = "-14"
    custom_lufs_tp: str = "-1.5"
    custom_lufs_lra: str = "11"
    extract_audio: bool = True
    metadata: bool = True
    extract_thumbnail: bool = False
    keep_original: bool = False
    dynamic_compression: bool = False

    @property
    def is_lossy(self):
        return self.codec in LOSSY_CODECS

    def loudnorm_targets(self):
        if self.normalization == "custom":
            return self.custom_lufs_i, self.custom_lufs_tp, self.custom_lufs_lra
        if self.normalization == "lufs_14":
            return "-14", "-1.5", "11"
        return "-23", "-2", "7"

    def effective_sample_rate(self):
        """Ajusta la frecuencia a una que el códec admita."""
        try:
            target = int(self.sample_rate)
        except (TypeError, ValueError):
            return self.sample_rate
        supported = SUPPORTED_SAMPLE_RATES.get((self.codec or "").lower())
        if supported and target not in supported:
            target = min(supported, key=lambda rate: abs(rate - target))
        return str(target)
