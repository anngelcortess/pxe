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
                
    # Fallback/generación ficticia para testeo
    print("[!] No se encontró clave pública SSH local. Usando clave pública por defecto.")
    return "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2r... admin@jumpstart"

def generate_pxe_configs(nodes, templates_dir="/home/Chadry/esi/gyar/trabajo/baremetal/templates"):
    """Genera configuraciones de DHCP, PXELINUX y perfiles de autoinstalación en el servidor Jumpstart."""
    print("[*] Iniciando generación de configuraciones de red y aprovisionamiento...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # La base es el directorio padre de gar_orchestrator
    base_dir = os.path.dirname(script_dir)
    
    # 1. Obtener la clave SSH pública del Jumpstart
    ssh_key = get_jumpstart_pubkey()
    
    # Directorios de destino finales
    dhcp_config_path = "/etc/dhcp/dhcpd.conf"
    tftp_pxe_dir = "/srv/tftp/pxelinux.cfg"
    web_autoinstall_dir = "/var/www/html/autoinstall"
    
    # Asegurar directorios de destino (si corremos localmente en jumpstart)
    is_live_server = os.path.exists("/srv/tftp") or os.path.exists("/etc/dhcp")
    
    if not is_live_server:
        print("[!] Entorno Jumpstart real no detectado. Generando archivos en la carpeta del repositorio para previsualización...")
        dhcp_config_path = os.path.join(base_dir, "baremetal", "dhcp", "dhcpd.conf")
        tftp_pxe_dir = os.path.join(base_dir, "baremetal", "pxe", "pxelinux.cfg")
        web_autoinstall_dir = os.path.join(base_dir, "baremetal", "autoinstall")
        
    os.makedirs(os.path.dirname(dhcp_config_path), exist_ok=True)
    os.makedirs(tftp_pxe_dir, exist_ok=True)
    os.makedirs(web_autoinstall_dir, exist_ok=True)

    # 2. Generar DHCPD.CONF
    print(f"[*] Generando archivo DHCP: {dhcp_config_path}")
    
    networks_path = os.path.join(base_dir, "baremetal", "networks.yml")
    networks_list = load_networks_file(networks_path)
    
    dhcp_content = """# Configuracion del servidor DHCP (Generado dinamicamente por orquestador)
option domain-name "pxe.local";
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
            
        networks = node.get('networks', [])
        if not networks:
            continue
            
        primary_net = networks[0]
        net_name = primary_net.get('name')
        ip_addr = primary_net.get('ip')
        netmask = primary_net.get('netmask', '255.255.255.0')
        gateway = primary_net.get('gateway', '')
        dns_servers = primary_net.get('dns', [])
        
        cidr = "24"
        if netmask == '255.255.255.0':
            cidr = "24"
        elif netmask == '255.255.0.0':
            cidr = "16"
            
        jumpstart_ip = None
        for net in networks_list:
            if net.get('name') == net_name:
                jumpstart_ip = net.get('gateway')
                break
        
        if not jumpstart_ip:
            print(f"[-] Error: No se pudo determinar la IP del jumpstart (gateway) para la red {net_name}.")
            continue
        
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

        node_install_dir = os.path.join(web_autoinstall_dir, name)
        os.makedirs(node_install_dir, exist_ok=True)
        
        meta_data_src = os.path.join(templates_dir, "common-meta-data")
        meta_data_dst = os.path.join(node_install_dir, "meta-data")
        if os.path.exists(meta_data_src):
            with open(meta_data_src, 'r') as src, open(meta_data_dst, 'w') as dst:
                dst.write(src.read())
        else:
            with open(meta_data_dst, 'w') as dst:
                dst.write("instance-id: nocloud-vm\n")
                
        template_name = f"user-data-{node_type}"
        template_path = os.path.join(templates_dir, template_name)
        if not os.path.exists(template_path):
            template_path = os.path.join(templates_dir, "user-data-web-frontend")
            
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                ud_template = f.read()
        else:
            ud_template = "#cloud-config\nautoinstall:\n  version: 1\n"
            
        dns_str = ""
        if dns_servers:
            dns_str = "\n".join([f"            - {d}" for d in dns_servers])
        
        netplan_interface_config = f"""      enp0s3:
        dhcp4: false
        addresses:
          - {ip_addr}/{cidr}"""
        
        if gateway:
            netplan_interface_config += f"\n        gateway4: {gateway}"
            
        if dns_str:
            netplan_interface_config += f"""
        nameservers:
          addresses:
{dns_str}"""

        user_data_content = ud_template.replace("{{ HOSTNAME }}", name)
        user_data_content = user_data_content.replace("{{ SSH_PUB_KEY }}", ssh_key)
        user_data_content = user_data_content.replace("{{ INTERFACES_CONFIG }}", netplan_interface_config)
        user_data_content = user_data_content.replace("{{ JUMPSTART_IP }}", jumpstart_ip)
        
        user_data_dst = os.path.join(node_install_dir, "user-data")
        with open(user_data_dst, 'w') as f:
            f.write(user_data_content)
        print(f"[+] Autoinstall user-data generado para {name} -> {user_data_dst}")

    if is_live_server:
        print("[*] Reiniciando servicios en el Jumpstart...")
        subprocess.run(["systemctl", "restart", "isc-dhcp-server"])
        subprocess.run(["systemctl", "restart", "tftpd-hpa"])
        subprocess.run(["systemctl", "restart", "apache2"])
        print("[+] Servicios DHCP, TFTP y HTTP actualizados y activos.")
        
    print("[*] Generación de configuraciones finalizada exitosamente.")
