#!/usr/bin/env python3
import os
import sys
import argparse
import urllib.request

from gar_orchestrator.parsers import load_all_nodes
from gar_orchestrator.validators import validate_nodes
from gar_orchestrator.baremetal import deploy_virtualbox_vms, undeploy_virtualbox_vms, start_virtualbox_vms, stop_virtualbox_vms, get_existing_vms
from gar_orchestrator.provisioning import run_callback_server, provision_nodes
from gar_orchestrator.config_generator import generate_pxe_configs

GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
NC = '\033[0m'

# ── Preflight checks ──────────────────────────────────────────────────────────

def _check_service(url, timeout=5):
    """Comprueba que un servicio HTTP responde en /health."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def preflight_checks(host_api_url, need_vbox=False, need_callback=False):
    """Verifica que los servicios necesarios estén activos antes de proceder."""
    errors = []

    if need_vbox:
        vbox_url = f"{host_api_url}/health"
        if not _check_service(vbox_url):
            errors.append(
                f"  {RED}✗{NC} vbox-api (Host)\n"
                f"    No responde en: {vbox_url}\n"
                f"    → Arranca el servicio en el Host: ./host_service.sh start"
            )
        else:
            print(f"[{GREEN}✓{NC}] vbox-api (Host) — OK")

    if need_callback:
        cb_url = "http://localhost:8081/health"
        if not _check_service(cb_url):
            errors.append(
                f"  {RED}✗{NC} config-manager (Jumpstart)\n"
                f"    No responde en: {cb_url}\n"
                f"    → Arranca el servicio: systemctl start config-manager"
            )
        else:
            print(f"[{GREEN}✓{NC}] config-manager (Jumpstart) — OK")

    if errors:
        print(f"\n[{RED}-{NC}] Preflight check fallido. Servicios no disponibles:\n")
        for e in errors:
            print(e)
        print()
        sys.exit(1)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_nodes_dir = os.path.join(script_dir, "config", "nodes")
    default_templates_dir = os.path.join(script_dir, "templates")

    parser = argparse.ArgumentParser(description="Orquestador Dinámico PXE/VirtualBox para GAR")
    subparsers = parser.add_subparsers(dest='action', required=True, help="Acción a realizar")

    # Argumentos comunes compartidos por los subcomandos
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--nodes-dir', default=default_nodes_dir, help=f"Directorio con archivos YAML de nodos")
    parent_parser.add_argument('--templates-dir', default=default_templates_dir, help=f"Directorio con plantillas Autoinstall")
    parent_parser.add_argument('--vm-dir', default="/home/Chadry/VirtualBox VMs", help="Ruta base para los discos virtuales en el host")

    # Subcomando: validate
    parser_validate = subparsers.add_parser('validate', parents=[parent_parser], help="Validar la sintaxis y reglas de los YAMLs de la maqueta")

    # Subcomando: deploy
    parser_deploy = subparsers.add_parser('deploy', parents=[parent_parser], help="Desplegar las VMs en VirtualBox a partir de la maqueta")
    parser_deploy.add_argument('node', nargs='?', help="Nombre de un nodo específico para desplegar (opcional, por defecto todos)")

    # Subcomando: undeploy
    parser_undeploy = subparsers.add_parser('undeploy', parents=[parent_parser], help="Eliminar las VMs de VirtualBox (excepto jumpstart)")
    parser_undeploy.add_argument('node', nargs='?', help="Nombre de un nodo específico para desinstalar (opcional, por defecto todos)")

    # Subcomando: generate-configs
    parser_generate = subparsers.add_parser('generate-configs', parents=[parent_parser], help="Generar configuraciones PXE, DHCP y Autoinstall")

    # Subcomando: provision
    parser_provision = subparsers.add_parser('provision', parents=[parent_parser], help="Aprovisionar software (Ansible) en las VMs saltándose la fase de baremetal")
    parser_provision.add_argument('node', nargs='*', help="Nombres de los nodos a aprovisionar (opcional, por defecto todos)")

    # Subcomando: listen-callbacks
    parser_listen = subparsers.add_parser('listen-callbacks', parents=[parent_parser], help="Inicia el servidor demonio para escuchar peticiones de finalización PXE")
    parser_listen.add_argument('--port', type=int, default=8081, help="Puerto de escucha (defecto: 8081)")

    # Subcomando: start
    parser_start = subparsers.add_parser('start', parents=[parent_parser], help="Iniciar las VMs en VirtualBox (excepto jumpstart)")
    parser_start.add_argument('node', nargs='?', help="Nombre de un nodo específico para iniciar (opcional, por defecto todos)")
    parser_start.add_argument('--type', choices=['headless', 'gui', 'separate'], default='headless', help="Modo de inicio de la VM (headless, gui, separate)")

    # Subcomando: stop
    parser_stop = subparsers.add_parser('stop', parents=[parent_parser], help="Detener las VMs en VirtualBox (excepto jumpstart)")
    parser_stop.add_argument('node', nargs='?', help="Nombre de un nodo específico para detener (opcional, por defecto todos)")
    parser_stop.add_argument('--mode', choices=['poweroff', 'acpipowerbutton', 'savestate', 'pause', 'resume'], default='poweroff', help="Modo de parada de la VM (poweroff, acpipowerbutton, savestate, pause, resume)")

    args = parser.parse_args()
    
    nodes = load_all_nodes(args.nodes_dir)
    if not nodes:
        print("[-] Error: No se encontraron definiciones de nodos YAML.")
        sys.exit(1)
        
    jumpstart_node = next((n for n in nodes if n.get('name') == 'jumpstart'), {})
    host_api_url = jumpstart_node.get('host_api_url', '').strip().rstrip('/')
        
    if args.action == 'validate':
        success = validate_nodes(nodes)
        sys.exit(0 if success else 1)
        
    elif args.action == 'deploy':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando despliegue de VMs.")
            sys.exit(1)
        preflight_checks(host_api_url, need_vbox=True, need_callback=True)
            
        # Comprobar si ya hay VMs desplegadas de la maqueta
        target_names = [n.get('name') for n in nodes if n.get('name') != 'jumpstart' and n.get('mac')]
        existing = get_existing_vms(host_api_url)
        conflicting = [name for name in target_names if name in existing]
        
        if conflicting:
            print(f"\n[{YELLOW}!{NC}] Ya existen VMs de un despliegue anterior: {', '.join(conflicting)}")
            print(f"    {YELLOW}Continuar las ELIMINARÁ y creará de nuevo desde cero.{NC}")
            confirm = input("\n    ¿Deseas continuar? (s/N): ").strip().lower()
            if confirm not in ('s', 'si', 'sí', 'y', 'yes'):
                print(f"[{YELLOW}-{NC}] Despliegue cancelado por el usuario.")
                sys.exit(0)
            print()

        # Generar configs PXE/DHCP/Autoinstall antes de desplegar (las VMs arrancan por PXE)
        print("[*] Generando configuraciones de red antes del despliegue...")
        generate_pxe_configs(nodes, args.templates_dir)
            
        deploy_nodes = nodes
        if args.node:
            deploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not deploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        deploy_virtualbox_vms(deploy_nodes, host_api_url, args.vm_dir)
        
    elif args.action == 'undeploy':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando desinstalación.")
            sys.exit(1)
        preflight_checks(host_api_url, need_vbox=True)
            
        undeploy_nodes = nodes
        if args.node:
            undeploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not undeploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        undeploy_virtualbox_vms(undeploy_nodes, host_api_url)
        
    elif args.action == 'generate-configs':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando generación de configs.")
            sys.exit(1)
            
        generate_pxe_configs(nodes, args.templates_dir)

    elif args.action == 'start':
        preflight_checks(host_api_url, need_vbox=True)
        start_nodes = nodes
        if args.node:
            start_nodes = [n for n in nodes if n.get('name') == args.node]
            if not start_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML.")
                sys.exit(1)
        start_virtualbox_vms(start_nodes, host_api_url, args.type)

    elif args.action == 'stop':
        preflight_checks(host_api_url, need_vbox=True)
        stop_nodes = nodes
        if args.node:
            stop_nodes = [n for n in nodes if n.get('name') == args.node]
            if not stop_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML.")
                sys.exit(1)
        stop_virtualbox_vms(stop_nodes, host_api_url, args.mode)

    elif args.action == 'provision':
        target_names = args.node if args.node else [n.get('name') for n in nodes if n.get('name') != 'jumpstart']
        print(f"[*] Iniciando aprovisionamiento directo para: {', '.join(target_names)}")
        provision_nodes(target_names, nodes, host_api_url, skip_boot_order=True)

    elif args.action == 'listen-callbacks':
        # Bloquea el hilo principal atendiendo peticiones HTTP
        run_callback_server(nodes, host_api_url, port=args.port)

if __name__ == '__main__':
    main()
