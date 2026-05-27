import os
import sys
import socket
import time
import json
import subprocess
import urllib.request
import urllib.error

GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
NC = '\033[0m'

def _make_get_request(api_url, path):
    """Realiza una petición GET genérica a la API de VirtualBox."""
    if not api_url:
        return None
    endpoint = f"{api_url}{path}"
    try:
        with urllib.request.urlopen(endpoint, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

def get_existing_vms(host_api_url):
    """Obtiene la lista de VMs registradas en VirtualBox a través de la API."""
    result = _make_get_request(host_api_url, "/vbox/vms")
    if result and result.get("status") == "ok":
        return result.get("vms", [])
    return []

def _make_api_request(api_url, path, payload_dict):
    """Realiza una petición POST genérica a la API de VirtualBox."""
    if not api_url:
        print(f"[-] Error: URL de la API no configurada. No se puede contactar con {path}.")
        return None
        
    endpoint = f"{api_url}{path}"
    payload = json.dumps(payload_dict).encode('utf-8')
    
    req = urllib.request.Request(endpoint, data=payload, method="POST")
    req.add_header('Content-Type', 'application/json')
    req.add_header('Content-Length', len(payload))
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"[-] Error al contactar con la API del Host ({endpoint}): {e}")
        if hasattr(e, 'read'):
            err_body = e.read().decode('utf-8', errors='ignore')
            print(f"    Detalle del servidor: {err_body}")
        print("\n[!] Asegúrate de que vbox_api_server.py se está ejecutando en tu Host físico.")
        return None
    except Exception as e:
        print(f"[!] Error inesperado al llamar a la API {endpoint}: {e}")
        return None

def _change_boot_order(host_api_url, name):
    """Cambia el orden de arranque de una VM para que inicie desde disco."""
    print(f"[*] Cambiando orden de arranque de '{name}' a disco primero...")
    result = _make_api_request(host_api_url, "/vbox/set-boot-order", {
        "vm": name,
        "boot": ["disk", "net", "none", "none"]
    })
    
    if result and result.get("status") == "ok":
        print(f"[+] Éxito: {result.get('message', 'Orden de arranque actualizado')}")
        return True
    else:
        print(f"    Puedes cambiarlo manualmente en el Host con:")
        print(f"    VBoxManage modifyvm '{name}' --boot1 disk --boot2 net")
        return False

