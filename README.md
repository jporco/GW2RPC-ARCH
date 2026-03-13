# 🐉 Guild Wars 2 Discord Rich Presence (Arch Linux / CachyOS)

Welcome to the ultimate **Linux/Proton optimized** fork of GW2RPC. Show off your Tyrian adventures on Discord while playing flawlessly on Arch-based distributions!

Unlike the original Windows version, this fork is completely rewritten to understand how Proton/Wine handles memory, ensuring your Discord status never drops when you alt-tab, change maps, or enter loading screens.

## ✨ Why this fork? (Linux Features)
* **Proton MumbleLink Native Support:** Bypasses Windows memory mapping issues. It uses deep file descriptor scanning to read your live coordinates and status directly from `/dev/shm/MumbleLink`.
* **X11 Native Tray Icon:** No more invisible icons. Uses `pystray` and `appindicator` to render a perfect, transparent UI tray icon in desktop environments like KDE Plasma.
* **Continuous Background Session:** The original app relied on active-window network sockets. This fork relies purely on game data, meaning your session timer and status stay active even if the game is minimized.
* **Immersive & Clean:** Removed external website links and redundant buttons from the Discord status for a cleaner, lore-friendly look.

---

## 📋 Requirements
* An Arch-based Linux distribution (Arch Linux, CachyOS, EndeavourOS, etc.)
* Guild Wars 2 running via **Steam** (Proton) or **Wine/Lutris**.
* Python 3 installed on your system.

---

## 📥 How to Install

Open your terminal and follow these steps:

**1. Clone this repository to your Home folder:**
```bash
cd ~
git clone https://github.com/jporco/GW2RPC-ARCH.git
cd GW2RPC-ARCH
```

**2. Run the automated installer:**
```bash
chmod +x install.sh
./install.sh
```
*The installer will automatically download the necessary Arch native packages, create an isolated virtual environment, and add a "GW2 RPC" shortcut to your desktop application menu!*

---

## 🚀 Usage & Steam Configuration

You can launch the program manually from your application menu by clicking on **GW2 RPC**. 

However, the best way to use it is to make it launch automatically whenever you hit "Play" on Steam.

### ⚙️ Auto-Start with Steam ( do it )
Right-click Guild Wars 2 in your Steam Library -> **Properties** -> **General** -> **Launch Options**.

Copy and paste the exact line below:

```text
(/home/porco/GW2RPC_fork/run_rpc.sh & MUMBLE_LINK_FILE=/dev/shm/MumbleLink 
```

**What does this do?**
* `sleep 15`: Waits for Proton to fully boot and allocate the game memory before the RPC tries to read it.
* `MUMBLE_LINK_FILE=/dev/shm/MumbleLink`: Forces Proton to share the game's positional memory with your Linux system.
* *(Note: If you use other parameters like DXVK or FSR, simply add them right before `%command%`)*.
