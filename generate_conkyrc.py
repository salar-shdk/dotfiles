#!/usr/bin/env python3
"""
Detects hardware and generates ~/.config/wal/all.conkyrc adapted to this system.
Preserves pywal __colorN placeholders intact for color_scheme to substitute later.
Run: python3 generate_conkyrc.py [output_path]
"""

import os, subprocess, glob, sys

HOME = os.path.expanduser('~')
OUT  = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HOME, '.config/wal/all.conkyrc')


# ── Hardware detection ────────────────────────────────────────────────────────

def run(cmd, default=''):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return default


def detect_cpu():
    n_cores = int(run('nproc', '4'))
    vendor_str = run('grep -m1 "vendor_id" /proc/cpuinfo', '').lower()
    if 'genuineintel' in vendor_str:
        vendor   = 'intel'
        # Package id 0 works for most Intel; fallback covers older/different layouts
        temp_cmd = ("sensors 2>/dev/null | "
                    "awk '/^Package id 0:/{print $4; exit} /^x86_pkg_temp/{f=1} "
                    "f && /^temp1:/{print $2; exit}'")
    else:
        vendor   = 'amd'
        temp_cmd = "sensors 2>/dev/null | awk '/Tctl:/{print $2; exit}'"
    return n_cores, vendor, temp_cmd


def detect_gpu():
    """Return 'nvidia' | 'amd' | 'intel_arc' | 'intel' | 'none'."""
    lspci = run('lspci', '')
    if 'nvidia' in lspci.lower():
        return 'nvidia'
    for line in lspci.splitlines():
        ll = line.lower()
        # Only look at display-class lines
        if not any(t in ll for t in ('vga compatible', '3d controller', 'display controller')):
            continue
        if 'amd' in ll or 'radeon' in ll or 'ati' in ll:
            return 'amd'
        if 'intel' in ll:
            # Distinguish Arc (discrete or integrated branded Arc) from legacy Intel
            if 'arc' in ll or _has_xe_driver():
                return 'intel_arc'
            return 'intel'
    return 'none'


def _has_xe_driver():
    """True if any DRM card is driven by the xe (Intel Arc) kernel driver."""
    for p in glob.glob('/sys/class/drm/card[0-9]*/device/driver'):
        if os.path.islink(p) and os.path.basename(os.readlink(p)) == 'xe':
            return True
    return False


def _intel_drm_info():
    """Return (driver_name, card_name) for the primary Intel GPU."""
    for p in sorted(glob.glob('/sys/class/drm/card[0-9]*/device/driver')):
        if os.path.islink(p):
            drv = os.path.basename(os.readlink(p))
            if drv in ('xe', 'i915'):
                card = os.path.basename(os.path.dirname(os.path.dirname(p)))
                return drv, card
    return 'i915', 'card0'


def _intel_gpu_hwmon():
    """Return path to the hwmon directory for Intel xe/i915 GPU, or None."""
    for p in glob.glob('/sys/class/hwmon/hwmon*/name'):
        name = open(p).read().strip()
        if name.startswith('xe') or name.startswith('i915'):
            return os.path.dirname(p)
    return None


def amd_hwmon_temp_path():
    for p in glob.glob('/sys/class/hwmon/hwmon*/name'):
        name = open(p).read().strip()
        if 'amdgpu' in name or 'radeon' in name:
            return os.path.join(os.path.dirname(p), 'temp1_input')
    return None


def detect_network():
    """Return (iface_name, is_wireless)."""
    out = run('ip -o -4 route show default')
    for line in out.splitlines():
        parts = line.split()
        if 'dev' in parts:
            iface = parts[parts.index('dev') + 1]
            return iface, _is_wireless(iface)
    # fallback: first non-loopback up interface
    for line in run('ip -o link show up').splitlines():
        parts = line.split()
        if len(parts) > 1:
            iface = parts[1].rstrip(':').split('@')[0]
            if iface != 'lo':
                return iface, _is_wireless(iface)
    return 'eth0', False


def _is_wireless(iface):
    """Robust wireless check: sysfs dirs OR predictable name prefix (wl*)."""
    return (
        os.path.isdir(f'/sys/class/net/{iface}/wireless') or
        os.path.isdir(f'/sys/class/net/{iface}/phy80211') or
        iface.startswith('wl')   # wlan0, wlo1, wlp3s0, etc.
    )


def detect_battery():
    bats = sorted(glob.glob('/sys/class/power_supply/BAT*'))
    return os.path.basename(bats[0]) if bats else None


# ── Section builders ──────────────────────────────────────────────────────────

