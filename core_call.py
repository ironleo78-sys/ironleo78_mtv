"""Calling ComfyUI's own nodes from inside the MTV (schema reading, dynamic inputs, the _core helper). Moved out of mtv.py in v0.3.17."""

import logging
import contextlib
import nodes as comfy_nodes
import folder_paths

from .settings import CORE_VAE_NODE

log = logging.getLogger("IronLeo78.MTV")


# ---------------------------------------------------------------------- #
# calling ComfyUI's own nodes (V1 and V3 style) by name
# ---------------------------------------------------------------------- #
_MISSING = object()


def _spec_options(spec):
    """Combo options of an INPUT_TYPES entry, or None when it is not a combo."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return None
    first = spec[0]
    if isinstance(first, (list, tuple)):
        return list(first)
    if first == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        return list(spec[1].get("options") or [])
    return None


def _spec_default(spec):
    """The widget default of an INPUT_TYPES entry, _MISSING for link inputs."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return _MISSING
    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    combo = _spec_options(spec)
    if combo is not None:
        return opts.get("default", combo[0] if combo else _MISSING)
    kind = spec[0]
    if kind == "BOOLEAN":
        return opts.get("default", False)
    if kind == "STRING":
        return opts.get("default", "")
    if kind in ("INT", "FLOAT"):
        return opts.get("default", opts.get("min", 0))
    return _MISSING


def _is_dynamic(spec):
    """V3 'DynamicCombo' input: a combo whose chosen option brings its own sub-inputs."""
    return (isinstance(spec, (list, tuple)) and bool(spec) and isinstance(spec[0], str)
            and "DYNAMICCOMBO" in spec[0].upper())


def _dyn_options(spec):
    """{option key: {sub-input name: sub-input spec}} of a dynamic combo."""
    raw = spec[1].get("options") if len(spec) > 1 and isinstance(spec[1], dict) else None
    out = {}
    for opt in raw or []:
        if isinstance(opt, dict):
            key, inputs = opt.get("key"), opt.get("inputs")
        elif isinstance(opt, (list, tuple)) and len(opt) >= 2:
            key, inputs = opt[0], opt[1]
        else:
            continue
        subs = {}
        if isinstance(inputs, dict):
            for section in ("required", "optional"):
                subs.update(inputs.get(section) or {})
        out[key] = subs
    return out


def _nested_names(spec):
    """Every sub-input name found inside a dynamic combo, at any depth."""
    names = set()
    for subs in _dyn_options(spec).values():
        for sub, sub_spec in subs.items():
            names.add(sub)
            if _is_dynamic(sub_spec):
                names |= _nested_names(sub_spec)
    return names


def _dyn_value(key, spec, provided, consumed, notes, node):
    """
    Build the dict a dynamic combo expects: {key: chosen option, sub-input: value, ...}.
    Sub-inputs we know (by name, e.g. codec / encoding) are filled from `provided`;
    the others get their own default.
    """
    options = _dyn_options(spec)
    if not options:
        return provided.get(key)
    chosen = provided.get(key)
    if chosen not in options:
        if chosen is not None and notes is not None:
            notes.append(f"{node}: '{key}' has no option '{chosen}' here, using its default")
        opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        chosen = opts.get("default", next(iter(options)))
        if chosen not in options:
            chosen = next(iter(options))
    value = {key: chosen}
    for sub, sub_spec in options[chosen].items():
        if _is_dynamic(sub_spec):          # a dynamic combo inside a dynamic combo (format -> codec -> encoding)
            value[sub] = _dyn_value(sub, sub_spec, provided, consumed, notes, node)
            consumed.add(sub)
            continue
        combo = _spec_options(sub_spec)
        if sub in provided and (not combo or provided[sub] in combo):
            value[sub] = provided[sub]
            consumed.add(sub)
            continue
        if sub in provided and notes is not None:
            notes.append(f"{node}: '{sub}' has no option '{provided[sub]}' here, using its default")
            consumed.add(sub)
        default = _spec_default(sub_spec)
        if default is not _MISSING:
            value[sub] = default
    return value


