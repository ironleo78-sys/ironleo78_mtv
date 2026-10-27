"""
IronLeo78 MTV Model Loader  v0.2
------------------------------------------------------------
Sister node of the IronLeo78 MTV. It has no inputs and one output ("models").
Plug that output into the optional "models" input of the MTV to replace the models and
the step counts that are hardcoded inside it:

  Diffusion model        ComfyUI/models/diffusion_models/
  Custom LoRA            Enable toggle (default OFF), LoRA file (ComfyUI/models/loras/) and strength (default 0.65)
  Turbo LoRA             ComfyUI/models/loras/
  Text encoder (Qwen3-VL) ComfyUI/models/text_encoders/   (clip type "minimax", device "default" stay fixed)
  Video VAE / Audio VAE  ComfyUI/models/vae/
  Steps (Turbo ON)       default 4
  Steps (Turbo OFF)      default 25
  Noise seed             default 1978, control after generate = fixed

(v0.2: the latent upscale model is gone together with the MTV's Latent Upscale stage.)

Every list is read from the installed files. Each default is the MTV's own hardcoded file,
pre-selected when it is installed. Without this node connected the MTV uses its hardcoded
models. Several MTVs can share one Model Loader.
"""

import folder_paths

from .mtv import (
    DEFAULT_UNET, DEFAULT_TURBO_LORA, DEFAULT_QWEN_VL, DEFAULT_VIDEO_VAE, DEFAULT_AUDIO_VAE,
    DEFAULT_CUSTOM_LORA, DEFAULT_CUSTOM_LORA_STR, DEFAULT_CUSTOM_LORA_ENABLED, NONE_LORA, DEFAULT_SEED, MAX_SEED, TURBO_STEPS, FULL_STEPS, MIN_STEPS, MAX_STEPS, MODELS_TYPE,
    MODEL_FILE_KEYS, NONE_CHOICE, _vae_options,
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
        for key, names, wanted in (
                ("unet_name", folder_paths.get_filename_list("diffusion_models"), DEFAULT_UNET),
                ("turbo_lora_name", folder_paths.get_filename_list("loras"), DEFAULT_TURBO_LORA),
                ("qwen_vl_name", folder_paths.get_filename_list("text_encoders"), DEFAULT_QWEN_VL),
                ("video_vae_name", _vae_options(), DEFAULT_VIDEO_VAE),
                ("audio_vae_name", _vae_options(), DEFAULT_AUDIO_VAE)):
            options, default = _choices(names, wanted)
            label, folder = MODEL_FILE_KEYS[key]
            r[key] = (options, {"default": default,
                                "tooltip": f"{label}. Files from ComfyUI/models/{folder}/. "
                                           f"The MTV's hardcoded file is {wanted}."})
            if key == "unet_name":      # v2.8.6: the custom LoRA sits right under the diffusion model
                loras = [NONE_LORA] + [n for n in folder_paths.get_filename_list("loras") if n != NONE_LORA]
                r["custom_lora_enabled"] = ("BOOLEAN", {
                    "default": DEFAULT_CUSTOM_LORA_ENABLED, "label_on": "ON", "label_off": "OFF",
                    "tooltip": "Custom LoRA ON / OFF (default OFF). Applied after the Turbo LoRA."})
                r["custom_lora_name"] = (loras, {
                    "default": DEFAULT_CUSTOM_LORA if DEFAULT_CUSTOM_LORA in loras else NONE_LORA,
                    "tooltip": f"Custom LoRA file from ComfyUI/models/loras/. The MTV's hardcoded file is {DEFAULT_CUSTOM_LORA}."})
                r["custom_lora_strength"] = ("FLOAT", {
                    "default": DEFAULT_CUSTOM_LORA_STR, "min": -100.0, "max": 100.0, "step": 0.01,
                    "tooltip": f"Custom LoRA strength (hardcoded default {DEFAULT_CUSTOM_LORA_STR})."})
        r["turbo_steps"] = ("INT", {
            "default": TURBO_STEPS, "min": MIN_STEPS, "max": MAX_STEPS,
            "tooltip": f"Sampling steps when the MTV's Turbo is ON (hardcoded default {TURBO_STEPS})."})
        r["full_steps"] = ("INT", {
            "default": FULL_STEPS, "min": MIN_STEPS, "max": MAX_STEPS,
            "tooltip": f"Sampling steps when the MTV's Turbo is OFF (hardcoded default {FULL_STEPS})."})
        r["noise_seed"] = ("INT", {
            "default": DEFAULT_SEED, "min": 0, "max": MAX_SEED, "control_after_generate": True,
            "tooltip": f"RandomNoise seed of the MTV (default {DEFAULT_SEED}, control after generate = fixed). "
                       "Used for the sampling pass."})
        return {"required": r}

    RETURN_TYPES = (MODELS_TYPE,)
    RETURN_NAMES = ("models",)
    FUNCTION = "build"
    CATEGORY = "IronLeo78/MTV"
    DESCRIPTION = (
        "Model Loader for the IronLeo78 MTV. Plug 'models' into the MTV's "
        "optional 'models' input to change the diffusion model, Turbo LoRA, text encoder, video / audio VAE, "
        "custom LoRA (toggle, file, strength), the step counts (Turbo ON / OFF) and the noise seed. Nothing connected = the MTV "
        "uses its hardcoded models.\nby IronLeo78"
    )

    def build(self, **kw):
        models = {key: str(kw[key]) for key in MODEL_FILE_KEYS}
        models["custom_lora_enabled"] = bool(kw["custom_lora_enabled"])
        models["custom_lora_name"] = str(kw["custom_lora_name"])
        models["custom_lora_strength"] = float(kw["custom_lora_strength"])
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
        if kw.get("custom_lora_enabled"):      # the LoRA is only checked while it is switched ON
            lora = kw.get("custom_lora_name")
            if lora in (None, "", NONE_LORA):
                return "Custom LoRA: no file selected. Put one in ComfyUI/models/loras/ and press R, or switch it OFF."
            if lora not in folder_paths.get_filename_list("loras"):
                return f"Custom LoRA: file not found: {lora} (ComfyUI/models/loras/)"
        try:
            if not -100.0 <= float(kw.get("custom_lora_strength", DEFAULT_CUSTOM_LORA_STR)) <= 100.0:
                return "custom_lora_strength must be between -100 and 100."
        except (TypeError, ValueError):
            return "custom_lora_strength must be a number."
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
