"""The HTTP routes of the segment panel and the Model Loader (free, segments, reset, jump, defaults). Moved out of mtv.py in v0.4.8."""

import logging

log = logging.getLogger("IronLeo78.MTV")


def register(m):
    """`m` = the mtv module (its names are read at call time, so a test that patches one still takes effect).
    POST .../free (the node's JS calls it after the last node was removed),
    GET .../segments (v2.5: segment count + counter for the node's segment panel),
    POST .../reset (v2.5: the Reset button), POST .../jump (v2.6: Go / Latest)."""
    try:
        from aiohttp import web
        from server import PromptServer
        if PromptServer.instance is None:
            return
        routes = PromptServer.instance.routes

        @routes.post(m.FREE_ROUTE)
        async def _free_route(request):
            # v0.4.12 (sweep B5): also refused while a Revitalizer or Prompt Generator runs (model_cache.busy), not only an MTV
            if m._RUNNING > 0 or m._models.is_busy():
                return web.json_response({"ok": False, "busy": True})
            m.free_cached_models("node removed")
            return web.json_response({"ok": True})

        @routes.get(m.SEGMENT_ROUTE)
        async def _segment_route(request):
            import asyncio
            params = dict(request.rel_url.query)
            try:      # the file probing runs in a worker thread: never block the server
                info = await asyncio.get_running_loop().run_in_executor(None, m._segment_info, params)
            except Exception as e:
                log.debug("segment info failed: %s", e)
                return web.json_response({"ok": False, "error": str(e)})
            info["ok"] = True
            return web.json_response(info)

        @routes.post(m.RESET_ROUTE)
        async def _reset_route(request):
            if m._RUNNING > 0:
                return web.json_response({"ok": False, "busy": True})
            try:      # v0.1.8: {"params": the node's widget values} picks the song's counter (nothing sent = the shared one)
                body = await request.json()
            except Exception:
                body = {}
            key = m._counter_key(body.get("params") if isinstance(body, dict) else None)
            import asyncio      # v0.4.14 (sweep N1): the file work runs in a worker thread, never on the web server's own thread
            await asyncio.get_running_loop().run_in_executor(None, m._reset_state, key)
            log.info("segment counter of %s reset to 0", m._counter_label(key))
            return web.json_response({"ok": True, "index": 0})

        @routes.post(m.JUMP_ROUTE)
        async def _jump_route(request):
            if m._RUNNING > 0:
                return web.json_response({"ok": False, "busy": True})
            try:
                body = await request.json()
            except Exception:
                body = {}
            import asyncio      # v0.4.14 (sweep N1): in a worker thread, like the segments route
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, m._handle_jump, body))

        @routes.get(m.LOADER_DEFAULTS_ROUTE)
        async def _loader_defaults_route(request):
            return web.json_response({"ok": True, "defaults": m.loader_defaults(), "factory": m.factory_defaults(),
                                      "custom": bool(m._read_user_defaults()),
                                      "seed_control": m._read_user_seed_control()})     # None = the saved set holds no seed control

        @routes.post(m.SAVE_DEFAULTS_ROUTE)
        async def _save_defaults_route(request):
            try:
                body = await request.json()
            except Exception:
                body = {}
            saved, err = m.save_user_defaults(body.get("values") if isinstance(body, dict) else None,
                                            body.get("seed_control") if isinstance(body, dict) else None)
            if err:
                return web.json_response({"ok": False, "error": err})
            log.info("Model Loader values saved as the new defaults (%d values)", len(saved))
            return web.json_response({"ok": True, "saved": saved, "missing": m.missing_default_files(saved)})

        @routes.post(m.RESET_DEFAULTS_ROUTE)
        async def _reset_defaults_route(request):
            err = m.clear_user_defaults()
            return web.json_response({"ok": err is None, "error": err})
    except Exception as e:
        log.debug("routes not registered: %s", e)