def _describe_spec(spec):
    if not _is_dynamic(spec):
        return ""
    parts = []
    for opt, subs in _dyn_options(spec).items():
        inner = ", ".join(k + ("=" + _describe_spec(v) if _is_dynamic(v) else "") for k, v in subs.items())
        parts.append(f"{opt}({inner})" if inner else str(opt))
    return "dynamic{" + " | ".join(parts) + "}"


def _describe_schema(schema):
    """Compact one-line description of a node's inputs (for the notes when something is off)."""
    return ", ".join(key + ("=" + _describe_spec(spec) if _is_dynamic(spec) else "")
                     for key, (_, spec) in schema.items())


def _split_result(res):
    """Any node result (tuple / dict / V3 NodeOutput) -> (outputs tuple, ui dict or None)."""
    ui = None
    if isinstance(res, dict):
        ui = res.get("ui")
        outs = res.get("result", ())
    elif isinstance(res, tuple):
        outs = res
    elif hasattr(res, "args") or hasattr(res, "result"):
        ui = getattr(res, "ui", None)
        outs = getattr(res, "args", None) or getattr(res, "result", None) or ()
    else:
        outs = (res,)
    if ui is not None and hasattr(ui, "as_dict"):
        ui = ui.as_dict()
    return tuple(outs), (ui if isinstance(ui, dict) else None)


def _core(name, provided, strict=(), hidden=None, notes=None, hoist=False):
    """
    Run a core ComfyUI node by name.
    - `provided` = the inputs we set; the node's own schema is read at run time, so
      inputs we do not set get the node's OWN default (survives ComfyUI updates).
    - `strict` = names that MUST exist in the schema (else a clear error).
    - Dynamic combos (V3) are built as the dict the node expects, nested to any depth.
      Inputs that the schema ALSO lists at top level but that live inside a dynamic combo
      are normally not passed separately; hoist=True passes them as well.
    - Names in `provided` that do not exist in this ComfyUI version are skipped and
      reported in `notes`; a combo value the node does not offer falls back to its default.
    Returns (outputs tuple, ui dict or None).
    """
    cls = comfy_nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:
        raise RuntimeError(f"core node '{name}' not found in this ComfyUI.")

    try:
        types = cls.INPUT_TYPES()
        schema = {}
        for section in ("required", "optional"):
            for key, spec in (types.get(section) or {}).items():
                schema[key] = (section, spec)
    except Exception as e:
        log.debug("No schema for %s (%s); passing inputs unchanged.", name, e)
        schema = None

    if schema is None:
        kwargs = dict(provided)
    else:
        for key in strict:
            if key not in schema:
                raise RuntimeError(f"core node '{name}' has no input '{key}' (ComfyUI changed?).")
        kwargs = {}
        consumed = set()   # names that live inside a dynamic combo
        nested = set()
        for _, spec in schema.values():
            if _is_dynamic(spec):
                nested |= _nested_names(spec)
        for key, (section, spec) in schema.items():
            if _is_dynamic(spec) and (key in provided or section == "required"):
                if key in nested and not hoist:
                    continue
                kwargs[key] = _dyn_value(key, spec, provided, set() if key in nested else consumed, notes, name)
        for key, value in provided.items():
            if key in consumed or key in nested or (key in schema and _is_dynamic(schema[key][1])):
                continue
            if key not in schema:
                msg = (f"{name}: input '{key}' does not exist in this ComfyUI, skipped "
                       f"(inputs here: {_describe_schema(schema)})")
                log.warning(msg)
                if notes is not None:
                    notes.append(msg)
                continue
            options = _spec_options(schema[key][1])
            if options and value not in options:
                msg = f"{name}: '{key}' has no option '{value}' here, using its default"
                log.warning(msg)
                if notes is not None:
                    notes.append(msg)
                continue
            kwargs[key] = value
        for key, (section, spec) in schema.items():
            if key in kwargs or section != "required":
                continue
            if key in nested and not hoist:
                continue
            default = _spec_default(spec)
            if default is _MISSING:
                raise RuntimeError(f"core node '{name}': required input '{key}' was not supplied.")
            kwargs[key] = default

    target = cls
    if hidden is not None and hasattr(cls, "PREPARE_CLASS_CLONE"):  # V3 nodes reading cls.hidden
        try:
            target = cls.PREPARE_CLASS_CLONE(hidden)
        except Exception as e:
            log.warning("PREPARE_CLASS_CLONE failed for %s: %s", name, e)
            target = cls

    # Safety net: V3 nodes such as SaveVideo read cls.hidden.extra_pnginfo. If the clone did
    # not provide it (hidden is None), set a plain holder on the class for the duration of the call.
    patched = []
    if hidden is not None:
        import types as _types
        holder = _types.SimpleNamespace(
            unique_id=hidden.get("UNIQUE_ID"), prompt=hidden.get("PROMPT"),
            extra_pnginfo=hidden.get("EXTRA_PNGINFO"), dynprompt=None,
            auth_token_comfy_org=None, api_key_comfy_org=None)
        for obj in {id(cls): cls, id(target): target}.values():
            if getattr(obj, "hidden", None) is None:
                try:
                    old_hidden = getattr(obj, "hidden", None)
                    obj.hidden = holder
                    patched.append((obj, old_hidden))
                except Exception as e:
                    log.debug("Could not set hidden on %s: %s", name, e)
    try:
        if hasattr(target, "EXECUTE_NORMALIZED"):
            res = target.EXECUTE_NORMALIZED(**kwargs)
        elif hasattr(cls, "FUNCTION") and callable(getattr(cls, cls.FUNCTION, None)):
            res = getattr(cls(), cls.FUNCTION)(**kwargs)
        else:
            res = cls.execute(**kwargs)
    finally:
        for obj, old_hidden in patched:
            try:
                obj.hidden = old_hidden
            except Exception as e:      # v0.0.9r
                log.debug("could not restore the 'hidden' flag of an input (%s)", e)
    return _split_result(res)


