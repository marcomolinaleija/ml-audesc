# -*- coding: utf-8 -*-
import json
import os

def save_project(file_path, data):
    """
    Saves the project data to a JSON file.
    Returns (True, None) on success, or (False, Exception) on failure.
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, e

def load_project(file_path):
    """
    Loads project data from a JSON file.
    Returns (data, None) on success, or (None, Exception) on failure.
    """
    if not os.path.exists(file_path):
        return None, FileNotFoundError(f"El archivo de proyecto no fue encontrado: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, None
    except Exception as e:
        return None, e