def _resolve_playbook_path(node_type, templates_dir):
    """Resuelve la ruta del playbook Ansible correspondiente al tipo de nodo."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    playbooks_dir = os.path.join(repo_root, 'playbooks')

    playbook_path = os.path.join(playbooks_dir, f'{node_type}.yml')
    if not os.path.exists(playbook_path):
        playbook_path = os.path.join(playbooks_dir, 'generic.yml')
        
    return playbook_path

def _wait_for_ssh(node_ip, name, max_wait=600):
    """Espera hasta que el puerto 22 (SSH) del nodo esté disponible."""
    print(f"[*] Esperando a que '{name}' ({node_ip}) responda por SSH tras el reinicio...")
    elapsed = 0
    while elapsed < max_wait:
        try:
            with socket.create_connection((node_ip, 22), timeout=3):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        time.sleep(5)
        elapsed += 5
        
    print(f"[!] Timeout ({max_wait}s) esperando SSH de '{name}'.")
    return False

def _run_ansible_playbook(playbook_path, node_ip, name):
    """Ejecuta el playbook Ansible para configurar un nodo."""
    print(f"[+] SSH de '{name}' disponible. Lanzando Ansible...")
    result = subprocess.run(
        [
            'ansible-playbook', playbook_path,
            '-i', f'{node_ip},',
            '--ssh-extra-args', '-o StrictHostKeyChecking=no'
        ],
        text=True
    )
    if result.returncode == 0:
        print(f"[+] Playbook completado con éxito para '{name}'.")
        return True
    else:
        print(f"[!] El playbook terminó con errores (código {result.returncode}).")
        return False

def finalize_node(name, nodes, host_api_url, tftp_pxe_dir=None, templates_dir=None):
    """
    Finaliza el aprovisionamiento de un nodo tras su instalación.
    """
    node = next((n for n in nodes if n.get('name') == name), None)
    if not node:
        print(f"[-] finalize_node: nodo '{name}' no encontrado en los YAMLs.")
        return False

    node_type = node.get('type', 'generic')
    node_networks = node.get('networks', [])
    node_ip = node_networks[0].get('ip') if node_networks else None

    if not host_api_url:
        print(f"[-] Error: 'host_api_url' no está configurado en el nodo jumpstart.")
        return False

    # 1. Cambiar boot order
    boot_ok = _change_boot_order(host_api_url, name)

    # 2. Resolver Playbook
    playbook_path = _resolve_playbook_path(node_type, templates_dir)
    
    if not node_ip:
        print(f"[!] No se pudo determinar la IP de '{name}'. Saltando Ansible.")
        return boot_ok

    if not os.path.exists(playbook_path):
        print(f"[!] No se encontró playbook en '{playbook_path}'. Saltando Ansible.")
        print(f"    Crea 'playbooks/{node_type}.yml' para automatizar.")
        return boot_ok

    # 3. Esperar SSH
    if not _wait_for_ssh(node_ip, name):
        return boot_ok

    # 4. Ejecutar Ansible
    _run_ansible_playbook(playbook_path, node_ip, name)
    return True

def deploy_virtualbox_vms(nodes, host_api_url, vm_dir=None):
    """Hace una petición a la API del Host para desplegar las VMs."""
    print("[*] Iniciando despliegue (deploy) de la maqueta a través de la API del Host...")
    
    print(f"[*] Enviando especificaciones de {len(nodes)} nodos a la API del Host...")
    result = _make_api_request(host_api_url, "/vbox/deploy", {"nodes": nodes})
    
    if result:
        print(f"[+] Éxito: {result.get('message', 'Despliegue completado')}")
        for msg in result.get('details', []):
            print(f"    - {msg}")

def undeploy_virtualbox_vms(nodes, host_api_url):
    """Hace una petición a la API del Host para eliminar todas las VMs."""
    print("[*] Iniciando desinstalación (undeploy) de la maqueta a través de la API del Host...")
    
    print(f"[*] Enviando petición de borrado a la API del Host...")
    result = _make_api_request(host_api_url, "/vbox/undeploy", {"nodes": nodes})
    
    if result:
        print(f"[+] Éxito: {result.get('message', 'Desinstalación completada')}")
        for msg in result.get('details', []):
            print(f"    - {msg}")

def start_virtualbox_vms(nodes, host_api_url, vm_type="headless"):
    """Inicia las VMs a través de la API del Host."""
    vms_to_process = [n for n in nodes if n.get('name') != 'jumpstart']
    print(f"[{CYAN}*{NC}] Enviando orden de INICIO para {len(vms_to_process)} VMs a través de la API del Host...")
    
    success_count = 0
    error_count = 0
    
    for node in vms_to_process:
        name = node.get('name')
        result = _make_api_request(host_api_url, "/vbox/start", {"vm": name, "type": vm_type})
        if result and result.get("status") == "ok":
            success_count += 1
        else:
            error_count += 1
            
    if success_count > 0:
        print(f"[{GREEN}✓{NC}] {success_count} VMs iniciadas con éxito.")
    if error_count > 0:
        print(f"[{YELLOW}!{NC}] {error_count} VMs no se pudieron iniciar (puede que no existan o ya estén encendidas).")

def stop_virtualbox_vms(nodes, host_api_url, mode="poweroff"):
    """Detiene las VMs a través de la API del Host."""
    vms_to_process = [n for n in nodes if n.get('name') != 'jumpstart']
    print(f"[{CYAN}*{NC}] Enviando orden de PARADA para {len(vms_to_process)} VMs a través de la API del Host...")
    
    success_count = 0
    error_count = 0
    
    for node in vms_to_process:
        name = node.get('name')
        result = _make_api_request(host_api_url, "/vbox/stop", {"vm": name, "mode": mode})
        if result and result.get("status") == "ok":
            success_count += 1
        else:
            error_count += 1
            
    if success_count > 0:
        print(f"[{GREEN}✓{NC}] {success_count} VMs detenidas con éxito.")
    if error_count > 0:
        print(f"[{YELLOW}!{NC}] {error_count} VMs no se pudieron detener (puede que no existan o ya estén apagadas).")