@contextlib.contextmanager
def _preview_scope(enabled):
    """
    Live Preview OFF: ComfyUI's latent previews are switched off while the sampler
    runs (restored afterwards), so the node's last picture is the saved video.
    Live Preview ON: ComfyUI's own --preview-method decides.
    """
    args = no_preview = old = None
    if not enabled:
        try:
            from comfy.cli_args import args, LatentPreviewMethod
            no_preview = LatentPreviewMethod.NoPreviews
            old = args.preview_method
            args.preview_method = no_preview
        except Exception as e:
            log.debug("Could not switch previews off: %s", e)
            args = None
    try:
        yield
    finally:
        if args is not None and old is not None:
            args.preview_method = old


# ---------------------------------------------------------------------- #
# model-side helpers
# ---------------------------------------------------------------------- #
def _first_output(result):
    """Normalise V1 tuples and V3 NodeOutput objects to the first output."""
    if isinstance(result, tuple):
        return result[0]
    for attr in ("result", "args"):
        val = getattr(result, attr, None)
        if val:
            return val[0]
    return result


def _core_options(node_name, input_name, fallback):
    """Read a combo list from a core node so it stays in sync with ComfyUI."""
    try:
        cls = comfy_nodes.NODE_CLASS_MAPPINGS[node_name]
        options = cls.INPUT_TYPES()["required"][input_name][0]
        if isinstance(options, (list, tuple)) and len(options) > 0:
            return list(options)
    except Exception as e:
        log.debug("Could not read %s.%s: %s", node_name, input_name, e)
    return list(fallback)


def _vae_options():
    return _core_options(CORE_VAE_NODE, "vae_name", folder_paths.get_filename_list("vae"))
