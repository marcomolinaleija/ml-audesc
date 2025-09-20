# -*- coding: utf-8 -*-
import wx
import wx.adv
import os
import sys
import threading
import time
from pathlib import Path
import srt
import shutil

# Intentar importar dependencias clave
try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

try:
    import comtypes.client
    from comtypes.gen import SpeechLib
    COMTYPES_AVAILABLE = True
except (ImportError, OSError):
    try:
        comtypes.client.GetModule("sapi.dll")
        from comtypes.gen import SpeechLib
        COMTYPES_AVAILABLE = True
    except (ImportError, OSError):
        COMTYPES_AVAILABLE = False

from .models import AudioDescriptionItem
from .processing import generate_tts_audio_files, generate_video_with_ads
from .project_handler import save_project, load_project, load_srt_file

def format_time(seconds):
    """Formatea segundos a una cadena HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

class TimeInputDialog(wx.Dialog):
    """Diálogo para que el usuario ingrese el tiempo."""
    def __init__(self, parent, video_duration_seconds=0.0):
        super().__init__(parent, title="Ingresar Tiempo", size=(350, 200))
        self.video_duration_seconds = video_duration_seconds
        self.time_in_seconds = 0.0
        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        time_format_label = wx.StaticText(panel, label="Tiempo (HH:MM:SS):")
        self.time_text_ctrl = wx.TextCtrl(panel, value="00:00:00")
        self.time_text_ctrl.Bind(wx.EVT_TEXT, self.on_time_text_change)
        seconds_label = wx.StaticText(panel, label="Tiempo (segundos):")
        self.seconds_spin_ctrl = wx.SpinCtrlDouble(panel, value="0.0", min=0, max=self.video_duration_seconds, inc=0.1)
        self.seconds_spin_ctrl.SetDigits(1)
        self.seconds_spin_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_seconds_spin_change)
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "&Aceptar")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "&Cancelar")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        main_sizer.Add(time_format_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.time_text_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(seconds_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.seconds_spin_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)
        panel.SetSizer(main_sizer)
        self.CenterOnParent()
        self.seconds_spin_ctrl.SetRange(0, self.video_duration_seconds)

    def on_time_text_change(self, event):
        time_str = self.time_text_ctrl.GetValue()
        try:
            parts = list(map(int, time_str.split(':')))
            h, m, s = (0, 0, 0)
            if len(parts) == 3: h, m, s = parts
            elif len(parts) == 2: m, s = parts
            elif len(parts) == 1: s = parts[0]
            else: raise ValueError("Formato inválido")
            total_seconds = h * 3600 + m * 60 + s
            if 0 <= total_seconds <= self.video_duration_seconds:
                self.seconds_spin_ctrl.SetValue(total_seconds)
                self.time_in_seconds = total_seconds
            else:
                self.seconds_spin_ctrl.SetValue(self.video_duration_seconds)
                self.time_in_seconds = self.video_duration_seconds
        except ValueError: pass

    def on_seconds_spin_change(self, event):
        self.time_in_seconds = self.seconds_spin_ctrl.GetValue()
        self.time_text_ctrl.SetValue(format_time(self.time_in_seconds))

    def get_time_in_seconds(self):
        return self.time_in_seconds

class AudioSourceDialog(wx.Dialog):
    """Diálogo para seleccionar el origen de la audiodescripción.""" 
    def __init__(self, parent):
        super().__init__(parent, title="Seleccionar Origen del Audio", size=(350, 150))
        self.source = None  # 'file' or 'tts'
        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        instructions = wx.StaticText(panel, label="¿Cómo deseas agregar la audiodescripción?")
        main_sizer.Add(instructions, 0, wx.ALL | wx.CENTER, 15)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        file_btn = wx.Button(panel, label="Desde Archivo de Audio")
        file_btn.Bind(wx.EVT_BUTTON, self.on_select_file)
        
        tts_btn = wx.Button(panel, label="Sintetizar con Voz (TTS)")
        tts_btn.Bind(wx.EVT_BUTTON, self.on_select_tts)

        btn_sizer.Add(file_btn, 1, wx.ALL | wx.EXPAND, 5)
        btn_sizer.Add(tts_btn, 1, wx.ALL | wx.EXPAND, 5)

        main_sizer.Add(btn_sizer, 1, wx.ALL | wx.EXPAND, 5)
        
        panel.SetSizer(main_sizer)
        self.CenterOnParent()

    def on_select_file(self, event):
        self.source = 'file'
        self.EndModal(wx.ID_OK)

    def on_select_tts(self, event):
        self.source = 'tts'
        self.EndModal(wx.ID_OK)

    def get_source(self):
        return self.source

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
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            self.sapi_voices = list(speaker.GetVoices())
            if not self.sapi_voices:
                print("No se encontraron voces SAPI5.")
        except Exception as e:
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
                subs, error = load_srt_file(srt_path)

                if error:
                    wx.MessageBox(f"Error al importar el archivo SRT: {error}", "Error de Importación", wx.OK | wx.ICON_ERROR)
                    return

                if not subs:
                    wx.MessageBox("El archivo SRT está vacío o no tiene un formato válido.", "Error", wx.OK | wx.ICON_ERROR)
                    return

                confirm = wx.MessageBox(f"Se encontraron {len(subs)} descripciones. ¿Deseas importarlas? Esto limpiará la lista actual.", "Confirmar Importación de SRT", wx.YES_NO | wx.ICON_QUESTION)
                if confirm == wx.YES:
                    self.audiodescriptions.clear()
                    self.clean_temp_files()
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
        
        thread = threading.Thread(target=self.run_tts_generation_thread, args=(items_to_generate,))
        thread.daemon = True
        thread.start()

    def run_tts_generation_thread(self, items_to_generate):
        def progress_callback(percent, message):
            if percent is not None:
                wx.CallAfter(self.progress.SetValue, percent)
            if message is not None:
                wx.CallAfter(self.status_text.SetLabel, message)

        selected_voice_token = self.sapi_voices[self.selected_voice_index] if self.sapi_voices else None
        rate = self.rate_slider.GetValue()
        
        success, error = generate_tts_audio_files(
            items_to_generate, 
            selected_voice_token, 
            rate, 
            self.temp_tts_dir, 
            progress_callback
        )

        if not success:
            wx.CallAfter(wx.MessageBox, f"Ocurrió un error durante la generación de audios con SAPI5: {error}", "Error de TTS", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, "Error en la generación de audios.")
        else:
            wx.CallAfter(self.update_ad_list_ctrl)

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
            index = self.ad_list_ctrl.InsertItem(self.ad_list_ctrl.GetItemCount(), format_time(item.tiempo))
            audio_display = os.path.basename(item.archivo_audio) if item.archivo_audio else "--- PENDIENTE DE GENERAR ---"
            self.ad_list_ctrl.SetItem(index, 1, audio_display)
            self.ad_list_ctrl.SetItem(index, 2, item.descripcion)
        
        self.update_action_buttons_state()

    def update_action_buttons_state(self):
        can_generate_video = bool(MOVIEPY_AVAILABLE and self.video_file and os.path.exists(self.video_file) and self.audiodescriptions and all(item.archivo_audio and os.path.exists(item.archivo_audio) for item in self.audiodescriptions))
        self.generate_btn.Enable(can_generate_video)
        
        can_generate_tts = bool(COMTYPES_AVAILABLE and self.sapi_voices and self.audiodescriptions and any(not item.archivo_audio and item.descripcion for item in self.audiodescriptions))
        self.generate_tts_btn.Enable(can_generate_tts)

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
                self.video_duration_label.SetLabel(f"Duración: {format_time(self.video_duration)}")
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
                    if desc_text:
                        item = AudioDescriptionItem(tiempo=tiempo, archivo_audio="", descripcion=desc_text)
                        self.audiodescriptions.append(item)
                        self.update_ad_list_ctrl()

    def on_edit_audiodescription(self, event):
        index = self.ad_list_ctrl.GetFirstSelected()
        if index == wx.NOT_FOUND: return
        item_to_edit = self.audiodescriptions[index]
        new_desc = wx.GetTextFromUser("Editar descripción:", "Editar", item_to_edit.descripcion)
        if new_desc:
            item_to_edit.descripcion = new_desc
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
        
        success, error = save_project(file_path, data)

        if success:
            if not is_autosave:
                self.status_text.SetLabel(f"Proyecto guardado como: {os.path.basename(file_path)}")
                self.current_project_name = Path(file_path).stem
                self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")
        else:
            wx.MessageBox(f"Error al guardar el proyecto: {error}", "Error de Guardado", wx.OK | wx.ICON_ERROR)

    def load_project_state(self, project_path=None):
        is_autosave = project_path is None
        if is_autosave:
            project_path = self.get_project_state_path()

        if not os.path.exists(project_path):
            return

        data, error = load_project(project_path)

        if error:
            wx.MessageBox(f"Error al cargar el proyecto: {error}", "Error de Carga", wx.OK | wx.ICON_ERROR)
            self.current_project_name = None
            self.SetTitle(self.app_title_base)
            return

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
        
        thread = threading.Thread(target=self.run_video_generation_thread)
        thread.daemon = True
        thread.start()

    def run_video_generation_thread(self):
        def progress_callback(percent, message):
            if percent is not None:
                wx.CallAfter(self.progress.SetValue, percent)
            if message is not None:
                wx.CallAfter(self.status_text.SetLabel, message)
        
        output_path = self.output_ctrl.GetValue()
        vol_orig = self.vol_orig_ctrl.GetValue()
        vol_desc = self.vol_desc_ctrl.GetValue()

        success, error = generate_video_with_ads(
            self.video_file,
            self.audiodescriptions,
            output_path,
            vol_orig,
            vol_desc,
            progress_callback
        )

        if success:
            wx.CallAfter(wx.MessageBox, f"Video generado exitosamente:\n{output_path}", "Éxito", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.CallAfter(wx.MessageBox, f"Error durante la generación del video: {error}", "Error", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, "Error en la generación.")
        
        wx.CallAfter(self.update_action_buttons_state)

class MyApp(wx.App):
    def OnInit(self):
        self.frame = MainFrame()
        self.frame.Show()
        return True