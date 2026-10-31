"""The MTV's hardcoded settings, factory defaults, route names and limits (constants only). Moved out of mtv.py in v0.4.7."""

from .consts import NONE_CHOICE


VERSION = "0.4.8"

PICTURE_INPUT = "Picture_{}"            # v0.0.9H: optional IMAGE sockets Picture_1 .. Picture_9 (the only way to give reference pictures; always on)
NONE_LORA = NONE_CHOICE
DIVISIBLE_BY = 32          # every width/height is a multiple of 32
CREDIT = "IronLeo78 MTV"

CORE_ATTN_NODE = "ModelAttentionBackend"
CORE_VAE_NODE = "VAELoader"

# Default values (taken from the reference workflow settings).
# A file default is only applied if that file is installed, otherwise "None".
DEFAULT_UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
DEFAULT_TURBO_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
DEFAULT_ATTENTION = "comfy kitchen attention"
DEFAULT_QWEN_VL = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
DEFAULT_VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
DEFAULT_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
DEFAULT_MEGAPIXELS = 0.2          # v2.7.1 (was 0.5)
DEFAULT_DURATION = 5.0            # v0.0.7 (was 15.0 from v2.7.1)
DEFAULT_CUSTOM_LORA = NONE_LORA   # v0.1.11: no custom LoRA in the factory set (was "H3_Unlocked_V2.safetensors")
DEFAULT_CUSTOM_LORA_STR = 1.0     # v0.1.11: the user's tuned defaults (0.65 from v2.7.1 to 0.1.10)
DEFAULT_TURBO_LORA_STR = 1.0      # v0.1.11: the Turbo LoRA strength, now on the Model Loader
DEFAULT_CUSTOM_LORA_ENABLED = False   # v2.8.6: OFF by default (the Model Loader can switch it ON)
LORA_SLOTS = 3                    # v0.0.9: LoRa_1 .. LoRa_3 (custom LoRAs, chained after the Turbo LoRA, each with its own ON / OFF)
MIN_REF_AUDIO_SECONDS = 0.25  # shorter audio can't be encoded by the audio VAE
MAX_REF_AUDIO_SECONDS = 15.0  # longer audio (a whole song) runs the audio VAE out of memory

# Hardcoded settings: not shown on the node any more.
FIXED_SETTINGS = {
    "unet_name": DEFAULT_UNET,
    "weight_dtype": "default",
    "turbo_lora_name": DEFAULT_TURBO_LORA,
    "turbo_lora_strength": DEFAULT_TURBO_LORA_STR,      # v0.1.11: the Model Loader can change it
    # v0.0.9: three custom LoRAs (was one "custom_lora_*"); hardcoded, the Model Loader can change all nine values
    "lora_1_enabled": DEFAULT_CUSTOM_LORA_ENABLED, "lora_1_name": DEFAULT_CUSTOM_LORA, "lora_1_strength": DEFAULT_CUSTOM_LORA_STR,
    "lora_2_enabled": False, "lora_2_name": NONE_LORA, "lora_2_strength": DEFAULT_CUSTOM_LORA_STR,
    "lora_3_enabled": False, "lora_3_name": NONE_LORA, "lora_3_strength": DEFAULT_CUSTOM_LORA_STR,
    "attention_enabled": True,
    "attention": DEFAULT_ATTENTION,
    "qwen_vl_name": DEFAULT_QWEN_VL,
    "qwen_vl_type": "minimax",
    "qwen_vl_device": "default",
    "video_vae_name": DEFAULT_VIDEO_VAE,
    "audio_vae_name": DEFAULT_AUDIO_VAE,
    "ref_image_size": "match",
    "Live Preview": True,        # v2.5.1: ComfyUI's latent preview during sampling stays ON (the saved video is never previewed)
    "force_rate": 24.0,          # always 24 fps
    "turbo_steps": 6,            # Turbo ON  (the Model Loader can change it; 4 until v0.1.10)
    "full_steps": 30,            # Turbo OFF (the Model Loader can change it; 25 until v0.0.8, 40 until v0.1.10)
}

# v2.3: what the optional "models" input (Model Loader) may override. key -> (label, folder)
MODELS_TYPE = "IRONLEO78_MTV_MODELS"
PICTURES_TYPE = "IRONLEO78_PICTURES"      # v0.1.19: a list of nine [1,H,W,3] pictures (empty slot = None or the grey NONE picture)
PICTURES_INPUT = "Pictures"
MODEL_FILE_KEYS = {
    "unet_name": ("Diffusion model", "diffusion_models"),
    "turbo_lora_name": ("Turbo LoRA", "loras"),
    "qwen_vl_name": ("Qwen3-VL text encoder", "text_encoders"),
    "video_vae_name": ("Video VAE", "vae"),
    "audio_vae_name": ("Audio VAE", "vae"),
}
MODEL_STEP_KEYS = ("turbo_steps", "full_steps")
# (the seed, "noise_seed", is read from the Model Loader too, see apply_model_overrides; v2.8.5)
MIN_STEPS, MAX_STEPS = 1, 200

# Hardcoded sampling / output settings.
SAMPLER_NAME = "res_multistep"
SCHEDULER_NAME = "simple"
DENOISE = 1.0
VIDEO_COLOR_SPACE = "sRGB"
VIDEO_CODEC = "h264"          # Create Video
SAVE_FORMAT = "mp4"
DEFAULT_FPS = 24.0            # Minimax runs at 24 fps: used everywhere
MAX_SEED = 0xFFFFFFFFFFFFFFFF
DEFAULT_SEED = 1978
TURBO_STEPS = 6               # Turbo LoRA ON (4 until v0.1.10)
FULL_STEPS = 30               # Turbo LoRA OFF (official r2v template path: no LoRA, more steps; 25 until v0.0.8, 40 until v0.1.10)
DEFAULT_SAVE_LATENT = True    # the "Save Latent" toggle of a NEW node (v0.1.11: ON; OFF from v0.6 to 0.1.10)
SAVE_LATENT_MISSING = False   # v0.1.11: a prompt that sends no "Save Latent" value at all (older than v0.6) still writes no latent files


# v2.2: routing / performance
COND_CACHE_MAX = 6                         # conditioning A / B + audio latent + headroom
AUDIO_CACHE_MAX_BYTES = 768 * 1024 * 1024  # a decoded custom audio file is kept in RAM up to this size
FREE_ROUTE = "/ironleo78/mtv/free"
SEGMENT_ROUTE = "/ironleo78/mtv/segments"   # v2.5: GET  = segment count + counter
RESET_ROUTE = "/ironleo78/mtv/reset"        # v2.5: POST = counter back to segment 1
JUMP_ROUTE = "/ironleo78/mtv/jump"          # v2.6: POST = counter to any segment
LOADER_DEFAULTS_ROUTE = "/ironleo78/mtv/loader_defaults"   # v0.0.9: GET = the current defaults (saved ones, else factory) + the factory ones
SAVE_DEFAULTS_ROUTE = "/ironleo78/mtv/save_defaults"       # v0.0.9: POST = the Model Loader's "Set New Defaults": its values become the new defaults
RESET_DEFAULTS_ROUTE = "/ironleo78/mtv/reset_defaults"     # v0.0.9: POST = back to the factory defaults (deletes the saved ones)
SEED_CONTROLS = ("fixed", "increment", "decrement", "randomize")   # v0.0.9: the seed's "control after generate" values; the saved set keeps the chosen one
