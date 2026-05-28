#!/usr/import/env python3
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

from provisioning.orchestrator.parsers import load_all_nodes, load_settings_file
from provisioning.orchestrator.validators import validate_nodes
from provisioning.orchestrator.baremetal import undeploy_virtualbox_vms, start_virtualbox_vms, stop_virtualbox_vms, get_existing_vms
from provisioning.orchestrator.coordinator import run_callback_server
from provisioning.orchestrator.config_generator import generate_pxe_configs
from provisioning.orchestrator.ansible_runner import provision_all_nodes

GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
NC = '\033[0m'

def _check_service(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def preflight_checks(host_api_url, settings, need_vbox=False, need_callback=False):
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
        callback_port = settings.get('jumpstart', {}).get('callback_port', 8081)
        cb_url = f"http://localhost:{callback_port}/health"
        if not _check_service(cb_url):
            errors.append(
                f"  {RED}✗{NC} config-manager (Coordinador local)\n"
                f"    No responde en: {cb_url}\n"
                f"    → Arranca el servicio: systemctl start config-manager"
            )
        else:
            print(f"[{GREEN}✓{NC}] config-manager (Coordinador) — OK")

    if errors:
        print(f"\n[{RED}-{NC}] Preflight check fallido. Servicios no disponibles:\n")
        for e in errors:
            print(e)
        print()
        sys.exit(1)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_nodes_dir = os.path.join(script_dir, "config", "nodes")
    default_templates_dir = os.path.join(script_dir, "templates")

    parser = argparse.ArgumentParser(description="Orquestador Dinámico PXE/VirtualBox para GAR")
    subparsers = parser.add_subparsers(dest='action', required=True, help="Acción a realizar")

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--nodes-dir', default=default_nodes_dir, help=f"Directorio con archivos YAML de nodos")
    parent_parser.add_argument('--templates-dir', default=default_templates_dir, help=f"Directorio con plantillas Autoinstall")
    parent_parser.add_argument('--vm-dir', default="/home/Chadry/VirtualBox VMs", help="Ruta base para los discos virtuales en el host")

    parser_validate = subparsers.add_parser('validate', parents=[parent_parser], help="Validar la sintaxis y reglas de los YAMLs de la maqueta")

    parser_deploy = subparsers.add_parser('deploy', parents=[parent_parser], help="Desplegar las VMs en VirtualBox a partir de la maqueta")
    parser_deploy.add_argument('node', nargs='?', help="Nombre de un nodo específico para desplegar (opcional, por defecto todos)")

    parser_undeploy = subparsers.add_parser('undeploy', parents=[parent_parser], help="Eliminar las VMs de VirtualBox (excepto jumpstart)")
    parser_undeploy.add_argument('node', nargs='?', help="Nombre de un nodo específico para desinstalar (opcional, por defecto todos)")

    parser_generate = subparsers.add_parser('generate-configs', parents=[parent_parser], help="Generar configuraciones PXE, DHCP y Autoinstall")

    parser_provision = subparsers.add_parser('provision', parents=[parent_parser], help="Aprovisionar software (Ansible) en las VMs de forma directa")
    parser_provision.add_argument('node', nargs='*', help="Nombres de los nodos a aprovisionar (opcional, por defecto todos)")

    parser_listen = subparsers.add_parser('listen-callbacks', parents=[parent_parser], help=argparse.SUPPRESS)
    parser_listen.add_argument('--port', type=int, default=None, help=argparse.SUPPRESS)

    parser_start = subparsers.add_parser('start', parents=[parent_parser], help="Iniciar las VMs en VirtualBox (excepto jumpstart)")
    parser_start.add_argument('node', nargs='?', help="Nombre de un nodo específico para iniciar (opcional, por defecto todos)")
    parser_start.add_argument('--type', choices=['headless', 'gui', 'separate'], default='headless', help="Modo de inicio de la VM (headless, gui, separate)")

    parser_stop = subparsers.add_parser('stop', parents=[parent_parser], help="Detener las VMs en VirtualBox (excepto jumpstart)")
    parser_stop.add_argument('node', nargs='?', help="Nombre de un nodo específico para detener (opcional, por defecto todos)")
    parser_stop.add_argument('--mode', choices=['poweroff', 'acpipowerbutton', 'savestate', 'pause', 'resume'], default='poweroff', help="Modo de parada de la VM (poweroff, acpipowerbutton, savestate, pause, resume)")

    args = parser.parse_args()
    
    nodes = load_all_nodes(args.nodes_dir)
    if not nodes:
        print("[-] Error: No se encontraron definiciones de nodos YAML.")
        sys.exit(1)
    settings_path = os.path.join(script_dir, "config", "settings.yml")
    settings = load_settings_file(settings_path)
    
    host_api_ip = settings.get('host_api', {}).get('ip', '192.168.56.1')
    host_api_port = settings.get('host_api', {}).get('port', 7070)
    host_api_url = f"http://{host_api_ip}:{host_api_port}"
    
    if args.action == 'validate':
        success = validate_nodes(nodes)
        sys.exit(0 if success else 1)
        
    elif args.action == 'deploy':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando despliegue.")
            sys.exit(1)
        preflight_checks(host_api_url, settings, need_vbox=True, need_callback=True)
            
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

        print("[*] Generando configuraciones de red antes del despliegue...")
        generate_pxe_configs(nodes, args.templates_dir)
            
        deploy_nodes = nodes
        if args.node:
            deploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not deploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML.")
                sys.exit(1)
                
        # Enviar al coordinador central
        callback_port = settings.get('jumpstart', {}).get('callback_port', 8081)
        url = f"http://127.0.0.1:{callback_port}/start-batch-deploy"
        payload = json.dumps({"vms": deploy_nodes}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header('Content-Type', 'application/json')
        req.add_header('Content-Length', str(len(payload)))
        try:
            with urllib.request.urlopen(req) as response:
                print(f"[{GREEN}✓{NC}] ¡Despliegue escalonado iniciado!")
                print(f"    El Coordinador Residente gestionará la instalación asíncrona de las VMs.")
                print(f"    Puedes monitorear el progreso revisando los logs del servicio:")
                print(f"    {CYAN}journalctl -u config-manager -f{NC}")
        except Exception as e:
            print(f"[{RED}!{NC}] Error contactando con el Coordinador local en {url}: {e}")
            sys.exit(1)
        
    elif args.action == 'undeploy':
        if not validate_nodes(nodes):
            sys.exit(1)
        preflight_checks(host_api_url, settings, need_vbox=True)
            
        undeploy_nodes = nodes
        if args.node:
            undeploy_nodes = [n for n in nodes if n.get('name') == args.node]
        undeploy_virtualbox_vms(undeploy_nodes, host_api_url)
        
    elif args.action == 'generate-configs':
        if not validate_nodes(nodes):
            sys.exit(1)
        generate_pxe_configs(nodes, args.templates_dir)

    elif args.action == 'start':
        preflight_checks(host_api_url, settings, need_vbox=True)
        start_nodes = nodes
        if args.node:
            start_nodes = [n for n in nodes if n.get('name') == args.node]
        start_virtualbox_vms(start_nodes, host_api_url, args.type)

    elif args.action == 'stop':
        preflight_checks(host_api_url, settings, need_vbox=True)
        stop_nodes = nodes
        if args.node:
            stop_nodes = [n for n in nodes if n.get('name') == args.node]
        stop_virtualbox_vms(stop_nodes, host_api_url, args.mode)

    elif args.action == 'provision':
        target_names = args.node if args.node else [n.get('name') for n in nodes if n.get('name') != 'jumpstart']
        print(f"[*] Iniciando aprovisionamiento directo de Ansible para: {', '.join(target_names)}")
        target_nodes = [n for n in nodes if n.get('name') in target_names]
        provision_all_nodes(target_nodes)

    elif args.action == 'listen-callbacks':
        port = args.port if args.port else settings.get('jumpstart', {}).get('callback_port', 8081)
        run_callback_server(nodes, host_api_url, port=port)

if __name__ == '__main__':
    main()
