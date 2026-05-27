import os
import subprocess
from gar_orchestrator.parsers import load_networks_file

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
                
    print("[!] No se encontró clave pública SSH local. Usando clave pública por defecto.")
    return "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2r... admin@jumpstart"

def _setup_target_paths(base_dir):
    """Establece y crea los directorios de destino dependiendo de si es entorno real o local."""
    dhcp_config_path = "/etc/dhcp/dhcpd.conf"
    tftp_pxe_dir = "/srv/tftp/pxelinux.cfg"
    web_autoinstall_dir = "/var/www/html/autoinstall"
    
    is_live_server = os.path.exists("/srv/tftp") or os.path.exists("/etc/dhcp")
    
    if not is_live_server:
        print("[!] Entorno Jumpstart real no detectado. Generando en carpeta local para previsualización...")
        dhcp_config_path = os.path.join(base_dir, ".local_output", "dhcp", "dhcpd.conf")
        tftp_pxe_dir = os.path.join(base_dir, ".local_output", "pxe", "pxelinux.cfg")
        web_autoinstall_dir = os.path.join(base_dir, ".local_output", "autoinstall")
        
    os.makedirs(os.path.dirname(dhcp_config_path), exist_ok=True)
    os.makedirs(tftp_pxe_dir, exist_ok=True)
    os.makedirs(web_autoinstall_dir, exist_ok=True)
    
    return dhcp_config_path, tftp_pxe_dir, web_autoinstall_dir, is_live_server

GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
NC = '\033[0m'

def _generate_dhcp_config(nodes, networks_list, dhcp_config_path):
    """Genera el fichero de configuración de DHCP."""
    print(f"[{CYAN}*{NC}] Generando archivo DHCP global...")
    
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    dhcp_header_path = os.path.join(assets_dir, 'dhcp_header.template')
    if os.path.exists(dhcp_header_path):
        with open(dhcp_header_path, 'r') as f:
            dhcp_content = f.read() + "\n"
    else:
        dhcp_content = ""

    for net in networks_list:
        net_name = net.get('name')
        subnet = net.get('subnet')
        netmask = net.get('netmask')
        gateway = net.get('gateway')
        dns_servers = net.get('dns', [])
        dhcp_range = net.get('dhcp_range', {})
        range_start = dhcp_range.get('start')
        range_end = dhcp_range.get('end')
        
        dns_list_str = ", ".join(dns_servers) if dns_servers else ""
        
        dhcp_content += f"""
# Red: {net_name}
subnet {subnet} netmask {netmask} {{
  option subnet-mask {netmask};
  option routers {gateway};
"""
        if dns_list_str:
            dhcp_content += f"  option domain-name-servers {dns_list_str};\n"
            
        dhcp_content += f"""  next-server {gateway};
  filename "pxelinux.0";
"""
        if range_start and range_end:
            dhcp_content += f"  range {range_start} {range_end}; # Rango dinamico\n"
            
        for node in nodes:
            name = node.get('name')
            mac = node.get('mac')
            if name == 'jumpstart' or not mac:
                continue
                
            for node_net in node.get('networks', []):
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

def _generate_pxe_menu(name, mac, jumpstart_ip, tftp_pxe_dir):
    """Genera el archivo de menú PXELINUX específico para la MAC de un nodo."""
    mac_formatted = "01-" + mac.lower().replace(':', '-')
    pxe_file_path = os.path.join(tftp_pxe_dir, mac_formatted)
    
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    pxe_template_path = os.path.join(assets_dir, 'pxe_menu.template')
    
    if os.path.exists(pxe_template_path):
        with open(pxe_template_path, 'r') as f:
            pxe_menu_content = f.read().format(name=name, jumpstart_ip=jumpstart_ip)
    else:
        pxe_menu_content = ""
        
    with open(pxe_file_path, 'w') as f:
        f.write(pxe_menu_content)

