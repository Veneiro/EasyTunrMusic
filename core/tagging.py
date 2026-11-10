"""Escritura de etiquetas (título, artista, álbum, año, ISRC, carátula y letra) con mutagen.

Se usa tras descargar canciones importadas de Spotify, para que el archivo lleve los
datos limpios de Spotify en lugar del título del vídeo de YouTube.
"""
import base64
import logging
import os

logger = logging.getLogger(__name__)


def _picture_mime(data):
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _split_artists(artist):
    return [a.strip() for a in (artist or "").replace(";", ",").split(",") if a.strip()]


def write_tags(path, track, cover=None, lyrics=None):
    """Escribe los datos de `track` (spotify.Track) en el archivo. Devuelve True si pudo.

    cover: bytes de la imagen (sustituye a la miniatura de YouTube).
    lyrics: texto de la letra sin marcas de tiempo.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            _write_id3(path, track, cover, lyrics)
        elif ext == ".wav":
            _write_wav(path, track, cover, lyrics)
        elif ext in (".m4a", ".aac", ".mp4"):
            _write_mp4(path, track, cover, lyrics)
        elif ext == ".flac":
            _write_flac(path, track, cover, lyrics)
        elif ext in (".opus", ".ogg", ".oga"):
            _write_ogg(path, track, cover, lyrics)
        else:
            return False  # .webm y otros: mutagen no los escribe
        return True
    except Exception:
        logger.warning("No se pudieron escribir las etiquetas de %s", path, exc_info=True)
        return False


# ------------------------------------------------------------------ ID3 (MP3, WAV)

def _fill_id3(tags, track, cover, lyrics):
    from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TRCK, TSRC, USLT
    tags.setall("TIT2", [TIT2(encoding=3, text=track.title)])
    if track.artist:
        # Un solo texto "A, B": en ID3 v2.3 varios valores se unen con "/" ("A/B")
        tags.setall("TPE1", [TPE1(encoding=3, text=", ".join(_split_artists(track.artist)) or track.artist)])
    if track.album:
        tags.setall("TALB", [TALB(encoding=3, text=track.album)])
    if track.release_date:
        tags.setall("TDRC", [TDRC(encoding=3, text=track.release_date[:10])])
    if track.isrc:
        tags.setall("TSRC", [TSRC(encoding=3, text=track.isrc)])
    if track.track_number:
        tags.setall("TRCK", [TRCK(encoding=3, text=str(track.track_number))])
    if cover:
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=_picture_mime(cover), type=3, desc="Cover", data=cover))
    if lyrics:
        tags.setall("USLT", [USLT(encoding=3, lang="spa", desc="", text=lyrics)])
    # El comentario de yt-dlp suele llevar la descripción del vídeo: no aporta nada
    tags.delall("COMM")


def _write_id3(path, track, cover, lyrics):
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    _fill_id3(tags, track, cover, lyrics)
    tags.save(path, v2_version=3)


def _write_wav(path, track, cover, lyrics):
    from mutagen.wave import WAVE
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    _fill_id3(audio.tags, track, cover, lyrics)
    audio.save()


# ------------------------------------------------------------------ MP4 (M4A: AAC, ALAC)

def _write_mp4(path, track, cover, lyrics):
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags["\xa9nam"] = [track.title]
    if track.artist:
        tags["\xa9ART"] = [track.artist]
    if track.album:
        tags["\xa9alb"] = [track.album]
    if track.release_date:
        tags["\xa9day"] = [track.release_date[:10]]
    if track.track_number:
        tags["trkn"] = [(int(track.track_number), 0)]
    if track.isrc:
        tags["----:com.apple.iTunes:ISRC"] = [track.isrc.encode()]
    if cover:
        fmt = MP4Cover.FORMAT_PNG if _picture_mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
        tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
    if lyrics:
        tags["\xa9lyr"] = [lyrics]
    tags.pop("\xa9cmt", None)
    tags.pop("desc", None)
    audio.save()


# ------------------------------------------------------------------ Vorbis (FLAC, Opus, OGG)

def _vorbis_fields(tags, track, lyrics):
    tags["title"] = [track.title]
    if track.artist:
        tags["artist"] = _split_artists(track.artist) or [track.artist]
    if track.album:
        tags["album"] = [track.album]
    if track.release_date:
        tags["date"] = [track.release_date[:10]]
    if track.isrc:
        tags["isrc"] = [track.isrc]
    if track.track_number:
        tags["tracknumber"] = [str(track.track_number)]
    if lyrics:
        tags["lyrics"] = [lyrics]
    for key in ("comment", "description", "synopsis", "purl"):
        if key in tags:
            del tags[key]


def _picture(cover):
    from mutagen.flac import Picture
    pic = Picture()
    pic.type = 3
    pic.mime = _picture_mime(cover)
    pic.desc = "Cover"
    pic.data = cover
    return pic


def _write_flac(path, track, cover, lyrics):
    from mutagen.flac import FLAC
    audio = FLAC(path)
    if audio.tags is None:
        audio.add_tags()
    _vorbis_fields(audio.tags, track, lyrics)
    if cover:
        audio.clear_pictures()
        audio.add_picture(_picture(cover))
    audio.save()


def _write_ogg(path, track, cover, lyrics):
    from mutagen import File as MutagenFile
    audio = MutagenFile(path)
    if audio is None:
        raise ValueError("Formato no reconocido")
    if audio.tags is None:
        audio.add_tags()
    _vorbis_fields(audio.tags, track, lyrics)
    if cover:
        audio.tags["metadata_block_picture"] = [base64.b64encode(_picture(cover).write()).decode("ascii")]
    audio.save()


def read_basic(path):
    """(título, artista, duración) de un archivo ya etiquetado, para buscar su letra.

    Sin el modo "easy" de mutagen, que no admite WAV: se usan las mismas claves que la
    Biblioteca (ID3, MP4 y Vorbis)."""
    from mutagen import File as MutagenFile
    from .library import _first
    try:
        audio = MutagenFile(path)
    except Exception:
        return "", "", 0.0
    if audio is None:
        return "", "", 0.0
    tags = getattr(audio, "tags", None)
    title = _first(tags, "TIT2", "©nam", "title")
    artist = _first(tags, "TPE1", "©ART", "artist")
    return title, artist, float(getattr(getattr(audio, "info", None), "length", 0) or 0)
