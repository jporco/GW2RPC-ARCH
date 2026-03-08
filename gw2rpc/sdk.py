import logging
import platform
import os

from .settings import config
from .rpc import DiscordRPC

log = logging.getLogger()
log.setLevel(config.log_level)

class DiscordSDK:
    def __init__(self, client_id) -> None:
        self.client_id = client_id
        self.app = None
        self.rpc = None
        self.start()

    def start(self):
        if platform.system() == "Linux":
            try:
                self.rpc = DiscordRPC(self.client_id)
                self.rpc.start()
                self.app = self # So self.sdk.app is not None
                self.activity_manager = self # For clear_activity
                log.info("Equivalente ao Discord SDK (Linux RPC) iniciado.")
            except Exception as e:
                self.app = None
                log.error(f"Erro ao iniciar o Discord RPC no Linux: {e}")
        else:
            try:
                # Fallback implementation or original import if available
                from .lib.discordsdk import Discord, CreateFlags
                self.app = Discord(int(self.client_id), CreateFlags.no_require_discord)
                self.activity_manager = self.app.get_activity_manager()
            except Exception as e:
                self.app = None
                log.debug(f"Discord Game SDK (Windows) não pôde ser iniciado: {e}")

    def run_callbacks(self):
        # Mock/Dummy function to keep compatibility with gw2rpc.py's main loop
        pass

    def clear_activity(self, callback=None):
        # Mock for when game is not running
        if self.rpc:
            try:
                # Send empty activity or just close
                self.rpc.send_rich_presence({}, os.getpid())
            except:
                pass

    def set_activity(self, a):
        if not self.app:
            return

        def verify_length(val):
            if len(val) > 100:
                val = val[:97] + "..."
            return val

        # Discord RPC payload format
        activity = {
            "state": verify_length(a.get("state", "")),
            "details": verify_length(a.get("details", "")),
            "assets": {}
        }
        
        assets = a.get("assets", {})
        if "large_image" in assets:
            activity["assets"]["large_image"] = assets["large_image"]
        if "large_text" in assets:
            activity["assets"]["large_text"] = verify_length(assets["large_text"])
        if "small_image" in assets:
            activity["assets"]["small_image"] = assets["small_image"]
        if "small_text" in assets:
            activity["assets"]["small_text"] = verify_length(assets["small_text"])
        
        if "timestamps" in a and a["timestamps"]:
            activity["timestamps"] = a["timestamps"]

        # Buttons support in newer RPC versions
        if "buttons" in a and a["buttons"]:
            activity["buttons"] = a["buttons"]

        if platform.system() == "Linux":
            try:
                import psutil
                # Try to get game PID or fallback to a dummy PID if needed
                pid = os.getpid() # Default fallback
                self.rpc.send_rich_presence(activity, pid)
            except Exception as e:
                log.error(f"Erro ao enviar Rich Presence (Linux): {e}")
        else:
            # Re-implementing original SDK logic for Windows if necessary
            # For now, this is a Linux port so we prioritize Linux
            pass

    def close(self):
        if platform.system() == "Linux" and self.rpc:
            try:
                self.rpc.close()
            except:
                pass
        self.app = None

    def callback(self, result):
        pass