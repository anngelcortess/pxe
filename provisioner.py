#!/usr/bin/env python3
import os
import sys
import argparse
import urllib.request

from gar_orchestrator.parsers import load_all_nodes
from gar_orchestrator.validators import validate_nodes
from gar_orchestrator.vbox_client import deploy_virtualbox_vms, undeploy_virtualbox_vms, finalize_node, start_virtualbox_vms, stop_virtualbox_vms, get_existing_vms
from gar_orchestrator.config_generator import generate_pxe_configs

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
                f"  ✗ vbox-api (Host)\n"
                f"    No responde en: {vbox_url}\n"
                f"    → Arranca el servicio en el Host: ./host_service.sh start"
            )
        else:
            print("[✓] vbox-api (Host) — OK")

    if need_callback:
        cb_url = "http://localhost:8081/health"
        if not _check_service(cb_url):
            errors.append(
                f"  ✗ provision-callback (Jumpstart)\n"
                f"    No responde en: {cb_url}\n"
                f"    → Arranca el servicio: systemctl start provision-callback"
            )
        else:
            print("[✓] provision-callback (Jumpstart) — OK")

    if errors:
        print("\n[-] Preflight check fallido. Servicios no disponibles:\n")
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

    # Subcomando: finalize-node
    parser_finalize = subparsers.add_parser('finalize-node', parents=[parent_parser], help="Finalizar aprovisionamiento de un nodo (uso interno)")
    parser_finalize.add_argument('node', help="Nombre del nodo a finalizar")

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
            print(f"\n[!] Ya existen VMs de un despliegue anterior: {', '.join(conflicting)}")
            print("    Continuar las ELIMINARÁ y creará de nuevo desde cero.")
            confirm = input("\n    ¿Deseas continuar? (s/N): ").strip().lower()
            if confirm not in ('s', 'si', 'sí', 'y', 'yes'):
                print("[-] Despliegue cancelado por el usuario.")
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

    elif args.action == 'finalize-node':
        if not args.node:
            print("[-] Error: la acción finalize-node requiere un nodo explícito.")
            sys.exit(1)
        preflight_checks(host_api_url, need_vbox=True)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        is_live = os.path.exists('/srv/tftp')
        tftp_pxe_dir = '/srv/tftp/pxelinux.cfg' if is_live else os.path.join(script_dir, '.local_output', 'pxe', 'pxelinux.cfg')
        success = finalize_node(args.node, nodes, host_api_url, tftp_pxe_dir=tftp_pxe_dir, templates_dir=args.templates_dir)
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
