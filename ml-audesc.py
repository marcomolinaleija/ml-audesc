# -*- coding: utf-8 -*-
"""
Generador de Audiodescripciones para Video - Interfaz Gráfica
Permite crear audiodescripciones personalizadas con interfaz visual intuitiva,
incluyendo generación por Texto a Voz (TTS) a partir de archivos SRT.

Dependencias:
pip install wxpython moviepy srt pyttsx3
"""

import wx
import wx.adv
import os
import sys
import json
import threading
import time
from pathlib import Path
import subprocess
import srt  # Para parsear archivos SRT
import shutil # Para borrar directorios de archivos temporales
from src.models import AudioDescriptionItem
from src.gui import TimeInputDialog, AudioSourceDialog

# Intentar importar dependencias clave
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

# Soporte para TTS a través de comtypes (SAPI5)
try:
    import comtypes.client
    # Generar wrappers de comtypes para la librería de voz de Windows si no existen
    from comtypes.gen import SpeechLib
    COMTYPES_AVAILABLE = True
except (ImportError, OSError):
    try:
        # Si falla la importación, es posible que los wrappers no se hayan generado.
        # Intentamos generarlos una vez.
        comtypes.client.GetModule("sapi.dll")
        from comtypes.gen import SpeechLib
        COMTYPES_AVAILABLE = True
    except (ImportError, OSError):
        COMTYPES_AVAILABLE = False






