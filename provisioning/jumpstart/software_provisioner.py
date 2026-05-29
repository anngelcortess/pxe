import os
import socket
import time
import subprocess

CYAN = '\033[96m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
NC = '\033[0m'

def resolve_playbook_path(node_type):
    """Resuelve la ruta del playbook Ansible correspondiente al tipo de nodo."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(script_dir))
    playbooks_dir = os.path.join(repo_root, 'ansible', 'playbooks')

    playbook_path = os.path.join(playbooks_dir, f'{node_type}.yml')
    if not os.path.exists(playbook_path):
        playbook_path = os.path.join(playbooks_dir, 'generic.yml')
        
    return playbook_path

def wait_for_ssh(node_ip, name, max_wait=600):
    """Espera hasta que el puerto 22 (SSH) del nodo esté disponible."""
    print(f"[{CYAN}*{NC}] Esperando a que '{name}' ({node_ip}) responda por SSH...")
    elapsed = 0
    while elapsed < max_wait:
        try:
            with socket.create_connection((node_ip, 22), timeout=3):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        time.sleep(5)
        elapsed += 5
        
    print(f"[{RED}!{NC}] Timeout ({max_wait}s) esperando SSH de '{name}'.")
    return False

def run_ansible_playbook(playbook_path, node_ip, name):
    """Ejecuta el playbook Ansible para configurar un nodo."""
    print(f"[{GREEN}+{NC}] SSH de '{name}' disponible. Lanzando Ansible ({playbook_path})...")
    result = subprocess.run(
        [
            'ansible-playbook', playbook_path,
            '-i', f'{node_ip},',
            '--ssh-extra-args', '-o StrictHostKeyChecking=no'
        ],
        text=True
    )
    if result.returncode == 0:
        print(f"[{GREEN}+{NC}] Playbook completado con éxito para '{name}'.")
        return True
    else:
        print(f"[{RED}!{NC}] El playbook terminó con errores (código {result.returncode}).")
        return False

def provision_all_nodes(nodes_list):
    """
    Ejecuta Ansible de forma secuencial para la lista final de nodos desplegados.
    (En la Fase 2 esto podrá evolucionar a una ejecución masiva con inventario).
    """
    print(f"[{CYAN}*{NC}] Fase final: Ejecutando Ansible para {len(nodes_list)} nodos...")
    for node in nodes_list:
        name = node.get('name')
        node_type = node.get('type', 'generic')
        node_networks = node.get('networks', [])
        node_ip = node_networks[0].get('ip') if node_networks else None

        if not node_ip:
            print(f"[{YELLOW}!{NC}] IP no encontrada para {name}. Saltando.")
            continue

        playbook_path = resolve_playbook_path(node_type)
        if wait_for_ssh(node_ip, name):
            run_ansible_playbook(playbook_path, node_ip, name)
