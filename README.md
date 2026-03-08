# GW2RPC - Linux/Proton Optimized (Arch/CachyOS)

This is a customized fork of GW2RPC fully optimized for Linux systems running Guild Wars 2 via Steam/Proton or Wine. 

## 🛠️ Key Linux Features
* **Proton MumbleLink Support:** Deep file descriptor scanning to accurately read mapped memory via `/dev/shm/MumbleLink` natively.
* **X11 Native Tray Icon:** Replaces legacy Windows UI with `pystray` and `appindicator` for perfect transparent icon rendering in environments like KDE Plasma.
* **Uninterrupted Background Session:** Keeps Discord presence running flawlessly even when alt-tabbed or in loading screens.
* **Clean UI:** Removed external web links from the rich presence interface for a minimalistic look.

## 📥 Installation

1. Clone the repository:
   ```bash
   git clone [https://github.com/jporco/GW2RPC-ARCH.git](https://github.com/jporco/GW2RPC-ARCH.git) /home/porco/GW2RPC_fork
   cd /home/porco/GW2RPC_fork
