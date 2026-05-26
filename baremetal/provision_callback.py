#!/usr/bin/env python3
# ==============================================================================
# provision_callback.py — Servidor HTTP de Callback para el Jumpstart
# Asignatura: Gestión y Administración de Redes (GAR)
# ==============================================================================
# Servidor HTTP ligero (sin dependencias externas) que escucha en el puerto 8081.
# Cuando un nodo termina su instalación de Ubuntu vía autoinstall, ejecuta:
#
#   curl -sf http://192.168.1.254:8081/node-ready?node=<nombre>
#
# Este servidor recibe esa petición y:
#   1. Actualiza el fichero PXE de esa MAC a LOCALBOOT 0 (evita re-instalación).
#   2. Ejecuta el playbook Ansible correspondiente al tipo de nodo.
#
# Instala como servicio systemd con: provision-callback.service
# ==============================================================================

import http.server
import urllib.parse
import subprocess
import os
import sys
import logging
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────
PORT = int(os.environ.get('PROVISION_PORT', 8081))
# Ruta al orquestador Python (orchestrate.py), relativa a este script
ORCHESTRATE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'orchestrate.py')
ORCHESTRATE_SCRIPT = os.path.normpath(ORCHESTRATE_SCRIPT)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('provision-callback')


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP para los callbacks de aprovisionamiento."""

    def log_message(self, format, *args):
        """Redirigir logs del servidor HTTP a nuestro logger."""
        log.info(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # ── GET /health ────────────────────────────────────────────────────────
        if parsed.path == '/health':
            self._respond(200, 'OK — provision-callback activo\n')
            return

        # ── GET /node-ready?node=<nombre> ──────────────────────────────────────
        if parsed.path == '/node-ready':
            node_name = params.get('node', [None])[0]
            if not node_name:
                self._respond(400, 'Error: parámetro "node" requerido\n')
                return

            # Sanitizar: solo alfanuméricos, guiones y guiones bajos
            safe_name = ''.join(c for c in node_name if c.isalnum() or c in '-_')
            if safe_name != node_name:
                log.warning(f"Nombre de nodo rechazado por contener caracteres no permitidos: '{node_name}'")
                self._respond(400, 'Error: nombre de nodo inválido\n')
                return

            log.info(f"¡Callback recibido! Nodo '{safe_name}' ha completado la instalación.")
            self._respond(200, f'Recibido. Finalizando aprovisionamiento de {safe_name}...\n')

            # Ejecutar finalize-node en background para no bloquear la respuesta HTTP
            # (el nodo puede estar reiniciando mientras procesamos)
            self._run_finalize(safe_name)
            return

        # ── Ruta no reconocida ─────────────────────────────────────────────────
        self._respond(404, f'Ruta no reconocida: {parsed.path}\n')

    def _respond(self, code, body):
        """Enviar respuesta HTTP simple."""
        body_bytes = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _run_finalize(self, node_name):
        """Invocar orchestrate.py finalize-node <nombre>."""
        if not os.path.exists(ORCHESTRATE_SCRIPT):
            log.error(f"No se encontró orchestrate.py en: {ORCHESTRATE_SCRIPT}")
            return

        cmd = [sys.executable, ORCHESTRATE_SCRIPT, 'finalize-node', node_name]
        log.info(f"Ejecutando: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=False,   # stdout/stderr van al journal de systemd
                text=True,
                timeout=600             # 10 minutos máximo para el playbook Ansible
            )
            if result.returncode == 0:
                log.info(f"finalize-node completado con éxito para '{node_name}'.")
            else:
                log.error(f"finalize-node terminó con código {result.returncode} para '{node_name}'.")
        except subprocess.TimeoutExpired:
            log.error(f"Timeout (600s) al ejecutar finalize-node para '{node_name}'.")
        except Exception as e:
            log.error(f"Error inesperado al ejecutar finalize-node: {e}")


def main():
    log.info(f"=== Servidor de Callback de Aprovisionamiento iniciando en puerto {PORT} ===")
    log.info(f"Esperando callbacks en: http://0.0.0.0:{PORT}/node-ready?node=<nombre>")
    log.info(f"Diagnóstico en:         http://0.0.0.0:{PORT}/health")
    log.info(f"Orquestador:            {ORCHESTRATE_SCRIPT}")

    server = http.server.HTTPServer(('0.0.0.0', PORT), CallbackHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor detenido manualmente.")
        server.server_close()


if __name__ == '__main__':
    main()
