import ctypes
import json
from json.decoder import JSONDecodeError
import mmap
import time
import socket
import logging
import os

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
        ("name_raw", ctypes.c_ubyte * 512),      # 256 * 2 bytes (UTF-16LE)
        ("fCameraPosition", ctypes.c_float * 3),
        ("fCameraFront", ctypes.c_float * 3),
        ("fCameraTop", ctypes.c_float * 3),
        ("identity_raw", ctypes.c_ubyte * 512),  # 256 * 2 bytes (UTF-16LE)
        ("context_len", ctypes.c_uint32),
        ("context", ctypes.c_ubyte * 256),
        ("description_raw", ctypes.c_ubyte * 4096), # 2048 * 2 bytes (UTF-16LE)
    ]

    @property
    def name(self):
        return bytes(self.name_raw).decode('utf-16-le').partition('\0')[0]

    @property
    def identity(self):
        return bytes(self.identity_raw).decode('utf-16-le').partition('\0')[0]

    @property
    def description(self):
        return bytes(self.description_raw).decode('utf-16-le').partition('\0')[0]
# yapf:enable QA ON

class MumbleData:
    def __init__(self, mumble_link="MumbleLink"):
        self.mumble_link = mumble_link
        self.memfile = None
        self._file = None
        self.last_map_id = None
        self.last_timestamp = None
        self.last_valid_data = time.time()
        self.last_rescan = 0
        self.last_character_name = None
        self._use_read = False
        self._fd = None
        self.size_link = 8192  
        self.size_context = ctypes.sizeof(Context)
        self.context = Context() 
        self.in_focus = False
        self.in_combat = False
        self.last_server_ip = None
        self.last_valid_data = time.time()
        self.last_rescan = 0

    def create_map(self, pid=None):
        import platform
        import os
        import psutil
        memfile_length = 8192
        
        if platform.system() == "Linux":
            log.debug(f"DEBUG: Scanning FDs for active MumbleLink (PID focus: {pid})...")
            shm_path = "/dev/shm/MumbleLink" 
            
            import subprocess
            found_fd = False
            
            # If PID is provided, only check that specific process
            if pid:
                target_processes = []
                try: target_processes.append(psutil.Process(pid))
                except: pass
            else:
                target_processes = psutil.process_iter(['name', 'cmdline'])

            for p in target_processes:
                try:
                    pinfo = p.info if hasattr(p, 'info') else p.as_dict(attrs=['name', 'cmdline'])
                    name = str(pinfo.get('name', '')).lower()
                    cmdline = pinfo.get('cmdline') or []
                    cmd_str = " ".join(cmdline).lower()
                    
                    if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2"):
                        try:
                            cmd = ["lsof", "-p", str(p.pid), "-n", "-w"]
                            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
                            for line in output.splitlines():
                                line_lower = line.lower()
                                if ("tmpmap" in line_lower or "mumblelink" in line_lower) and ("REG" in line or "DEL" in line):
                                     parts = line.split()
                                     fd_str = "".join(filter(str.isdigit, parts[3])) 
                                     if fd_str:
                                         test_path = f"/proc/{p.pid}/fd/{fd_str}"
                                         try:
                                             with open(test_path, "rb") as test_f:
                                                 data = test_f.read(8192)
                                                 if len(data) >= 594:
                                                     ui_version = int.from_bytes(data[:4], "little")
                                                     guild_wars_2_hex = "Guild Wars 2".encode('utf-16le')
                                                     if ui_version in (1, 2) and guild_wars_2_hex in data:
                                                         shm_path = test_path
                                                         log.info(f"SURGICAL FD DETECTED (VALID): {shm_path}")
                                                         found_fd = True
                                                         break
                                         except:
                                             pass
                        except Exception as e:
                            log.debug(f"Surgical scan failed for PID {p.pid}: {e}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                
                if found_fd:
                    break

            try:
                if found_fd or os.path.exists(shm_path):
                    log.info(f"OPENING MUMBLELINK: {shm_path}")
                    if shm_path.startswith("/proc/"):
                        self._file = open(shm_path, "rb")
                        self._use_read = True
                        self.memfile = True # Flag
                    else:
                        self._fd = os.open(shm_path, os.O_RDONLY)
                        self.memfile = mmap.mmap(self._fd, memfile_length, access=mmap.ACCESS_READ)
                    log.info(f"MumbleLink READY at {shm_path}")
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

    def _read_data(self, size):
        if not self.memfile:
            return None
        try:
            if self._use_read:
                self._file.seek(0)
                # Note: using os.read on the fileno is often more reliable for /proc
                return os.read(self._file.fileno(), size)
            else:
                self.memfile.seek(0)
                return self.memfile.read(size)
        except Exception as e:
            log.error(f"Error reading MumbleLink data: {e}")
            return None

    def get_mumble_data(self, process=None):
        data = self._read_data(ctypes.sizeof(Link))
        if not data or len(data) < ctypes.sizeof(Link):
            return None
            
        try:
                
            link = self.Unpack(Link, data)
            
            identity_str = link.identity
            if not identity_str.startswith('{'):
                # Some versions/states might have empty identity
                log.debug(f"MumbleLink identity is not JSON: {identity_str!r}")
                return None
                
            # Extract only the JSON part
            end_idx = identity_str.rfind('}')
            if end_idx != -1:
                identity_str = identity_str[:end_idx+1]
            
            try:
                data_json = json.loads(identity_str)
            except json.JSONDecodeError as e:
                log.error(f"JSON decode error in identity: {e} | Content: {identity_str!r}")
                return None

            self.last_valid_data = time.time()
            
            # Update internal state from MumbleLink
            self.last_character_name = data_json.get("name")
            
            # Map Context
            # GW2 often reports context_len=48 but actually contains more data (uiState, mountIndex)
            # We will read up to 88 bytes (sizeof Context) from the 256-byte context buffer.
            context_data = bytes(link.context[:max(link.context_len, ctypes.sizeof(Context))])
            
            if len(context_data) >= 48: 
                try:
                    # Unpack the fixed Context structure
                    ctx = self.Unpack(Context, context_data[:ctypes.sizeof(Context)])
                    self.last_map_id = ctx.mapId
                    
                    # Log raw values only in debug
                    log.debug(f"PARSED CONTEXT: uiState={ctx.uiState}, mountIndex={ctx.mountIndex}, mapId={ctx.mapId}")
                    
                    # Game focus and other flags
                    # GW2 Mumble Link: bit 3 (val 8) is Focus, bit 6 (val 64) is Combat
                    self.in_focus = bool(ctx.uiState & 8)
                    self.in_combat = bool(ctx.uiState & 64)
                    
                    # Server IP
                    if len(ctx.serverAddress) >= 8:
                        self.last_server_ip = socket.inet_ntoa(bytes(ctx.serverAddress[4:8]))
                except Exception as e:
                    log.error(f"Error unpacking Context: {e}")
            


            # Add combat and mount status to the JSON
            data_json["mount_index"] = ctx.mountIndex if 'ctx' in locals() else 0
            data_json["in_combat"] = self.in_combat
            
            # Track character/map changes for duration resets
            character = data_json.get("name")
            map_id = data_json.get("map_id")
            if character and map_id:
                if self.last_character_name != character or self.last_map_id != map_id:
                    self.last_timestamp = int(time.time())
                self.last_map_id = map_id
                self.last_character_name = character
            
            return data_json

        except Exception as e:
            log.error(f"FATAL ERROR in get_mumble_data: {e}", exc_info=True)
            return None

    def get_position(self):
        data = self._read_data(ctypes.sizeof(Link))
        if not data or len(data) < ctypes.sizeof(Link):
            return Position([0,0,0])
        result = self.Unpack(Link, data)
        return Position(result.fAvatarPosition)


class Position:
    def __init__(self, position_data):
        def m_to_in(m):
            return m * 39.3700787

        self.x = m_to_in(position_data[0])
        self.y = m_to_in(position_data[2])
        self.z = position_data[1]
