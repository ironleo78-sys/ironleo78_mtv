# Changelog

All notable changes to **IronLeo78 MTV**. The version in `pyproject.toml` (Comfy Registry) is the same as the one shown on the MTV node.

## v0.0.2

### Fixed
- **Model Loader: steps and seed turned into "fixed" after a few loads.** The old-workflow migration decided a Model Loader was "old" by counting its saved values. ComfyUI's frontend saves one value (the *control after generate* setting) that is not listed among the widget names, so a current-format workflow was mistaken for an old one and one value was dropped at every load + save: `turbo_steps` was lost first, then `full_steps`, then `noise_seed`, until all three read `fixed` and the node reported "must be a whole number". The migration now recognises the old format by **what the values are** (an upscale model file name where a number should be), so a current workflow is never touched.
- **Same safeguard for the MTV node:** the 0.5 -> 0.6 migration of the MTV widgets also looks at the values instead of counting them, so extra saved values (such as the picture upload button) can no longer trigger it by accident.
- **Model Loader repairs damaged workflows on load:** if `turbo_steps`, `full_steps`, `noise_seed` or `custom_lora_strength` is not a number (or `custom_lora_enabled` is not ON/OFF), it is reset to the default (4 / 25 / 1978 / 0.65 / OFF) instead of raising an error. Values lost earlier have to be typed in again.
- **Revitalizer:** `megapixels` is rounded to 2 decimals before it reaches the upscaler (a saved `1.1999999999999993` is now exactly `1.2`).

### Changed
- Version shown on the node: **IronLeo78 MTV (v0.0.2)**. Node ids are unchanged, so existing workflows keep loading.
- Added regression tests for the cases above (`tests/test_migration.mjs`, sections 5 and 6).

## v0.0.1

First public pre-alpha: IronLeo78 MTV node, MTV Model Loader and 2in1 Revitalizer in one pack, Audio Stem cache, Save Latent, README in English and French, Comfy Registry metadata and publish workflow.