def build_cpu_cores(n_cores):
    lines = ['${color2}CPU Cores:${color}']
    cols, col_w = 4, 60
    for start in range(0, n_cores, cols):
        row = range(start + 1, min(start + cols + 1, n_cores + 1))
        lines.append(''.join(
            '${goto ' + str(col_w * (i + 1)) + '}${cpu cpu' + str(c) + '}%'
            for i, c in enumerate(row)
        ))
    return '\n'.join(lines)


def build_gpu(gpu_type):
    if gpu_type == 'nvidia':
        return (
            '${color5}${font Roboto:size=10}N V I D I A   ${hr 2}${font}${color}\n'
            '${color2}GPU:${color}${alignr}${execi 60 nvidia-smi --query-gpu=name --format=csv,noheader}\n'
            '${color2}Temp:${color}${alignr}${execi 20 nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader}°C\n'
            '${color2}Utilization:${color}${alignr}${execi 20 nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader}\n'
            '${color2}Power:${color}${alignr}${execi 20 nvidia-smi --query-gpu=power.draw --format=csv,noheader}\n'
            '${color2}Memory:${color}${alignr}'
            '${execi 20 nvidia-smi --query-gpu=memory.used --format=csv,noheader}'
            ' / ${execi 60 nvidia-smi --query-gpu=memory.total --format=csv,noheader}'
        )

    elif gpu_type == 'amd':
        temp_path = amd_hwmon_temp_path()
        if temp_path:
            temp_cmd = ("awk '{printf \"%.0f°C\", $1/1000}' "
                        + temp_path + " 2>/dev/null || echo N/A")
        else:
            temp_cmd = ("sensors 2>/dev/null | "
                        "awk '/^amdgpu/,0 {if(/edge:/) {print $2; exit}}'")
        return (
            '${color5}${font Roboto:size=10}A M D   G P U   ${hr 2}${font}${color}\n'
            '${color2}GPU:${color}${alignr}'
            '${execi 60 lspci | grep -iE "vga|3d" | grep -i amd | head -1 | sed "s/.*: //" | cut -c1-35}\n'
            '${color2}Temp:${color}${alignr}${execi 10 ' + temp_cmd + '}\n'
            '${color2}Utilization:${color}${alignr}'
            '${execi 5 cat /sys/class/drm/card0/device/gpu_busy_percent 2>/dev/null || echo N/A}%\n'
            '${color2}VRAM:${color}${alignr}'
            '${execi 10 awk \'{printf "%.0f MiB",$1/1048576}\' /sys/class/drm/card0/device/mem_info_vram_used 2>/dev/null || echo N/A}'
            ' / ${execi 60 awk \'{printf "%.0f MiB",$1/1048576}\' /sys/class/drm/card0/device/mem_info_vram_total 2>/dev/null || echo N/A}'
        )

    elif gpu_type in ('intel_arc', 'intel'):
        drv, card = _intel_drm_info()
        hwmon     = _intel_gpu_hwmon()

        # Frequency paths differ between xe and i915 drivers
        if drv == 'xe':
            freq_cmd = ('cat /sys/class/drm/' + card + '/gt/gt0/freq0/cur_freq'
                        ' 2>/dev/null || echo N/A')
            fmax_cmd = ('cat /sys/class/drm/' + card + '/gt/gt0/freq0/max_freq'
                        ' 2>/dev/null || echo N/A')
        else:
            freq_cmd = ('cat /sys/class/drm/' + card + '/gt_cur_freq_mhz'
                        ' 2>/dev/null || echo N/A')
            fmax_cmd = ('cat /sys/class/drm/' + card + '/gt_max_freq_mhz'
                        ' 2>/dev/null || echo N/A')

        # Temperature: prefer direct hwmon file, fall back to sensors parsing
        if hwmon:
            temp_input = os.path.join(hwmon, 'temp1_input')
            temp_cmd = ("awk '{printf \"%.0f°C\", $1/1000}' "
                        + temp_input + " 2>/dev/null || echo N/A")
        else:
            temp_cmd = ("sensors 2>/dev/null | "
                        "awk '/^xe-pci|^i915-pci/{f=1} f && /^temp1:/{print $2; exit}'")

        title = 'I N T E L   A R C' if gpu_type == 'intel_arc' else 'I N T E L   G P U'
        return (
            '${color5}${font Roboto:size=10}' + title + '   ${hr 2}${font}${color}\n'
            '${color2}GPU:${color}${alignr}'
            '${execi 60 lspci | grep -iE "vga|display|3d" | grep -i intel | tail -1 | sed "s/.*: //" | cut -c1-35}\n'
            '${color2}Temp:${color}${alignr}${execi 10 ' + temp_cmd + '}\n'
            '${color2}Freq:${color}${alignr}${execi 5 ' + freq_cmd + '} MHz\n'
            '${color2}Max Freq:${color}${alignr}${execi 60 ' + fmax_cmd + '} MHz'
        )

    return ''  # no discrete GPU


