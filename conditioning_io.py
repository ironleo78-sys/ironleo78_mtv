"""
IronLeo78 MTV: saving / loading CONDITIONING  (v0.4.1)
------------------------------------------------------------
ComfyUI has no file format for conditioning, so this module defines a small one: a safetensors file
(extension .conditioning) that holds

  * every tensor of the conditioning, stored once (a tensor that appears twice is stored once and shared again on load),
  * in the file metadata, a JSON description of the structure around them (lists, tuples, dicts, strings, numbers ...).

A MiniMax H3 conditioning is a list of [tensor, {options}] pairs; the options can hold reference latents, guide
data, flags and so on, and all of that is kept. Anything that is not a tensor, a number, a string, a bool, None or a
list / tuple / dict of those cannot be stored: it is written as a placeholder, loads back as None and is reported in
the return value of save_conditioning, so nothing is lost silently.

The structure codec (encode / decode) is plain Python and takes the tensor test as a parameter, so it is testable
without torch. torch, comfy and safetensors are only imported inside save_conditioning / load_conditioning.
"""

import json

FORMAT = "ironleo78_conditioning_v1"
EXTENSION = ".conditioning"

_TENSOR, _TUPLE, _DICT, _OTHER = "__tensor__", "__tuple__", "__dict__", "__unsupported__"
_PLAIN = (type(None), bool, int, float, str)


def encode(obj, tensors, is_tensor, prepare, unsupported, _seen=None, _path="conditioning"):
    """obj -> a JSON-safe structure. Tensors go into `tensors` ({key: prepared tensor}); `prepare` makes the copy
    that is stored. `unsupported` collects 'path: type' for everything that had to be replaced by a placeholder."""
    seen = {} if _seen is None else _seen
    if is_tensor(obj):
        key = seen.get(id(obj))
        if key is None:
            key = f"t{len(tensors)}"
            tensors[key] = prepare(obj)
            seen[id(obj)] = key
        return {_TENSOR: key}
    if isinstance(obj, _PLAIN):
        return obj
    if isinstance(obj, list):
        return [encode(v, tensors, is_tensor, prepare, unsupported, seen, f"{_path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, tuple):
        return {_TUPLE: [encode(v, tensors, is_tensor, prepare, unsupported, seen, f"{_path}[{i}]")
                         for i, v in enumerate(obj)]}
    if isinstance(obj, dict):
        pairs = []
        for k, v in obj.items():
            if not isinstance(k, _PLAIN):
                unsupported.append(f"{_path}: dict key of type {type(k).__name__}")
                k = str(k)
            pairs.append([k, encode(v, tensors, is_tensor, prepare, unsupported, seen, f"{_path}.{k}")])
        return {_DICT: pairs}
    unsupported.append(f"{_path}: {type(obj).__name__}")
    return {_OTHER: type(obj).__name__}


def decode(node, tensors):
    """The inverse of encode. `tensors` is {key: tensor}."""
    if isinstance(node, list):
        return [decode(v, tensors) for v in node]
    if isinstance(node, dict):
        if _TENSOR in node:
            return tensors[node[_TENSOR]]
        if _TUPLE in node:
            return tuple(decode(v, tensors) for v in node[_TUPLE])
        if _DICT in node:
            return {k: decode(v, tensors) for k, v in node[_DICT]}
        if _OTHER in node:
            return None
        raise ValueError("unknown node in the conditioning structure")
    return node


def save_conditioning(path, conditioning, metadata=None):
    """Write `conditioning` to `path`. Returns {"tensors": n, "bytes": tensor bytes, "unsupported": [...]}."""
    import torch
    import comfy.utils

    tensors, unsupported = {}, []
    structure = encode(
        conditioning, tensors, torch.is_tensor,
        lambda t: t.detach().cpu().contiguous().clone(),      # own storage: safetensors refuses shared memory
        unsupported)
    meta = {str(k): str(v) for k, v in (metadata or {}).items()}
    meta["ironleo78_format"] = FORMAT
    meta["structure"] = json.dumps(structure, ensure_ascii=False)
    comfy.utils.save_torch_file(tensors, path, metadata=meta)
    size = 0
    for t in tensors.values():
        try:
            size += int(t.numel()) * int(t.element_size())
        except Exception:
            pass
    return {"tensors": len(tensors), "bytes": size, "unsupported": unsupported}


def load_conditioning(path):
    """Read a .conditioning file written by save_conditioning. Returns the conditioning (a list of [tensor, dict])."""
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as f:
        meta = f.metadata() or {}
        if meta.get("ironleo78_format") != FORMAT or "structure" not in meta:
            raise ValueError("not an IronLeo78 conditioning file (written by IronLeo78 MTV)")
        tensors = {k: f.get_tensor(k) for k in f.keys()}
    return decode(json.loads(meta["structure"]), tensors)
