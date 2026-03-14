# ComfyUI-VST

ComfyUI custom nodes for audio processing using VST3 and Audio Unit plugins via [Spotify's Pedalboard](https://github.com/spotify/pedalboard) library.

## Features

- Load VST3 plugins with auto-detection from system paths
- Auto-detect plugin parameters (booleans, choices, numeric sliders)
- Apply effects to audio with adjustable parameters
- Manual or dynamic parameter configuration
- Compatible with ComfyUI V3 API

**Note:** Currently only **Effect VST plugins** are supported. Instrument/Synthesizer plugins are not yet supported.

## Installation

1. Clone this repository into your ComfyUI custom nodes folder:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/yourusername/ComfyUI-VST.git
```

2. Install dependencies:

```bash
cd ComfyUI-VST
pip install -r requirements.txt
```

## Requirements

- Python 3.10+
- ComfyUI with V3 API support
- `pedalboard>=0.9.0`

## Nodes

### 1. Load VST Plugin (VSTLoader)

Loads a VST3 plugin from disk. Auto-scans system VST directories and provides a dropdown of detected plugins.

**Inputs:**

- `vst_selection` (COMBO): Dropdown of detected VST plugins (scans standard directories)
- `manual_vst_path` (STRING, optional): Manual path override for plugins not in scanned directories
- `plugin_name` (STRING, optional): For multi-plugin bundles
- `timeout` (FLOAT): Initialization timeout in seconds [1.0-60.0], default 10.0

**Outputs:**

- `PLUGIN` (VST_PLUGIN): The loaded plugin object
- `PARAMETERS` (STRING): JSON string with parameter information
- `IS_EFFECT` (BOOLEAN): True if plugin is an audio effect
- `IS_INSTRUMENT` (BOOLEAN): True if plugin is a synthesizer/instrument

**Scanned directories:**

- **Windows**: `Program Files\Common Files\VST3`, `Program Files\VSTPlugins`, `Steinberg\VSTPlugins`
- **macOS**: `/Library/Audio/Plug-Ins/VST3`, `~/Library/Audio/Plug-Ins/VST3`, `/Library/Audio/Plug-Ins/VST`
- **Linux**: `~/.vst3`, `/usr/lib/vst3`, `/usr/local/lib/vst3`

### 2. Inspect VST Plugin (VSTInspector)

Inspects a loaded plugin to display its parameters and metadata.

**Inputs:**

- `plugin` (VST_PLUGIN): Loaded plugin from VSTLoader

**Outputs:**

- `SUMMARY` (STRING): Human-readable parameter list
- `PARAMETERS_JSON` (STRING): Full parameter metadata as JSON
- `PARAMETER_NAMES` (STRING): Comma-separated list of parameter names

### 3. VST Manual Parameters (VSTManualParameters)

Creates a parameter dictionary using autogrowing name-value pairs.

**Inputs:**

- `param_names` (AUTOGROW): List of parameter names
  - Each slot: `name_0`, `name_1`, etc. (STRING)
- `param_values` (AUTOGROW): List of parameter values
  - Each slot: `value_0`, `value_1`, etc. (accepts any type)

**Outputs:**

- `PARAMS` (VST_PARAMS): Parameter dictionary for Apply VST Effect

**Usage:**

1. Add parameter name slots and set names (e.g., "mix", "room_size")
2. Connect Float nodes, Int nodes, or other widgets to value slots
3. Names and values are paired by position (name_0 with value_0, etc.)

**Note:** Any parameters not explicitly defined in this node will use the plugin's default values when processed by `Apply VST Effect`.

### 4. VST Parameters (VSTParameters) ⚠️ EXPERIMENTAL

Dynamic parameter configuration with auto-generated widgets.

**Warning:** This node is **experimental** and currently **does not work inside Subgraphs**. Use `VST Manual Parameters` instead if you need to encapsulate your workflow in a Subgraph.

**How it works:**
This node generates parameter widgets dynamically based on the connected plugin. The workflow must be run twice to fully configure parameters:

1. **First run:** Connect your plugin and execute the workflow. The audio is processed using the plugin's default parameter values. Meanwhile, the node detects the available parameters and generates the corresponding widgets.
2. **Second run:** The parameter widgets are now visible and adjustable. Modify the values and run the workflow again to process the audio with your custom settings.

_Note: This is required because the node needs to "see" the plugin output once to know what parameters to create._

**Inputs:**

- `parameters` (STRING): Parameter configuration string
- `dynamic_values_json` (STRING, multiline): JSON string of parameter values from frontend widgets

**Outputs:**

- `VST_PARAMS` (VST_PARAMS): Parameter dictionary

**Note:** This node requires the frontend JavaScript extension to generate parameter widgets dynamically based on the connected plugin.

### 5. Apply VST Effect (VSTApplyEffect)

Applies a VST plugin effect to audio.

**Note:** This node only works with **Effect plugins**. Instrument/Synthesizer plugins (VSTi) are not supported - they require MIDI input which is not yet implemented.

**Inputs:**

- `audio` (AUDIO): Input audio from ComfyUI
- `plugin` (VST_PLUGIN): Loaded plugin
- `parameters` (VST_PARAMS, optional): Parameter settings from VST Manual Parameters or VST Parameters
- `buffer_size` (INT): Processing buffer size [512-65536], default 8192
- `reset` (BOOLEAN): Reset plugin state before processing, default True

**Outputs:**

- `AUDIO`: Processed audio

## Usage Example

### Basic VST Effect Chain

![Basic example workflow](https://github.com/user-attachments/assets/0377c68e-a122-4ea9-9487-2b2a878b4dff)

### Workflow Steps

1. **Load a plugin:**
   - Use `Load VST Plugin` and select from the dropdown
   - Or enter a manual path for plugins not auto-detected

2. **Inspect parameters:**
   - Connect to `Inspect VST Plugin` to see available parameters
   - Check `SUMMARY` output for parameter names, types, and ranges

3. **Configure parameters:**
   - Option A: Use `VST Manual Parameters` with autogrowing name-value pairs (recommended for Subgraphs)
   - Option B: Use `VST Parameters` with dynamic widgets (requires JS extension, not for Subgraphs)

4. **Apply effect:**
   - Connect audio to `Apply VST Effect`
   - Connect plugin from `Load VST Plugin`
   - Connect parameters from parameter node

## Parameter Types

The nodes automatically detect three types of VST parameters:

### 1. Boolean (Toggle)

Parameters with two valid values: `true`/`false`

### 2. Choice (Dropdown)

Parameters with a list of valid text values (up to 16 options or text-based values)

### 3. Numeric (Slider)

Continuous parameters with min/max ranges. Values are automatically normalized.

## Platform Support

- **Linux**: VST3 (.vst3 files and bundles)
- **macOS**: VST3 (.vst3) and Audio Units (.component)
- **Windows**: VST3 (.vst3 files and bundles), VST2 (.dll)

## Troubleshooting

### Plugin not in dropdown

- Check that the plugin is in a scanned directory
- Use `manual_vst_path` to load plugins from custom locations
- Ensure the plugin file exists and is readable

### Plugin fails to load

- Ensure the plugin format matches your OS (VST3 for Linux/Windows, VST3/AU for macOS)
- Increase the `timeout` value if the plugin takes long to initialize
- Check that the plugin binary exists inside bundle directories (`.vst3` folders)

### Audio processing fails

- Verify that the plugin is an effect plugin (check `IS_EFFECT` output)
- Try increasing `buffer_size` if you encounter glitches
- Set `reset=True` if audio sounds wrong (clears plugin internal state)

### Parameters not working

- Use `Inspect VST Plugin` to verify parameter names are correct
- Check that parameter names match exactly (case-sensitive)
- Some plugins may reject invalid parameter values

### VST Parameters node not working in Subgraphs

- This is a known limitation
- Use `VST Manual Parameters` instead for Subgraph workflows

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html) (GPL v3.0).

## Credits

Built using [Spotify's Pedalboard](https://github.com/spotify/pedalboard) library.

---

_VST is a registered trademark of Steinberg Media Technologies GmbH._
