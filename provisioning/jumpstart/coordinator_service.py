import json
import logging
import threading
import http.server
import urllib.parse

import os
import sys

# Añadir la raíz del repositorio al path antes de hacer imports locales
REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from provisioning.jumpstart.baremetal import create_vms, apply_post_install_specs, start_virtualbox_vms
from provisioning.jumpstart.software_provisioner import provision_all_nodes

log = logging.getLogger('coordinator')
log.setLevel(logging.INFO)

class DeploymentState:
    def __init__(self):
        self.batch_size = 3
        self.pending_nodes = []
        self.in_progress_nodes = []
        self.completed_nodes = []
        self.status = "IDLE"  # Posibles estados: IDLE, PXE_INSTALLING, ANSIBLE_PROVISIONING
        self.lock = threading.Lock()

state = DeploymentState()
host_api_global = None

class CoordinatorHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")

    def _respond(self, code, body):
        body_bytes = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/health':
            self._respond(200, '{"status": "ok", "message": "Coordinator active"}')
            return

        if parsed.path == '/node-ready':
            node_name = params.get('node', [None])[0]
            if not node_name:
                self._respond(400, '{"error": "node parameter required"}')
                return
            
            safe_name = ''.join(c for c in node_name if c.isalnum() or c in '-_')
            log.info(f"Callback recibido de PXE: '{safe_name}'")
            self._respond(200, '{"status": "ok"}')
            
            # Lanzamos el proceso del evento en background para no bloquear el HTTP Server
            threading.Thread(target=process_node_ready, args=(safe_name,), daemon=True).start()
            return

        self._respond(404, '{"error": "not found"}')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/start-batch-deploy':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._respond(400, '{"error": "Invalid JSON"}')
                return
            
            vms = data.get('vms', [])
            if not vms:
                self._respond(400, '{"error": "No VMs provided"}')
                return
            
            success, message = start_batch_deployment(vms)
            if success:
                self._respond(200, json.dumps({"status": "ok", "message": message}))
            else:
                self._respond(409, json.dumps({"error": message}))
            return

        self._respond(404, '{"error": "not found"}')

def start_batch_deployment(vms):
    """
    Recibe una lista de VMs desde el CLI.
    Si la cola está inactiva, la inicializa.
    Si está instalando por PXE, añade a la cola dinámicamente evitando duplicados.
    Si está en fase final (Ansible), rechaza la petición.
    """
    to_start = []
    
    with state.lock:
        if state.status == "ANSIBLE_PROVISIONING":
            return False, "El clúster ya está en la fase final de configuración de Ansible. Espera a que termine para añadir más máquinas."
            
        new_nodes = [n for n in vms if n.get('name') != 'jumpstart']
        added_count = 0
        
        if state.status == "IDLE":
            state.pending_nodes = new_nodes
            state.in_progress_nodes = []
            state.completed_nodes = []
            state.status = "PXE_INSTALLING"
            
            # Extraer el primer bloque
            to_start = state.pending_nodes[:state.batch_size]
            state.pending_nodes = state.pending_nodes[state.batch_size:]
            state.in_progress_nodes.extend(to_start)
            added_count = len(new_nodes)
        else:
            # state.status es PXE_INSTALLING, añadimos de forma inteligente a la cola
            for node in new_nodes:
                name = node.get('name')
                in_pending = any(n.get('name') == name for n in state.pending_nodes)
                in_progress = any(n.get('name') == name for n in state.in_progress_nodes)
                
                if not in_pending and not in_progress:
                    # Sacamos de completados por si el usuario está forzando una reinstalación
                    state.completed_nodes = [n for n in state.completed_nodes if n.get('name') != name]
                    state.pending_nodes.append(node)
                    added_count += 1
            
            # Si hay "huecos" en la ventana deslizante, aprovechamos para rellenarlos al instante
            while len(state.in_progress_nodes) < state.batch_size and state.pending_nodes:
                next_node = state.pending_nodes.pop(0)
                state.in_progress_nodes.append(next_node)
                to_start.append(next_node)
                
    # Las llamadas de red a la Host API siempre fuera del lock de memoria
    if to_start:
        log.info(f"Enviando {len(to_start)} VMs a la API del Host (Fase PXE).")
        create_vms(to_start, host_api_global)
        
    return True, f"Añadidos {added_count} nodos a la cola de despliegue."

