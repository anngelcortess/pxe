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
import threading
import time

from gar_orchestrator.parsers import load_settings_file

# ── Configuración por defecto ──────────────────────────────────────────────────
base_dir = os.path.dirname(os.path.abspath(__file__))
settings = load_settings_file(os.path.join(base_dir, "config", "settings.yml"))

DEFAULT_PORT = settings.get('host_api', {}).get('port', 7070)
DEFAULT_BIND = settings.get('host_api', {}).get('ip', '0.0.0.0')

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

    def _handle_vbox_error(self, err_output):
        """Mapea errores conocidos de VBoxManage a códigos HTTP correctos."""
        if "VBOX_E_OBJECT_NOT_FOUND" in err_output or "Could not find a registered machine" in err_output:
            self._error(404, err_output)
        elif "VBOX_E_INVALID_OBJECT_STATE" in err_output or "already locked" in err_output or "already running" in err_output:
            self._error(409, err_output) # 409 Conflict
        else:
            self._error(500, err_output)

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
                self._handle_vbox_error(out)

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

            ram_mb = body.get("ram_mb")
            cpus = body.get("cpus")
            if ram_mb:
                args += ["--memory", str(ram_mb)]
            if cpus:
                args += ["--cpus", str(cpus)]

            def apply_boot_order_bg():
                log.info(f"[{vm_name}] Comprobando estado de la VM antes de aplicar specs finales y orden de arranque...")
                max_retries = 90 # 3 minutos
                for _ in range(max_retries):
                    # Consultar estado de forma segura sin modificar nada
                    ok, out = vbox("showvminfo", sanitize_vm_name(vm_name), "--machinereadable")
                    if ok and 'VMState="poweroff"' in out:
                        log.info(f"[{vm_name}] La VM se ha apagado. Aplicando configuración...")
                        bg_ok, bg_out = vbox("modifyvm", sanitize_vm_name(vm_name), *args)
                        if bg_ok:
                            log.info(f"[{vm_name}] ¡Orden de arranque actualizado! Encendiendo VM...")
                            vbox("startvm", sanitize_vm_name(vm_name), "--type", "headless")
                        else:
                            log.error(f"[{vm_name}] Error al modificar el boot order: {bg_out}")
                        return
                    # Si sigue encendida, esperamos 2 segundos y volvemos a preguntar
                    time.sleep(2)
                
                log.error(f"[{vm_name}] Timeout: la VM no se apagó tras 3 minutos de espera.")

            # Responder 200 OK inmediatamente al curl para que la VM pueda seguir su curso y apagarse
            threading.Thread(target=apply_boot_order_bg, daemon=True).start()
            self._ok(message=f'Operación puesta en cola. Esperando a que "{vm_name}" se apague de forma segura para aplicar los cambios.')

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
                self._handle_vbox_error(out)

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
                self._handle_vbox_error(out)

        # POST /vbox/create-vms
        # Body: {"vms": [...]}
        elif path == "/vbox/create-vms":
            vms = body.get("vms", [])
            if not isinstance(vms, list):
                self._error(400, '"vms" debe ser una lista')
                return

            vm_dir = os.path.expanduser("~/VirtualBox VMs")

            ok, out = vbox("list", "vms")
            existing_vms = parse_vms_output(out) if ok else []

            log_msgs = []
            for vm in vms:
                name = vm.get("name")
                if not name:
                    continue
                
                if name in existing_vms:
                    vbox("controlvm", sanitize_vm_name(name), "poweroff")
                    vbox("unregistervm", sanitize_vm_name(name), "--delete")
                    log_msgs.append(f"Eliminada VM previa '{name}'")
                
                cpus = str(vm.get("cpus", 1))
                ram = str(vm.get("ram_mb", 1024))
                disk_gb = vm.get("disk_gb", 20)
                ostype = vm.get("ostype", "Ubuntu_64")
                vram = str(vm.get("vram", 16))
                graphicscontroller = vm.get("graphicscontroller", "vmsvga")
                
                # 1. Crear VM
                ok, err = vbox("createvm", "--name", sanitize_vm_name(name), "--ostype", ostype, "--register")
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
                    "--vram", vram,
                    "--graphicscontroller", graphicscontroller
                ]
                networks = vm.get("networks", [])
                for idx, net in enumerate(networks, start=1):
                    net_type = net.get("type", "intnet")
                    cmd_modify += [f"--nic{idx}", net_type]
                    if net_type == "intnet":
                        cmd_modify += [f"--intnet{idx}", net.get("name", "")]
                    if net.get("mac"):
                        mac_clean = net.get("mac").replace(":", "").replace("-", "").upper()
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

            self._ok(message="Creación masiva completada", details=log_msgs)

        # POST /vbox/delete-vms
        # Body: {"vms": [{"name": "..."}]}
        elif path == "/vbox/delete-vms":
            vms = body.get("vms", [])
            if not isinstance(vms, list):
                self._error(400, '"vms" debe ser una lista')
                return

            ok, out = vbox("list", "vms")
            existing_vms = parse_vms_output(out) if ok else []

            log_msgs = []
            for vm in vms:
                name = vm.get("name")
                if not name:
                    continue
                
                if name in existing_vms:
                    vbox("controlvm", sanitize_vm_name(name), "poweroff")
                    if vbox("unregistervm", sanitize_vm_name(name), "--delete")[0]:
                        log_msgs.append(f"VM '{name}' eliminada")
            
            self._ok(message="Borrado masivo completado", details=log_msgs)

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
