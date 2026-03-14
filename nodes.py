"""
ComfyUI VST Nodes using Pedalboard
Provides nodes for loading and applying VST3/AU plugins to audio
"""

from comfy_api.latest import io
import torch
import hashlib
import json
from .vst_utils import (
    comfy_audio_to_numpy,
    numpy_to_comfy_audio,
    extract_parameter_info,
    get_vst_list,
    resolve_vst_path,
)

try:
    from pedalboard import load_plugin, Pedalboard

    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False


VST_MAP = get_vst_list()


class VSTLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        vst_names = sorted(list(VST_MAP.keys()))

        return io.Schema(
            node_id="VSTLoader",
            display_name="Load VST Plugin",
            category="audio/vst",
            inputs=[
                io.Combo.Input("vst_selection", options=vst_names, default="[None]"),
                io.String.Input(
                    "manual_vst_path",
                    default="",
                    placeholder="Optional: Paste a path here to override selection",
                ),
                io.String.Input("plugin_name", default=""),
                io.Float.Input("timeout", default=10.0, min=1.0, max=60.0, step=1.0),
            ],
            outputs=[
                io.Custom("VST_PLUGIN").Output("plugin"),
                io.Custom("VST_PARAMETER_SCHEMA").Output("parameter_schema"),
                io.Boolean.Output("is_effect"),
                io.Boolean.Output("is_instrument"),
            ],
        )

    @classmethod
    def execute(cls, vst_selection, manual_vst_path, plugin_name, timeout):
        # Determine which path to use
        # If manual_vst_path is provided, use it. Otherwise, look up the selection.
        vst_path = manual_vst_path.strip()
        if not vst_path:
            vst_path = VST_MAP.get(vst_selection, "")

        if not vst_path:
            raise ValueError("No VST plugin selected or manual path provided.")

        # Resolve internal binary path (for Windows VST3 bundles)
        actual_path = resolve_vst_path(vst_path)

        # Load the plugin
        try:
            plugin = load_plugin(
                actual_path,
                plugin_name=plugin_name if plugin_name else None,
                initialization_timeout=timeout,
            )

            params_info = extract_parameter_info(plugin)
            params_json = json.dumps(params_info, indent=2)

            is_effect = getattr(plugin, "is_effect", True)
            is_instrument = getattr(plugin, "is_instrument", False)

            return io.NodeOutput(
                plugin,
                params_json,
                is_effect,
                is_instrument,
                ui={"vst_params": [params_json]},
            )

        except Exception as e:
            raise RuntimeError(f"Failed to load VST plugin '{vst_path}': {str(e)}")


