"""Probe: does Edge-TTS work right now? Exit 0 + non-empty mp3 = yes."""
import asyncio

import edge_tts
import edge_tts.communicate as _comm
import edge_tts.constants as _C

# Same newer-endpoint patch as dub._synth_edge (2026-10).
_new_wss = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={_C.TRUSTED_CLIENT_TOKEN}"
)
_comm.WSS_URL = _new_wss
_C.WSS_URL = _new_wss


async def main():
    await edge_tts.Communicate("မင်္ဂလာပါ", "my-MM-NilarNeural").save("/tmp/edge_probe.mp3")


asyncio.run(main())
