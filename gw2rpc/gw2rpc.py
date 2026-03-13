import ctypes
import logging
import os
import sys
import threading
import time
import webbrowser
import math
from datetime import datetime, timedelta

import psutil
import requests
import platform
if platform.system() != "Windows":
    import pystray
    from PIL import Image
    class SysTrayIcon:
        def __init__(self, icon_path, title, menu_options=None, on_quit=None):
            self.title = title
            self.icon_path = icon_path
            self.menu_options = menu_options
            self.on_quit = on_quit
            self.icon = None

        def start(self):
            try:
                image = Image.open(self.icon_path)
            except Exception as e:
                log.error(f"Erro ao carregar icone: {e}")
                image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            
            items = []
            if self.menu_options:
                for text, _icon, callback in self.menu_options:
                    items.append(pystray.MenuItem(text, callback))
            
            items.append(pystray.MenuItem(_("Quit"), self.on_quit_internal))
            
            self.icon = pystray.Icon("GW2RPC", image, self.title, pystray.Menu(*items))
            threading.Thread(target=self.icon.run, daemon=True).start()

        def update(self, *args, **kwargs): pass
        def shutdown(self):
            if self.icon: self.icon.stop()
        
        def on_quit_internal(self, icon, item):
            icon.stop()
            if self.on_quit: self.on_quit(self)
else:
    from infi.systray import SysTrayIcon
import socket

def check_single_instance():
    if platform.system() != "Windows":
        try:
            lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            lock_socket.bind('\0gw2rpc_lock_socket')
            return lock_socket 
        except socket.error:
            sys.exit(0)
    return None

_lock = check_single_instance()
import gettext

from .api import APIError, api   
from .character import Character
from .mumble import MumbleData
from .settings import config
from .sdk import DiscordSDK

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

VERSION = 2.55
HEADERS = {'User-Agent': 'GW2RPC v{}'.format(VERSION)}
GW2RPC_BASE_URL = "https://gw2rpc.info/api/v2/"
GW2RPC_APP_ID = "385475290614464513"

log = logging.getLogger()
log.setLevel(config.log_level)

locales_path = resource_path("./locales")

try:
    lang = gettext.translation('base', localedir=locales_path, languages=[config.lang])
    lang.install()
    _ = lang.gettext
except:
    _ = lambda s: s

class GameNotRunningError(Exception):
    pass

worlds = {
    'NA': [
        _('Anvil Rock'), _('Blackgate'), _('Borlis Pass'), _('Crystal Desert'),
        _('Darkhaven'), _("Devona's Rest"), _('Dragonbrand'), _('Ehmry Bay'),
        _('Eredon Terrace'), _("Ferguson's Crossing"), _('Fort Aspenwood'),
        _('Gate of Madness'), _('Henge of Denravi'), _('Isle of Janthir'),
        _('Jade Quarry'), _('Kaineng'), _('Maguuma'), _('Northern Shiverpeaks'),
        _('Sanctum of Rall'), _('Sea of Sorrows'), _("Sorrow's Furnace"),
        _('Stormbluff Isle'), _('Tarnished Coast'), _("Yak's Bend")
    ],
    'EU': [
        _('Aurora Glade'), _('Blacktide'), _('Desolation'), _('Far Shiverpeaks'),
        _('Fissure of Woe'), _('Gandara'), _("Gunnar's Hold"), _('Piken Square'),
        _('Ring of Fire'), _('Ruins of Surmia'), _("Seafarer's Rest"), _('Underworld'),
        _('Vabbi'), _('Whiteside Ridge'), _('Arborstone [FR]'), _('Augury Rock [FR]'),
        _('Fort Ranik [FR]'), _('Jade Sea [FR]'), _('Vizunah Square [FR]'),
        _("Abaddon's Mouth [DE]"), _('Drakkar Lake [DE]'), _('Dzagonur [DE]'),
        _('Elona Reach [DE]'), _('Kodash [DE]'), _("Miller's Sound [DE]"),
        _('Riverside [DE]'), _('Baruch Bay [SP]')
    ]
}

def create_msgbox(description, *, title='GW2RPC', code=0):
    if platform.system() == "Windows":
        MessageBox = ctypes.windll.user32.MessageBoxW
        return MessageBox(None, description, title, code)
    else:
        return 0