def process_node_ready(node_name):
    """
    Lógica de la Ventana Deslizante desencadenada por un callback.
    """
    to_start = None
    all_done = False
    
    with state.lock:
        if state.status != "PXE_INSTALLING":
            log.warning(f"Se recibió callback para {node_name} pero el estado global es {state.status}.")
            return
            
        node = next((n for n in state.in_progress_nodes if n.get('name') == node_name), None)
        if not node:
            log.warning(f"Nodo {node_name} no encontrado en in_progress_nodes (¿Evento duplicado o cancelado?).")
            return
            
        # 1. Reconfigurar boot y bajar RAM
        apply_post_install_specs(host_api_global, node)
        
        # 2. Desplazar nodo
        state.in_progress_nodes.remove(node)
        state.completed_nodes.append(node)
        
        log.info(f"Nodo {node_name} completado. Quedan {len(state.pending_nodes)} en cola.")
        
        # 3. Avanzar ventana
        if state.pending_nodes:
            next_node = state.pending_nodes.pop(0)
            state.in_progress_nodes.append(next_node)
            log.info(f"Avanzando ventana deslizante con nodo: {next_node.get('name')}")
            to_start = next_node
        else:
            if len(state.in_progress_nodes) == 0:
                all_done = True
                state.status = "ANSIBLE_PROVISIONING"

    if to_start:
        create_vms([to_start], host_api_global)
        
    if all_done:
        log.info("¡PXE finalizado para todas las máquinas! Iniciando encendido global y ejecución de Ansible.")
        
        # Usamos una copia de los nodos para no retener la referencia mutable
        nodes_to_provision = list(state.completed_nodes)
        
        start_virtualbox_vms(nodes_to_provision, host_api_global, vm_type="headless")
        provision_all_nodes(nodes_to_provision)
        
        # Al terminar todo el bloque de Ansible (que puede tardar minutos), reiniciamos el estado
        with state.lock:
            state.status = "IDLE"
            state.completed_nodes = []
            log.info("Despliegue global finalizado. Orquestador vuelve a estado IDLE.")

def run_callback_server(nodes, host_api_url, port=8081, batch_size=3):
    global host_api_global
    host_api_global = host_api_url
    state.batch_size = batch_size
    log.info(f"=== Servidor Coordinador iniciando en puerto {port} (Batch Size: {batch_size}) ===")
    server = http.server.HTTPServer(('0.0.0.0', port), CoordinatorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == '__main__':
    # Redirigir logs a stdout para que systemd los capture en journalctl
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout
    )

    from provisioning.jumpstart.parsers import load_all_nodes, load_settings_file

    nodes_dir = os.path.join(REPO_DIR, 'config', 'nodes')
    settings_path = os.path.join(REPO_DIR, 'config', 'settings.yml')

    nodes = load_all_nodes(nodes_dir)
    if not nodes:
        print('[-] Error: No se encontraron definiciones de nodos YAML.')
        sys.exit(1)

    settings = load_settings_file(settings_path)

    host_api_ip   = settings.get('host_api', {}).get('ip', '192.168.56.1')
    host_api_port = settings.get('host_api', {}).get('port', 7070)
    host_api_url  = f'http://{host_api_ip}:{host_api_port}'

    port       = settings.get('orchestrator', {}).get('port', 8081)
    batch_size = settings.get('orchestrator', {}).get('batch_size', 3)

    run_callback_server(nodes, host_api_url, port=port, batch_size=batch_size)
