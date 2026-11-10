"""Posprocesado de audio con FFmpeg: códec, canales, frecuencia, compresión y normalización."""
import json
import os

from . import tools
from .process import ProcessGroup


class AudioProcessingError(RuntimeError):
    pass


# Contenedores donde FFmpeg puede conservar la carátula como "attached_pic".
COVER_CONTAINERS = (".mp3", ".flac", ".m4a")


def _codec_args(codec, bit_depth):
    """Codificador de FFmpeg y formato de muestra para cada códec de la UI."""
    depth = str(bit_depth or "16")
    if codec == "mp3":
        return ["-c:a", "libmp3lame"]
    if codec == "aac":
        return ["-c:a", "aac"]
    if codec == "opus":
        return ["-c:a", "libopus"]
    if codec == "flac":
        args = ["-c:a", "flac", "-sample_fmt", "s16" if depth == "16" else "s32"]
        if depth == "24":
            args += ["-bits_per_raw_sample", "24"]
        return args
    if codec == "alac":
        return ["-c:a", "alac", "-sample_fmt", "s16p" if depth == "16" else "s32p"]
    if codec == "wav":
        return ["-c:a", {"16": "pcm_s16le", "24": "pcm_s24le", "32": "pcm_s32le"}.get(depth, "pcm_s16le")]
    return ["-c:a", codec]


def parse_loudnorm_json(output_text):
    start = output_text.rfind("{")
    end = output_text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(output_text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _check(code, err, step):
    if code != 0:
        tail = err.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        raise AudioProcessingError(f"FFmpeg falló ({step}): {' | '.join(tail)}")


def postprocess(input_path, settings, group: ProcessGroup, on_stage=None):
    """Recodifica `input_path` en su sitio. on_stage(clave, porcentaje)."""
    if not input_path or not os.path.exists(input_path):
        return
    stage = on_stage or (lambda *_: None)
    ffmpeg = tools.require_ffmpeg()
    codec = settings.codec

    root, ext = os.path.splitext(input_path)
    base_args = [ffmpeg, "-y", "-i", input_path, "-map_metadata", "0", "-map", "0:a:0"]
    output_args = _codec_args(codec, settings.bit_depth)
    if ext.lower() in COVER_CONTAINERS:
        # Conservar la carátula que yt-dlp ya incrustó
        output_args += ["-map", "0:v:0?", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    if settings.is_lossy:
        output_args += ["-b:a", f"{settings.bitrate}k"]
    if settings.channels == "mono":
        output_args += ["-ac", "1"]
    elif settings.channels == "multichannel":
        output_args += ["-ac", "6"]
    rate = settings.effective_sample_rate()
    if rate:
        output_args += ["-ar", rate]

    filters = []
    if settings.dynamic_compression:
        filters.append("acompressor=threshold=-21dB:ratio=9:attack=200:release=1000")

    temp_path = root + ".tmp" + ext
    try:
        if settings.normalization != "off":
            stage("analyzing", 84.0)
            target_i, target_tp, target_lra = settings.loudnorm_targets()
            pass1 = filters + [f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"]
            code, out, err = group.run(base_args + ["-af", ",".join(pass1), "-f", "null", "-"])
            _check(code, err, "análisis")
            analysis = parse_loudnorm_json(err.decode("utf-8", errors="replace") or out.decode("utf-8", errors="replace"))
            if not analysis:
                raise AudioProcessingError("No se pudo analizar el volumen (loudnorm)")
            pass2 = filters + [
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                f"measured_I={analysis.get('input_i')}:measured_LRA={analysis.get('input_lra')}:"
                f"measured_TP={analysis.get('input_tp')}:measured_thresh={analysis.get('input_thresh')}:"
                f"offset={analysis.get('target_offset')}:linear=true:print_format=summary"
            ]
            stage("normalizing", 92.0)
            code, _, err = group.run(base_args + ["-af", ",".join(pass2)] + output_args + [temp_path])
            _check(code, err, "normalización")
        else:
            stage("filtering", 90.0)
            args = base_args + (["-af", ",".join(filters)] if filters else [])
            code, _, err = group.run(args + output_args + [temp_path])
            _check(code, err, "conversión")

        stage("finalizing", 98.0)
        os.replace(temp_path, input_path)
        stage("done", 100.0)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