class VSTInspector(io.ComfyNode):
    """
    Inspect a loaded VST plugin to see its parameters and metadata.
    Provides a human-readable summary of the plugin's capabilities.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VSTInspector",
            display_name="Inspect VST Plugin",
            category="audio/vst",
            description="Inspect a loaded VST plugin to see its parameters",
            inputs=[
                io.Custom("VST_PLUGIN").Input("plugin"),
            ],
            outputs=[
                io.String.Output("summary"),
                io.Custom("VST_PARAMETER_SCHEMA").Output("parameter_schema"),
                io.Custom("DICT").Output("parameter_schema_dict"),
                io.Custom("JSON").Output("parameter_schema_json"),
                io.String.Output("parameter_names"),
            ],
        )

    @classmethod
    def execute(cls, plugin):
        if not PEDALBOARD_AVAILABLE:
            raise RuntimeError("Pedalboard library not installed")

        if plugin is None:
            raise ValueError("No plugin provided")

        # Extract parameter information
        params_info = extract_parameter_info(plugin)

        # Create human-readable summary
        summary_lines = ["VST Plugin Parameters:", "=" * 40]
        for name, info in params_info.items():
            line = f"  {name}"
            if info.get("units"):
                line += f" ({info['units']})"

            # Handle different parameter types
            if info.get("is_boolean"):
                # Boolean parameter
                line += f" [boolean] default: {info.get('value', False)}"
            elif info.get("is_choice"):
                # Choice/Categorical parameter
                valid_values = info.get("valid_values", [])
                current_val = info.get("value", "")
                line += f" [choice: {len(valid_values)} options] default: {current_val}"
            else:
                # Numeric/Slider parameter
                min_val = info.get("min", 0.0)
                max_val = info.get("max", 1.0)
                default_val = info.get("value", 0.5)
                line += f" [{min_val:.3f} - {max_val:.3f}] default: {default_val:.3f}"

            summary_lines.append(line)

        # Get plugin type info
        is_effect = getattr(plugin, "is_effect", True)
        is_instrument = getattr(plugin, "is_instrument", False)
        summary_lines.insert(1, f"Type: {'Effect' if is_effect else 'Instrument'}")

        summary = "\n".join(summary_lines)
        params_json = json.dumps(params_info, indent=2)
        param_names = ", ".join(params_info.keys())

        return io.NodeOutput(summary, params_json, params_info, params_json, param_names)


class VSTManualParameters(io.ComfyNode):
    """
    Define parameters for a VST plugin using autogrowing name-value pairs.
    This allows you to set multiple plugin parameters with real input connections.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VSTManualParameters",
            display_name="VST Manual Parameters",
            category="audio/vst",
            description="Set VST plugin parameters with controllable inputs",
            inputs=[
                # Autogrowing list of parameter names
                io.Autogrow.Input(
                    "param_names",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.String.Input("name"),
                        prefix="name_",
                        min=1,
                        max=64,
                    ),
                ),
                # Autogrowing list of parameter values (accepts any type per slot)
                io.Autogrow.Input(
                    "param_values",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.AnyType.Input("value"),
                        prefix="value_",
                        min=1,
                        max=64,
                    ),
                ),
            ],
            outputs=[
                io.Custom("VST_SETTINGS").Output("vst_settings"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, param_names, param_values):
        m = hashlib.sha256()
        # Sort keys for consistent hashing
        for key in sorted(param_names.keys()):
            m.update(f"{key}:{param_names[key]}".encode())
        for key in sorted(param_values.keys()):
            m.update(f"{key}:{param_values[key]}".encode())
        return m.digest().hex()

    @classmethod
    def execute(cls, param_names, param_values):
        """
        Convert autogrow name-value pairs to a parameter dictionary.

        Args:
            param_names: Dictionary from autogrow: {"name_0": "mix", "name_1": "room_size", ...}
            param_values: Dictionary from autogrow: {"value_0": 0.5, "value_1": 0.3", ...}

        Returns:
            Dictionary mapping parameter names to values
        """
        result = {}

        # Get sorted keys to ensure names and values align
        name_keys = sorted([k for k in param_names.keys() if k.startswith("name_")])
        value_keys = sorted([k for k in param_values.keys() if k.startswith("value_")])

        # Pair up names with values
        for i, name_key in enumerate(name_keys):
            param_name = param_names.get(name_key, "").strip()
            if not param_name:  # Skip empty names
                continue

            # Get corresponding value (if exists)
            value_key = f"value_{i}" if i < len(value_keys) else None
            if value_key and value_key in param_values:
                value = param_values[value_key]
            else:
                value = 0.5  # Default value

            result[param_name] = value

        return io.NodeOutput(result)


class VSTParameters(io.ComfyNode):
    """
    Dynamically generates widgets for VST parameters.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VSTParameters",
            display_name="VST Parameters",
            category="audio/vst",
            inputs=[
                io.Custom("VST_PARAMETER_SCHEMA").Input("parameter_schema"),
                io.String.Input("dynamic_values_json", default="{}", socketless=True),
            ],
            outputs=[
                io.Custom("VST_SETTINGS").Output("vst_settings"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, parameter_schema, dynamic_values_json="{}", **kwargs):
        return dynamic_values_json

    @classmethod
    def execute(cls, parameter_schema, dynamic_values_json="{}", **kwargs):
        # We unpack the JSON string sent from the Javascript sliders
        clean_params = {}
        try:
            clean_params = json.loads(dynamic_values_json)
        except Exception as e:
            print(f"Warning: Failed to parse dynamic parameters: {e}")

        return io.NodeOutput(clean_params)


class VSTApplyEffect(io.ComfyNode):
    """
    Apply a VST effect plugin to audio.
    Takes audio input, a loaded plugin, and optional parameters.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VSTApplyEffect",
            display_name="Apply VST Effect",
            category="audio/vst",
            description="Apply a VST plugin effect to audio",
            inputs=[
                io.Audio.Input("audio"),
                io.Custom("VST_PLUGIN").Input("plugin"),
                io.Custom("VST_SETTINGS").Input("vst_settings", optional=True),
                io.Int.Input("buffer_size", default=8192, min=512, max=65536, step=512),
                io.Boolean.Input("reset", default=True),
            ],
            outputs=[
                io.Audio.Output("AUDIO"),
            ],
        )

    @classmethod
    def execute(
        cls, audio, plugin, vst_settings=None, buffer_size=8192, reset=True, **kwargs
    ):
        if not PEDALBOARD_AVAILABLE:
            raise RuntimeError("Pedalboard library not installed")

        if plugin is None:
            raise ValueError("No plugin provided")

        if audio is None:
            raise ValueError("No audio input provided")

        # Helper to safely apply the value, letting Pedalboard handle the VST mapping natively
        def apply_param(plugin, param_name, value):
            if param_name in plugin.parameters:
                try:
                    param_obj = plugin.parameters[param_name]

                    # Handle Booleans (Toggles)
                    if isinstance(value, bool) or param_name.lower() == "bypass":
                        # If it's a string "true"/"false" from a saved graph, convert it
                        if isinstance(value, str):
                            setattr(plugin, param_name, value.lower() == "true")
                        else:
                            setattr(plugin, param_name, bool(value))

                    # Handle Strings (Dropdowns)
                    elif isinstance(value, str):
                        setattr(plugin, param_name, value)

                    # Handle Numbers (Sliders)
                    else:
                        setattr(plugin, param_name, float(value))

                except Exception as e:
                    print(f"Warning: Could not set parameter '{param_name}': {e}")

        # Apply parameters from explicitly linked dictionary (VSTParameters node)
        if vst_settings:
            for param_name, value in vst_settings.items():
                apply_param(plugin, param_name, value)

        # Apply parameters from the dynamically generated JS widgets (if placed directly on this node)
        for param_name, value in kwargs.items():
            if param_name not in ["prompt", "extra_pnginfo", "dynprompt"]:
                apply_param(plugin, param_name, value)

        # Convert ComfyUI audio to numpy
        try:
            np_audio, sample_rate = comfy_audio_to_numpy(audio)
        except Exception as e:
            raise RuntimeError(f"Failed to convert audio format: {e}")

        # Process audio through the plugin
        try:
            processed = plugin(
                np_audio, sample_rate, buffer_size=buffer_size, reset=reset
            )
        except Exception as e:
            raise RuntimeError(f"Failed to process audio through VST: {e}")

        # Convert back to ComfyUI format
        batch_size = audio["waveform"].shape[0]
        result = numpy_to_comfy_audio(processed, sample_rate, batch_size)

        return io.NodeOutput(result)

    @classmethod
    def fingerprint_inputs(
        cls, audio, plugin, vst_settings=None, buffer_size=8192, reset=True
    ):
        m = hashlib.sha256()
        # Hash audio waveform data
        if isinstance(audio, dict) and "waveform" in audio:
            waveform = audio["waveform"]
            if isinstance(waveform, torch.Tensor):
                m.update(waveform.numpy().tobytes())
            else:
                m.update(waveform.tobytes())
            # Also hash sample rate
            sample_rate = audio.get("sample_rate", 0)
            m.update(str(sample_rate).encode())
        # Hash plugin identifier
        plugin_name = getattr(plugin, "name", str(plugin))
        m.update(plugin_name.encode())
        # Hash parameters
        if vst_settings:
            for key in sorted(vst_settings.keys()):
                m.update(f"{key}:{vst_settings[key]}".encode())
        # Hash buffer settings
        m.update(f"buffer_size:{buffer_size}:reset:{reset}".encode())
        return m.digest().hex()
