"""
Audio format conversion utilities for ComfyUI ↔ Pedalboard
"""

import torch
import numpy as np
from typing import Tuple, Dict, Any
import os
import platform


def comfy_audio_to_numpy(audio: Dict[str, Any]) -> Tuple[np.ndarray, int]:
    """
    Convert ComfyUI AUDIO format to Pedalboard numpy format.

    ComfyUI AUDIO: {"waveform": Tensor[B, C, T], "sample_rate": int}
    Pedalboard: numpy array [channels, samples]

    Args:
        audio: ComfyUI audio dictionary

    Returns:
        Tuple of (numpy_array [C, T], sample_rate)
    """
    waveform = audio["waveform"]  # [B, C, T]
    sample_rate = audio["sample_rate"]

    # Handle batch dimension - process first item
    # If batch size > 1, we only process the first one for now
    if waveform.dim() == 3:
        waveform = waveform[0]  # [C, T]

    # Convert to numpy and ensure float32
    np_audio = waveform.cpu().numpy().astype(np.float32)

    return np_audio, sample_rate


def numpy_to_comfy_audio(
    np_audio: np.ndarray, sample_rate: int, batch_size: int = 1
) -> Dict[str, Any]:
    """
    Convert Pedalboard numpy format to ComfyUI AUDIO format.

    Args:
        np_audio: numpy array [channels, samples]
        sample_rate: audio sample rate
        batch_size: batch size for output

    Returns:
        ComfyUI audio dictionary
    """
    # Convert to torch tensor
    waveform = torch.from_numpy(np_audio.astype(np.float32))

    # Add batch dimension if not present
    if waveform.dim() == 2:
        waveform = waveform.unsqueeze(0)  # [1, C, T]

    # Expand to requested batch size if needed
    if batch_size > 1 and waveform.shape[0] == 1:
        waveform = waveform.repeat(batch_size, 1, 1)

    return {"waveform": waveform, "sample_rate": sample_rate}


def extract_parameter_info(plugin) -> dict:
    params_info = {}

    for name, param in plugin.parameters.items():
        param_type = getattr(param, "type", str)
        units = getattr(param, "label", "") or getattr(param, "units", "")
        current_value = getattr(param, "value", None)

        if param_type is bool:
            params_info[name] = {
                "name": name,
                "value": bool(current_value) if current_value is not None else False,
                "is_boolean": True,
                "units": str(units),
            }
            continue

        if param_type is float:
            min_val = getattr(param, "min_value", 0.0)
            max_val = getattr(param, "max_value", 1.0)
            step = getattr(param, "step_size", None) or getattr(
                param, "approximate_step_size", None
            )

            # Use actual value if available, otherwise raw_value mapped to range
            if current_value is not None:
                nice_val = float(current_value)
            else:
                raw_val = float(getattr(param, "raw_value", 0.0))
                nice_val = float(min_val) + (
                    raw_val * (float(max_val) - float(min_val))
                )

            params_info[name] = {
                "name": name,
                "value": nice_val,
                "is_choice": False,
                "is_boolean": False,
                "min": float(min_val) if min_val is not None else 0.0,
                "max": float(max_val) if max_val is not None else 1.0,
                "step": float(step) if step is not None else None,
                "units": str(units),
            }
            continue

        valid_values = getattr(param, "valid_values", None)
        if valid_values and len(valid_values) > 0:
            # Use current value or first valid value
            if current_value is not None:
                current_str = str(current_value)
            else:
                current_str = str(valid_values[0])

            params_info[name] = {
                "name": name,
                "value": current_str,
                "is_choice": True,
                "valid_values": [str(v) for v in valid_values],
                "units": str(units),
            }
            continue

        min_val = getattr(param, "min_value", 0.0) or 0.0
        max_val = getattr(param, "max_value", 1.0) or 1.0
        raw_val = float(getattr(param, "raw_value", 0.0))
        nice_val = float(min_val) + (raw_val * (float(max_val) - float(min_val)))

        params_info[name] = {
            "name": name,
            "value": nice_val,
            "is_choice": False,
            "is_boolean": False,
            "min": float(min_val),
            "max": float(max_val),
            "units": str(units)
        }

    return params_info

def resolve_vst_path(vst_path: str) -> str:
    """
    If the path is a VST3 bundle directory, attempt to find the 
    actual binary hidden inside the Contents folder.
    """
    if not os.path.isdir(vst_path):
        return vst_path

    # Standard VST3 directory structure:
    # BundleName.vst3/Contents/[Architecture]/PluginName.vst3 (or .dll)

    sys_platform = platform.system()
    
    if sys_platform == "Windows":
        # Look for the Windows 64-bit binary
        internal_path = os.path.join(vst_path, "Contents", "x86_64-win")
        if os.path.exists(internal_path):
            files = [f for f in os.listdir(internal_path) if f.endswith(".vst3") or f.endswith(".dll")]
            if files:
                return os.path.join(internal_path, files[0])
                
    elif sys_platform == "Darwin": # macOS
        # Look for the macOS binary
        internal_path = os.path.join(vst_path, "Contents", "MacOS")
        if os.path.exists(internal_path):
            files = os.listdir(internal_path)
            # Find the first file that doesn't start with a dot
            binary = next((f for f in files if not f.startswith(".")), None)
            if binary:
                return os.path.join(internal_path, binary)

    return vst_path

def get_vst_list():
    """
    Scans system paths recursively for VST3 and VST2 plugins.
    Handles both folder bundles (.vst3) and single files (.dll/.vst3).
    """
    vst_map = {"[None]": ""} 
    
    paths_to_scan = []
    sys_platform = platform.system()

    if sys_platform == "Windows":
        paths_to_scan = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Common Files\\VST3"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "VSTPlugins"),
            "C:\\Program Files\\Steinberg\\VSTPlugins",
        ]
    elif sys_platform == "Darwin": # macOS
        paths_to_scan = ["/Library/Audio/Plug-Ins/VST3", "~/Library/Audio/Plug-Ins/VST3", "/Library/Audio/Plug-Ins/VST"]
    elif sys_platform == "Linux":
        paths_to_scan = [os.path.expanduser("~/.vst3"), "/usr/lib/vst3", "/usr/local/lib/vst3"]

    for base_path in paths_to_scan:
        base_path = os.path.expanduser(base_path)
        if not os.path.exists(base_path):
            continue

        for root, dirs, files in os.walk(base_path):
            # Look for VST3 Bundles (Directories ending in .vst3)
            # We iterate a copy so we can prune 'dirs' to prevent walking into the bundle
            for d in list(dirs):
                if d.lower().endswith(".vst3"):
                    full_path = os.path.normpath(os.path.join(root, d))
                    display_name = os.path.relpath(full_path, base_path).replace("\\", "/")
                    vst_map[display_name] = full_path
                    
                    # Stop scanning inside this plugin bundle
                    dirs.remove(d)

            # Look for single-file plugins (.dll or standalone .vst3 files)
            for f in files:
                if f.lower().endswith(".dll") or f.lower().endswith(".vst3"):
                    full_path = os.path.normpath(os.path.join(root, f))
                    display_name = os.path.relpath(full_path, base_path).replace("\\", "/")
                    
                    # Only add if it wasn't already added as a directory bundle
                    if display_name not in vst_map:
                        vst_map[display_name] = full_path

    return vst_map