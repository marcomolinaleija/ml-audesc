# -*- coding: utf-8 -*-
import comtypes.client
from pathlib import Path

# It's possible comtypes.gen is not available on first run
# This is a robust way to handle it.
try:
    from comtypes.gen import SpeechLib
    COMTYPES_AVAILABLE = True
except (ImportError, OSError):
    COMTYPES_AVAILABLE = False

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