def build_network(iface, is_wifi):
    header = '${color5}${font Roboto:size=10}N E T W O R K   ${hr 2}${font}${color}\n'
    common = (
        '${color2}Local IP:${color}${alignr}${addr ' + iface + '}\n'
        '${color2}External IP:${color}${alignr}'
        '${execi 600 curl -s https://api.ipify.org 2>/dev/null || echo "---"}\n'
        '${color2}Ping (8.8.8.8):${color}${alignr}'
        "${execi 10 ping -c 1 -W 1 8.8.8.8 2>/dev/null | grep 'time=' | cut -d'=' -f4 | cut -d' ' -f1 || echo '---'} ms\n"
        '${color2}Speed:${color} ${upspeedf ' + iface + '} kb/s ↑'
        '${alignr}${downspeedf ' + iface + '} kb/s ↓\n'
        '${color}${upspeedgraph ' + iface + ' 25,140 303030 4679cc}'
        '${alignr}${downspeedgraph ' + iface + ' 25,140 303030 d95468}\n'
        '${color2}Today:${color} ${totalup ' + iface + '} ↑${alignr}${totaldown ' + iface + '} ↓'
    )
    if is_wifi:
        wifi_lines = (
            '${color2}Status:${color}${alignr}'
            '${if_up ' + iface + '}${color7}Connected${else}${color9}Disconnected${endif}\n'
            '${color2}Signal:${color}${alignr}'
            '${wireless_link_qual_perc ' + iface + '}% '
            '${if_match ${wireless_link_qual_perc ' + iface + '} > 80}${color7}✓'
            '${else}${if_match ${wireless_link_qual_perc ' + iface + '} > 40}${color8}~'
            '${else}${color9}✗${endif}${endif}\n'
            '${color2}SSID:${color}${alignr}${wireless_essid ' + iface + '}\n'
        )
        return header + wifi_lines + common
    else:
        wired_line = (
            '${color2}Status:${color}${alignr}'
            '${if_up ' + iface + '}${color7}Connected${else}${color9}Disconnected${endif}\n'
        )
        return header + wired_line + common


def build_battery(bat):
    if not bat:
        return ''
    power_path = f'/sys/class/power_supply/{bat}/power_now'
    if os.path.exists(power_path):
        power_cmd = ("awk '{printf \"%.1f W\", $1/1000000}' "
                     "/sys/class/power_supply/" + bat + "/power_now")
    else:
        # current_now (µA) × voltage_now (µV) ÷ 10^12 = W
        power_cmd = (
            "awk 'NR==1{c=$1} NR==2{printf \"%.1f W\", c*$1/1e12}' "
            "/sys/class/power_supply/" + bat + "/current_now "
            "/sys/class/power_supply/" + bat + "/voltage_now 2>/dev/null || echo N/A"
        )
    return (
        '${color2}Battery:${color}${alignr}${battery_percent ' + bat + '}%\n'
        '${color2}Power draw:${color}${alignr}${execi 5 ' + power_cmd + '}'
    )


# ── Full template ─────────────────────────────────────────────────────────────

