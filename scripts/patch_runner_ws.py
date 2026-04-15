"""Patch runner.py: fix subscribe-before-connect WS crash."""
import pathlib, sys

path = pathlib.Path("engine/runner.py")
content = path.read_text(encoding="utf-8")
lines = content.split("\n")

start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "# " in line and "6. Subscribe WebSocket" in line:
        start_idx = i
    if start_idx is not None and 'log.info("ws_subscribed"' in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    sys.stdout.buffer.write(b"SECTION NOT FOUND\n")
    sys.exit(1)

sys.stdout.buffer.write(f"Patching lines {start_idx+1} to {end_idx+1}\n".encode())

new_block = [
    '    # -- 6. Subscribe WebSocket --',
    '    loop = asyncio.get_event_loop()',
    '    if _ticker is None:',
    '        _ticker_new = AsyncKiteTicker(',
    '            api_key=settings.KITE_API_KEY,',
    '            access_token=access_token,',
    '            loop=loop,',
    '            coordinator=coordinator,',
    '        )',
    '        # Store tokens before start() so _on_connect subscribes once WS is open',
    '        if _universe_tokens:',
    '            _ticker_new._subscribed_tokens = _universe_tokens',
    '        _ticker_new.start()',
    '        globals()["_ticker"] = _ticker_new',
    '        log.info("ws_connecting_tokens_queued", token_count=len(_universe_tokens))',
    '    else:',
    '        # Already running (reinit after re-login) - update tokens',
    '        if _universe_tokens:',
    '            globals()["_ticker"]._subscribed_tokens = _universe_tokens',
    '            try:',
    '                globals()["_ticker"].subscribe(_universe_tokens)',
    '                globals()["_ticker"].set_mode(MODE_QUOTE, _universe_tokens)',
    '                log.info("ws_resubscribed", token_count=len(_universe_tokens))',
    '            except AttributeError:',
    '                log.info("ws_subscribe_deferred_until_connect")',
]

lines[start_idx:end_idx+1] = new_block
path.write_text("\n".join(lines), encoding="utf-8")
sys.stdout.buffer.write(b"PATCHED OK\n")