class FileDropTarget(wx.FileDropTarget):
    def __init__(self, window, callback):
        wx.FileDropTarget.__init__(self)
        self.window = window
        self.callback = callback

    def OnDropFiles(self, x, y, filenames):
        if filenames and len(filenames) == 1:
            self.callback(filenames[0])
            return True
        return False

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Generador de Audiodescripciones", size=(1000, 800))
        self.app_title_base = "Generador de Audiodescripciones"
        self.current_project_name = None
        self.video_file = ""
        self.video_duration = 0.0
        self.audiodescriptions = []
        self.temp_preview_files = []
        self.temp_tts_dir = None

        self.sapi_voices = []
        self.selected_voice_index = 0
        self.init_tts_engine()

        self.init_ui()
        self.check_dependencies()
        self.load_project_state()
        self.Bind(wx.EVT_CLOSE, self.save_project_state_and_exit)

    def init_tts_engine(self):
        if not COMTYPES_AVAILABLE:
            self.sapi_voices = []
            return
        try:
            # Creamos una instancia de voz para obtener la lista de voces disponibles
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            self.sapi_voices = list(speaker.GetVoices())
            if not self.sapi_voices:
                print("No se encontraron voces SAPI5.")
        except Exception as e:
            # Usamos print porque la UI podría no estar lista para un MessageBox
            print(f"Error fatal al inicializar SAPI5: {e}")
            self.sapi_voices = []

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        menu_bar = wx.MenuBar()
        file_menu = wx.Menu()
        import_srt_item = file_menu.Append(wx.ID_ANY, "Importar Proyecto desde &SRT...", "Cargar audiodescripciones desde un archivo SRT para generar con TTS")
        save_as_item = file_menu.Append(wx.ID_SAVEAS, "&Guardar proyecto como...", "Guardar el proyecto actual con un nuevo nombre")
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "&Cerrar\tAlt+F4", "Cerrar la aplicación")
        self.Bind(wx.EVT_MENU, self.on_import_srt_project, import_srt_item)
        self.Bind(wx.EVT_MENU, self.on_save_as_project, save_as_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        menu_bar.Append(file_menu, "&Archivo")
        
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "&Acerca de...", "Información sobre esta aplicación")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menu_bar.Append(help_menu, "&Ayuda")
        self.SetMenuBar(menu_bar)

        title = wx.StaticText(panel, label="Generador de Audiodescripciones para Video")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        video_box = wx.StaticBox(panel, label="Archivo de Video")
        video_sizer = wx.StaticBoxSizer(video_box, wx.HORIZONTAL)
        self.video_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.video_ctrl.SetDropTarget(FileDropTarget(self.video_ctrl, self.on_drop_video_file))
        video_browse_btn = wx.Button(panel, label="&Seleccionar Video...")
        video_browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_video)
        self.video_duration_label = wx.StaticText(panel, label="Duración: 00:00:00")
        video_sizer.Add(self.video_ctrl, 1, wx.ALL|wx.EXPAND, 5)
        video_sizer.Add(video_browse_btn, 0, wx.ALL, 5)
        video_sizer.Add(self.video_duration_label, 0, wx.ALL|wx.CENTER, 5)

        audio_box = wx.StaticBox(panel, label="Audiodescripciones")
        audio_sizer = wx.StaticBoxSizer(audio_box, wx.VERTICAL)
        
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="&Agregar Audiodescripción")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_audiodescription)
        import_btn = wx.Button(panel, label="&Importar Proyecto")
        import_btn.Bind(wx.EVT_BUTTON, self.on_import_project)
        export_btn = wx.Button(panel, label="&Exportar Proyecto")
        export_btn.Bind(wx.EVT_BUTTON, self.on_export_project)
        clear_btn = wx.Button(panel, label="&Limpiar Proyecto")
        clear_btn.Bind(wx.EVT_BUTTON, self.on_clear_project)
        control_sizer.Add(add_btn, 0, wx.ALL, 5)
        control_sizer.Add(import_btn, 0, wx.ALL, 5)
        control_sizer.Add(export_btn, 0, wx.ALL, 5)
        control_sizer.Add(clear_btn, 0, wx.ALL, 5)

        self.ad_list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES)
        self.ad_list_ctrl.InsertColumn(0, "Tiempo", width=100)
        self.ad_list_ctrl.InsertColumn(1, "Archivo de Audio", width=300)
        self.ad_list_ctrl.InsertColumn(2, "Descripción", width=400)
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit_audiodescription)
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_ad_list_selection_change)
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_ad_list_selection_change)

        list_and_buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        list_and_buttons_sizer.Add(self.ad_list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        ad_action_buttons_sizer = wx.BoxSizer(wx.VERTICAL)
        self.edit_ad_btn = wx.Button(panel, label="&Editar")
        self.edit_ad_btn.Bind(wx.EVT_BUTTON, self.on_edit_audiodescription)
        self.edit_ad_btn.Enable(False)
        self.delete_ad_btn = wx.Button(panel, label="&Borrar")
        self.delete_ad_btn.Bind(wx.EVT_BUTTON, self.on_remove_audiodescription_from_list)
        self.delete_ad_btn.Enable(False)
        ad_action_buttons_sizer.Add(self.edit_ad_btn, 0, wx.ALL, 5)
        ad_action_buttons_sizer.Add(self.delete_ad_btn, 0, wx.ALL, 5)
        list_and_buttons_sizer.Add(ad_action_buttons_sizer, 0, wx.EXPAND | wx.ALL, 5)

        audio_sizer.Add(control_sizer, 0, wx.ALL, 5)
        audio_sizer.Add(list_and_buttons_sizer, 1, wx.ALL|wx.EXPAND, 5)

        tts_box = wx.StaticBox(panel, label="Configuración de Voz (TTS)")
        tts_sizer = wx.StaticBoxSizer(tts_box, wx.VERTICAL)
        tts_grid_sizer = wx.FlexGridSizer(2, 2, 5, 5)
        tts_grid_sizer.AddGrowableCol(1, 1)

        voice_label = wx.StaticText(panel, label="Voz:")
        voice_names = [v.GetDescription() for v in self.sapi_voices]
        self.voice_choice = wx.Choice(panel, choices=voice_names)
        if self.sapi_voices:
            self.voice_choice.SetSelection(self.selected_voice_index)
        self.voice_choice.Bind(wx.EVT_CHOICE, self.on_tts_voice_change)
        tts_grid_sizer.Add(voice_label, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        tts_grid_sizer.Add(self.voice_choice, 1, wx.EXPAND|wx.ALL, 5)

        rate_label = wx.StaticText(panel, label="Velocidad:")
        self.rate_slider = wx.Slider(panel, value=0, minValue=-10, maxValue=10, style=wx.SL_HORIZONTAL)
        tts_grid_sizer.Add(rate_label, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        tts_grid_sizer.Add(self.rate_slider, 1, wx.EXPAND|wx.ALL, 5)
        
        tts_sizer.Add(tts_grid_sizer, 1, wx.EXPAND|wx.ALL, 5)

        self.generate_tts_btn = wx.Button(panel, label="&Generar Audios con Voz (TTS)")
        self.generate_tts_btn.Bind(wx.EVT_BUTTON, self.on_generate_tts_audios)
        tts_sizer.Add(self.generate_tts_btn, 0, wx.ALL|wx.CENTER, 5)
        
        output_box = wx.StaticBox(panel, label="Configuración de Salida")
        output_sizer = wx.StaticBoxSizer(output_box, wx.HORIZONTAL)
        output_label = wx.StaticText(panel, label="Archivo de salida:")
        self.output_ctrl = wx.TextCtrl(panel, value="video_con_audiodescripcion.mp4")
        vol_orig_label = wx.StaticText(panel, label="Vol. original:")
        self.vol_orig_ctrl = wx.SpinCtrlDouble(panel, value="0.6", min=0, max=2, inc=0.1)
        self.vol_orig_ctrl.SetDigits(1)
        vol_desc_label = wx.StaticText(panel, label="Vol. descripción:")
        self.vol_desc_ctrl = wx.SpinCtrlDouble(panel, value="1.5", min=0, max=3, inc=0.1)
        self.vol_desc_ctrl.SetDigits(1)
        output_sizer.Add(output_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.output_ctrl, 1, wx.ALL|wx.EXPAND, 5)
        output_sizer.Add(vol_orig_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.vol_orig_ctrl, 0, wx.ALL, 5)
        output_sizer.Add(vol_desc_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.vol_desc_ctrl, 0, wx.ALL, 5)

        final_action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.generate_btn = wx.Button(panel, label="&Generar Video con Audiodescripción")
        self.generate_btn.Bind(wx.EVT_BUTTON, self.on_generate)
        final_action_sizer.Add(self.generate_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(title, 0, wx.ALL|wx.CENTER, 10)
        main_sizer.Add(video_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(audio_sizer, 1, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(tts_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(output_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(final_action_sizer, 0, wx.ALL|wx.CENTER, 10)
        self.progress = wx.Gauge(panel, range=100)
        self.status_text = wx.StaticText(panel, label="Listo")
        main_sizer.Add(self.progress, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(self.status_text, 0, wx.ALL, 5)

        panel.SetSizer(main_sizer)
        self.Center()

    def check_dependencies(self):
        if not MOVIEPY_AVAILABLE:
            wx.MessageBox("MoviePy no está instalado. Funciones de video deshabilitadas.", "Dependencias faltantes", wx.OK | wx.ICON_WARNING)
            self.generate_btn.Enable(False)
        if not COMTYPES_AVAILABLE or not self.sapi_voices:
            wx.MessageBox("El motor de voz de Windows (SAPI5) no está disponible o no se encontraron voces. Funciones de TTS deshabilitadas.", "Dependencias faltantes", wx.OK | wx.ICON_WARNING)
            self.generate_tts_btn.Enable(False)
            self.voice_choice.Enable(False)
            self.rate_slider.Enable(False)

    def on_import_srt_project(self, event):
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Primero selecciona un archivo de video válido.", "Error", wx.OK | wx.ICON_ERROR)
            return

        with wx.FileDialog(self, "Importar archivo SRT", wildcard="Archivos SRT (*.srt)|*.srt", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                srt_path = dialog.GetPath()
                try:
                    with open(srt_path, 'r', encoding='utf-8-sig') as f:
                        subs = list(srt.parse(f.read()))
                    
                    if not subs:
                        wx.MessageBox("El archivo SRT está vacío o no tiene un formato válido.", "Error", wx.OK | wx.ICON_ERROR)
                        return

                    confirm = wx.MessageBox(f"Se encontraron {len(subs)} descripciones. ¿Deseas importarlas? Esto limpiará la lista actual.", "Confirmar Importación de SRT", wx.YES_NO | wx.ICON_QUESTION)
                    if confirm == wx.YES:
                        self.audiodescriptions.clear()
                        self.clean_temp_files() # Limpiar audios anteriores
                        for sub in subs:
                            item = AudioDescriptionItem(
                                tiempo=sub.start.total_seconds(),
                                descripcion=sub.content.replace('\n', ' '),
                                archivo_audio=""
                            )
                            self.audiodescriptions.append(item)
                        
                        self.update_ad_list_ctrl()
                        self.status_text.SetLabel(f"{len(subs)} descripciones cargadas desde SRT. Listas para generar audio.")
                        self.current_project_name = Path(srt_path).stem
                        self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")

                except Exception as e:
                    wx.MessageBox(f"Error al importar el archivo SRT: {e}", "Error de Importación", wx.OK | wx.ICON_ERROR)

    def on_generate_tts_audios(self, event):
        items_to_generate = [item for item in self.audiodescriptions if not item.archivo_audio and item.descripcion]
        if not items_to_generate:
            wx.MessageBox("No hay descripciones sin audio para generar.", "Información", wx.OK | wx.ICON_INFORMATION)
            return
        
        if not COMTYPES_AVAILABLE or not self.sapi_voices:
            wx.MessageBox("El motor de Texto a Voz (TTS) no está disponible.", "Error TTS", wx.OK | wx.ICON_ERROR)
            return

        if not self.temp_tts_dir or not os.path.exists(self.temp_tts_dir):
            self.temp_tts_dir = Path(wx.StandardPaths.Get().GetTempDir()) / f"ml-audesc-tts-{int(time.time())}"
            os.makedirs(self.temp_tts_dir, exist_ok=True)

        self.generate_tts_btn.Enable(False)
        self.generate_btn.Enable(False)
        
        thread = threading.Thread(target=self.generate_tts_thread, args=(items_to_generate,))
        thread.daemon = True
        thread.start()

    def generate_tts_thread(self, items_to_generate):
        total_items = len(items_to_generate)
        wx.CallAfter(self.status_text.SetLabel, "Iniciando generación de audios TTS...")
        wx.CallAfter(self.progress.SetValue, 0)

        try:
            # Crear objetos SAPI una vez
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            # Asignar la voz y velocidad seleccionada
            if self.sapi_voices:
                speaker.Voice = self.sapi_voices[self.selected_voice_index]
            speaker.Rate = self.rate_slider.GetValue()

            for i, item in enumerate(items_to_generate):
                progress_percent = int(((i + 1) / total_items) * 100)
                wx.CallAfter(self.status_text.SetLabel, f"Generando audio {i+1}/{total_items}...")
                
                output_filename = self.temp_tts_dir / f"tts_{item.tiempo:.2f}_{i:03d}.wav".replace('.', '_')

                # Configurar stream para guardar a archivo
                file_stream = comtypes.client.CreateObject("SAPI.SpFileStream")
                file_stream.Open(str(output_filename), SpeechLib.SSFMCreateForWrite)
                speaker.AudioOutputStream = file_stream
                
                # Generar el audio
                speaker.Speak(item.descripcion)
                
                # Cerrar el stream
                file_stream.Close()
                
                item.archivo_audio = str(output_filename)
                wx.CallAfter(self.progress.SetValue, progress_percent)
            
            wx.CallAfter(self.status_text.SetLabel, "¡Generación de audios completada!")
            wx.CallAfter(self.update_ad_list_ctrl)

        except Exception as e:
            # Mostramos el error en un MessageBox para mejor diagnóstico
            wx.CallAfter(wx.MessageBox, f"Ocurrió un error durante la generación de audios con SAPI5: {e}", "Error de TTS", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, "Error en la generación de audios.")
        finally:
            wx.CallAfter(self.generate_tts_btn.Enable, True)
            wx.CallAfter(self.update_action_buttons_state)

    def on_tts_voice_change(self, event):
        self.selected_voice_index = self.voice_choice.GetSelection()

    def on_exit(self, event):
        self.Close()

    def save_project_state_and_exit(self, event):
        self.save_project_state()
        self.clean_temp_files()
        event.Skip()

    def clean_temp_files(self):
        for f_path in self.temp_preview_files:
            try:
                if os.path.exists(f_path): os.remove(f_path)
            except Exception as e:
                print(f"Error al eliminar archivo temporal {f_path}: {e}")
        self.temp_preview_files.clear()

        if self.temp_tts_dir and os.path.exists(self.temp_tts_dir):
            try:
                shutil.rmtree(self.temp_tts_dir)
                print(f"Directorio temporal TTS eliminado: {self.temp_tts_dir}")
            except Exception as e:
                print(f"Error al eliminar directorio temporal TTS {self.temp_tts_dir}: {e}")
        self.temp_tts_dir = None

    def update_ad_list_ctrl(self):
        self.ad_list_ctrl.DeleteAllItems()
        sorted_descriptions = sorted(self.audiodescriptions, key=lambda x: x.tiempo)
        self.audiodescriptions = sorted_descriptions

        for item in self.audiodescriptions:
            index = self.ad_list_ctrl.InsertItem(self.ad_list_ctrl.GetItemCount(), self.format_time(item.tiempo))
            audio_display = os.path.basename(item.archivo_audio) if item.archivo_audio else "--- PENDIENTE DE GENERAR ---"
            self.ad_list_ctrl.SetItem(index, 1, audio_display)
            self.ad_list_ctrl.SetItem(index, 2, item.descripcion)
        
        self.update_action_buttons_state()

    def update_action_buttons_state(self):
        can_generate_video = bool(MOVIEPY_AVAILABLE and self.video_file and os.path.exists(self.video_file) and self.audiodescriptions and all(item.archivo_audio and os.path.exists(item.archivo_audio) for item in self.audiodescriptions))
        self.generate_btn.Enable(can_generate_video)
        
        can_generate_tts = bool(COMTYPES_AVAILABLE and self.sapi_voices and self.audiodescriptions and any(not item.archivo_audio and item.descripcion for item in self.audiodescriptions))
        self.generate_tts_btn.Enable(can_generate_tts)

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"

    def on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName(self.app_title_base)
        info.SetVersion("2.0.0")
        info.SetDescription("Herramienta para generar audiodescripciones, con soporte para TTS desde SRT.")
        info.SetCopyright("(C) 2025 MarcoML")
        info.AddDeveloper("MarcoML")
        info.SetWebSite("https://web.marco-ml.com")
        wx.adv.AboutBox(info)

    def on_browse_video(self, event):
        wildcard = "Archivos de video (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv"
        with wx.FileDialog(self, "Seleccionar archivo de video", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.on_drop_video_file(dialog.GetPath())

    def on_drop_video_file(self, file_path):
        self.video_file = file_path
        self.video_ctrl.SetValue(self.video_file)
        self.update_video_duration()
        video_path = Path(self.video_file)
        output_name = f"{video_path.stem}_con_audiodescripcion{video_path.suffix}"
        self.output_ctrl.SetValue(output_name)
        self.update_action_buttons_state()

    def update_video_duration(self):
        if self.video_file and os.path.exists(self.video_file):
            try:
                with VideoFileClip(self.video_file) as video_clip:
                    self.video_duration = video_clip.duration
                self.video_duration_label.SetLabel(f"Duración: {self.format_time(self.video_duration)}")
            except Exception as e:
                self.video_duration = 0.0
                self.video_duration_label.SetLabel("Duración: Error")
                wx.MessageBox(f"No se pudo obtener la duración del video: {e}", "Error de Video", wx.OK | wx.ICON_ERROR)
        else:
            self.video_duration = 0.0
            self.video_duration_label.SetLabel("Duración: N/A")
        self.update_action_buttons_state()

    def on_add_audiodescription(self, event):
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Primero selecciona un archivo de video válido.", "Error", wx.OK | wx.ICON_ERROR)
            return

        with TimeInputDialog(self, self.video_duration) as time_dialog:
            if time_dialog.ShowModal() != wx.ID_OK:
                return
            
            tiempo = time_dialog.get_time_in_seconds()

            with AudioSourceDialog(self) as source_dialog:
                if source_dialog.ShowModal() != wx.ID_OK:
                    return
                
                source = source_dialog.get_source()

                if source == 'file':
                    wildcard = "Archivos de audio (*.wav;*.mp3)|*.wav;*.mp3"
                    with wx.FileDialog(self, "Seleccionar archivo de audio", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as audio_dialog:
                        if audio_dialog.ShowModal() == wx.ID_OK:
                            audio_path = audio_dialog.GetPath()
                            desc_text = wx.GetTextFromUser("Ingresa una breve descripción (opcional):", "Descripción", "")
                            item = AudioDescriptionItem(tiempo=tiempo, archivo_audio=audio_path, descripcion=desc_text)
                            self.audiodescriptions.append(item)
                            self.update_ad_list_ctrl()
                
                elif source == 'tts':
                    desc_text = wx.GetTextFromUser("Ingresa el texto para la audiodescripción:", "Sintetizar Texto", "")
                    if desc_text: # Solo agregar si el usuario ingresó texto
                        item = AudioDescriptionItem(tiempo=tiempo, archivo_audio="", descripcion=desc_text)
                        self.audiodescriptions.append(item)
                        self.update_ad_list_ctrl()

    def on_edit_audiodescription(self, event):
        index = self.ad_list_ctrl.GetFirstSelected()
        if index == wx.NOT_FOUND: return
        item_to_edit = self.audiodescriptions[index]
        # NOTE: This is a simplified edit dialog. A more complex one could be built.
        new_desc = wx.GetTextFromUser("Editar descripción:", "Editar", item_to_edit.descripcion)
        if new_desc:
            item_to_edit.descripcion = new_desc
            # If audio was generated, it's now outdated. Clear it to allow regeneration.
            if self.temp_tts_dir and self.temp_tts_dir in Path(item_to_edit.archivo_audio).parents:
                 item_to_edit.archivo_audio = ""
            self.update_ad_list_ctrl()

    def on_ad_list_selection_change(self, event):
        selected_count = self.ad_list_ctrl.GetSelectedItemCount()
        self.edit_ad_btn.Enable(selected_count > 0)
        self.delete_ad_btn.Enable(selected_count > 0)
        event.Skip()

    def on_remove_audiodescription_from_list(self, event):
        index = self.ad_list_ctrl.GetFirstSelected()
        if index != wx.NOT_FOUND:
            if wx.MessageBox("¿Estás seguro de que quieres eliminar esta audiodescripción?", "Confirmar Eliminación", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
                del self.audiodescriptions[index]
                self.update_ad_list_ctrl()

    def get_project_state_path(self):
        app_data_dir = wx.StandardPaths.Get().GetUserDataDir()
        if not os.path.exists(app_data_dir): os.makedirs(app_data_dir)
        return os.path.join(app_data_dir, "audiodescription_project_autosave.json")

    def save_project_state(self, file_path=None):
        is_autosave = file_path is None
        if is_autosave:
            file_path = self.get_project_state_path()

        data = {
            'video_file': self.video_file,
            'audiodescriptions': [{'tiempo': item.tiempo, 'archivo_audio': item.archivo_audio, 'descripcion': item.descripcion} for item in self.audiodescriptions],
            'output_file': self.output_ctrl.GetValue(),
            'volume_original': self.vol_orig_ctrl.GetValue(),
            'volume_description': self.vol_desc_ctrl.GetValue(),
            'tts_settings': {
                'voice_index': self.selected_voice_index,
                'rate': self.rate_slider.GetValue()
            }
        }
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if not is_autosave:
                self.status_text.SetLabel(f"Proyecto guardado como: {os.path.basename(file_path)}")
                self.current_project_name = Path(file_path).stem
                self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")
        except Exception as e:
            wx.MessageBox(f"Error al guardar el proyecto: {e}", "Error de Guardado", wx.OK | wx.ICON_ERROR)

    def load_project_state(self, project_path=None):
        is_autosave = project_path is None
        if is_autosave:
            project_path = self.get_project_state_path()

        if not os.path.exists(project_path):
            return

        try:
            with open(project_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.audiodescriptions.clear()
            self.clean_temp_files()

            self.video_file = data.get('video_file', '')
            self.video_ctrl.SetValue(self.video_file)
            self.output_ctrl.SetValue(data.get('output_file', 'video_con_audiodescripcion.mp4'))
            self.vol_orig_ctrl.SetValue(data.get('volume_original', 0.6))
            self.vol_desc_ctrl.SetValue(data.get('volume_description', 1.5))

            tts_settings = data.get('tts_settings', {})
            self.selected_voice_index = tts_settings.get('voice_index', 0)
            self.rate_slider.SetValue(tts_settings.get('rate', 0))

            if self.sapi_voices and 0 <= self.selected_voice_index < len(self.sapi_voices):
                self.voice_choice.SetSelection(self.selected_voice_index)

            for desc_data in data.get('audiodescriptions', []):
                self.audiodescriptions.append(AudioDescriptionItem(**desc_data))

            self.update_ad_list_ctrl()
            self.update_video_duration()
            
            if is_autosave:
                self.status_text.SetLabel("Proyecto anterior cargado automáticamente.")
                self.current_project_name = "Proyecto anterior"
            else:
                self.status_text.SetLabel(f"Proyecto '{os.path.basename(project_path)}' cargado.")
                self.current_project_name = Path(project_path).stem
            
            self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")

        except Exception as e:
            wx.MessageBox(f"Error al cargar el proyecto: {e}", "Error de Carga", wx.OK | wx.ICON_ERROR)
            self.current_project_name = None
            self.SetTitle(self.app_title_base)

    def on_import_project(self, event):
        with wx.FileDialog(self, "Importar proyecto", wildcard="Archivos JSON (*.json)|*.json", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.load_project_state(dialog.GetPath())

    def on_export_project(self, event):
        default_file = f"{self.current_project_name}.json" if self.current_project_name else "proyecto.json"
        with wx.FileDialog(self, "Exportar proyecto", defaultFile=default_file, wildcard="Archivos JSON (*.json)|*.json", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                project_path = dialog.GetPath()
                if not project_path.lower().endswith('.json'):
                    project_path += '.json'
                self.save_project_state(project_path)

    def on_save_as_project(self, event):
        self.on_export_project(event)

    def on_clear_project(self, event):
        if wx.MessageBox("¿Estás seguro de que quieres limpiar todo el proyecto?", "Confirmar Limpieza", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            self.clean_temp_files()
            self.video_file = ""
            self.video_duration = 0.0
            self.audiodescriptions.clear()
            self.video_ctrl.SetValue("")
            self.video_duration_label.SetLabel("Duración: 00:00:00")
            self.update_ad_list_ctrl()
            self.status_text.SetLabel("Proyecto limpiado.")
            self.current_project_name = None
            self.SetTitle(self.app_title_base)

    def on_generate(self, event):
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Selecciona un archivo de video válido.", "Error", wx.OK | wx.ICON_ERROR)
            return
        if not self.audiodescriptions:
            wx.MessageBox("Agrega al menos una audiodescripción.", "Error", wx.OK | wx.ICON_ERROR)
            return
        if not all(item.archivo_audio and os.path.exists(item.archivo_audio) for item in self.audiodescriptions):
            wx.MessageBox("Faltan archivos de audio. Genéralos con TTS o agrégalos manualmente.", "Archivos Faltantes", wx.OK | wx.ICON_ERROR)
            return

        output_path = self.output_ctrl.GetValue()
        if os.path.exists(output_path):
            if wx.MessageBox(f"El archivo '{output_path}' ya existe. ¿Sobrescribir?", "Confirmar", wx.YES_NO | wx.ICON_WARNING) == wx.NO:
                return

        self.generate_btn.Enable(False)
        self.generate_tts_btn.Enable(False)
        thread = threading.Thread(target=self.generate_video_thread)
        thread.daemon = True
        thread.start()

    def generate_video_thread(self):
        wx.CallAfter(self.status_text.SetLabel, "Paso 1/5: Iniciando generación...")
        wx.CallAfter(self.progress.SetValue, 0)
        try:
            output_path = self.output_ctrl.GetValue()
            
            wx.CallAfter(self.status_text.SetLabel, "Paso 2/5: Cargando video principal...")
            wx.CallAfter(self.progress.SetValue, 10)
            video = VideoFileClip(self.video_file)
            
            wx.CallAfter(self.status_text.SetLabel, f"Paso 3/5: Procesando audios de descripción...")
            audio_clips = []
            total_ads = len(self.audiodescriptions)
            for i, item in enumerate(self.audiodescriptions):
                try:
                    ad_clip = AudioFileClip(item.archivo_audio).set_start(item.tiempo)
                    audio_clips.append(ad_clip)
                except Exception as e:
                    print(f"Error cargando {item.archivo_audio}: {e}")
            
            wx.CallAfter(self.progress.SetValue, 30)
            
            if audio_clips:
                descriptions_audio = CompositeAudioClip(audio_clips).volumex(self.vol_desc_ctrl.GetValue())
            else:
                descriptions_audio = None

            original_audio = video.audio.volumex(self.vol_orig_ctrl.GetValue()) if video.audio else None
            
            wx.CallAfter(self.status_text.SetLabel, "Paso 4/5: Combinando audios...")
            wx.CallAfter(self.progress.SetValue, 60)

            final_audio_clips = []
            if original_audio: final_audio_clips.append(original_audio)
            if descriptions_audio: final_audio_clips.append(descriptions_audio)

            if final_audio_clips:
                final_audio = CompositeAudioClip(final_audio_clips)
                video_final = video.set_audio(final_audio)
            else:
                video_final = video.set_audio(None)

            wx.CallAfter(self.status_text.SetLabel, "Paso 5/5: Exportando video final (esto puede tardar)...")
            wx.CallAfter(self.progress.SetValue, 80)

            # Dejar que moviepy maneje el archivo de audio temporal y usar el logger de barra
            video_final.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                remove_temp=True,
                verbose=False,
                logger='bar'
            )

            wx.CallAfter(self.progress.SetValue, 100)
            wx.CallAfter(self.status_text.SetLabel, f"¡Completado! Video guardado en: {output_path}")
            wx.CallAfter(wx.MessageBox, f"Video generado exitosamente:\n{output_path}", "Éxito", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.CallAfter(wx.MessageBox, f"Error durante la generación del video: {e}", "Error", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, "Error en la generación.")
        finally:
            # Liberar recursos
            if 'video' in locals(): video.close()
            if 'original_audio' in locals() and original_audio: original_audio.close()
            if 'descriptions_audio' in locals() and descriptions_audio: descriptions_audio.close()
            if 'final_audio' in locals() and final_audio: final_audio.close()
            if 'video_final' in locals(): video_final.close()
            for clip in audio_clips: clip.close()
            
            wx.CallAfter(self.update_action_buttons_state)


class MyApp(wx.App):
    def OnInit(self):
        self.frame = MainFrame()
        self.frame.Show()
        return True

if __name__ == '__main__':
    app = MyApp()
    app.MainLoop()