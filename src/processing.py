# -*- coding: utf-8 -*-
import comtypes.client
from pathlib import Path
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip

# It's possible comtypes.gen is not available on first run
# This is a robust way to handle it.
try:
    from comtypes.gen import SpeechLib
    COMTYPES_AVAILABLE = True
except (ImportError, OSError):
    COMTYPES_AVAILABLE = False

def get_sapi_voices():
    """Returns a list of available SAPI5 voices."""
    if not COMTYPES_AVAILABLE:
        return []
    
    voices = []
    try:
        comtypes.CoInitialize()
        speaker = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = list(speaker.GetVoices())
    except Exception as e:
        print(f"Error al obtener voces SAPI5: {e}")
    finally:
        comtypes.CoUninitialize()
    return voices

def generate_tts_audio_files(items_to_generate, voice_token, rate, temp_dir, progress_callback):
    """
    Generates TTS audio files for a list of items.
    This function is designed to be run in a separate thread.
    """
    if not COMTYPES_AVAILABLE:
        return False, ImportError("La librería de voz de Windows (SAPI5) no está disponible.")

    total_items = len(items_to_generate)
    progress_callback(0, "Iniciando generación de audios TTS...")

    try:
        # It's better to initialize COM in the thread where it's used.
        comtypes.CoInitialize()
        
        speaker = comtypes.client.CreateObject("SAPI.SpVoice")
        if voice_token:
            speaker.Voice = voice_token
        speaker.Rate = rate

        for i, item in enumerate(items_to_generate):
            progress_percent = int(((i + 1) / total_items) * 100)
            # Callback to update message only
            progress_callback(None, f"Generando audio {i+1}/{total_items}...")

            output_filename = Path(temp_dir) / f"tts_{item.tiempo:.2f}_{i:03d}.wav".replace('.', '_')

            file_stream = comtypes.client.CreateObject("SAPI.SpFileStream")
            file_stream.Open(str(output_filename), SpeechLib.SSFMCreateForWrite)
            speaker.AudioOutputStream = file_stream
            
            speaker.Speak(item.descripcion)
            file_stream.Close()
            
            item.archivo_audio = str(output_filename)
            # Callback to update percentage only
            progress_callback(progress_percent, None)

        progress_callback(100, "¡Generación de audios completada!")
        return True, None  # Success, no error
    except Exception as e:
        return False, e  # Failure, return exception
    finally:
        # Uninitialize COM
        comtypes.CoUninitialize()


def get_video_metadata(video_path):
    """Extracts metadata from a video file."""
    try:
        with VideoFileClip(video_path) as video_clip:
            return {"duration": video_clip.duration}
    except Exception as e:
        print(f"Error al obtener metadatos del video {video_path}: {e}")
        return None

def generate_video_with_ads(video_path, audio_items, output_path, vol_original, vol_description, progress_callback):
    """
    Generates a new video file with audio descriptions.
    Designed to be run in a separate thread.
    """
    try:
        progress_callback(0, "Paso 1/5: Iniciando generación...")
        
        progress_callback(10, "Paso 2/5: Cargando video principal...")
        video = VideoFileClip(video_path)
        
        progress_callback(20, "Paso 3/5: Procesando audios de descripción...")
        audio_clips = []
        for item in audio_items:
            try:
                ad_clip = AudioFileClip(item.archivo_audio).set_start(item.tiempo)
                audio_clips.append(ad_clip)
            except Exception as e:
                # It's better to log this to the console than to do nothing.
                print(f"Advertencia: No se pudo cargar el archivo de audio {item.archivo_audio}: {e}")
        
        if audio_clips:
            descriptions_audio = CompositeAudioClip(audio_clips).volumex(vol_description)
        else:
            descriptions_audio = None

        original_audio = video.audio.volumex(vol_original) if video.audio else None
        
        progress_callback(60, "Paso 4/5: Combinando audios...")
        final_audio_clips = []
        if original_audio: final_audio_clips.append(original_audio)
        if descriptions_audio: final_audio_clips.append(descriptions_audio)

        if final_audio_clips:
            final_audio = CompositeAudioClip(final_audio_clips)
            video_final = video.set_audio(final_audio)
        else:
            video_final = video.set_audio(None)

        progress_callback(80, "Paso 5/5: Exportando video final (esto puede tardar)...")
        
        video_final.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            remove_temp=True,
            verbose=False,
            logger=None
        )

        progress_callback(100, f"¡Completado! Video guardado en: {output_path}")
        
        # It's crucial to close clips to release file handles
        video.close()
        if original_audio: original_audio.close()
        if descriptions_audio: descriptions_audio.close()
        if 'final_audio' in locals() and final_audio: final_audio.close()
        video_final.close()
        for clip in audio_clips: clip.close()

        return True, None
    except Exception as e:
        return False, e
