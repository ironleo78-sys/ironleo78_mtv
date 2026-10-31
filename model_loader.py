"""
IronLeo78 MTV Model Loader  v0.3
------------------------------------------------------------
Sister node of the IronLeo78 MTV. It has no inputs and one output ("models").
Plug that output into the optional "models" input of the MTV to replace the models and
the step counts that are hardcoded inside it:

  Diffusion model        ComfyUI/models/diffusion_models/
  Turbo LoRA             ComfyUI/models/loras/
  Turbo LoRA strength    default 1.0 (v0.1.11: was hardcoded)
  LoRa_1, LoRa_2, LoRa_3 three custom LoRAs chained after the Turbo LoRA, in this order. Each one has its own ON / OFF
                         toggle (default OFF), LoRA file (ComfyUI/models/loras/, default None) and strength (default 1.0)
  Text encoder (Qwen3-VL) ComfyUI/models/text_encoders/   (clip type "minimax", device "default" stay fixed)
  Video VAE / Audio VAE  ComfyUI/models/vae/
  Steps (Turbo ON)       default 6
  Steps (Turbo OFF)      default 30
  Noise seed             default 1978, control after generate = fixed

(v0.0.9: the node also has a "Set New Defaults" button (a panel on top of the widgets, added by web/ironleo78_mtv.js, it is
 not a saved widget). It SAVES the Model Loader's current values as the new defaults (mtv_defaults.json in the pack folder, via the
 backend), reads them back and prints a confirmation line. It is ONE SET held on both sides: the MTV uses it from its next run (with no
 Model Loader connected, or as the starting values), and every Model Loader loads the same set again when it is created or a workflow
 is opened (the seed's control after generate is part of it). "Factory" goes back to the built-in values. v0.0.9c: the set is also sent
 to the 2in1 Revitalizers of the open workflow, which have LoRa_1-3 too.)
(v0.2: the latent upscale model is gone together with the MTV's Latent Upscale stage.
 v0.3: three custom LoRAs, all placed right after the Turbo LoRA; Turbo OFF = 40 steps.)

Every list is read from the installed files. Each default is the MTV's own hardcoded file,
pre-selected when it is installed. Without this node connected the MTV uses its hardcoded
models. Several MTVs can share one Model Loader.
"""

import folder_paths

from .mtv import (
    DEFAULT_CUSTOM_LORA, DEFAULT_CUSTOM_LORA_STR, DEFAULT_TURBO_LORA_STR, NONE_LORA, LORA_SLOTS, DEFAULT_SEED, MAX_SEED, TURBO_STEPS, FULL_STEPS, MIN_STEPS, MAX_STEPS, MODELS_TYPE,
    MODEL_FILE_KEYS, NONE_CHOICE, _vae_options, loader_defaults,
)


def _choices(names, wanted):
    """(options, default): the installed files, the hardcoded file pre-selected when it is installed."""
    names = [n for n in names if n != NONE_CHOICE]
    if not names:
        return [NONE_CHOICE], NONE_CHOICE
    return names, (wanted if wanted in names else names[0])


