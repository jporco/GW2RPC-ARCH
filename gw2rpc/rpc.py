"""
This is a modified version of GiovanniMCMXCIX's PyDiscordRPC
https://github.com/GiovanniMCMXCIX/PyDiscordRPC

MIT License

Copyright (c) 2017 GiovanniMCMXCIX

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import asyncio
import json
import struct
import time
import logging

log = logging.getLogger(__name__)


import platform
import os

class DiscordRPC:
    def __init__(self, client_id):
        if platform.system() == "Linux":
            uid = os.getuid()
            # Locais comuns do socket do Discord no Linux
            paths = [
                f'/run/user/{uid}/discord-ipc-0',
                f'/run/user/{uid}/app/com.discordapp.Discord/discord-ipc-0',
                '/tmp/discord-ipc-0'
            ]
            self.ipc_path = next((p for p in paths if os.path.exists(p)), paths[0])
            try:
                self.loop = asyncio.get_event_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
        else:
            self.ipc_path = r'\\?\pipe\discord-ipc-0'
            self.loop = asyncio.ProactorEventLoop()
        
        self.sock_reader: asyncio.StreamReader = None
        self.sock_writer: asyncio.StreamWriter = None
        self.client_id = client_id
        self.running = False
        self.last_update = time.time()
        self.last_payload = {}
        self.last_pid = None

    async def read_output(self):
        try:
            # Add a small timeout so we don't hang during shutdown
            data = await asyncio.wait_for(self.sock_reader.read(1024), timeout=1.0)
            if data:
                code, length = struct.unpack('<ii', data[:8])
                log.debug(f'OP Code: {code}; Length: {length}\nResponse:\n{json.loads(data[8:].decode("utf-8"))}\n')
        except asyncio.TimeoutError:
            log.debug("Discord didn't respond to RPC command (timeout)")
        except Exception as e:
            log.debug(f"Error reading Discord output: {e}")

    def send_data(self, op: int, payload: dict):
        payload = json.dumps(payload)
        self.sock_writer.write(struct.pack('<ii',
                               op, len(payload)) + payload.encode('utf-8'))

    async def handshake(self):
        self.sock_reader = asyncio.StreamReader(loop=self.loop)
        reader_protocol = asyncio.StreamReaderProtocol(self.sock_reader, loop=self.loop)
        
        if platform.system() == "Linux":
            self.sock_writer, _ = await self.loop.create_unix_connection(lambda: reader_protocol, self.ipc_path)
        else:
            self.sock_writer, _ = await self.loop.create_pipe_connection(lambda: reader_protocol, self.ipc_path)
            
        self.send_data(0, {'v': 1, 'client_id': self.client_id})
        data = await self.sock_reader.read(1024)
        code, length = struct.unpack('<ii', data[:8])
        log.debug(f'OP Code: {code}; Length: {length}\nResponse:\n{json.loads(data[8:].decode("utf-8"))}\n')

    def send_rich_presence(self, activity, pid):
        current_time = time.time()
        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "activity": activity,
                "pid": pid
            },
            "nonce": f'{current_time:.20f}'
        }
        self.send_data(1, payload)
        self.last_pid = pid
        try:
            # Garante que os dados foram enviados (flush/drain)
            async def drain():
                await self.sock_writer.drain()
            self.loop.run_until_complete(drain())
            # Lê a resposta para confirmar
            self.loop.run_until_complete(self.read_output())
        except:
            pass

    def close(self):
        try:
            self.send_data(2, {'v': 1, 'client_id': self.client_id})
            async def finish():
                await self.sock_writer.drain()
            self.loop.run_until_complete(finish())
        except:
            pass
        self.last_pid = None
        self.running = False
        if self.sock_writer:
            self.sock_writer.close()
        self.sock_writer: asyncio.StreamWriter = None
        if self.loop.is_running():
            pass # Non-blocking loop
        else:
            try:
                self.loop.close()
            except:
                pass

    def start(self):
        if platform.system() != "Linux":
            self.loop = asyncio.ProactorEventLoop()
        
        # self.loop já deve estar definido no __init__ para Linux
        self.running = True
        self.loop.run_until_complete(self.handshake())
