# 🐉 Guild Wars 2 Discord Rich Presence (Arch Linux / CachyOS)

Welcome to the ultimate **Linux/Proton optimized** fork of GW2RPC. Show off your Tyrian adventures on Discord while playing flawlessly on Arch-based distributions!

Unlike the original Windows version, this fork is completely rewritten to understand how Proton/Wine handles memory, ensuring your Discord status never drops when you alt-tab, change maps, or enter loading screens.

## ✨ Why this fork? (Linux Features)
* **Proton MumbleLink Native Support:** Bypasses Windows memory mapping issues. It uses deep file descriptor scanning to read your live coordinates and status directly from `/dev/shm/MumbleLink`.
* **X11 Native Tray Icon:** No more invisible icons. Uses `pystray` and `appindicator` to render a perfect, transparent UI tray icon in desktop environments like KDE Plasma 6.
* **Continuous Background Session:** The original app relied on active-window network sockets. This fork relies purely on game data, meaning your session timer and status stay active even if the game is minimized.
* **Immersive & Clean:** Removed external website links and redundant buttons from the Discord status for a cleaner, lore-friendly look.

---

## 📋 Requirements
* An Arch-based Linux distribution (Arch Linux, CachyOS, EndeavourOS, etc.)
* Guild Wars 2 running via **Steam** (Proton) or **Wine/Lutris**.
* Python 3 installed on your system.

---

## 📥 How to Install

We made it as simple as possible. Open your terminal and follow these steps:

**1. Clone this repository to your Home folder:**
```bash
cd ~
git clone [https://github.com/jporco/GW2RPC-ARCH.git](https://github.com/jporco/GW2RPC-ARCH.git)
cd GW2RPC-ARCH
