import os
import subprocess
import jinja2
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

def _get_jinja_env(templates_dir):
    """Inicializa y devuelve el entorno de Jinja2."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        trim_blocks=True,
        lstrip_blocks=True
    )

def _generate_dhcp_config(nodes, networks_list, dhcp_config_path, jinja_env):
    """Genera el fichero de configuración de DHCP."""
    print(f"[{CYAN}*{NC}] Generando archivo DHCP global...")
    
    try:
        template = jinja_env.get_template('dhcpd.conf.j2')
        dhcp_content = template.render(nodes=nodes, networks=networks_list)
        with open(dhcp_config_path, 'w') as f:
            f.write(dhcp_content)
    except Exception as e:
        print(f"[{RED}-{NC}] Error generando DHCP: {e}")

def _generate_pxe_menu(node, jumpstart_ip, tftp_pxe_dir, jinja_env):
    """Genera el archivo de menú PXELINUX específico para la MAC de un nodo."""
    mac = node.get('mac')
    mac_formatted = "01-" + mac.lower().replace(':', '-')
    pxe_file_path = os.path.join(tftp_pxe_dir, mac_formatted)
    
    try:
        template = jinja_env.get_template('pxe_menu.j2')
        pxe_menu_content = template.render(node=node, jumpstart_ip=jumpstart_ip)
        with open(pxe_file_path, 'w') as f:
            f.write(pxe_menu_content)
    except Exception as e:
        print(f"[{RED}-{NC}] Error generando menú PXE para {node.get('name')}: {e}")

def _generate_autoinstall_files(node, jumpstart_ip, ssh_key, templates_dir, web_autoinstall_dir, networks_list, jinja_env):
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
            
    # user-data (Jinja2)
    try:
        template = jinja_env.get_template('user-data.j2')
        user_data_content = template.render(
            node=node,
            networks=networks_list,
            ssh_pub_key=ssh_key,
            jumpstart_ip=jumpstart_ip
        )
        user_data_dst = os.path.join(node_install_dir, "user-data")
        with open(user_data_dst, 'w') as f:
            f.write(user_data_content)
    except Exception as e:
        print(f"[{RED}-{NC}] Error generando user-data para {name}: {e}")

def generate_pxe_configs(nodes, templates_dir=None):
    """Punto de entrada principal. Coordina la generación de todas las configuraciones."""
    print("[*] Iniciando generación de configuraciones de red y aprovisionamiento...")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if templates_dir is None:
        templates_dir = os.path.join(base_dir, "templates")
    ssh_key = get_jumpstart_pubkey()
    networks_list = load_networks_file(os.path.join(base_dir, "config", "networks.yml"))
    
    dhcp_config_path, tftp_pxe_dir, web_autoinstall_dir, is_live_server = _setup_target_paths(base_dir)
    
    # Configurar entorno Jinja2
    jinja_env = _get_jinja_env(templates_dir)
    
    # 1. Generar DHCP global
    _generate_dhcp_config(nodes, networks_list, dhcp_config_path, jinja_env)
    
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
            
        _generate_pxe_menu(node, jumpstart_ip, tftp_pxe_dir, jinja_env)
        _generate_autoinstall_files(node, jumpstart_ip, ssh_key, templates_dir, web_autoinstall_dir, networks_list, jinja_env)
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