class IronLeo78_MTV_ModelLoader:
    @classmethod
    def INPUT_TYPES(cls):
        r = {}
        d = loader_defaults()      # v0.0.9: the defaults saved with "Set New Defaults" (factory values for what was not saved)
        for key, names, wanted in (
                ("unet_name", folder_paths.get_filename_list("diffusion_models"), d["unet_name"]),
                ("turbo_lora_name", folder_paths.get_filename_list("loras"), d["turbo_lora_name"]),
                ("qwen_vl_name", folder_paths.get_filename_list("text_encoders"), d["qwen_vl_name"]),
                ("video_vae_name", _vae_options(), d["video_vae_name"]),
                ("audio_vae_name", _vae_options(), d["audio_vae_name"])):
            options, default = _choices(names, wanted)
            label, folder = MODEL_FILE_KEYS[key]
            r[key] = (options, {"default": default,
                                "tooltip": f"{label}. Files from ComfyUI/models/{folder}/. "
                                           f"The MTV's hardcoded file is {wanted}."})
            if key == "turbo_lora_name":      # v0.0.9: LoRa_1 .. LoRa_3 sit right after the Turbo LoRA (they are applied after it)
                # v0.1.11: the Turbo LoRA strength (was hardcoded 1.0), right under its file. Saved workflows: named copy /
                # migrateLoaderLayout in web/ironleo78_mtv.js
                r["turbo_lora_strength"] = ("FLOAT", {
                    "default": d["turbo_lora_strength"], "min": -100.0, "max": 100.0, "step": 0.01,
                    "tooltip": f"Turbo LoRA strength (default {DEFAULT_TURBO_LORA_STR}). Only used while the MTV's Turbo is ON."})
                loras = [NONE_LORA] + [n for n in folder_paths.get_filename_list("loras") if n != NONE_LORA]
                for n in range(1, LORA_SLOTS + 1):
                    first = n == 1
                    r[f"LoRa_{n}_enabled"] = ("BOOLEAN", {
                        "default": d[f"LoRa_{n}_enabled"], "label_on": "ON", "label_off": "OFF",
                        "tooltip": f"LoRa_{n} ON / OFF (default OFF). Applied after the Turbo LoRA"
                                   + ("." if first else f" and after LoRa_{n - 1}.")})
                    r[f"LoRa_{n}"] = (loras, {
                        "default": d[f"LoRa_{n}"] if d[f"LoRa_{n}"] in loras else NONE_LORA,
                        "tooltip": f"LoRa_{n}: LoRA file from ComfyUI/models/loras/."
                                   + (f" The MTV's hardcoded file is {DEFAULT_CUSTOM_LORA}." if first and DEFAULT_CUSTOM_LORA != NONE_LORA else "")})
                    r[f"LoRa_{n}_strength"] = ("FLOAT", {
                        "default": d[f"LoRa_{n}_strength"], "min": -100.0, "max": 100.0, "step": 0.01,
                        "tooltip": f"LoRa_{n} strength (default {DEFAULT_CUSTOM_LORA_STR})."})
        r["turbo_steps"] = ("INT", {
            "default": d["turbo_steps"], "min": MIN_STEPS, "max": MAX_STEPS,
            "tooltip": f"Sampling steps when the MTV's Turbo is ON (hardcoded default {TURBO_STEPS})."})
        r["full_steps"] = ("INT", {
            "default": d["full_steps"], "min": MIN_STEPS, "max": MAX_STEPS,
            "tooltip": f"Sampling steps when the MTV's Turbo is OFF (hardcoded default {FULL_STEPS})."})
        r["noise_seed"] = ("INT", {
            "default": d["noise_seed"], "min": 0, "max": MAX_SEED, "control_after_generate": True,
            "tooltip": f"RandomNoise seed of the MTV (default {DEFAULT_SEED}, control after generate = fixed). "
                       "Used for the sampling pass."})
        return {"required": r}

    RETURN_TYPES = (MODELS_TYPE,)
    RETURN_NAMES = ("models",)
    FUNCTION = "build"
    CATEGORY = "IronLeo78/MTV"
    DESCRIPTION = (
        "Model Loader for the IronLeo78 MTV. Plug 'models' into the MTV's "
        "optional 'models' input to change the diffusion model, Turbo LoRA (file + strength), text encoder, video / audio VAE, "
        "three custom LoRAs LoRa_1-3 (toggle, file, strength each, chained after the Turbo LoRA), the step counts (Turbo ON / OFF) and the noise seed. Nothing connected = the MTV "
        "uses its hardcoded models.\nby IronLeo78"
    )

    def build(self, **kw):
        models = {key: str(kw[key]) for key in MODEL_FILE_KEYS}
        models["turbo_lora_strength"] = float(kw.get("turbo_lora_strength", DEFAULT_TURBO_LORA_STR))      # v0.1.11
        for n in range(1, LORA_SLOTS + 1):
            models[f"lora_{n}_enabled"] = bool(kw[f"LoRa_{n}_enabled"])
            models[f"lora_{n}_name"] = str(kw[f"LoRa_{n}"])
            models[f"lora_{n}_strength"] = float(kw[f"LoRa_{n}_strength"])
        models["turbo_steps"] = int(kw["turbo_steps"])
        models["full_steps"] = int(kw["full_steps"])
        models["noise_seed"] = int(kw["noise_seed"])
        return (models,)

    @classmethod
    def VALIDATE_INPUTS(cls, **kw):
        lists = {"unet_name": folder_paths.get_filename_list("diffusion_models"),
                 "turbo_lora_name": folder_paths.get_filename_list("loras"),
                 "qwen_vl_name": folder_paths.get_filename_list("text_encoders"),
                 "video_vae_name": _vae_options(), "audio_vae_name": _vae_options()}
        for key, installed in lists.items():
            label, folder = MODEL_FILE_KEYS[key]
            value = kw.get(key)
            if value in (None, "", NONE_CHOICE):
                return f"{label}: no file available. Put one in ComfyUI/models/{folder}/ and press R to refresh."
            if value not in installed:
                return f"{label}: file not found: {value} (ComfyUI/models/{folder}/)"
        try:
            if not -100.0 <= float(kw.get("turbo_lora_strength", DEFAULT_TURBO_LORA_STR)) <= 100.0:
                return "turbo_lora_strength must be between -100 and 100."
        except (TypeError, ValueError):
            return "turbo_lora_strength must be a number."
        for n in range(1, LORA_SLOTS + 1):
            if kw.get(f"LoRa_{n}_enabled"):      # a LoRA is only checked while it is switched ON
                lora = kw.get(f"LoRa_{n}")
                if lora in (None, "", NONE_LORA):
                    return f"LoRa_{n}: no file selected. Put one in ComfyUI/models/loras/ and press R, or switch it OFF."
                if lora not in folder_paths.get_filename_list("loras"):
                    return f"LoRa_{n}: file not found: {lora} (ComfyUI/models/loras/)"
            try:
                if not -100.0 <= float(kw.get(f"LoRa_{n}_strength", DEFAULT_CUSTOM_LORA_STR)) <= 100.0:
                    return f"LoRa_{n}_strength must be between -100 and 100."
            except (TypeError, ValueError):
                return f"LoRa_{n}_strength must be a number."
        for key in ("turbo_steps", "full_steps"):
            try:
                if not MIN_STEPS <= int(kw.get(key)) <= MAX_STEPS:
                    return f"{key} must be between {MIN_STEPS} and {MAX_STEPS}."
            except (TypeError, ValueError):
                return f"{key} must be a whole number."
        try:
            if not 0 <= int(kw.get("noise_seed", DEFAULT_SEED)) <= MAX_SEED:
                return "noise_seed is out of range."
        except (TypeError, ValueError):
            return "noise_seed must be a whole number."
        return True


NODE_CLASS_MAPPINGS = {"IronLeo78_MTV_ModelLoader": IronLeo78_MTV_ModelLoader}
NODE_DISPLAY_NAME_MAPPINGS = {
    "IronLeo78_MTV_ModelLoader": "IronLeo78 MTV Model Loader"}
