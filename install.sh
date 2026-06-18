#!/usr/bin/env bash
# Openbox environment setup for Arch Linux
# Copy this entire openbox-setup/ directory to the target machine and run:
#   bash install.sh

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()   { echo -e "${RED}[ERR ]${NC} $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ -f /etc/arch-release ]] || die "This script targets Arch Linux only."
[[ "$EUID" -eq 0 ]]        && die "Run as a regular user (sudo is invoked internally)."

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="$HOME"
USERNAME="$(id -un)"

info "Setting up openbox environment for user: $USERNAME ($USER_HOME)"

# ── AUR helper ────────────────────────────────────────────────────────────────
install_aur_helper() {
    if command -v paru &>/dev/null; then ok "paru already installed."; return; fi
    if command -v yay  &>/dev/null; then ok "yay already installed.";  return; fi
    info "Installing yay (AUR helper)..."
    sudo pacman -S --needed --noconfirm base-devel git
    local tmpdir; tmpdir=$(mktemp -d)
    git clone https://aur.archlinux.org/yay.git "$tmpdir/yay"
    (cd "$tmpdir/yay" && makepkg -si --noconfirm)
    rm -rf "$tmpdir"
    ok "yay installed."
}

# ── Package installation ──────────────────────────────────────────────────────
CORE_PKGS=(
    # Window manager + compositor
    openbox picom obconf-qt
    # Panel / monitor / launcher / wallpaper
    tint2 conky rofi dmenu feh
    # Display manager
    ly
    # File manager + GTK dark theme
    thunar 
    # System tray
    blueman network-manager-applet volumeicon
    # PolicyKit authentication agent
    polkit-gnome
    # Fonts
    ttf-roboto noto-fonts
    # Terminal emulator
    sakura
    # Media controls
    playerctl pavucontrol pipewire wireplumber pipewire-pulse
    # Screenshots + clipboard
    scrot xclip
    # Misc tools used by keybindings / scripts
    xorg-xkill geany gsimplecal i3lock redshift brightnessctl
    # Hardware sensors (for conky)
    lm_sensors
    # Python + pywal + notify
    python python-pywal python-pip python-notify2
    # Shell
    zsh zsh-syntax-highlighting zsh-autosuggestions
)

# Installed only when not already present — avoids redundant work on XFCE4 systems.
XFCE4_PKGS=(
    xfce4-settings xfce4-power-manager xfce4-notifyd
    xfce4-appfinder xfce4-taskmanager xfce4-screenshooter exo
)

install_packages() {
    info "Updating system and installing core packages..."
    sudo pacman -Syu --needed --noconfirm "${CORE_PKGS[@]}"
    ok "Core packages installed."

    if pacman -Qi xfce4-settings &>/dev/null; then
        info "XFCE4 utilities already installed — skipping."
    else
        info "Installing XFCE4 utilities..."
        sudo pacman -S --needed --noconfirm "${XFCE4_PKGS[@]}"
        ok "XFCE4 utilities installed."
    fi
}

# ── Zsh setup ─────────────────────────────────────────────────────────────────
setup_zsh() {
    info "Copying zsh config..."
    cp "$SETUP_DIR/configs/zshrc" "$USER_HOME/.zshrc"
    ok "~/.zshrc installed."

    info "Setting zsh as default shell for $USERNAME..."
    local zsh_path; zsh_path="$(command -v zsh)"
    # Add to /etc/shells if missing
    if ! grep -qxF "$zsh_path" /etc/shells; then
        echo "$zsh_path" | sudo tee -a /etc/shells > /dev/null
    fi
    sudo chsh -s "$zsh_path" "$USERNAME"
    ok "Default shell set to $zsh_path"
}

# ── Python venv for translate.py ──────────────────────────────────────────────
setup_venv() {
    info "Creating Python venv for translate script..."
    local venv="$USER_HOME/scripts/.venv"
    python -m venv "$venv"
    "$venv/bin/pip" install --upgrade pip --quiet
    "$venv/bin/pip" install deep-translator notify2 --quiet
    ok "Python venv ready at $venv"
}

# ── Generate hardware-adapted conky template ──────────────────────────────────
generate_conky() {
    info "Detecting hardware and generating conky template..."
    python3 "$SETUP_DIR/generate_conkyrc.py" "$USER_HOME/.config/wal/all.conkyrc"
    ok "Conky template generated."
}

# ── Copy config files ─────────────────────────────────────────────────────────
copy_configs() {
    info "Copying openbox configs..."
    mkdir -p "$USER_HOME/.config/openbox"
    cp "$SETUP_DIR/configs/openbox/rc.xml"      "$USER_HOME/.config/openbox/rc.xml"
    cp "$SETUP_DIR/configs/openbox/menu.xml"    "$USER_HOME/.config/openbox/menu.xml"
    cp "$SETUP_DIR/configs/openbox/autostart"   "$USER_HOME/.config/openbox/autostart"
    cp "$SETUP_DIR/configs/openbox/environment" "$USER_HOME/.config/openbox/environment"
    chmod +x "$USER_HOME/.config/openbox/autostart"
    ok "Openbox configs copied."

    info "Copying picom config..."
    cp "$SETUP_DIR/configs/picom.conf" "$USER_HOME/.config/picom.conf"
    ok "Picom config copied."

    info "Copying pywal templates..."
    mkdir -p "$USER_HOME/.config/wal/templates"
    # all.conkyrc is generated by generate_conky(), not copied from configs/
    cp "$SETUP_DIR/configs/wal/templates/rofi.rasi"  "$USER_HOME/.config/wal/templates/rofi.rasi"
    cp "$SETUP_DIR/configs/wal/templates/tint2rc"    "$USER_HOME/.config/wal/templates/tint2rc"
    ok "Pywal templates copied."

    info "Creating rofi theme config..."
    mkdir -p "$USER_HOME/.config/rofi"
    echo "@theme \"$USER_HOME/.cache/wal/rofi.rasi\"" > "$USER_HOME/.config/rofi/config.rasi"
    ok "~/.config/rofi/config.rasi written."
}

# ── Install Natura openbox theme ──────────────────────────────────────────────
install_theme() {
    info "Installing Natura openbox theme..."
    sudo mkdir -p /usr/share/themes/Natura/openbox-3
    sudo cp -r "$SETUP_DIR/themes/Natura/openbox-3/." /usr/share/themes/Natura/openbox-3/
    ok "Natura theme installed."
}

# ── Copy personal scripts ─────────────────────────────────────────────────────
copy_scripts() {
    info "Copying scripts to ~/scripts/..."
    mkdir -p "$USER_HOME/scripts"
    cp "$SETUP_DIR/scripts/"* "$USER_HOME/scripts/"
    chmod +x \
        "$USER_HOME/scripts/color_scheme" \
        "$USER_HOME/scripts/rofi" \
        "$USER_HOME/scripts/switch_keyboard" \
        "$USER_HOME/scripts/todo" \
        "$USER_HOME/scripts/reading_mode" \
        "$USER_HOME/scripts/jdate" \
        "$USER_HOME/scripts/cycle-audio.sh" \
        "$USER_HOME/scripts/run_translate.sh" \
        "$USER_HOME/scripts/translate.py"
    ok "Scripts copied."
}

# ── Wallpaper directory ───────────────────────────────────────────────────────
setup_wallpaper_dir() {
    mkdir -p "$USER_HOME/Pictures/wallpaper"
    if [[ -z "$(ls -A "$USER_HOME/Pictures/wallpaper" 2>/dev/null)" ]]; then
        warn "~/Pictures/wallpaper/ is empty."
        warn "Add .jpg/.png wallpapers there, then run: ~/scripts/color_scheme"
    fi
}

# ── Run initial wal to generate color cache ───────────────────────────────────
init_colorscheme() {
    local first_wp
    first_wp=$(find "$USER_HOME/Pictures/wallpaper" -maxdepth 1 \
        \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) \
        -print -quit 2>/dev/null || true)

    if [[ -n "$first_wp" ]]; then
        info "Generating initial color scheme from: $first_wp"
        wal -i "$first_wp" -n
        # Process the hardware-adapted conky template with pywal colors
        python3 - <<'PYEOF'
import json, os
home = os.path.expanduser('~')
src  = f'{home}/.config/wal/all.conkyrc'
dst  = f'{home}/.cache/wal/all.conkyrc'
cjson = f'{home}/.cache/wal/colors.json'
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(src) as f:
    data = f.read()
with open(cjson) as f:
    colors = json.load(f)['colors']
for k, v in colors.items():
    data = data.replace('__' + k, f"'{v}'")
with open(dst, 'w') as f:
    f.write(data)
print("Conky cache written.")
PYEOF
        ok "Initial color scheme applied."
    else
        warn "No wallpapers found — skipping initial color scheme."
        warn "Add images to ~/Pictures/wallpaper/ and run: ~/scripts/color_scheme"
    fi
}

