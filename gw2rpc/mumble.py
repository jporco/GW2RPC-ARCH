import ctypes
import json
from json.decoder import JSONDecodeError
import mmap
import time
import socket
import logging

log = logging.getLogger()

class MumbleLinkException(Exception):
    pass

class Context(ctypes.Structure):
    _fields_ = [
        ("serverAddress", ctypes.c_ubyte * 28),
        ("mapId", ctypes.c_uint32),
        ("mapType", ctypes.c_uint32),
        ("shardId", ctypes.c_uint32),
        ("instance", ctypes.c_uint32),
        ("buildId", ctypes.c_uint32),
        ("uiState", ctypes.c_uint32),
        ("compassWidth", ctypes.c_uint16),
        ("compassHeight", ctypes.c_uint16),
        ("compassRotation", ctypes.c_float),
        ("playerX", ctypes.c_float),
        ("playerY", ctypes.c_float),
        ("mapCenterX", ctypes.c_float),
        ("mapCenterY", ctypes.c_float),
        ("mapScale", ctypes.c_float),
        ("processId", ctypes.c_uint32),
        ("mountIndex", ctypes.c_uint8),
    ]

# yapf:disable QA OFF
class Link(ctypes.Structure):
    _fields_ = [
        ("uiVersion", ctypes.c_uint32),
        ("uiTick", ctypes.c_uint32),
        ("fAvatarPosition", ctypes.c_float * 3),
        ("fAvatarFront", ctypes.c_float * 3),
        ("fAvatarTop", ctypes.c_float * 3),
        ("name", ctypes.c_wchar * 256),
        ("fCameraPosition", ctypes.c_float * 3),
        ("fCameraFront", ctypes.c_float * 3),
        ("fCameraTop", ctypes.c_float * 3),
        ("identity", ctypes.c_wchar * 256),
        ("context_len", ctypes.c_uint32),
        ("context", ctypes.c_ubyte * 256),
        ("description", ctypes.c_wchar * 2048),
    ]
# yapf:enable QA ON