TEMPLATE = """\
--[[

]]

conky.config = {

\t--Various settings

\tbackground = true,
\tcpu_avg_samples = 2,
\tdiskio_avg_samples = 10,
\tdouble_buffer = true,
\tif_up_strictness = 'address',
\tnet_avg_samples = 2,
\tno_buffers = true,
\ttemperature_unit = 'celsius',
\ttext_buffer_size = 2048,
\tupdate_interval = 1,
\timlib_cache_size = 0,


\t--Placement

\talignment = 'middle_right',
\tgap_x = 15,
\tgap_y = 0,
\tminimum_height = 600,
\tminimum_width = 300,
\tmaximum_width = 300,

\t--Graphical

\tborder_inner_margin = 10,
\tborder_outer_margin = 5,
\tborder_width = 0,
\tdefault_bar_width = 80,
\tdefault_bar_height = 10,
\tdefault_gauge_height = 25,
\tdefault_gauge_width =40,
\tdefault_graph_height = 40,
\tdefault_graph_width = 0,
\tdefault_shade_color = {color0},
\tdefault_outline_color = {color0},
\tdraw_borders = false,
\tdraw_graph_borders = true,
\tdraw_shades = false,
\tdraw_outline = false,
\tstippled_borders = 0,

\t--Textual

\textra_newline = false,
\tformat_human_readable = true,
\tfont = 'Roboto Mono:size=10',
\tmax_text_width = 0,
\tmax_user_text = 16384,
\toverride_utf8_locale = true,
\tshort_units = true,
\ttop_name_width = 21,
\ttop_name_verbose = false,
\tuppercase = false,
\tuse_spacer = 'none',
\tuse_xft = true,
\txftalpha = 1,

\t--Windows

\town_window = true,
\town_window_argb_value = 100,
\town_window_argb_visual = true,
\town_window_class = 'Conky',
\town_window_colour = {color0},
\town_window_hints = 'undecorated,below,above,sticky,skip_taskbar,skip_pager',
\town_window_transparent = false,
\town_window_title = 'system_conky',
\town_window_type = 'desktop',


\t--Colours

\tdefault_color = __color8,
\tcolor1 = __color3,
\tcolor2 = __color4,
\tcolor3 = __color5,
\tcolor4 = __color1,
\tcolor5 = __color2,
\tcolor6 = __color8,

\t--Signal Colours
\tcolor7 = __color5,\t\t\t\t\t\t--green
\tcolor8 = __color4,\t\t\t\t\t\t--orange
\tcolor9 = __color1,\t\t\t\t\t\t--firebrick

};

conky.text = [[
${color6}${voffset 4}${font Roboto:size=36}${alignc}${time %H}:${time %M}${font}${color}
${color6}${voffset 4}${font Roboto:size=12}${alignc}${time %A} ${time %B} ${time %e}, ${time %Y}${font}${color}

${color5}${font Roboto:size=10}S Y S T E M   ${hr 2}${font}${color}
${color2}Kernel:${color}${alignr}${exec uname} ${exec uname -r}
${color2}Uptime:${color} ${alignr}${uptime}
${color2}SSD:${color}${alignr}${fs_used /} | ${fs_size /}
${color2}SSD Temp:${color}${alignr}${execi 30 sensors 2>/dev/null | awk '/Composite:/{print $2; exit}'}
${color2}Motherboard Temp:${color}${alignr}${execi 30 sensors 2>/dev/null | awk '/temp1:/ && NR>5 {print $2; exit}'}
@@BATTERY@@
${color5}${font Roboto:size=10}P R O C E S S O R S  ${hr 2}${font}${color}
${color2}CPU Freq:${color} ${alignr}${freq}MHz
${color2}CPU Temp:${color}${alignr}${execi 10 @@CPU_TEMP@@}
@@CPU_CORES@@
${color2}Top Processes${alignr}cpu${color}
${voffset 4}     1  -  ${top name 1}${alignr}${top cpu 1}%
${voffset 4}     2  -  ${top name 2}${alignr}${top cpu 2}%
${voffset 4}     3  -  ${top name 3}${alignr}${top cpu 3}%
${voffset 4}     4  -  ${top name 4}${alignr}${top cpu 4}%
${voffset 4}     5  -  ${top name 5}${alignr}${top cpu 5}%

@@GPU@@

${color5}${font Roboto:size=10}M E M O R Y   ${hr 2}${font}${color}
${color2}RAM: ${color}${alignr}${mem} / ${memmax}
${color2}Swap:${color} ${alignr}${swap} / ${swapmax}
${color2}Top Processes${alignr}mem${color}
${voffset 4}     1  -  ${top_mem name 1}${alignr} ${top_mem mem_res 1}
${voffset 4}     2  -  ${top_mem name 2}${alignr} ${top_mem mem_res 2}
${voffset 4}     3  -  ${top_mem name 3}${alignr} ${top_mem mem_res 3}
${voffset 4}     4  -  ${top_mem name 4}${alignr} ${top_mem mem_res 4}
${voffset 4}     5  -  ${top_mem name 5}${alignr} ${top_mem mem_res 5}

@@NETWORK@@

${color5}${color5}${font Roboto:size=10}N O T E   ${hr 2}${font}${color}
I waste my time whenever I like
]];
"""


def main():
    n_cores, cpu_vendor, cpu_temp_cmd = detect_cpu()
    gpu_type        = detect_gpu()
    iface, is_wifi  = detect_network()
    bat             = detect_battery()

    out = TEMPLATE
    out = out.replace('@@CPU_TEMP@@',  cpu_temp_cmd)
    out = out.replace('@@CPU_CORES@@', build_cpu_cores(n_cores))
    out = out.replace('@@GPU@@',       build_gpu(gpu_type))
    out = out.replace('@@NETWORK@@',   build_network(iface, is_wifi))
    bat_content = build_battery(bat)
    out = out.replace('@@BATTERY@@', (bat_content + '\n') if bat_content else '')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        f.write(out)

    print(f"Generated: {OUT}")
    print(f"  CPU : {n_cores} cores ({cpu_vendor})")
    print(f"  GPU : {gpu_type}" + (" [xe driver]" if _has_xe_driver() else ""))
    print(f"  Net : {iface} ({'wifi' if is_wifi else 'ethernet'})")
    print(f"  Bat : {bat or 'none'}")


if __name__ == '__main__':
    main()
