#!/usr/bin/env python3
"""
Minecraft Backup Manager
- Reads configuration from config.yaml
- Sends warnings to Minecraft server via Docker
- Stops server, backs up world, applies retention policy, restarts server
"""
import os
import sys
import time
import subprocess
import yaml
from datetime import datetime, timedelta

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)

def send_server_command(container, command):
    subprocess.run([
        'docker', 'exec', container, 'rcon-cli', command
    ], check=False)

def send_warnings(container, warnings):
    for i, minutes in enumerate(sorted(warnings, reverse=True)):
        wait_time = (warnings[i-1] - minutes) * 60 if i > 0 else 0
        if wait_time > 0:
            time.sleep(wait_time)
        send_server_command(container, f"say Server backup in {minutes} minute(s)! Please prepare.")
    time.sleep(warnings[-1] * 60)

def stop_server(container):
    send_server_command(container, "say Server is shutting down for backup!")
    send_server_command(container, "stop")
    # Wait for server to stop
    time.sleep(30)

def start_server(container):
    subprocess.run(['docker', 'start', container], check=False)

def backup_world(container, world_path, backup_dir):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"world_backup_{timestamp}.tar.gz"
    backup_path = os.path.join(backup_dir, backup_name)
    os.makedirs(backup_dir, exist_ok=True)
    subprocess.run([
        'docker', 'cp', f"{container}:{world_path}", backup_path
    ], check=True)
    return backup_path

def backup_worlds(container, world_paths, backup_dir):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"worlds_backup_{timestamp}.tar.gz"
    backup_path = os.path.join(backup_dir, backup_name)
    os.makedirs(backup_dir, exist_ok=True)
    temp_dir = os.path.join(backup_dir, f"_tmp_{timestamp}")
    os.makedirs(temp_dir, exist_ok=True)
    # Copy each world directory from the container to temp_dir
    for path in world_paths:
        world_name = os.path.basename(path)
        local_path = os.path.join(temp_dir, world_name)
        subprocess.run([
            'docker', 'cp', f"{container}:{path}", local_path
        ], check=True)
    # Create a tar.gz archive of all worlds
    subprocess.run([
        'tar', '-czf', backup_path, '-C', temp_dir, '.'
    ], check=True)
    # Clean up temp_dir
    for root, dirs, files in os.walk(temp_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(temp_dir)
    return backup_path

def apply_retention_policy(backup_dir, max_backups, max_days):
    backups = sorted([
        os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
        if f.startswith('world_backup_') and f.endswith('.tar.gz')
    ], key=os.path.getmtime, reverse=True)
    # Remove old backups by count
    if max_backups > 0 and len(backups) > max_backups:
        for old in backups[max_backups:]:
            os.remove(old)
    # Remove old backups by age
    if max_days > 0:
        cutoff = datetime.now() - timedelta(days=max_days)
        for b in backups:
            if datetime.fromtimestamp(os.path.getmtime(b)) < cutoff:
                os.remove(b)

def main():
    config = load_config()
    container = config['container_name']
    world_paths = config.get('world_paths')
    backup_dir = config['backup_dir']
    warnings = config['warnings']
    retention = config['retention']
    dev = config.get('dev', False)
    if dev:
        print("[DEV MODE] Testing send_server_command...")
        send_server_command(container, "say This is a test message from the backup manager (dev mode)")
        send_server_command(container, "list")
        print("[DEV MODE] Test commands sent. Exiting.")
        return
    send_warnings(container, warnings)
    stop_server(container)
    backup_path = backup_worlds(container, world_paths, backup_dir)
    apply_retention_policy(backup_dir, retention.get('max_backups', 0), retention.get('max_days', 0))
    start_server(container)
    print(f"Backup complete: {backup_path}")

if __name__ == "__main__":
    main()