# ── Sensors auto-detect ───────────────────────────────────────────────────────
setup_sensors() {
    info "Running sensors-detect (auto mode)..."
    sudo sensors-detect --auto &>/dev/null || warn "sensors-detect failed (non-fatal)."
}

# ── Enable display manager ────────────────────────────────────────────────────
enable_ly() {
    info "Enabling ly display manager..."
    for dm in gdm lightdm sddm lxdm; do
        if systemctl is-enabled "$dm.service" &>/dev/null; then
            warn "Disabling $dm.service in favour of ly..."
            sudo systemctl disable "$dm.service" || true
        fi
    done
    sudo systemctl enable ly.service
    ok "ly.service enabled."
}

# ── Ensure openbox.desktop session exists ─────────────────────────────────────
ensure_xsession() {
    if [[ ! -f /usr/share/xsessions/openbox.desktop ]]; then
        info "Creating openbox.desktop xsession entry..."
        sudo tee /usr/share/xsessions/openbox.desktop > /dev/null <<'EOF'
[Desktop Entry]
Name=Openbox
Comment=Log in using the Openbox window manager (without a session manager)
Exec=/usr/bin/openbox-session
TryExec=/usr/bin/openbox-session
Icon=openbox
Type=Application
EOF
        ok "openbox.desktop created."
    else
        ok "openbox.desktop already present."
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "════════════════════════════════════════════════"
    echo "  Openbox Environment Setup — Arch Linux"
    echo "════════════════════════════════════════════════"
    echo ""

    install_aur_helper
    install_packages
    setup_zsh
    setup_venv
    copy_configs
    generate_conky       # detects hardware → writes ~/.config/wal/all.conkyrc
    install_theme
    copy_scripts
    setup_wallpaper_dir
    init_colorscheme
    setup_sensors
    ensure_xsession
    enable_ly

    echo ""
    echo "════════════════════════════════════════════════"
    ok "Setup complete!"
    echo "════════════════════════════════════════════════"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Add wallpaper images (.jpg/.png) to ~/Pictures/wallpaper/"
    echo "  2. Reboot — ly will present the login screen"
    echo "  3. Select 'Openbox' session and log in (shell will be zsh)"
    echo "  4. Press  Win+Alt+P  to cycle wallpapers and regenerate the color scheme"
    echo "  5. Press  Ctrl+Space  to open rofi app launcher"
    echo "  6. Press  Win+Return  to open a terminal (sakura)"
    echo ""
    echo -e "${YELLOW}Optional:${NC}"
    echo "  • NVIDIA GPU section in conky requires: sudo pacman -S nvidia-utils"
    echo "  • AMD GPU section uses /sys/class/drm/ — no extra package needed"
    echo "  • Re-run 'python3 ~/scripts/openbox-setup/generate_conkyrc.py' if hardware changes"
    echo "  • Run 'sensors-detect' manually if hardware temps don't appear in conky"
    echo "  • obkey (keybinding GUI) needs python2 to build — skip or install manually from AUR"
    echo ""
}

main
