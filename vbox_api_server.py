#!/usr/bin/env python3
# ==============================================================================
# vbox_api_server.py — REST API para VBoxManage en el Host Anfitrión
# Asignatura: Gestión y Administración de Redes (GAR)
# ==============================================================================
# Servidor HTTP sin dependencias externas (solo stdlib) que expone endpoints
# para gestionar máquinas virtuales de VirtualBox.
#
# Debe ejecutarse en el HOST (tu ordenador), no en el Jumpstart.
# El Jumpstart le envía peticiones HTTP cuando necesita operar sobre VMs,
# por ejemplo, cambiar el boot order tras instalar un SO.
#
# Uso directo:
#   python3 vbox_api_server.py
#   python3 vbox_api_server.py --port 7070 --bind 192.168.56.1
#
# Instalar como servicio de usuario systemd (recomendado):
#   mkdir -p ~/.config/systemd/user
#   sed "s|REPO_PATH|$(pwd)|g" vbox-api.service > ~/.config/systemd/user/vbox-api.service
#   systemctl --user daemon-reload && systemctl --user enable --now vbox-api
#
# Verificar desde el Jumpstart:
#   curl http://192.168.56.1:7070/health
# ==============================================================================

import os
import http.server
import json
import subprocess
import logging
import sys
import argparse
from urllib.parse import urlparse, parse_qs

# ── Configuración por defecto ──────────────────────────────────────────────────
DEFAULT_PORT = 7070
DEFAULT_BIND = "0.0.0.0"   # Escucha en todas las interfaces. Para mayor seguridad,
                            # limitar a "192.168.56.1" (solo red Host-Only de VirtualBox).

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("vbox-api")


# ── Helpers VBoxManage ─────────────────────────────────────────────────────────