def _generate_autoinstall_files(node, jumpstart_ip, ssh_key, templates_dir, web_autoinstall_dir, networks_list):
    """Genera los archivos meta-data y user-data inyectando variables en las plantillas."""
    name = node.get('name')
    
    node_install_dir = os.path.join(web_autoinstall_dir, name)
    os.makedirs(node_install_dir, exist_ok=True)
    
    # meta-data
    meta_data_src = os.path.join(templates_dir, "meta-data")
    meta_data_dst = os.path.join(node_install_dir, "meta-data")
    if os.path.exists(meta_data_src):
        with open(meta_data_src, 'r') as src, open(meta_data_dst, 'w') as dst:
            dst.write(src.read())
    else:
        with open(meta_data_dst, 'w') as dst:
            dst.write("instance-id: nocloud-vm\n")
            
    # user-data
    template_path = os.path.join(templates_dir, "user-data")
        
    if os.path.exists(template_path):
        with open(template_path, 'r') as f:
            ud_template = f.read()
    else:
        ud_template = "#cloud-config\nautoinstall:\n  version: 1\n"
        
    # Mapeo de NICs de VirtualBox a nombres de interfaz Linux
    # --nic1 → enp0s3, --nic2 → enp0s8, --nic3 → enp0s9, --nic4 → enp0s10
    VBOX_NIC_NAMES = ["enp0s3", "enp0s8", "enp0s9", "enp0s10"]
    
    netplan_interface_config = ""
    for idx, net in enumerate(node.get('networks', [])):
        if idx >= len(VBOX_NIC_NAMES):
            break
        nic_name = VBOX_NIC_NAMES[idx]
        net_type = net.get('type', 'intnet').lower()
        
        if net_type == 'nat':
            # Interfaz NAT de VirtualBox: usa DHCP (VBox asigna IP automáticamente)
            netplan_interface_config += f"      {nic_name}:\n        dhcp4: true"
        else:
            # Buscar la red global para heredar configuraciones
            global_net = next((n for n in networks_list if n.get('name') == net.get('name')), {})
            
            # Interfaz de red interna: configuración estática
            ip = net.get('ip', '')
            # Usar .get() con el valor global como default
            nm = net.get('netmask', global_net.get('netmask', '255.255.255.0'))
            gw = net.get('gateway', global_net.get('gateway', ''))
            dns_list = net.get('dns', global_net.get('dns', []))
            
            cidr = "24" if nm == '255.255.255.0' else "16"
            
            netplan_interface_config += f"      {nic_name}:\n        dhcp4: false\n        addresses:\n          - {ip}/{cidr}"
            if gw:
                netplan_interface_config += f"\n        gateway4: {gw}"
            if dns_list:
                dns_entries = "\n".join([f"            - {d}" for d in dns_list])
                netplan_interface_config += f"\n        nameservers:\n          addresses:\n{dns_entries}"
        
        # Separador entre interfaces
        if idx < len(node.get('networks', [])) - 1:
            netplan_interface_config += "\n"

    user_data_content = ud_template.replace("{{ HOSTNAME }}", name)
    user_data_content = user_data_content.replace("{{ SSH_PUB_KEY }}", ssh_key)
    user_data_content = user_data_content.replace("{{ INTERFACES_CONFIG }}", netplan_interface_config)
    user_data_content = user_data_content.replace("{{ JUMPSTART_IP }}", jumpstart_ip)
    
    user_data_dst = os.path.join(node_install_dir, "user-data")
    with open(user_data_dst, 'w') as f:
        f.write(user_data_content)

def generate_pxe_configs(nodes, templates_dir=None):
    """Punto de entrada principal. Coordina la generación de todas las configuraciones."""
    print("[*] Iniciando generación de configuraciones de red y aprovisionamiento...")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if templates_dir is None:
        templates_dir = os.path.join(base_dir, "templates")
    ssh_key = get_jumpstart_pubkey()
    networks_list = load_networks_file(os.path.join(base_dir, "config", "networks.yml"))
    
    dhcp_config_path, tftp_pxe_dir, web_autoinstall_dir, is_live_server = _setup_target_paths(base_dir)
    
    # 1. Generar DHCP global
    _generate_dhcp_config(nodes, networks_list, dhcp_config_path)

    # 2. Generar ficheros por nodo
    processed_nodes = 0
    for node in nodes:
        name = node.get('name')
        mac = node.get('mac')
        
        if name == 'jumpstart' or not mac or not node.get('networks'):
            continue
            
        # Determinar IP del jumpstart (Gateway de la red primaria del nodo)
        primary_net_name = node['networks'][0].get('name')
        jumpstart_ip = next((n.get('gateway') for n in networks_list if n.get('name') == primary_net_name), None)
        
        if not jumpstart_ip:
            print(f"[{RED}-{NC}] Error: No se pudo determinar la IP del jumpstart para la red {primary_net_name}.")
            continue
            
        _generate_pxe_menu(name, mac, jumpstart_ip, tftp_pxe_dir)
        _generate_autoinstall_files(node, jumpstart_ip, ssh_key, templates_dir, web_autoinstall_dir, networks_list)
        processed_nodes += 1
        
    if processed_nodes > 0:
        print(f"[{GREEN}+{NC}] Generados menús PXE y plantillas Cloud-Init para {processed_nodes} nodos.")

    # 3. Reiniciar servicios
    if is_live_server:
        print(f"[{CYAN}*{NC}] Reiniciando servicios en el Jumpstart...")
        subprocess.run(["systemctl", "restart", "isc-dhcp-server"])
        subprocess.run(["systemctl", "restart", "tftpd-hpa"])
        subprocess.run(["systemctl", "restart", "apache2"])
        print(f"[{GREEN}+{NC}] Servicios DHCP, TFTP y HTTP actualizados y activos.")
        
    print(f"[{GREEN}✓{NC}] Generación de configuraciones finalizada exitosamente.")
