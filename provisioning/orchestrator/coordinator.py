import json
import logging
import threading
import http.server
import urllib.parse

from provisioning.orchestrator.baremetal import create_vms, apply_post_install_specs, start_virtualbox_vms
from provisioning.orchestrator.ansible_runner import provision_all_nodes

log = logging.getLogger('coordinator')
log.setLevel(logging.INFO)

class DeploymentState:
    def __init__(self):
        self.batch_size = 3
        self.pending_nodes = []
        self.in_progress_nodes = []
        self.completed_nodes = []
        self.is_deploying = False
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
            
            threading.Thread(target=start_batch_deployment, args=(vms,), daemon=True).start()
            self._respond(200, '{"status": "ok", "message": "Deployment initiated in background"}')
            return

        self._respond(404, '{"error": "not found"}')

def start_batch_deployment(vms):
    with state.lock:
        state.pending_nodes = [n for n in vms if n.get('name') != 'jumpstart']
        state.in_progress_nodes = []
        state.completed_nodes = []
        state.is_deploying = True
        
        to_start = state.pending_nodes[:state.batch_size]
        state.pending_nodes = state.pending_nodes[state.batch_size:]
        state.in_progress_nodes.extend(to_start)
    
    log.info(f"Iniciando despliegue. Batch inicial de {len(to_start)} VMs.")
    create_vms(to_start, host_api_global)

def process_node_ready(node_name):
    with state.lock:
        node = next((n for n in state.in_progress_nodes if n.get('name') == node_name), None)
        if not node:
            log.warning(f"Nodo {node_name} no encontrado en in_progress_nodes.")
            # Intento de fallback por si acaso se reinició el servidor de callbacks
            # o si el comando provision_nodes individual saltó aquí
            return
            
        # Reconfigurar boot y bajar RAM a 1024
        apply_post_install_specs(host_api_global, node)
        
        state.in_progress_nodes.remove(node)
        state.completed_nodes.append(node)
        
        log.info(f"Nodo {node_name} completado y reconfigurado. Quedan {len(state.pending_nodes)} en cola.")
        
        if state.pending_nodes:
            next_node = state.pending_nodes.pop(0)
            state.in_progress_nodes.append(next_node)
            log.info(f"Lanzando siguiente nodo en la ventana deslizante: {next_node.get('name')}")
            node_to_start = next_node
        else:
            node_to_start = None
            
        all_done = (len(state.pending_nodes) == 0 and len(state.in_progress_nodes) == 0)

    if node_to_start:
        create_vms([node_to_start], host_api_global)
        
    if all_done:
        log.info("¡PXE finalizado para todas las máquinas! Iniciando encendido global y Ansible.")
        start_virtualbox_vms(state.completed_nodes, host_api_global, vm_type="headless")
        provision_all_nodes(state.completed_nodes)
        
        with state.lock:
            state.is_deploying = False

def run_callback_server(nodes, host_api_url, port=8081):
    global host_api_global
    host_api_global = host_api_url
    log.info(f"=== Servidor Coordinador iniciando en puerto {port} ===")
    server = http.server.HTTPServer(('0.0.0.0', port), CoordinatorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