def vbox(*args):
    """Ejecuta un comando VBoxManage. Devuelve (ok: bool, output: str)."""
    cmd = ["VBoxManage"] + list(args)
    log.info("Ejecutando: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("VBoxManage error: %s", result.stderr.strip())
        return False, result.stderr.strip()
    return True, result.stdout.strip()


def sanitize_vm_name(name):
    """Elimina caracteres peligrosos de un nombre de VM."""
    forbidden = set('"\';&|`$\\/<>')
    return "".join(c for c in name if c not in forbidden)


def parse_vms_output(raw):
    """Extrae nombres de VM de la salida de 'VBoxManage list vms'."""
    vms = []
    for line in raw.splitlines():
        if '"' in line:
            try:
                vms.append(line.split('"')[1])
            except IndexError:
                pass
    return vms


# ── Manejador HTTP ─────────────────────────────────────────────────────────────

class VBoxAPIHandler(http.server.BaseHTTPRequestHandler):
    """Manejador de peticiones HTTP para la API de VBoxManage."""

    def log_message(self, fmt, *args):
        log.info("%s — %s", self.client_address[0], fmt % args)

    # ── Utilidades de respuesta ────────────────────────────────────────────────

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, **kwargs):
        self._json(200, {"status": "ok", **kwargs})

    def _error(self, code, message):
        self._json(code, {"status": "error", "message": message})

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # ── GET ────────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path

        # GET /health
        if path == "/health":
            ok, _ = vbox("--version")
            self._ok(service="vbox-api", vboxmanage_available=ok)

        # GET /vbox/vms — listar todas las VMs registradas
        elif path == "/vbox/vms":
            ok, out = vbox("list", "vms")
            if ok:
                self._ok(vms=parse_vms_output(out))
            else:
                self._error(500, out)

        # GET /vbox/running-vms — listar VMs encendidas
        elif path == "/vbox/running-vms":
            ok, out = vbox("list", "runningvms")
            if ok:
                self._ok(vms=parse_vms_output(out))
            else:
                self._error(500, out)

        # GET /vbox/vm-info?vm=<nombre> — información de una VM
        elif path == "/vbox/vm-info":
            vm_name = params.get("vm", [None])[0]
            if not vm_name:
                self._error(400, 'Parámetro "vm" requerido')
                return
            ok, out = vbox("showvminfo", sanitize_vm_name(vm_name), "--machinereadable")
            if ok:
                info = {}
                for line in out.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        info[k.strip()] = v.strip().strip('"')
                self._ok(vm=vm_name, info=info)
            else:
                self._error(500, out)

        else:
            self._error(404, f"Ruta no encontrada: {path}")

    # ── POST ───────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            body = self._read_body()
        except (json.JSONDecodeError, ValueError) as e:
            self._error(400, f"JSON inválido en el cuerpo: {e}")
            return

        # POST /vbox/set-boot-order
        # Body: {"vm": "nombre", "boot": ["disk", "net", "none", "none"]}
        if path == "/vbox/set-boot-order":
            vm_name = body.get("vm", "").strip()
            boot    = body.get("boot", ["disk", "net", "none", "none"])

            if not vm_name:
                self._error(400, 'Campo "vm" requerido')
                return

            valid_boot_values = {"disk", "net", "dvd", "floppy", "none"}
            if not isinstance(boot, list) or len(boot) < 1:
                self._error(400, '"boot" debe ser una lista con al menos un elemento')
                return
            for b in boot:
                if b not in valid_boot_values:
                    self._error(400, f'Valor de boot inválido: "{b}". Válidos: {sorted(valid_boot_values)}')
                    return

            # Rellenar hasta 4 slots con "none"
            boot = (boot + ["none", "none", "none", "none"])[:4]

            args = []
            for i, b in enumerate(boot, 1):
                args += [f"--boot{i}", b]

            ok, out = vbox("modifyvm", sanitize_vm_name(vm_name), *args)
            if ok:
                order_str = " → ".join(b for b in boot if b != "none") or "none"
                self._ok(message=f'Boot order de "{vm_name}" actualizado: {order_str}')
            else:
                self._error(500, out)

        # POST /vbox/start
        # Body: {"vm": "nombre", "type": "headless"}  (type opcional, default headless)
        elif path == "/vbox/start":
            vm_name  = body.get("vm", "").strip()
            vm_type  = body.get("type", "headless")

            if not vm_name:
                self._error(400, 'Campo "vm" requerido')
                return
            if vm_type not in {"headless", "gui", "separate"}:
                self._error(400, f'Tipo de inicio inválido: "{vm_type}". Válidos: headless, gui, separate')
                return

            ok, out = vbox("startvm", sanitize_vm_name(vm_name), "--type", vm_type)
            if ok:
                self._ok(message=f'VM "{vm_name}" iniciada en modo {vm_type}')
            else:
                self._error(500, out)

        # POST /vbox/stop
        # Body: {"vm": "nombre", "mode": "poweroff"}  (mode opcional, default poweroff)
        elif path == "/vbox/stop":
            vm_name = body.get("vm", "").strip()
            mode    = body.get("mode", "poweroff")

            if not vm_name:
                self._error(400, 'Campo "vm" requerido')
                return
            if mode not in {"poweroff", "acpipowerbutton", "savestate", "pause", "resume"}:
                self._error(400, f'Modo inválido: "{mode}"')
                return

            ok, out = vbox("controlvm", sanitize_vm_name(vm_name), mode)
            if ok:
                self._ok(message=f'VM "{vm_name}" detenida ({mode})')
            else:
                self._error(500, out)

        # POST /vbox/deploy
        # Body: {"nodes": [...]}
        elif path == "/vbox/deploy":
            nodes = body.get("nodes", [])
            if not isinstance(nodes, list):
                self._error(400, '"nodes" debe ser una lista')
                return

            vm_dir = os.path.expanduser("~/VirtualBox VMs")

            ok, out = vbox("list", "vms")
            existing_vms = parse_vms_output(out) if ok else []

            log_msgs = []
            for node in nodes:
                name = node.get("name")
                if not name or name == "jumpstart":
                    continue
                
                if name in existing_vms:
                    vbox("controlvm", sanitize_vm_name(name), "poweroff")
                    vbox("unregistervm", sanitize_vm_name(name), "--delete")
                    log_msgs.append(f"Eliminada VM previa '{name}'")
                
                specs = node.get("vbox_specs", {})
                cpus = str(specs.get("cpus", 1))
                ram = str(specs.get("ram_mb", 1024))
                disk_gb = specs.get("disk_gb", 20)
                
                # 1. Crear VM
                ok, err = vbox("createvm", "--name", sanitize_vm_name(name), "--ostype", "Ubuntu_64", "--register")
                if not ok:
                    self._error(500, f"Error creando VM {name}: {err}")
                    return

                # 2. Configurar hardware y redes
                cmd_modify = [
                    "modifyvm", sanitize_vm_name(name),
                    "--cpus", cpus,
                    "--memory", ram,
                    "--boot1", "net",
                    "--boot2", "disk",
                    "--boot3", "none",
                    "--boot4", "none",
                    "--vram", "16",
                    "--graphicscontroller", "vmsvga"
                ]
                networks = node.get("networks", [])
                for idx, net in enumerate(networks, start=1):
                    net_type = net.get("type", "intnet")
                    cmd_modify += [f"--nic{idx}", net_type]
                    if net_type == "intnet":
                        cmd_modify += [f"--intnet{idx}", net.get("name")]
                    if idx == 1 and node.get("mac"):
                        mac_clean = node.get("mac").replace(":", "").replace("-", "").upper()
                        cmd_modify += [f"--macaddress{idx}", mac_clean]
                
                vbox(*cmd_modify)

                # 3. Crear controlador SATA y disco
                vbox("storagectl", sanitize_vm_name(name), "--name", "SATA Controller", "--add", "sata", "--controller", "IntelAHCI")
                
                disk_path = os.path.join(vm_dir, sanitize_vm_name(name), f"{sanitize_vm_name(name)}.vdi")
                os.makedirs(os.path.dirname(disk_path), exist_ok=True)
                
                if vbox("createmedium", "disk", "--filename", disk_path, "--size", str(disk_gb * 1024), "--format", "VDI")[0]:
                    vbox("storageattach", sanitize_vm_name(name), "--storagectl", "SATA Controller", "--port", "0", "--device", "0", "--type", "hdd", "--medium", disk_path)

                # 4. Encender VM
                vbox("startvm", sanitize_vm_name(name), "--type", "headless")
                log_msgs.append(f"Desplegada y encendida VM '{name}'")

            self._ok(message="Despliegue completado", details=log_msgs)

        # POST /vbox/undeploy
        # Body: {"nodes": [...]}
        elif path == "/vbox/undeploy":
            nodes = body.get("nodes", [])
            if not isinstance(nodes, list):
                self._error(400, '"nodes" debe ser una lista')
                return

            ok, out = vbox("list", "vms")
            existing_vms = parse_vms_output(out) if ok else []

            log_msgs = []
            for node in nodes:
                name = node.get("name")
                if not name or name == "jumpstart":
                    continue
                
                if name in existing_vms:
                    vbox("controlvm", sanitize_vm_name(name), "poweroff")
                    if vbox("unregistervm", sanitize_vm_name(name), "--delete")[0]:
                        log_msgs.append(f"VM '{name}' eliminada")
            
            self._ok(message="Desinstalación completada", details=log_msgs)

        else:
            self._error(404, f"Endpoint no encontrado: {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VBox API Server — REST API para VBoxManage")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Puerto de escucha (por defecto: {DEFAULT_PORT})")
    parser.add_argument("--bind", default=DEFAULT_BIND,
                        help=f"Dirección IP de escucha (por defecto: {DEFAULT_BIND})")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("  GAR — VBox API Server")
    log.info("  Escuchando en http://%s:%d", args.bind, args.port)
    log.info("=" * 60)
    log.info("Endpoints disponibles:")
    log.info("  GET  /health")
    log.info("  GET  /vbox/vms")
    log.info("  GET  /vbox/running-vms")
    log.info("  GET  /vbox/vm-info?vm=<nombre>")
    log.info("  POST /vbox/set-boot-order  {\"vm\": \"...\", \"boot\": [\"disk\", \"net\"]}")
    log.info("  POST /vbox/start           {\"vm\": \"...\", \"type\": \"headless\"}")
    log.info("  POST /vbox/stop            {\"vm\": \"...\", \"mode\": \"poweroff\"}")
    log.info("=" * 60)

    server = http.server.HTTPServer((args.bind, args.port), VBoxAPIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor detenido manualmente.")
        server.server_close()


if __name__ == "__main__":
    main()
