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
    except urllib.error.HTTPError as e:
        # Si el servidor devuelve 500 pero con JSON, lo parseamos silenciosamente
        err_body = e.read().decode('utf-8', errors='ignore')
        try:
            return json.loads(err_body)
        except json.JSONDecodeError:
            print(f"[{RED}-{NC}] Error HTTP {e.code} en {endpoint}")
            return None
    except urllib.error.URLError as e:
        print(f"[{RED}-{NC}] Error de conexión con la API del Host ({endpoint}): {e}")
        print(f"[{YELLOW}!{NC}] Asegúrate de que vbox_api_server.py se está ejecutando en tu Host físico.")
        return None
    except Exception as e:
        print(f"[{RED}!{NC}] Error inesperado al llamar a la API {endpoint}: {e}")
        return None

def apply_post_install_specs(host_api_url, node):
    """Cambia el orden de arranque a disco y aplica la memoria/cpu final de producción."""
    name = node.get("name")
    specs = node.get("vbox_specs", {})
    print(f"[*] Aplicando orden de arranque y recursos finales a '{name}'...")
    result = _make_api_request(host_api_url, "/vbox/set-boot-order", {
        "vm": name,
        "boot": ["disk", "net", "none", "none"],
        "ram_mb": specs.get("ram_mb", 1024),
        "cpus": specs.get("cpus", 1)
    })
    
    if result and result.get("status") == "ok":
        print(f"[+] Éxito: {result.get('message', 'Orden de arranque y recursos actualizados')}")
        return True
    else:
        print(f"    Puedes cambiarlo manualmente en el Host con:")
        print(f"    VBoxManage modifyvm '{name}' --boot1 disk --boot2 net --memory {specs.get('ram_mb', 1024)}")
        return False


def deploy_virtualbox_vms(nodes, host_api_url, vm_dir=None):
    """Hace una petición a la API del Host para desplegar las VMs con recursos de aprovisionamiento."""
    vms_to_process = [n for n in nodes if n.get('name') != 'jumpstart']
    print(f"[{CYAN}*{NC}] Iniciando despliegue masivo (deploy) de {len(vms_to_process)} VMs a través de la API del Host...")
    
    # Transformando ("masticando") la configuración de los YAMLs
    payload_vms = []
    for node in vms_to_process:
        prov = node.get("provisioning", {})
        specs = node.get("vbox_specs", {})
        networks = node.get("networks", [])
        if networks and node.get("mac"):
            # Añadir la MAC principal a la primera interfaz de red para que vbox_api_server la configure
            networks[0]["mac"] = node.get("mac")

        payload_vms.append({
            "name": node.get("name"),
            "ostype": "Ubuntu_64",
            "cpus": prov.get("cpus", 2),
            "ram_mb": prov.get("ram_mb", 7168),
            "disk_gb": specs.get("disk_gb", 10),
            "vram": 16,
            "graphicscontroller": "vmsvga",
            "networks": networks
        })

    result = _make_api_request(host_api_url, "/vbox/create-vms", {"vms": payload_vms})
    
    if result and result.get("status") == "ok":
        print(f"[{GREEN}✓{NC}] {result.get('message', 'Despliegue completado')}")
        for msg in result.get('details', []):
            print(f"    - {msg}")
    else:
        print(f"[{RED}!{NC}] Fallo en el despliegue.")

def undeploy_virtualbox_vms(nodes, host_api_url):
    """Hace una petición a la API del Host para eliminar todas las VMs."""
    vms_to_process = [{"name": n.get('name')} for n in nodes if n.get('name') != 'jumpstart']
    print(f"[{CYAN}*{NC}] Enviando petición de borrado masivo de {len(vms_to_process)} VMs a la API del Host...")
    
    result = _make_api_request(host_api_url, "/vbox/delete-vms", {"vms": vms_to_process})
    
    if result and result.get("status") == "ok":
        print(f"[{GREEN}✓{NC}] {result.get('message', 'Desinstalación completada')}")
        for msg in result.get('details', []):
            print(f"    - {msg}")
    else:
        print(f"[{RED}!{NC}] Fallo en la desinstalación.")

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
