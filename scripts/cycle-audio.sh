#!/bin/bash

if [[ "$1" != "audio" && "$1" != "mic" ]]; then
    echo "Usage: $0 [audio|mic]"
    exit 1
fi

if [[ "$1" == "audio" ]]; then
    target_class="Audio/Sink"
    config_key="Audio/Sink"
    notify_prefix="Audio Output"
else
    target_class="Audio/Source"
    config_key="Audio/Source"
    notify_prefix="Mic Input"
fi

# Get all IDs in one stable snapshot
all_ids=$(wpctl status | grep -P '^\s+[│]\s+' | grep -oP '^\s+[│]\s+[\*\s]*\K\d+(?=\.)')

# Get current default node.name from Settings
current_node_name=$(wpctl status | grep -A10 "Default Configured" | grep "$config_key" | grep -oP 'alsa\S+')

# Find all nodes matching target class
nodes=()
current_id=""

while IFS= read -r id; do
    inspect=$(wpctl inspect "$id" 2>/dev/null)
    class=$(echo "$inspect" | grep '^\s*\* media\.class' | grep -oP '(?<= = ").*(?=")')
    if [[ "$class" == "$target_class" ]]; then
        nodes+=("$id")
        node_name=$(echo "$inspect" | grep '^\s*\* node\.name' | grep -oP '(?<= = ").*(?=")')
        if [[ "$node_name" == "$current_node_name" ]]; then
            current_id="$id"
        fi
    fi
done <<< "$all_ids"

echo "nodes: ${nodes[@]}"
echo "current_id: $current_id"

idx=0
for i in "${!nodes[@]}"; do [[ "${nodes[$i]}" == "$current_id" ]] && idx=$i; done

count=${#nodes[@]}
next="${nodes[$(( (idx + 1) % count ))]}"
wpctl set-default "$next"
device_name=$(wpctl inspect "$next" 2>/dev/null | grep '^\s*\* node\.description' | grep -oP '(?<= = ").*(?=")')
notify-send "$notify_prefix" "$device_name"
echo "$notify_prefix → $device_name"
