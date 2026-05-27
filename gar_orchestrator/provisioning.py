import os
import sys
import socket
import time
import subprocess
import logging
import threading
import http.server
import urllib.parse
from gar_orchestrator.baremetal import change_boot_order_to_disk

GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
NC = '\033[0m'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('provisioning')

def _resolve_playbook_path(node_type, templates_dir=None):
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

def _run_ansible_playbook(playbook_path, node_ip, name):
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

def provision_nodes(target_nodes, nodes, host_api_url, skip_boot_order=False):
    """
    Modo Directo: Ejecuta Ansible para una lista de nodos especificados.
    target_nodes: Lista de nombres de nodos a aprovisionar.
    nodes: Diccionario/lista completo de nodos parseado del YAML.
    """
    for name in target_nodes:
        node = next((n for n in nodes if n.get('name') == name), None)
        if not node:
            print(f"[{RED}-{NC}] Nodo '{name}' no encontrado en los YAMLs.")
            continue
            
        node_type = node.get('type', 'generic')
        node_networks = node.get('networks', [])
        node_ip = node_networks[0].get('ip') if node_networks else None

        if not node_ip:
            print(f"[{YELLOW}!{NC}] No se pudo determinar la IP de '{name}'. Saltando Ansible.")
            continue

        playbook_path = _resolve_playbook_path(node_type)
        if not os.path.exists(playbook_path):
            print(f"[{YELLOW}!{NC}] No se encontró playbook en '{playbook_path}'. Saltando Ansible.")
            continue

        if not skip_boot_order and host_api_url:
            change_boot_order_to_disk(host_api_url, name)

        if _wait_for_ssh(node_ip, name):
            _run_ansible_playbook(playbook_path, node_ip, name)

# ── Servidor de Callbacks (Modo Demonio) ───────────────────────────────────────

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, nodes, host_api_url, *args, **kwargs):
        self.nodes = nodes
        self.host_api_url = host_api_url
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/health':
            self._respond(200, 'OK — provision-callback activo\n')
            return

        if parsed.path == '/node-ready':
            node_name = params.get('node', [None])[0]
            if not node_name:
                self._respond(400, 'Error: parámetro "node" requerido\n')
                return

            safe_name = ''.join(c for c in node_name if c.isalnum() or c in '-_')
            if safe_name != node_name:
                self._respond(400, 'Error: nombre de nodo inválido\n')
                return

            log.info(f"¡Callback recibido! Nodo '{safe_name}' ha completado la instalación.")
            self._respond(200, f'Recibido. Finalizando aprovisionamiento de {safe_name}...\n')

            # Ejecutar el aprovisionamiento en un hilo en segundo plano
            threading.Thread(
                target=provision_nodes,
                args=([safe_name], self.nodes, self.host_api_url, False),
                daemon=True
            ).start()
            return

        self._respond(404, f'Ruta no reconocida: {parsed.path}\n')

    def _respond(self, code, body):
        body_bytes = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

def run_callback_server(nodes, host_api_url, port=8081):
    """
    Inicia el servidor HTTP de callbacks. 
    Se queda bloqueando el hilo actual (serve_forever).
    """
    log.info(f"=== Servidor de Callback de Aprovisionamiento iniciando en puerto {port} ===")
    log.info(f"Esperando callbacks en: http://0.0.0.0:{port}/node-ready?node=<nombre>")
    
    # Factory para pasar argumentos al Handler
    def handler_factory(*args, **kwargs):
        return CallbackHandler(nodes, host_api_url, *args, **kwargs)

    server = http.server.HTTPServer(('0.0.0.0', port), handler_factory)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor detenido manualmente.")
        server.server_close()
