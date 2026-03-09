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
    # Mock SysTrayIcon for compatibility with the rest of the code
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
                image = Image.new('RGBA', (64, 64), (0, 0, 0, 0)) # Fallback transparente
            
            # Convert menu_options from (text, icon, callback) to pystray.MenuItem
            items = []
            if self.menu_options:
                for text, _icon, callback in self.menu_options:
                    items.append(pystray.MenuItem(text, callback))
            
            # Add final Quit option
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
import sys

# Single Instance Lock for Linux
def check_single_instance():
    if platform.system() != "Windows":
        try:
            lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            lock_socket.bind('\0gw2rpc_lock_socket')
            return lock_socket # Keep reference to keep lock
        except socket.error:
            print("GW2RPC já está em execução.")
            sys.exit(0)
    return None

_lock = check_single_instance()
import gettext
import urllib.parse

from .api import APIError, api   
from .character import Character
from .mumble import MumbleData
from .settings import config
from .sdk import DiscordSDK

import sys
import os
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
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
        print(f"[{title}] {description}")
        return 0


class GW2RPC:
    def __init__(self):

        def fetch_registry():
            url = GW2RPC_BASE_URL + "registry"
            try:
                res = requests.get(url, headers=HEADERS)
            except:
                log.error(f"Could not open connection to {url}. Web API will not be available!")
                return None
            if res.status_code != 200:
                log.error("Could not fetch the web registry")
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
        self.commander_webhook_sent = False
        self.no_pois = set()
        self.check_for_updates()
        
        # Initialize monitoring variables
        self.process = None
        self.mumble_links = set()
        self.mumble_objects = []
        
        # Initial scan to populate links and process
        self.update_mumble_links()
        
        self.game = None
        if len(self.mumble_objects) > 0:
            self.game = self.mumble_objects[0][0]
            
        self.last_map_info = None
        self.last_continent_info = None
        self.last_boss = None
        self.boss_timestamp = None
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
        """ This is now a lightweight wrapper as scanning is handled in update_mumble_links """
        return self.mumble_links

    def update_mumble_links(self):
        """ 
        Consolidated scanner: 
        1. Finds the GW2 process for shutdown monitoring.
        2. Detects MumbleLink instances.
        3. Only uses one psutil.process_iter() pass.
        """
        all_found_links = set()
        gw2_proc = None
        
        try:
            for process in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
                try:
                    pinfo = process.info
                    name = str(pinfo.get('name', '')).lower()
                    cmdline = pinfo.get('cmdline') or []
                    cmd_str = " ".join(cmdline).lower()

                    if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2") or "gw2-64.exe" in cmd_str or "gw2.exe" in cmd_str:
                        if not gw2_proc:
                            gw2_proc = process
                        
                        try:
                            # Try to find -mumble argument
                            mumble_name = "MumbleLink"
                            if '-mumble' in cmdline:
                                mumble_name = cmdline[cmdline.index('-mumble') + 1]
                            all_found_links.add((mumble_name, process))
                        except (ValueError, IndexError):
                            all_found_links.add(("MumbleLink", process))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            log.error(f"Error scanning processes: {e}")

        # Update self.process for main_loop monitoring
        if gw2_proc:
            self.process = gw2_proc
        elif self.process and not self.process.is_running():
            self.process = None

        # Compare using PIDs for stability
        all_pids = set((m, p.pid) for m, p in all_found_links)
        current_pids = set((m, p.pid) for m, p in self.mumble_links)
        
        new_pids = all_pids.difference(current_pids)
        dead_pids = current_pids.difference(all_pids)

        # Remove dead links
        for m, pid1 in dead_pids:
            for o, p2 in self.mumble_objects[:]:
                if o.mumble_link == m and p2.pid == pid1:
                    o.close_map()
                    self.mumble_objects.remove((o, p2))
            self.mumble_links = set((m_l, p_l) for m_l, p_l in self.mumble_links if not (m_l == m and p_l.pid == pid1))

        # Add new links
        for m, pid in new_pids:
            try:
                p = next(p_obj for m_l, p_obj in all_found_links if m_l == m and p_obj.pid == pid)
                o = MumbleData(m)
                o.create_map()
                self.mumble_objects.append((o, p))
                self.mumble_links.add((m, p))
            except StopIteration:
                continue

    def create_mumble_objects(self):
        mumble_objects = []
        for m, p in self.mumble_links:
            o = MumbleData(m)
            if not o.memfile:
                o.create_map()
            mumble_objects.append((o, p))
        log.debug(f"Mumble Link objects created: {mumble_objects}")
        return mumble_objects

    def shutdown(self, _=None):
        log.info("Shutdown!")
        # Força limpeza do status no Discord antes de fechar
        try:
            if hasattr(self, 'sdk') and self.sdk and self.sdk.app:
                # Send empty activity first
                self.sdk.set_activity({})
                self.sdk.activity_manager.clear_activity(self.sdk.callback)
                if hasattr(self.sdk.app, 'run_callbacks'):
                    self.sdk.app.run_callbacks()
                # Give it a small time to flush the packet to the socket
                time.sleep(1)
                self.sdk.close()
        except Exception as e:
            log.debug(f"Erro ao limpar Discord SDK: {e}")

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
            except Exception as e:
                log.debug(f"Erro ao limpar instâncias: {e}")
        os._exit(0)

    def about(self, _):
        message = (
            "Version: {}\n\nhttps://gw2rpc.info\n\nBy Maselkov & "
            "N1tR0\nIcons by Zebban\nWebsite by Penemue\nTranslations by Seshu (de), TheRaytheone (es), z0n3g (fr)".format(VERSION))
        threading.Thread(target=create_msgbox, args=[message]).start()

    def join_guild(self, _):
        try:
            webbrowser.open(self.support_invite)
        except webbrowser.Error:
            pass

    def toggle_announce_raid(self, _):
        config.announce_raid = not config.announce_raid
        config.change_boolean_item("Webhooks", "AnnounceRaid", config.announce_raid)
        menu_options = self.get_systray_menu()
        self.systray.update(menu_options=menu_options)

    def check_for_updates(self):
        def get_build():
            url = GW2RPC_BASE_URL + "build"
            try:
                r = requests.get(url, headers=HEADERS)
            except:
                log.error(f"Could not open connection to {url}")
                return None
            try:
                return r.json()["build"]
            except:
                return None

        build = get_build()
        if not build:
            log.error("Could not retrieve build!")
            create_msgbox(_("Could not check for updates - check your connection!"))
            return
        if build > VERSION:
            log.info("New version found! Current: {} New: {}".format(VERSION, build))
            res = create_msgbox(
                _("There is a new update for GW2 Rich Presence available. "
                "Would you like to be taken to the download page now?"),
                code=68)
            if res == 6:
                webbrowser.open("https://gw2rpc.info/")

    def get_active_instance(self):
        for o, p in self.mumble_objects:
            o.get_mumble_data(process=p)
            if o.in_focus:
                return (o, p)
        return None, None

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
            special = {
                "1068": "gh_hollow",  
                "1101": "gh_hollow",  
                "1107": "gh_hollow",  
                "1108": "gh_hollow",  
                "1121": "gh_hollow",  
                "1069": "gh_precipice",  
                "1076": "gh_precipice",  
                "1071": "gh_precipice",  
                "1104": "gh_precipice",  
                "1124": "gh_precipice",  
                "882": "wintersday_snowball",
                "877": "wintersday_snowball",  
                "1155": "1155",  
                "1214": "gh_haven",  
                "1215": "gh_haven",  
                "1232": "gh_haven",  
                "1224": "gh_haven",  
                "1243": "gh_haven",  
                "1250": "gh_haven"
            }.get(map_info["id"])
            if special:
                return special
            if map_info["type"] == "Public":
                image = map_id
            else:
                valid_ids = [1062, 1149, 1156, 38, 1264]
                if map_id in valid_ids:
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
            return " ".join([
                x.capitalize() if x not in dont_capitalize else x for x in _id
            ])

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
        return state, {
            "large_image": boss["id"],
            "large_text": name + " - {}".format(map_info["name"])
        }

    def get_activity(self, mumble_targets=None):
        if not mumble_targets:
            return None
        
        # In a multi-account scenario, pick the active one if possible
        active, active_p = self.get_active_instance()
        self.game = active if active else self.game
        self.process = active_p if active_p else self.process
        
        if not self.game:
            return None

        # Helper functions
        def get_region():
            world = api.world
            if world:
                for k, v in worlds.items():
                    if world in v:
                        return " [{}]".format(k)
            return ""

        def get_closest_poi(map_info, continent_info):
            region = map_info.get("region_id")
            if config.disable_pois:
                return None
            if config.disable_pois_in_wvw and region == 7:
                return None
            return self.find_closest_point(map_info, continent_info)
        active, active_p = self.get_active_instance()
        self.game = active if active else self.game
        self.process = active_p if active_p else self.process
        data = self.game.get_mumble_data(process=active_p)
        if not data:
            return None
        log.debug(f"DEBUG RAW MUMBLE DATA: {data}")
        buttons = []
        map_id = data.get("map_id", self.game.context.mapId)
        is_commander = data.get("commander", False)
        mount_index = data.get("mount_index", 0)
        in_combat = data.get("in_combat", False)
        copy_paste_url = None
        point = None
        try:
            mount_index = data.get("mount_index", 0)
            is_commander = data.get("commander", False)
            map_id = data.get("map_id", self.game.context.mapId)
            
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
            log.error("API Error!")
            self.last_map_info = None
            return None
        except Exception as e:
            log.error(f"Identity processing error: {e}")
            return None
            
        state, map_asset = self.get_map_asset(map_info, mount_index=mount_index)

        tag = tag if config.display_tag else ""
        try:
            if map_id in self.no_pois or "continent_id" not in map_info:
                raise APIError(404)
            if (self.last_continent_info
                    and map_id == self.last_continent_info["id"]):
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
                point = get_closest_poi(map_info, continent_info)
                if point:
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

        if config.announce_raid and is_commander and not self.commander_webhook_sent:
            region = map_info.get("region_id")
            if not config.disable_raid_announce_in_wvw or region != 7:
                copy_paste_url = copy_paste_url or "https://gw2rpc.info"
                chat_link = f"*{point['name']}: `{point['chat_link']}`*" if point else None
                for u in config.webhooks:
                    self.send_webhook(u, character.name, _(state), copy_paste_url, character.profession, chat_link)
                self.commander_webhook_sent = True
        if not is_commander and self.commander_webhook_sent:
            self.commander_webhook_sent = False

        activity = {
            "state": _(state),
            "details": details,
            "timestamps": {
                'start': timestamp
            },
            "assets": {
                **map_asset,
                "small_image": small_image,
                "small_text": small_text
            },
            "buttons": buttons
        }
        return activity

    def in_character_selection(self):
        activity = {
            "state": _("in character selection") + " / " + _("loading screen"),
            "details": _("Character Selection"),
            "timestamps": {
                'start': self.session_start_time
            },
            "assets": {
                "large_image":
                "default",
                "large_text":
                _("Character Selection")
            },
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
            distance = (item["coord"][0] - x_coord)**2 + (
                item["coord"][1] - y_coord)**2
            if distance < lowest_distance:
                lowest_distance = distance
                point = item
        return point

    def find_closest_boss(self, map_info):
        position = self.game.get_position()
        x_coord, y_coord = self.convert_mumble_coordinates(map_info, position)
        closest = None
        for boss in self.registry["raids"][str(map_info["id"])]:
            distance = math.sqrt((boss["coord"][0] - x_coord)**2 +
                                 (boss["coord"][1] - y_coord)**2)
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
                    distance = math.sqrt((boss["coord"][0] - position.x)**2 +
                                         (boss["coord"][1] - position.y)**2)
                    
                    if distance <= boss["radius"]:
                        if (len(boss["coord"]) > 2 and "height" in boss
                         and position.z >= boss["coord"][2] and position.z <= boss["coord"][2] + boss["height"]) or len(boss["coord"]) <= 2:
                            state = _("fighting ") + _(boss["name"]) + " " + _("in ") + _(fractal["name"])
                            if self.last_boss != boss["name"]:
                                self.boss_timestamp = int(time.time())
                            self.last_boss = boss["name"]
                            return state, boss["name"]
                else:
                    self.boss_timestamp = None
                    self.last_boss = None
                    state = _("in ") + _("fractal") + ": " + _(fractal["name"])
            except KeyError:
                self.boss_timestamp = None
                self.last_boss = None
                state = _("in ") + _("fractal") + ": " + _(fractal["name"])
        return state, None

    def send_webhook(self, url, name, map, website_url, profession, poi=None):
        timestamp = datetime.now()
        ts = time.time()
        utc_offset = (datetime.fromtimestamp(ts) -
              datetime.utcfromtimestamp(ts)).total_seconds()
        timestamp = (timestamp - timedelta(seconds=utc_offset)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        logo_url = "https://gw2rpc.info/static/img/logo.png"
        profession_url = f"https://gw2rpc.info/static/img/professions/prof_{profession.lower()}.png"

        data = {
            "username": "GW2RPC",
            "avatar_url": logo_url
        }
        data["embeds"] = [
            {
                "author": {
                    "name": _("GW2RPC Raid Announcer"),
                    "icon_url": profession_url,
                    "url": "https://gw2rpc.info"
                },
                "thumbnail": {
                    "url": "https://gw2rpc.info/static/img/professions/commander_tag.png"
                },
                "footer": {
                    "text": "by GW2RPC https://gw2rpc.info",
                    "icon_url": logo_url
                },
                "title" : f"{name} " + _("tagged up") + f" {map}",
                "url": website_url,
                "color": "12660011",
                "timestamp": timestamp,
                "fields": [
                    {
                        "name": _("Copy and paste the following to join"),
                        "value": f"`/sqjoin {name}`"
                    }
                ]
            }
        ]   
        if poi:  
            data["embeds"][0]["fields"].append({"name": _("Closest PoI"), "value": f"{poi}"})

        try:
            result = requests.post(url, json = data)
            result.raise_for_status()
        except requests.exceptions.HTTPError as err:
            log.error(err)
        except:
            log.error(f"Invalid webhook url: {url}")

    def main_loop(self):
        def update_gw2_process():
            shutdown = False
            if self.process:
                if self.process.is_running():
                    return
                else:
                    # FORÇA SHUTDOWN ASSIM QUE O JOGO FECHAR
                    shutdown = True
            try:
                names = []
                for process in psutil.process_iter(attrs=['name', 'cmdline']):
                    name = str(process.info.get('name', '')).lower()
                    cmdline = process.info.get('cmdline') or []
                    cmd_str = " ".join(cmdline).lower()
                    names.append(name)
                    
                    if name in ("gw2-64.exe", "gw2.exe", "gw2-64", "gw2") or "gw2-64.exe" in cmd_str or "gw2.exe" in cmd_str:
                        log.debug(f"Found GW2 process: {name}")
                        self.process = process
                        return
                else:  
                    log.debug(f"GW2 process not found, List of processes: {names}")
            except psutil.NoSuchProcess:
                log.debug("A process exited while iterating over the process list.")
                pass

            if shutdown:
                self.shutdown()
            self.process = None
            raise GameNotRunningError

        def check_for_running_rpc():
            count = 0
            try:
                for process in psutil.process_iter(attrs=['name']):
                    name = process.info['name']
                    if name == "gw2rpc.exe":
                        count += 1
                    if count > 2:
                        break
                else:
                    return
            except psutil.NoSuchProcess:
                log.debug("A process exited while iterating over the process list.")
                pass    
            log.info("Another gw2rpc process is already running, exiting.")
            if self.sdk.app:
                self.sdk.activity_manager.clear_activity(self.sdk.callback)
                self.sdk.close()
                log.debug("Killing SDK")
            self.shutdown()

        try:
            check_for_running_rpc()
            self.create_systray()
            
            while True:
                try:
                    # Comprehensive process and link update
                    self.update_mumble_links()
                    
                    if not self.process:
                        raise GameNotRunningError

                    self.interval = 1 / 2
                    data = None
                    
                    if self.mumble_objects:
                        try:
                            data = self.get_activity(self.mumble_objects)
                        except requests.exceptions.ConnectionError:
                            raise GameNotRunningError
                        except Exception as e:
                            log.error(f"Error in get_activity: {e}")
                    
                    if not data:
                        data = self.in_character_selection()
                    
                    if not self.sdk.app:
                        self.sdk.start()
                    
                    if self.sdk.app:
                        try:
                            self.sdk.set_activity(data)
                            self.sdk.app.run_callbacks()
                        except Exception as e:
                            log.debug(f"Erro no SDK: {e}")
                            self.sdk.close()
                    
                    self.timeticks = (self.timeticks + 1) % 1000
                    time.sleep(2) # Normal loop interval
                    
                except GameNotRunningError:
                    self.interval = 5
                    if self.game:
                        self.game.close_map()
                    if self.sdk.app:
                        try:
                            self.sdk.set_activity({}) # Send empty to clear
                            self.sdk.activity_manager.clear_activity(self.sdk.callback)
                            if hasattr(self.sdk.app, 'run_callbacks'):
                                self.sdk.app.run_callbacks()
                            time.sleep(0.5) # Small flush delay
                        except:
                            pass
                        self.sdk.close()
                    time.sleep(self.interval)
        except Exception as e:
            log.critical(f"GW2RPC v{VERSION} has crashed", exc_info=e)
            create_msgbox(
                "GW2 Rich Presence has crashed.\nPlease check your "
                "log file and report this to the author!",
                code=16)
            self.shutdown()
