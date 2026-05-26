#!/usr/bin/env python3
import os
import sys
import argparse

from gar_orchestrator.parsers import load_all_nodes
from gar_orchestrator.validators import validate_nodes
from gar_orchestrator.vbox_client import deploy_virtualbox_vms, undeploy_virtualbox_vms, finalize_node
from gar_orchestrator.config_generator import generate_pxe_configs

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_nodes_dir = os.path.join(script_dir, "baremetal", "nodes")
    default_templates_dir = os.path.join(script_dir, "baremetal", "templates")

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

    args = parser.parse_args()
    
    nodes = load_all_nodes(args.nodes_dir)
    if not nodes:
        print("[-] Error: No se encontraron definiciones de nodos YAML.")
        sys.exit(1)
        
    if args.action == 'validate':
        success = validate_nodes(nodes)
        sys.exit(0 if success else 1)
        
    elif args.action == 'deploy':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando despliegue de VMs.")
            sys.exit(1)
            
        deploy_nodes = nodes
        if args.node:
            deploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not deploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        deploy_virtualbox_vms(deploy_nodes, args.vm_dir)
        
    elif args.action == 'undeploy':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando desinstalación.")
            sys.exit(1)
            
        undeploy_nodes = nodes
        if args.node:
            undeploy_nodes = [n for n in nodes if n.get('name') == args.node]
            if not undeploy_nodes:
                print(f"[-] Error: El nodo '{args.node}' no está definido en los archivos YAML del directorio '{args.nodes_dir}'.")
                sys.exit(1)
        undeploy_virtualbox_vms(undeploy_nodes)
        
    elif args.action == 'generate-configs':
        if not validate_nodes(nodes):
            print("[-] Error de validación en los YAML. Abortando generación de configs.")
            sys.exit(1)
            
        generate_pxe_configs(nodes, args.templates_dir)

    elif args.action == 'finalize-node':
        if not args.node:
            print("[-] Error: la acción finalize-node requiere un nodo explícito.")
            sys.exit(1)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        is_live = os.path.exists('/srv/tftp')
        tftp_pxe_dir = '/srv/tftp/pxelinux.cfg' if is_live else os.path.join(script_dir, 'baremetal', 'pxe', 'pxelinux.cfg')
        success = finalize_node(args.node, nodes, tftp_pxe_dir=tftp_pxe_dir, templates_dir=args.templates_dir)
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