class MumbleData:
    def __init__(self, mumble_link="MumbleLink"):
        self.mumble_link = mumble_link
        self.memfile = None
        self.last_map_id = None
        self.last_timestamp = None
        self.last_character_name = None
        self.size_link = 8192  
        self.size_context = ctypes.sizeof(Context)
        self.context = Context() 
        self.in_focus = False
        self.in_combat = False
        self.last_server_ip = None
        self.last_valid_data = time.time()
        self.last_rescan = 0

    def create_map(self):
        import platform
        import os
        import psutil
        memfile_length = 8192
        
        if platform.system() == "Linux":
            log.debug("DEBUG: Scanning Gw2-64.exe FDs for active MumbleLink...")
            shm_path = "/dev/shm/MumbleLink" 
            
            import subprocess
            found_fd = False
            for p in psutil.process_iter(['name', 'cmdline']):
                name = str(p.info.get('name', '')).lower()
                cmdline = p.info.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()
                
                if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2") or "gw2-64.exe" in cmd_str or "gw2.exe" in cmd_str:
                    try:
                        cmd = ["lsof", "-p", str(p.pid), "-n", "-w"]
                        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
                        for line in output.splitlines():
                            if "tmpmap" in line and ("REG" in line or "DEL" in line):
                                 parts = line.split()
                                 fd_str = "".join(filter(str.isdigit, parts[3])) 
                                 if fd_str:
                                     test_path = f"/proc/{p.pid}/fd/{fd_str}"
                                     try:
                                         with open(test_path, "rb") as test_f:
                                             # MumbleLink offset for identity is 592
                                             # UTF-16LE for '{' is 0x7b 0x00
                                             data = test_f.read(594)
                                             if len(data) >= 594:
                                                 ui_version = int.from_bytes(data[:4], "little")
                                                 # ui_version in [1, 2] AND identity starts with '{'
                                                 if ui_version in (1, 2) and data[592] == 0x7b and data[593] == 0x00:
                                                     shm_path = test_path
                                                     log.info(f"SURGICAL FD DETECTED (VALID): {shm_path}")
                                                     found_fd = True
                                                     break
                                     except:
                                         pass
                    except Exception as e:
                        log.debug(f"Surgical scan failed for PID {p.pid}: {e}")
                    
                    if found_fd:
                        break

            try:
                if found_fd or os.path.exists(shm_path):
                    log.info(f"OPENING MUMBLELINK: {shm_path}")
                    self._fd = os.open(shm_path, os.O_RDONLY)
                    self.memfile = mmap.mmap(self._fd, memfile_length, access=mmap.ACCESS_READ)
                else:
                    self.memfile = None
                    log.error("MumbleLink memory not found. Game might be loading or lsof failed.")
            except Exception as e:
                self.memfile = None
                log.error(f"Failed to open MumbleLink at {shm_path}: {e}")
        else:
            self.memfile = mmap.mmap(-1, memfile_length, self.mumble_link)

    def close_map(self):
        if self.memfile:
            self.memfile.close()
            self.memfile = None
        if hasattr(self, '_fd') and self._fd is not None:
            import os
            os.close(self._fd)
            self._fd = None
            self.last_map_id = None
            self.last_timestamp = None
            self.last_character_name = None
            self.in_focus = False
            self.in_combat = False
            self.last_server_ip = None

    @staticmethod
    def Unpack(ctype, buf):
        cstring = ctypes.create_string_buffer(buf)
        ctype_instance = ctypes.cast(
            ctypes.pointer(cstring), ctypes.POINTER(ctype)).contents
        return ctype_instance

    def get_mumble_data(self, process=None):
        if not self.memfile:
            return None
        self.memfile.seek(0)
        data = self.memfile.read(8192)
        
        try:
            identity_raw = data[592:592+512]
            identity_str = identity_raw.decode('utf-16le', errors='ignore').split('\x00')[0]
            
            if identity_str.startswith('{'):
                data_json = json.loads(identity_str)
            else:
                now = time.time()
                if now - self.last_valid_data > 5 and now - self.last_rescan > 2:
                    log.info("MumbleLink data invalid for 5s, attempting re-scan...")
                    self.last_rescan = now
                    self.create_map()
                return None
        except Exception as e:
            now = time.time()
            if now - self.last_valid_data > 5 and now - self.last_rescan > 2:
                log.info(f"MumbleLink error ({e}), attempting re-scan...")
                self.last_rescan = now
                self.create_map()
            return None

        self.last_valid_data = time.time()

        context_data = data[1108:1108+self.size_context]
        result_context = self.Unpack(Context, context_data)
        self.context = result_context
        
        uiState = result_context.uiState
        self.in_focus = bool(uiState & 0b1000)
        self.in_combat = bool(uiState & 0b1000000)
        
        address_family = result_context.serverAddress[0]
        if address_family == socket.AF_INET:
            self.last_server_ip = socket.inet_ntop(socket.AF_INET, bytearray(result_context.serverAddress[4:8]))
        elif address_family == socket.AF_INET6:
            self.last_server_ip = None
        else:
            self.last_server_ip = None
        
        data_json["mount_index"] = result_context.mountIndex
        data_json["in_combat"] = self.in_combat
        character = data_json.get("name")
        map_id = data_json.get("map_id")
        if character and map_id:
            if self.last_character_name != character or self.last_map_id != map_id:
                self.last_timestamp = int(time.time())
            self.last_map_id = map_id
            self.last_character_name = character
        
        return data_json

    def get_position(self):
        if not self.memfile:
            return Position([0,0,0])
        self.memfile.seek(0)
        data = self.memfile.read(self.size_link)
        result = self.Unpack(Link, data)
        return Position(result.fAvatarPosition)


class Position:
    def __init__(self, position_data):
        def m_to_in(m):
            return m * 39.3700787

        self.x = m_to_in(position_data[0])
        self.y = m_to_in(position_data[2])
        self.z = position_data[1]