class GW2RPC:
    def __init__(self):
        def fetch_registry():
            url = GW2RPC_BASE_URL + "registry"
            try:
                res = requests.get(url, headers=HEADERS)
            except:
                return None
            if res.status_code != 200:
                return None
            return res.json()

        def fetch_support_invite():
            try:
                return requests.get(GW2RPC_BASE_URL + "support", headers=HEADERS).json()["support"]
            except:
                return None

        self.sdk = DiscordSDK(GW2RPC_APP_ID)
        self.registry = fetch_registry()
        self.support_invite = fetch_support_invite()
        self.process = None
        self.last_map_info = None
        self.last_continent_info = None
        self.last_boss = None
        self.boss_timestamp = None
        self.commander_webhook_sent = False
        self.no_pois = set()
        self.game = None
        self.mumble_links = set()
        self.mumble_objects = []
        self.timeticks = 0
        self.prev_char = None
        self.interval = 1 / 2
        self.session_start_time = int(time.time())

    def get_systray_menu(self):
        menu_options = ((_("About"), None, self.about), )
        if self.support_invite:
            menu_options += ((_("Join support server"), None, self.join_guild), )
        if config.webhooks:
            yes_no = _("Yes") if config.announce_raid else _("No")
            menu_options += ((_("Announce raids:") + f" {yes_no}", None, self.toggle_announce_raid), )
        return menu_options

    def create_systray(self):
        def icon_path():
            if platform.system() != "Windows":
                return resource_path("../icon.png") if os.path.exists(resource_path("../icon.png")) else resource_path("icon.png")
            return resource_path("icon.ico")
        
        menu_options = self.get_systray_menu()
        self.systray = SysTrayIcon(
            icon_path(),
            _("Guild Wars 2 with Discord"),
            menu_options,
            on_quit=self.shutdown)
        self.systray.start()

    def get_mumble_links(self):
        mumble_links = set()
        try:
            for process in psutil.process_iter():
                pinfo = process.as_dict(attrs=['pid', 'name', 'cmdline'])
                name = str(pinfo.get('name', '')).lower()
                cmdline = pinfo.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()

                if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2") or "gw2-64.exe" in cmd_str or "gw2.exe" in cmd_str:
                    try:
                        mumble_links.add((cmdline[cmdline.index('-mumble') + 1], process))
                    except ValueError:
                        mumble_links.add(("MumbleLink", process))
                    except AttributeError:
                        continue
        except psutil.NoSuchProcess:
            pass
        return mumble_links

    def create_mumble_objects(self):
        mumble_objects = []
        for m, p in self.mumble_links:
            o = MumbleData(m)
            if not o.memfile:
                o.create_map()
            mumble_objects.append((o, p))
        return mumble_objects

    def shutdown(self, _=None):
        try:
            if hasattr(self, 'sdk') and self.sdk and self.sdk.app:
                self.sdk.activity_manager.clear_activity(self.sdk.callback)
                self.sdk.app.run_callbacks()
                self.sdk.close()
            if os.path.exists("/dev/shm/MumbleLink"):
                os.remove("/dev/shm/MumbleLink")
        except: pass
        if platform.system() != "Windows":
            try:
                current_pid = os.getpid()
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['pid'] != current_pid:
                            cmdline = str(proc.info['cmdline'])
                            if "run.py" in cmdline or "gw2rpc" in proc.info['name'].lower():
                                proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except: pass
        os._exit(0)

    def about(self, _): pass
    def join_guild(self, _): pass
    def toggle_announce_raid(self, _): pass

    def get_active_instance(self):
        for o, p in self.mumble_objects:
            o.get_mumble_data(process=p)
            if o.in_focus:
                return (o, p)
        return None, None

    def in_character_selection(self):
        activity = {
            "state": _("in character selection") + " / " + _("loading screen"),
            "details": _("Character Selection"),
            "timestamps": {
                'start': self.session_start_time
            },
            "assets": {
                "large_image": "default",
                "large_text": _("Character Selection")
            },
            "buttons": []
        }
        return activity

    def get_map_asset(self, map_info, mount_index=None):
        map_id = map_info["id"]
        map_name = map_info["name"]
        region = str(map_info.get("region_id", "thanks_anet"))
        position = self.game.get_position()
        m_x, m_y = self.convert_mumble_coordinates(map_info, position)
        
        state = None
        if self.registry:
            if region == "26":  
                image = "fotm"
                for fractal in self.registry["fractals"]:
                    state, name = self.find_fractal_boss(map_id, fractal, position)
                    if name:
                        image = name.replace('.', "_").lower().replace(" ", "_")
                    if state:
                        break
                    if fractal["id"] == map_id:
                        state = _("in ") + _("fractal") + ": " + _(fractal["name"])  
                        break
                else:
                    if not state:
                        state = _("in ") + _("Fractals of the Mists")
                name = "Fractals of the Mists"
            else:
                if map_name in self.registry["special"]:
                    image = self.registry["special"][map_name]
                elif str(map_id) in self.registry["special"]:
                    image = self.registry["special"][str(map_id)]
                elif map_id in self.registry["valid"]:
                    image = map_id
                elif region in self.registry["regions"]:
                    image = self.registry["regions"][region]
                else:
                    image = "default"
                name = map_name
                mounts = self.registry["mounts"].keys()
                if not config.hide_mounts and mount_index and str(mount_index) in mounts:
                    mount = self.registry["mounts"][str(mount_index)]
                    state = _("on") + " " + _(mount) + " " + _("in ") + name
                else:
                    state = _("in ") + name
        else:
            if map_info["type"] == "Public":
                image = map_id
            else:
                image = "default"
            name = map_name
            state = _("in ") + name
        return state, {"large_image": str(image), "large_text":  _(name)}

    def get_raid_assets(self, map_info, mount_index=None):
        def readable_id(_id):
            _id = _id.split("_")
            dont_capitalize = ("of", "the", "in")
            return " ".join([x.capitalize() if x not in dont_capitalize else x for x in _id])
        boss = self.find_closest_boss(map_info)
        if not boss:
            self.boss_timestamp = None
            return self.get_map_asset(map_info, mount_index)
        if boss["type"] == "boss":
            state = _("fighting ")
        else:
            state = _("completing ")
        name = _(readable_id(boss["id"]))
        state += name
        if self.last_boss != boss["id"]:
            self.boss_timestamp = int(time.time())
        self.last_boss = boss["id"]
        return state, {"large_image": boss["id"], "large_text": name + " - {}".format(map_info["name"])}

    def get_activity(self):
        def get_region():
            world = api.world
            if world:
                for k, v in worlds.items():
                    if world in v:
                        return " [{}]".format(k)
            return ""

        def update_mumble_links():
            all_links = self.get_mumble_links()
            new_links = all_links.difference(self.mumble_links)
            dead_links = self.mumble_links.difference(all_links)

            for m, p1 in dead_links:
                for o, p2 in self.mumble_objects:
                    if o.mumble_link == m:
                        o.close_map()
                        self.mumble_objects.remove((o, p2))
                        del o
                self.mumble_links.remove((m, p1))

            for m, p in new_links:
                o = MumbleData(m)
                if not o.memfile:
                    o.create_map()
                self.mumble_objects.append((o, p))
                self.mumble_links.add((m, p))

            if all_links and all_links == new_links:
                if len(self.mumble_objects) > 0:
                    self.game = self.mumble_objects[0][0]

        update_mumble_links()
        active, active_p = self.get_active_instance()
        self.game = active if active else self.game
        self.process = active_p if active_p else self.process
        
        if not self.game:
            return self.in_character_selection()
            
        data = self.game.get_mumble_data(process=active_p)
        
        if not data or not data.get("name") or data.get("map_id", 0) == 0:
            return self.in_character_selection()
        
        map_id = data.get("map_id", self.game.context.mapId)
        mount_index = data.get("mount_index", 0)
        is_commander = data.get("commander", False)
        in_combat = data.get("in_combat", False)
        point = None
        
        try:
            if self.last_map_info and map_id == self.last_map_info["id"]:
                map_info = self.last_map_info
            else:
                map_info = api.get_map_info(map_id)
                self.last_map_info = map_info

            if (not self.prev_char) or ((self.prev_char and data["name"] != self.prev_char.name)) or (self.timeticks == 0):
                character = Character(data, self.registry)
                tag = character.guild_tag
            else:
                character = Character(data, self.registry, query_guild=False)
                character.guild_tag = self.prev_char.guild_tag
                tag = self.prev_char.guild_tag if self.prev_char else character.guild_tag
            self.prev_char = character
        except APIError:
            self.last_map_info = None
            return None # Ignora falhas da API do jogo em vez de piscar tela
        except Exception:
            return None # Ignora erros gerais de rede em vez de piscar tela
            
        state, map_asset = self.get_map_asset(map_info, mount_index=mount_index)
        tag = tag if config.display_tag else ""
        
        try:
            if map_id in self.no_pois or "continent_id" not in map_info:
                raise APIError(404)
            if (self.last_continent_info and map_id == self.last_continent_info["id"]):
                continent_info = self.last_continent_info
            else:
                continent_info = api.get_continent_info(map_info)
                self.last_continent_info = continent_info
        except APIError:
            self.last_continent_info = None
            self.no_pois.add(map_id)
        
        details = character.name + tag
        timestamp = self.session_start_time

        if self.registry and str(map_id) in self.registry.get("raids", {}):
            state, map_asset = self.get_raid_assets(map_info, mount_index)
        elif self.registry and map_id in [f["id"] for f in self.registry["fractals"]]:
            pass
        else:
            self.last_boss = None
            if self.last_continent_info:
                point = self.find_closest_point(map_info, continent_info)
                if point and not config.disable_pois:
                    map_asset["large_text"] += _(" near ") + point["name"]
        map_asset["large_text"] += get_region()

        if not config.hide_commander_tag and is_commander:
            small_image = "commander_tag"
            details = "{}: {}".format(_("Commander"), details)
        elif character.race == "Jade Bot" or character.profession == "Jade Bot":
            small_image = "jade_bot"
        else:  
            small_image = character.profession_icon
        if in_combat:
            details = "{} {}".format(details, "⚔")
        small_text = "{} {} {}".format(_(character.race), _(character.profession), tag)

        activity = {
            "state": _(state),
            "details": details,
            "timestamps": {'start': timestamp},
            "assets": {**map_asset, "small_image": small_image, "small_text": small_text},
            "buttons": []
        }
        return activity

    def convert_mumble_coordinates(self, map_info, position):
        crect = map_info.get("continent_rect")
        mrect = map_info.get("map_rect")
        if not crect or not mrect:
            return 0, 0
        x = crect[0][0] + (position.x - mrect[0][0]) / 24
        y = crect[0][1] + (mrect[1][1] - position.y) / 24
        return x, y

    def find_closest_point(self, map_info, continent_info):
        position = self.game.get_position()
        x_coord, y_coord = self.convert_mumble_coordinates(map_info, position)
        lowest_distance = float("inf")
        point = None
        for item in continent_info["points_of_interest"].values():
            if "name" not in item:
                continue
            distance = (item["coord"][0] - x_coord)**2 + (item["coord"][1] - y_coord)**2
            if distance < lowest_distance:
                lowest_distance = distance
                point = item
        return point

    def find_closest_boss(self, map_info):
        position = self.game.get_position()
        x_coord, y_coord = self.convert_mumble_coordinates(map_info, position)
        closest = None
        for boss in self.registry["raids"][str(map_info["id"])]:
            distance = math.sqrt((boss["coord"][0] - x_coord)**2 + (boss["coord"][1] - y_coord)**2)
            if "radius" in boss and distance < boss["radius"]:
                if "height" in boss:
                    if position.z < boss["height"]:
                        closest = boss
                else:
                    closest = boss
        return closest

    def find_fractal_boss(self, map_id, fractal, position):
        state = None
        if fractal["id"] == map_id:
            try:
                for boss in fractal["bosses"]:
                    distance = math.sqrt((boss["coord"][0] - position.x)**2 + (boss["coord"][1] - position.y)**2)
                    if distance <= boss["radius"]:
                        if (len(boss["coord"]) > 2 and "height" in boss
                         and position.z >= boss["coord"][2] and position.z <= boss["coord"][2] + boss["height"]) or len(boss["coord"]) <= 2:
                            state = _("fighting ") + _(boss["name"]) + " " + _("in ") + _(fractal["name"])
                            self.last_boss = boss["name"]
                            return state, boss["name"]
                else:
                    self.last_boss = None
                    state = _("in ") + _("fractal") + ": " + _(fractal["name"])
            except KeyError:
                self.last_boss = None
                state = _("in ") + _("fractal") + ": " + _(fractal["name"])
        return state, None

    def is_gw2_running(self):
        try:
            for process in psutil.process_iter(attrs=['name', 'cmdline']):
                name = str(process.info.get('name', '')).lower()
                cmdline = process.info.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()
                if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2") or "gw2-64.exe" in cmd_str or "gw2.exe" in cmd_str:
                    return process
        except psutil.NoSuchProcess:
            pass
        return None

    def main_loop(self):
        try:
            self.create_systray()
            while True:
                try:
                    if not self.process:
                        proc = self.is_gw2_running()
                        if proc:
                            if not os.path.exists("/dev/shm/MumbleLink"):
                                raise GameNotRunningError
                            self.process = proc
                        else:
                            raise GameNotRunningError
                    elif not self.process.is_running():
                        self.process = None
                        raise GameNotRunningError

                    self.interval = 1 / 2
                    try:
                        data = self.get_activity()
                    except requests.exceptions.ConnectionError:
                        self.mumble_objects = []
                        raise GameNotRunningError
                    except Exception as e:
                        time.sleep(2)
                        continue

                    if not self.sdk.app:
                        self.sdk.start()

                    if data is not None:
                        try:
                            if self.sdk.app:
                                self.sdk.set_activity(data)
                                try:
                                    self.sdk.app.run_callbacks()
                                except: pass
                        except BrokenPipeError:
                            raise GameNotRunningError
                    self.timeticks = (self.timeticks + 1) % 1000

                except GameNotRunningError:
                    self.interval = 5
                    if self.game:
                        self.game.close_map()
                    if self.sdk.app:
                        self.sdk.activity_manager.clear_activity(self.sdk.callback)
                        try: self.sdk.app.run_callbacks()
                        except: pass
                        self.sdk.close()
                    
                    if not self.is_gw2_running():
                        if os.path.exists("/dev/shm/MumbleLink"):
                            try: os.remove("/dev/shm/MumbleLink")
                            except: pass
                    time.sleep(self.interval)
        except Exception as e:
            self.shutdown()
