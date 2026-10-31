"""The Model Loader's factory defaults, the saved defaults (Set New Defaults), the overrides applied to a Run and the model-file check. Moved out of mtv.py in v0.4.7."""

import json
import os
import folder_paths

from .consts import NONE_CHOICE, _replace_retry, _truthy
from .core_call import _vae_options
from .settings import (DEFAULT_SEED, FIXED_SETTINGS, LORA_SLOTS, MAX_SEED, MAX_STEPS, MIN_STEPS, MODEL_FILE_KEYS, MODEL_STEP_KEYS,
                       NONE_LORA, SEED_CONTROLS, VERSION)
from .state import DATA_DIR


DEFAULTS_FILE = os.path.join(DATA_DIR, "mtv_defaults.json")   # v0.0.9: the defaults saved by "Set New Defaults"

# ---------------------------------------------------------------------- #
# v2.3: Model Loader overrides + run-time model check
# ---------------------------------------------------------------------- #
def factory_defaults():
    """The MTV's built-in models, LoRAs, steps and seed, keyed by the NAMES of the Model Loader's widgets."""
    out = {key: FIXED_SETTINGS[key] for key in MODEL_FILE_KEYS}
    out["turbo_lora_strength"] = FIXED_SETTINGS["turbo_lora_strength"]      # v0.1.11
    for n in range(1, LORA_SLOTS + 1):
        out[f"LoRa_{n}_enabled"] = FIXED_SETTINGS[f"lora_{n}_enabled"]
        out[f"LoRa_{n}"] = FIXED_SETTINGS[f"lora_{n}_name"]
        out[f"LoRa_{n}_strength"] = FIXED_SETTINGS[f"lora_{n}_strength"]
    for key in MODEL_STEP_KEYS:
        out[key] = FIXED_SETTINGS[key]
    out["noise_seed"] = DEFAULT_SEED
    return out


def _defaults_key_map():
    """Model Loader widget name -> the MTV's internal key."""
    m = {key: key for key in MODEL_FILE_KEYS}
    m["turbo_lora_strength"] = "turbo_lora_strength"      # v0.1.11
    for n in range(1, LORA_SLOTS + 1):
        m[f"LoRa_{n}_enabled"] = f"lora_{n}_enabled"
        m[f"LoRa_{n}"] = f"lora_{n}_name"
        m[f"LoRa_{n}_strength"] = f"lora_{n}_strength"
    for key in MODEL_STEP_KEYS:
        m[key] = key
    m["noise_seed"] = "noise_seed"
    return m


def _normalize_default(name, value):
    """(clean value, None) or (None, error text) for one Model Loader widget value."""
    if name in MODEL_FILE_KEYS or (name.startswith("LoRa_") and not name.endswith(("_enabled", "_strength"))):
        if not isinstance(value, str) or not value.strip():
            return None, f"{name}: a file name is needed"
        if name in MODEL_FILE_KEYS and value == NONE_CHOICE:
            return None, f"{name}: no file selected"
        return value, None
    if name.endswith("_enabled"):
        return (value, None) if isinstance(value, bool) else (None, f"{name}: must be ON or OFF")
    try:
        if isinstance(value, bool):
            raise ValueError("bool")
        if name.endswith("_strength"):
            f = float(value)
            if not -100.0 <= f <= 100.0:
                return None, f"{name} must be between -100 and 100"
            return f, None
        n = int(value)
        if n != value:
            raise ValueError("not whole")
        if name == "noise_seed":
            return (n, None) if 0 <= n <= MAX_SEED else (None, "noise_seed is out of range")
        return (n, None) if MIN_STEPS <= n <= MAX_STEPS else (None, f"{name} must be between {MIN_STEPS} and {MAX_STEPS}")
    except (TypeError, ValueError):
        return None, f"{name}: not a valid number"


