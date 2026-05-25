#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import re

# Intentar importar PyYAML. Si no está instalado, se usa un parser YAML básico fallback para evitar fallos de dependencias.
try:
    import yaml
except ImportError:
    yaml = None

def parse_simple_yaml(filepath):
    """
    Parser fallback muy simple para ficheros YAML básicos de definición de nodos.
    Soporta pares clave-valor y listas indentadas de un nivel.
    """
    data = {}
    current_key = None
    current_list = None
    current_map_in_list = None

    with open(filepath, 'r') as f:
        for line in f:
            line_raw = line.split('#')[0] # Eliminar comentarios
            if not line_raw.strip():
                continue
            
            # Detectar indentación
            indent = len(line_raw) - len(line_raw.lstrip())
            line_stripped = line_raw.strip()

            if line_stripped.startswith('-'):
                # Es un elemento de lista
                item_content = line_stripped[1:].strip()
                if current_list is not None:
                    if ':' in item_content:
                        # Lista de mapas (ej. interfaces)
                        if indent > 2:
                            # Continuación de mapa en lista
                            key, val = item_content.split(':', 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if val.startswith('[') and val.endswith(']'):
                                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                            if current_map_in_list is not None:
                                current_map_in_list[key] = val
                        else:
                            # Nuevo elemento de mapa en lista
                            key, val = item_content.split(':', 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if val.startswith('[') and val.endswith(']'):
                                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                            current_map_in_list = {key: val}
                            current_list.append(current_map_in_list)
                    else:
                        # Lista simple
                        item_content = item_content.strip('"').strip("'")
                        current_list.append(item_content)
                continue

            if ':' in line_stripped:
                key, val = line_stripped.split(':', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if not val: # Inicio de un bloque (mapa o lista)
                    current_key = key
                    current_list = []
                    data[current_key] = current_list
                    current_map_in_list = None
                else:
                    if val.startswith('[') and val.endswith(']'): # Lista inline ej [8.8.8.8, 8.8.4.4]
                        val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                    elif val.lower() == 'true':
                        val = True
                    elif val.lower() == 'false':
                        val = False
                    else:
                        try:
                            val = int(val)
                        except ValueError:
                            pass
                    
                    if indent > 0 and current_map_in_list is not None:
                        current_map_in_list[key] = val
                    else:
                        data[key] = val
                        current_list = None
                        current_key = None

    # Limpieza de listas vacías si resultaron ser mapas simples
    for k in list(data.keys()):
        if isinstance(data[k], list) and len(data[k]) == 0:
            # Re-analizar si era un mapa indentado en vez de lista
            pass
    return data

def load_node_file(filepath):
    """Carga y procesa un archivo YAML de nodo, usando PyYAML o el parser de fallback."""
    if yaml:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    else:
        return parse_simple_yaml(filepath)

def load_all_nodes(nodes_dir):
    """Carga todos los nodos del directorio especificado."""
    nodes = []
    if not os.path.isdir(nodes_dir):
        print(f"[-] Error: El directorio {nodes_dir} no existe.")
        return nodes
    
    for filename in sorted(os.listdir(nodes_dir)):
        if filename.endswith('.yml') or filename.endswith('.yaml'):
            filepath = os.path.join(nodes_dir, filename)
            try:
                node_data = load_node_file(filepath)
                if node_data and 'name' in node_data:
                    nodes.append(node_data)
            except Exception as e:
                print(f"[-] Error al parsear {filename}: {e}")
    return nodes

def load_networks_file(filepath):
    """Carga la definición de redes desde networks.yml. Retorna una lista de redes."""
    if not os.path.exists(filepath):
        # Fallback por defecto si no existe el archivo
        return [
            {
                "name": "intnet_main",
                "subnet": "192.168.1.0",
                "netmask": "255.255.255.0",
                "gateway": "192.168.1.254",
                "dns": ["8.8.8.8", "8.8.4.4"],
                "dhcp_range": {"start": "192.168.1.150", "end": "192.168.1.200"}
            },
            {
                "name": "intnet_internal",
                "subnet": "192.168.2.0",
                "netmask": "255.255.255.0",
                "gateway": "192.168.2.254",
                "dns": ["8.8.8.8", "8.8.4.4"],
                "dhcp_range": {"start": "192.168.2.150", "end": "192.168.2.200"}
            }
        ]
        
    try:
        data = load_node_file(filepath) # load_node_file ya procesa YAML con fallback simple
        if data and 'networks' in data:
            return data['networks']
    except Exception as e:
        print(f"[-] Advertencia al parsear redes en {filepath}: {e}. Usando valores por defecto.")
    
    # Fallback si falla
    return [
        {
            "name": "intnet_main",
            "subnet": "192.168.1.0",
            "netmask": "255.255.255.0",
            "gateway": "192.168.1.254",
            "dns": ["8.8.8.8", "8.8.4.4"],
            "dhcp_range": {"start": "192.168.1.150", "end": "192.168.1.200"}
        },
        {
            "name": "intnet_internal",
            "subnet": "192.168.2.0",
            "netmask": "255.255.255.0",
            "gateway": "192.168.2.254",
            "dns": ["8.8.8.8", "8.8.4.4"],
            "dhcp_range": {"start": "192.168.2.150", "end": "192.168.2.200"}
        }
    ]

# ----------------- VALIDACIÓN -----------------

def validate_nodes(nodes):
    """Valida la consistencia de todas las definiciones de nodos."""
    print("[*] Iniciando validación de consistencia de la maqueta...")
    errors = 0
    warnings = 0
    
    ips = {}
    macs = {}
    names = set()
    
    for node in nodes:
        name = node.get('name')
        if not name:
            print("[-] Error: Nodo sin nombre definido en archivo.")
            errors += 1
            continue
            
        if name in names:
            print(f"[-] Error: Nombre duplicado '{name}'.")
            errors += 1
        names.add(name)
        
        # Validar MAC
        mac = node.get('mac')
        if mac:
            mac_clean = mac.lower().replace('-', ':')
            if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac_clean):
                print(f"[-] Error [{name}]: Formato de MAC '{mac}' inválido.")
                errors += 1
            if mac_clean in macs:
                print(f"[-] Error [{name}]: Dirección MAC duplicada '{mac}' con '{macs[mac_clean]}'.")
                errors += 1
            macs[mac_clean] = name
            
        # Validar Redes e IPs
        networks = node.get('networks', [])
        if not networks:
            print(f"[!] Warning [{name}]: El nodo no tiene redes definidas.")
            warnings += 1
            
        for i, net in enumerate(networks):
            net_name = net.get('name')
            ip = net.get('ip')
            
            if not net_name:
                print(f"[-] Error [{name}]: Red #{i} sin nombre ('name').")
                errors += 1
                
            if ip:
                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    print(f"[-] Error [{name}]: IP '{ip}' inválida.")
                    errors += 1
                
                ip_key = f"{net_name}/{ip}"
                if ip_key in ips:
                    print(f"[-] Error [{name}]: Conflicto de IP. '{ip}' ya asignada en la red '{net_name}' para el nodo '{ips[ip_key]}'.")
                    errors += 1
                ips[ip_key] = name

        # Validar especificaciones VirtualBox
        specs = node.get('vbox_specs', {})
        if not specs:
            print(f"[!] Warning [{name}]: Sin especificaciones de hardware vbox_specs.")
            warnings += 1
            
    print(f"\n[*] Validación finalizada: {errors} errores, {warnings} advertencias.")
    return errors == 0

# ----------------- VIRTUALBOX -----------------

def run_vbox_cmd(cmd, cwd=None):
    """Ejecuta un comando de VBoxManage y devuelve el resultado."""
    print(f"    Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    if result.returncode != 0:
        print(f"    [-] Error en comando: {result.stderr.strip()}")
        return False
    return True


def finalize_node(name, nodes, tftp_pxe_dir=None, templates_dir=None):
    """
    Finaliza el aprovisionamiento de un nodo tras su instalación:
      1. Sobreescribe su fichero PXE (por MAC) con LOCALBOOT 0 para que en el
         siguiente arranque PXE el jumpstart lo redirija al disco local.
      2. Ejecuta el playbook Ansible correspondiente al tipo de nodo.

    Esta función se invoca desde provision_callback.py (servidor HTTP del jumpstart)
    cuando el nodo llama a /node-ready al terminar su autoinstall.
    """
    # Localizar el nodo en la lista
    node = next((n for n in nodes if n.get('name') == name), None)
    if not node:
        print(f"[-] finalize_node: nodo '{name}' no encontrado en los YAMLs.")
        return False

    mac = node.get('mac')
    if not mac:
        print(f"[-] finalize_node: el nodo '{name}' no tiene MAC definida.")
        return False

    node_type = node.get('type', 'generic')
    node_networks = node.get('networks', [])
    node_ip = node_networks[0].get('ip') if node_networks else None

    # Determinar directorio TFTP
    if tftp_pxe_dir is None:
        is_live = os.path.exists('/srv/tftp')
        if is_live:
            tftp_pxe_dir = '/srv/tftp/pxelinux.cfg'
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            tftp_pxe_dir = os.path.join(script_dir, 'baremetal', 'pxe', 'pxelinux.cfg')

    os.makedirs(tftp_pxe_dir, exist_ok=True)

    # 1. Escribir LOCALBOOT en el fichero PXE de esta MAC
    mac_formatted = '01-' + mac.lower().replace(':', '-')
    pxe_file_path = os.path.join(tftp_pxe_dir, mac_formatted)
    localboot_content = f"""# Nodo '{name}' — instalación completada. Arranca desde disco local.
DEFAULT local
LABEL local
  LOCALBOOT 0
"""
    with open(pxe_file_path, 'w') as f:
        f.write(localboot_content)
    print(f"[+] finalize_node: PXE de '{name}' ({mac_formatted}) actualizado a LOCALBOOT 0.")
    print(f"    El nodo arrancará desde disco en el próximo boot PXE.")

    # 2. Ejecutar playbook Ansible
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if templates_dir is None:
        playbooks_dir = os.path.join(script_dir, 'playbooks')
    else:
        playbooks_dir = os.path.join(os.path.dirname(templates_dir), '..', 'playbooks')
        playbooks_dir = os.path.normpath(playbooks_dir)

    playbook_path = os.path.join(playbooks_dir, f'{node_type}.yml')
    if not os.path.exists(playbook_path):
        # Fallback: playbook genérico
        playbook_path = os.path.join(playbooks_dir, 'generic.yml')

    if node_ip and os.path.exists(playbook_path):
        # --- NUEVO: Esperar a que el nodo esté arriba (reinicio completado) ---
        import socket, time
        print(f"[*] finalize_node: esperando a que el nodo '{name}' (IP: {node_ip}) responda por SSH...")
        max_wait = 600  # 10 minutos máximo de espera
        elapsed = 0
        ready = False
        while elapsed < max_wait:
            try:
                with socket.create_connection((node_ip, 22), timeout=3):
                    ready = True
                    break
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
            time.sleep(5)
            elapsed += 5
            
        if not ready:
            print(f"[!] finalize_node: timeout esperando a SSH en '{name}'. Saltando Ansible.")
            return False
            
        print(f"[+] finalize_node: SSH de '{name}' detectado. Ejecutando playbook Ansible '{playbook_path}'...")
        result = subprocess.run(
            ['ansible-playbook', playbook_path, '-i', f'{node_ip},', '--ssh-extra-args', '-o StrictHostKeyChecking=no'],
            text=True
        )
        if result.returncode == 0:
            print(f"[+] finalize_node: playbook completado con éxito para '{name}'.")
        else:
            print(f"[!] finalize_node: el playbook terminó con errores (código {result.returncode}). Revisa la salida de Ansible.")
    elif not os.path.exists(playbook_path):
        print(f"[!] finalize_node: no se encontró playbook en '{playbook_path}'. Saltando Ansible.")
        print(f"    Crea 'playbooks/{node_type}.yml' o 'playbooks/generic.yml' para automatizar la configuración post-instalación.")
    else:
        print(f"[!] finalize_node: no se pudo determinar la IP de '{name}'. Saltando Ansible.")

    return True


def deploy_virtualbox_vms(nodes, vm_dir="/home/Chadry/VirtualBox VMs"):
    """Crea las máquinas virtuales en VirtualBox a partir de las especificaciones YAML (limpiando previas)."""
    print("[*] Iniciando despliegue (deploy) de la maqueta en VirtualBox...")
    
    # 1. Comprobar VMs registradas y en ejecución en VirtualBox
    print("[*] Comprobando estado de las VMs en VirtualBox...")
    vms_list_proc = subprocess.run(["VBoxManage", "list", "vms"], stdout=subprocess.PIPE, text=True)
    existing_vms = []
    for line in vms_list_proc.stdout.splitlines():
        match = re.match(r'^"([^"]+)"', line)
        if match:
            existing_vms.append(match.group(1))
            
    running_vms_proc = subprocess.run(["VBoxManage", "list", "runningvms"], stdout=subprocess.PIPE, text=True)
    running_vms = []
    for line in running_vms_proc.stdout.splitlines():
        match = re.match(r'^"([^"]+)"', line)
        if match:
            running_vms.append(match.group(1))
            
    # 2. Control inteligente y encendido automático de Jumpstart
    # Buscar el nodo jumpstart en la lista para leer su host_only_ip
    jumpstart_node = next((n for n in nodes if n.get('name') == 'jumpstart'), {})
    jumpstart_host_ip = jumpstart_node.get('host_only_ip', '').strip()

    if "jumpstart" not in running_vms:
        if "jumpstart" in existing_vms:
            print("[!] El servidor de aprovisionamiento 'jumpstart' está apagado.")
            print("[*] Encendiendo 'jumpstart' automáticamente en segundo plano (headless)...")
            subprocess.run(["VBoxManage", "startvm", "jumpstart", "--type", "headless"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            import time, socket

            if jumpstart_host_ip:
                # --- Sondeo activo: esperar hasta que Apache (puerto 80) responda ---
                max_wait = 120  # Timeout máximo en segundos
                poll_interval = 2
                elapsed = 0
                print(f"[*] Sondeo activo: esperando a que los servicios PXE del 'jumpstart' ({jumpstart_host_ip}) respondan...")
                print(f"    (Timeout máximo: {max_wait} segundos)")
                ready = False
                while elapsed < max_wait:
                    sys.stdout.write(f"\r    [ {elapsed}s ] Comprobando puerto 80 (Apache) en {jumpstart_host_ip}...")
                    sys.stdout.flush()
                    try:
                        with socket.create_connection((jumpstart_host_ip, 80), timeout=2):
                            ready = True
                            break
                    except (socket.timeout, ConnectionRefusedError, OSError):
                        pass
                    time.sleep(poll_interval)
                    elapsed += poll_interval

                if ready:
                    print(f"\r    [+] ¡Servicios PXE del 'jumpstart' detectados y activos! ({elapsed}s)      ")
                else:
                    print(f"\r    [!] Timeout: el jumpstart no respondió en {max_wait}s. Continuando igualmente...")
            else:
                # --- Fallback: espera fija si no hay IP Host-Only configurada ---
                wait_time = 25
                print(f"[*] Esperando {wait_time} segundos (espera fija). Para activar la espera inteligente,")
                print(f"    añade la IP Host-Only del jumpstart al campo 'host_only_ip' en baremetal/nodes/jumpstart.yml")
                for i in range(wait_time, 0, -1):
                    sys.stdout.write(f"\r    [ {i} segundos restantes... ] ")
                    sys.stdout.flush()
                    time.sleep(1)
                print("\r    [+] 'jumpstart' encendido. Continuando el despliegue...              \n")
        else:
            print("\n[-] ERROR DE CONFIGURACIÓN BÁSICA:")
            print("    La máquina virtual 'jumpstart' no está creada ni registrada en VirtualBox.")
            print("    El Jumpstart es la máquina manual que aprovisiona el resto de tu clúster.")
            print("    Por favor, crea la VM 'jumpstart' manualmente en VirtualBox (con sus 3 adaptadores de red) antes de desplegar.")
            print("    Abortando despliegue.\n")
            sys.exit(1)
    else:
        print("[+] El servidor 'jumpstart' ya está en ejecución. Procediendo directamente al despliegue.")

    for node in nodes:
        name = node.get('name')
        if name == 'jumpstart':
            # Jumpstart se gestiona de forma manual y no se creará por este script
            print(f"[*] El nodo '{name}' (Jumpstart) es el servidor de aprovisionamiento manual. Saltando su creación en VirtualBox.")
            continue
            
        if name in existing_vms:
            print(f"[!] La máquina '{name}' ya existe en VirtualBox. Eliminándola para realizar un despliegue limpio desde cero...")
            # 1. Intentar apagarla por si estuviera encendida
            subprocess.run(["VBoxManage", "controlvm", name, "poweroff"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # 2. Desregistrar y borrar
            run_vbox_cmd(["VBoxManage", "unregistervm", name, "--delete"])
            
        specs = node.get('vbox_specs', {})
        cpus = specs.get('cpus', 1)
        ram = specs.get('ram_mb', 1024)
        disk_size_gb = specs.get('disk_gb', 20)
        
        print(f"\n[+] Creando VM: {name} ({cpus} CPUs, {ram}MB RAM, {disk_size_gb}GB Disco)")
        
        # 1. Crear VM
        cmd_create = ["VBoxManage", "createvm", "--name", name, "--ostype", "Ubuntu_64", "--register"]
        if not run_vbox_cmd(cmd_create):
            continue
            
        # 2. Configurar hardware básico
        cmd_modify = [
            "VBoxManage", "modifyvm", name,
            "--cpus", str(cpus),
            "--memory", str(ram),
            "--boot1", "net",   # Primero Red (PXE)
            "--boot2", "disk",  # Segundo Disco Duro
            "--boot3", "none",
            "--boot4", "none",
            "--vram", "16",
            "--graphicscontroller", "vmsvga"
        ]
        
        # Configurar adaptadores de red en orden
        networks = node.get('networks', [])
        for idx, net in enumerate(networks, start=1):
            net_name = net.get('name')
            net_type = net.get('type', 'intnet') # por defecto red interna
            mac = node.get('mac') if idx == 1 else None # la mac principal va en el primer adaptador
            
            # Para jumpstart u otros nodos con múltiples interfaces
            if name == 'jumpstart':
                # Jumpstart tiene una MAC específica por interfaz definida en el YAML o lógica
                if net_name == 'NAT':
                    net_type = 'nat'
                # Las MACs para Jumpstart las obtenemos de su propio registro si se especifican
                
            cmd_modify += [f"--nic{idx}", net_type]
            if net_type == 'intnet':
                cmd_modify += [f"--intnet{idx}", net_name]
                
            # Asociar MAC estática si está definida para este nodo
            if idx == 1 and mac:
                mac_clean = mac.replace(':', '').replace('-', '')
                cmd_modify += [f"--macaddress{idx}", mac_clean.upper()]
                
        run_vbox_cmd(cmd_modify)
        
        # 3. Crear almacenamiento y disco
        # Crear controlador SATA
        run_vbox_cmd(["VBoxManage", "storagectl", name, "--name", "SATA Controller", "--add", "sata", "--controller", "IntelAHCI"])
        
        # Crear archivo VDI de disco virtual
        disk_path = os.path.join(vm_dir, name, f"{name}.vdi")
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        
        cmd_disk = ["VBoxManage", "createmedium", "disk", "--filename", disk_path, "--size", str(disk_size_gb * 1024), "--format", "VDI"]
        # Nota: si createmedium falla o ya existe el medio, se captura.
        if run_vbox_cmd(cmd_disk):
            # Adjuntar disco al controlador SATA
            run_vbox_cmd([
                "VBoxManage", "storageattach", name,
                "--storagectl", "SATA Controller",
                "--port", "0",
                "--device", "0",
                "--type", "hdd",
                "--medium", disk_path
            ])
            
        print(f"[+] VM '{name}' creada y configurada con éxito.")
        # Encender la VM automáticamente para que arranque por PXE
        print(f"[*] Encendiendo VM '{name}' en segundo plano (headless)...")
        vm_folder = os.path.join(vm_dir, name)
        run_vbox_cmd(["VBoxManage", "startvm", name, "--type", "headless"], cwd=vm_folder)
        print(f"[*] La VM '{name}' está arrancando. El jumpstart gestionará automáticamente")
        print(f"    el cambio a arranque desde disco al finalizar la instalación.")


def undeploy_virtualbox_vms(nodes):
    """Elimina por completo todas las VMs creadas (excepto jumpstart) y limpia sus archivos asociados."""
    print("[*] Iniciando desinstalación (undeploy) de la maqueta en VirtualBox...")
    
    # Comprobar VMs existentes
    vms_list_proc = subprocess.run(["VBoxManage", "list", "vms"], stdout=subprocess.PIPE, text=True)
    existing_vms = []
    for line in vms_list_proc.stdout.splitlines():
        match = re.match(r'^"([^"]+)"', line)
        if match:
            existing_vms.append(match.group(1))
            
    for node in nodes:
        name = node.get('name')
        if name == 'jumpstart':
            print(f"[*] El nodo '{name}' (Jumpstart) se gestiona de forma manual. No se eliminará.")
            continue
            
        if name in existing_vms:
            print(f"[-] Eliminando VM: {name}...")
            # 1. Apagar si está activa
            subprocess.run(["VBoxManage", "controlvm", name, "poweroff"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # 2. Desregistrar y borrar
            if run_vbox_cmd(["VBoxManage", "unregistervm", name, "--delete"]):
                print(f"[+] VM '{name}' eliminada con éxito.")
        else:
            print(f"[*] La VM '{name}' no existe en VirtualBox. Saltando.")
    print("[*] Desinstalación completada.")


# ----------------- GENERADOR CONFIGURACIONES PXE (EN JUMPSTART) -----------------

def get_jumpstart_pubkey():
    """Lee la clave pública SSH local del jumpstart. Genera una de prueba si no existe."""
    key_paths = [
        "/root/.ssh/id_rsa.pub",
        "/home/admin/.ssh/id_rsa.pub",
        os.path.expanduser("~/.ssh/id_rsa.pub")
    ]
    for path in key_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read().strip()
                
    # Fallback/generación ficticia para testeo
    print("[!] No se encontró clave pública SSH local. Usando clave pública por defecto.")
    return "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2r... admin@jumpstart"

def generate_pxe_configs(nodes, templates_dir="/home/Chadry/esi/gyar/trabajo/baremetal/templates"):
    """Genera configuraciones de DHCP, PXELINUX y perfiles de autoinstalación en el servidor Jumpstart."""
    print("[*] Iniciando generación de configuraciones de red y aprovisionamiento...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Obtener la clave SSH pública del Jumpstart
    ssh_key = get_jumpstart_pubkey()
    
    # Directorios de destino finales
    dhcp_config_path = "/etc/dhcp/dhcpd.conf"
    tftp_pxe_dir = "/srv/tftp/pxelinux.cfg"
    web_autoinstall_dir = "/var/www/html/autoinstall"
    
    # Asegurar directorios de destino (si corremos localmente en jumpstart)
    # Si estamos en modo de desarrollo en local, los escribimos en un directorio temporal del espacio de trabajo
    # para que el usuario pueda validarlos y luego copiarlos, pero si somos root/sudo en el jumpstart los pondrá directos.
    is_live_server = os.path.exists("/srv/tftp") or os.path.exists("/etc/dhcp")
    
    if not is_live_server:
        print("[!] Entorno Jumpstart real no detectado. Generando archivos en la carpeta del repositorio para previsualización...")
        dhcp_config_path = os.path.join(script_dir, "baremetal", "dhcp", "dhcpd.conf")
        tftp_pxe_dir = os.path.join(script_dir, "baremetal", "pxe", "pxelinux.cfg")
        web_autoinstall_dir = os.path.join(script_dir, "baremetal", "autoinstall")
        
    os.makedirs(os.path.dirname(dhcp_config_path), exist_ok=True)
    os.makedirs(tftp_pxe_dir, exist_ok=True)
    os.makedirs(web_autoinstall_dir, exist_ok=True)

    # 2. Generar DHCPD.CONF
    print(f"[*] Generando archivo DHCP: {dhcp_config_path}")
    
    # Cargar redes parametrizadas (de forma relativa al script)
    networks_path = os.path.join(script_dir, "baremetal", "networks.yml")
    networks_list = load_networks_file(networks_path)
    
    dhcp_content = """# Configuracion del servidor DHCP (Generado dinamicamente por orquestador)
option domain-name "pxe.local";
option domain-name-servers 8.8.8.8, 8.8.4.4;
default-lease-time 600;
max-lease-time 7200;
ddns-update-style none;
authoritative;
"""

    for net in networks_list:
        net_name = net.get('name')
        subnet = net.get('subnet')
        netmask = net.get('netmask')
        gateway = net.get('gateway')
        dns_servers = net.get('dns', ["8.8.8.8"])
        dhcp_range = net.get('dhcp_range', {})
        range_start = dhcp_range.get('start')
        range_end = dhcp_range.get('end')
        
        dns_list_str = ", ".join(dns_servers)
        
        dhcp_content += f"""
# Red: {net_name}
subnet {subnet} netmask {netmask} {{
  option subnet-mask {netmask};
  option routers {gateway};
  option domain-name-servers {dns_list_str};
  next-server {gateway};
  filename "pxelinux.0";
"""
        if range_start and range_end:
            dhcp_content += f"  range {range_start} {range_end}; # Rango dinamico\n"
            
        # Agregar hosts estáticos para esta red específica
        for node in nodes:
            name = node.get('name')
            mac = node.get('mac')
            if name == 'jumpstart' or not mac:
                continue
                
            node_networks = node.get('networks', [])
            for node_net in node_networks:
                if node_net.get('name') == net_name:
                    ip = node_net.get('ip')
                    dhcp_content += f"""
  host {name} {{
    hardware ethernet {mac.upper()};
    fixed-address {ip};
  }}
"""
        dhcp_content += "}\n"
    
    with open(dhcp_config_path, 'w') as f:
        f.write(dhcp_content)

    # 3. Generar perfiles PXELINUX por MAC y perfiles Autoinstall
    for node in nodes:
        name = node.get('name')
        mac = node.get('mac')
        node_type = node.get('type')
        
        if name == 'jumpstart' or not mac:
            continue
            
        # Determinar red principal y IP de jumpstart
        networks = node.get('networks', [])
        if not networks:
            continue
            
        primary_net = networks[0]
        net_name = primary_net.get('name')
        ip_addr = primary_net.get('ip')
        netmask = primary_net.get('netmask', '255.255.255.0')
        gateway = primary_net.get('gateway', '')
        dns_servers = primary_net.get('dns', ["8.8.8.8"])
        
        # Calcular prefijo de red en notación CIDR
        cidr = "24" # default
        if netmask == '255.255.255.0':
            cidr = "24"
        elif netmask == '255.255.0.0':
            cidr = "16"
            
        # Jumpstart IP desde la perspectiva de la subred del nodo (dinámico desde networks.yml)
        jumpstart_ip = "192.168.1.254" # fallback por defecto
        for net in networks_list:
            if net.get('name') == net_name:
                jumpstart_ip = net.get('gateway', jumpstart_ip)
                break
        
        # A. Crear fichero de menú PXE por MAC
        # Formato de nombre VirtualBox: 01-mac-con-guiones en minúsculas (ej: 01-08-00-27-00-01-0a)
        mac_formatted = "01-" + mac.lower().replace(':', '-')
        pxe_file_path = os.path.join(tftp_pxe_dir, mac_formatted)
        
        pxe_menu_content = f"""DEFAULT menu.c32
PROMPT 0
TIMEOUT 10
ONTIMEOUT ubuntu-22.04
MENU TITLE PXE Boot Menu

LABEL ubuntu-22.04
  MENU LABEL Install Ubuntu 22.04 Server ({name})
  KERNEL images/ubuntu-22.04/vmlinuz
  INITRD images/ubuntu-22.04/initrd
  IPAPPEND 2
  APPEND initrd=images/ubuntu-22.04/initrd ip=dhcp url=http://{jumpstart_ip}/ubuntu-22.04/ubuntu-22.04.5-live-server-amd64.iso autoinstall ds=nocloud-net;s=http://{jumpstart_ip}/autoinstall/{name}/
"""
        with open(pxe_file_path, 'w') as f:
            f.write(pxe_menu_content)
        print(f"[+] Menú PXE generado para {name} -> {pxe_file_path}")

        # B. Generar archivos Autoinstall (user-data y meta-data)
        node_install_dir = os.path.join(web_autoinstall_dir, name)
        os.makedirs(node_install_dir, exist_ok=True)
        
        # Copiar meta-data
        meta_data_src = os.path.join(templates_dir, "common-meta-data")
        meta_data_dst = os.path.join(node_install_dir, "meta-data")
        if os.path.exists(meta_data_src):
            with open(meta_data_src, 'r') as src, open(meta_data_dst, 'w') as dst:
                dst.write(src.read())
        else:
            with open(meta_data_dst, 'w') as dst:
                dst.write("instance-id: nocloud-vm\n")
                
        # Cargar plantilla de user-data
        template_name = f"user-data-{node_type}"
        template_path = os.path.join(templates_dir, template_name)
        if not os.path.exists(template_path):
            # Usar una por defecto si no existe
            template_path = os.path.join(templates_dir, "user-data-web-frontend")
            
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                ud_template = f.read()
        else:
            ud_template = "#cloud-config\nautoinstall:\n  version: 1\n" # Fallback extremo
            
        # Generar la sección Netplan dynamic en formato YAML indentado
        # Normalmente cloud-init espera indentación en ethernets de 4 o 6 espacios según plantilla
        dns_str = "\n".join([f"            - {d}" for d in dns_servers])
        
        netplan_interface_config = f"""      enp0s3:
        dhcp4: false
        addresses:
          - {ip_addr}/{cidr}"""
        
        if gateway:
            netplan_interface_config += f"\n        gateway4: {gateway}"
            
        netplan_interface_config += f"""
        nameservers:
          addresses:
{dns_str}"""

        # Si el nodo es el load-balancer o un cluster con varias interfaces, podemos programar el mapeo de interfaces adicionales
        # Para el jumpstart no se autoinstala, así que no nos preocupamos.
        
        # Reemplazar placeholders en la plantilla
        user_data_content = ud_template.replace("{{ HOSTNAME }}", name)
        user_data_content = user_data_content.replace("{{ SSH_PUB_KEY }}", ssh_key)
        user_data_content = user_data_content.replace("{{ INTERFACES_CONFIG }}", netplan_interface_config)
        user_data_content = user_data_content.replace("{{ JUMPSTART_IP }}", jumpstart_ip)
        
        user_data_dst = os.path.join(node_install_dir, "user-data")
        with open(user_data_dst, 'w') as f:
            f.write(user_data_content)
        print(f"[+] Autoinstall user-data generado para {name} -> {user_data_dst}")

    # 4. Reiniciar servicios si estamos en modo live
    if is_live_server:
        print("[*] Reiniciando servicios en el Jumpstart...")
        subprocess.run(["systemctl", "restart", "isc-dhcp-server"])
        subprocess.run(["systemctl", "restart", "tftpd-hpa"])
        subprocess.run(["systemctl", "restart", "apache2"])
        print("[+] Servicios DHCP, TFTP y HTTP actualizados y activos.")
        
    print("[*] Generación de configuraciones finalizada exitosamente.")

# ----------------- MAIN -----------------

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_nodes_dir = os.path.join(script_dir, "baremetal", "nodes")
    default_templates_dir = os.path.join(script_dir, "baremetal", "templates")

    parser = argparse.ArgumentParser(description="Orquestador Dinámico PXE/VirtualBox para GAR")
    parser.add_argument('--action', required=True,
                        choices=['validate', 'deploy', 'undeploy', 'generate-configs', 'finalize-node'],
                        help="Acción a realizar: validar YAMLs, desplegar VMs, desinstalar VMs, generar configs PXE, o finalizar aprovisionamiento de un nodo.")
    parser.add_argument('--nodes-dir', default=default_nodes_dir, help=f"Directorio con archivos YAML de nodos (por defecto {default_nodes_dir})")
    parser.add_argument('--templates-dir', default=default_templates_dir, help=f"Directorio con plantillas Autoinstall (por defecto {default_templates_dir})")
    parser.add_argument('--vm-dir', default="/home/Chadry/VirtualBox VMs", help="Ruta base para los discos virtuales en el host")
    parser.add_argument('--node', help="Nombre de un nodo específico para desplegar o desinstalar (opcional).")
    
    args = parser.parse_args()
    
    # Cargar nodos
    nodes = load_all_nodes(args.nodes_dir)
    if not nodes:
        print("[-] Error: No se encontraron definiciones de nodos YAML.")
        sys.exit(1)
        
    # Acciones
    if args.action == 'validate':
        success = validate_nodes(nodes)
        sys.exit(0 if success else 1)
        
    elif args.action == 'deploy':
        # Primero validar
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando despliegue de VMs.")
            sys.exit(1)
            
        # Filtrar si se especificó un nodo concreto
        deploy_nodes = nodes
        if args.node:
            deploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not deploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        deploy_virtualbox_vms(deploy_nodes, args.vm_dir)
        
    elif args.action == 'undeploy':
        # Primero validar
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando desinstalación.")
            sys.exit(1)
            
        # Filtrar si se especificó un nodo concreto
        undeploy_nodes = nodes
        if args.node:
            undeploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not undeploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        undeploy_virtualbox_vms(undeploy_nodes)
        
    elif args.action == 'generate-configs':
        # Primero validar
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando generación de configs.")
            sys.exit(1)
            
        generate_pxe_configs(nodes, args.templates_dir)

    elif args.action == 'finalize-node':
        # Invocado por el servidor de callback del jumpstart al recibir /node-ready
        if not args.node:
            print("[-] Error: --action finalize-node requiere --node <nombre>.")
            sys.exit(1)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        is_live = os.path.exists('/srv/tftp')
        tftp_pxe_dir = '/srv/tftp/pxelinux.cfg' if is_live else os.path.join(script_dir, 'baremetal', 'pxe', 'pxelinux.cfg')
        success = finalize_node(args.node, nodes, tftp_pxe_dir=tftp_pxe_dir, templates_dir=args.templates_dir)
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