def _read_user_defaults():
    """The defaults saved by "Set New Defaults" ({widget name: value}); a damaged value is skipped, no file = {}."""
    try:
        with open(DEFAULTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    values = data.get("values") if isinstance(data, dict) else None
    if not isinstance(values, dict):
        return {}
    keys = _defaults_key_map()
    out = {}
    for name, value in values.items():
        if name in keys:
            clean, err = _normalize_default(name, value)
            if err is None:
                out[name] = clean
    return out


def _read_user_seed_control():
    """The seed's "control after generate" saved with the defaults (fixed / increment / decrement / randomize), None when there is none."""
    try:
        with open(DEFAULTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    value = data.get("seed_control") if isinstance(data, dict) else None
    return value if value in SEED_CONTROLS else None


def _defaults_stamp():
    """v0.0.9w: (mtime_ns, size) of mtv_defaults.json, None when there is none. Part of IS_CHANGED: saving a new set (or Factory)
    changes what the MTV runs with, even when no widget of the node changed."""
    try:
        st = os.stat(DEFAULTS_FILE)
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None


def loader_defaults():
    """The CURRENT defaults, by Model Loader widget name: the ones the user saved with "Set New Defaults", factory values for
    everything not saved. The MTV uses them with no Model Loader connected; a new Model Loader starts from them."""
    out = factory_defaults()
    out.update(_read_user_defaults())
    return out


def save_user_defaults(values, seed_control=None):
    """The Model Loader's "Set New Defaults": validates, writes mtv_defaults.json, returns (saved dict, error text or None).
    seed_control (v0.0.9, optional): the seed's "control after generate", saved with the values so a reload gives the same set."""
    if not isinstance(values, dict):
        return {}, "no values received"
    if seed_control is not None and seed_control not in SEED_CONTROLS:
        return {}, "seed control: must be " + " / ".join(SEED_CONTROLS)
    keys = _defaults_key_map()
    clean, errors = {}, []
    for name in keys:
        if name in values:
            value, err = _normalize_default(name, values[name])
            if err is None:
                clean[name] = value
            else:
                errors.append(err)
    if errors:
        return {}, "; ".join(errors)
    if not clean:
        return {}, "no Model Loader values received"
    tmp = DEFAULTS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            data = {"version": VERSION, "values": clean}
            if seed_control is not None:
                data["seed_control"] = seed_control
            json.dump(data, f, indent=2)
        _replace_retry(tmp, DEFAULTS_FILE)      # v0.4.12 (sweep B1): retried on a Windows "Access denied"
    except OSError as e:
        return {}, f"could not write {os.path.basename(DEFAULTS_FILE)}: {e}"
    return clean, None


def clear_user_defaults():
    """Back to the factory defaults: deletes the saved ones. Returns an error text or None."""
    try:
        if os.path.exists(DEFAULTS_FILE):
            os.remove(DEFAULTS_FILE)
    except OSError as e:
        return f"could not delete {os.path.basename(DEFAULTS_FILE)}: {e}"
    return None


def missing_default_files(values):
    """Names of the saved FILES that are not installed (a LoRA slot that is OFF is not checked)."""
    folders = {"unet_name": "diffusion_models", "turbo_lora_name": "loras", "qwen_vl_name": "text_encoders"}
    out = []
    for name, value in values.items():
        if name in folders:
            installed = folder_paths.get_filename_list(folders[name])
        elif name in ("video_vae_name", "audio_vae_name"):
            installed = _vae_options()
        elif name.startswith("LoRa_") and not name.endswith(("_enabled", "_strength")):
            if not values.get(f"{name}_enabled") or value == NONE_LORA:
                continue
            installed = folder_paths.get_filename_list("loras")
        else:
            continue
        if value not in installed:
            out.append(f"{name} ({value})")
    return out


def apply_saved_defaults(kw):
    """Puts the saved defaults into kw (over the factory ones). True when a saved file changed anything."""
    saved = _read_user_defaults()
    keys = _defaults_key_map()
    for name, value in saved.items():
        kw[keys[name]] = value
    return bool(saved)


def apply_model_overrides(kw, models):
    """Apply the dict of the optional "models" input to kw. Returns (from_manager, 'what changed' text).
    Only whitelisted keys count; an empty / "None" file name keeps the hardcoded default."""
    if models is None:
        return False, ""
    if not isinstance(models, dict):
        raise RuntimeError("[IronLeo78 MTV] the 'models' input must come from the "
                           "IronLeo78 MTV Model Loader node.")
    changed = []
    for key in MODEL_FILE_KEYS:
        value = models.get(key)
        if isinstance(value, str) and value.strip() and value != NONE_CHOICE:
            if value != kw.get(key):
                changed.append(f"{key.replace('_name', '')}={value}")
            kw[key] = value
    if models.get("turbo_lora_strength") is not None:      # v0.1.11: the Turbo LoRA strength is on the Model Loader
        try:
            strength = float(models["turbo_lora_strength"])
        except (TypeError, ValueError):
            raise RuntimeError("[IronLeo78 MTV] Model Loader: turbo_lora_strength must be a number.")
        if not -100.0 <= strength <= 100.0:
            raise RuntimeError("[IronLeo78 MTV] Model Loader: turbo_lora_strength must be between -100 and 100.")
        if strength != kw.get("turbo_lora_strength"):
            changed.append(f"turbo_lora_strength={strength:g}")
        kw["turbo_lora_strength"] = strength
    for key in MODEL_STEP_KEYS:
        if models.get(key) is None:
            continue
        try:
            n = int(models[key])
        except (TypeError, ValueError):
            raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {key} must be a whole number.")
        if not MIN_STEPS <= n <= MAX_STEPS:
            raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {key} must be between "
                               f"{MIN_STEPS} and {MAX_STEPS}.")
        if n != kw.get(key):
            changed.append(f"{key}={n}")
        kw[key] = n
    for n in range(1, LORA_SLOTS + 1):      # v0.0.9: LoRa_1 .. LoRa_3 (toggle / file / strength)
        tag = f"LoRa_{n}"
        if models.get(f"lora_{n}_enabled") is not None:
            enabled = _truthy(models[f"lora_{n}_enabled"])
            if enabled != kw.get(f"lora_{n}_enabled"):
                changed.append(f"{tag}={'ON' if enabled else 'OFF'}")
            kw[f"lora_{n}_enabled"] = enabled
        lora = models.get(f"lora_{n}_name")
        if isinstance(lora, str) and lora.strip() and lora != NONE_CHOICE:
            if lora != kw.get(f"lora_{n}_name"):
                changed.append(f"{tag}_name={lora}")
            kw[f"lora_{n}_name"] = lora
        if models.get(f"lora_{n}_strength") is not None:
            try:
                strength = float(models[f"lora_{n}_strength"])
            except (TypeError, ValueError):
                raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {tag}_strength must be a number.")
            if not -100.0 <= strength <= 100.0:
                raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {tag}_strength must be between -100 and 100.")
            if strength != kw.get(f"lora_{n}_strength"):
                changed.append(f"{tag}_strength={strength:g}")
            kw[f"lora_{n}_strength"] = strength
    if models.get("noise_seed") is not None:      # v2.8.5: the seed lives on the Model Loader
        try:
            seed = int(models["noise_seed"])
        except (TypeError, ValueError):
            raise RuntimeError("[IronLeo78 MTV] Model Loader: noise_seed must be a whole number.")
        if not 0 <= seed <= MAX_SEED:
            raise RuntimeError("[IronLeo78 MTV] Model Loader: noise_seed is out of range.")
        if seed != kw.get("noise_seed"):
            changed.append(f"noise_seed={seed}")
        kw["noise_seed"] = seed
    return True, ", ".join(changed) if changed else "nothing changed from the defaults"


def _check_models(kw):
    """Friendly error (before any model is loaded or a segment is used) for a missing model file."""
    source = "Model Loader" if kw.get("models_source") else "saved defaults" if kw.get("defaults_custom") else "hardcoded"
    wanted = [("unet_name", folder_paths.get_filename_list("diffusion_models")),
              ("qwen_vl_name", folder_paths.get_filename_list("text_encoders")),
              ("video_vae_name", _vae_options()),
              ("audio_vae_name", _vae_options())]
    if kw.get("Turbo"):
        wanted.append(("turbo_lora_name", folder_paths.get_filename_list("loras")))
    for n in range(1, LORA_SLOTS + 1):      # v0.0.9: a LoRa is only checked while it is switched ON
        if kw.get(f"lora_{n}_enabled"):
            name = kw.get(f"lora_{n}_name")
            if not name or name == NONE_LORA or name not in folder_paths.get_filename_list("loras"):
                if not name or name == NONE_LORA:      # v0.1.11: the factory set has no custom LoRA file to suggest
                    raise RuntimeError(f"[IronLeo78 MTV] LoRa_{n} ({source}) is ON but no file is selected: pick one "
                                       f"from ComfyUI/models/loras/ (or switch LoRa_{n} OFF on the Model Loader)")
                raise RuntimeError(f"[IronLeo78 MTV] LoRa_{n} ({source}) not found: put "
                                   f"{name} in ComfyUI/models/loras/ "
                                   f"(or switch LoRa_{n} OFF on the Model Loader)")
    for key, options in wanted:
        label, folder = MODEL_FILE_KEYS[key]
        name = kw[key]
        if name not in options:
            where = f"ComfyUI/models/{folder}/"
            extra = " (or switch Turbo OFF)" if key == "turbo_lora_name" else ""
            raise RuntimeError(f"[IronLeo78 MTV] {label} ({source}) not found: "
                               f"put {name} in {where}{extra}")
