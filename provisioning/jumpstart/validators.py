import re

def validate_nodes(nodes):
    """Valida la consistencia de todas las definiciones de nodos."""
    print("[*] Iniciando validación de consistencia de la maqueta...")
    errors = 0
    warnings = 0
    
    ips = {}
    macs = {}
    names = set()
    
    for node in nodes:
        name = node.get('name')
        if not name:
            print("[-] Error: Nodo sin nombre definido en archivo.")
            errors += 1
            continue
            
        if name in names:
            print(f"[-] Error: Nombre duplicado '{name}'.")
            errors += 1
        names.add(name)
        
        # Validar MAC
        mac = node.get('mac')
        if mac:
            mac_clean = mac.lower().replace('-', ':')
            if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac_clean):
                print(f"[-] Error [{name}]: Formato de MAC '{mac}' inválido.")
                errors += 1
            if mac_clean in macs:
                print(f"[-] Error [{name}]: Dirección MAC duplicada '{mac}' con '{macs[mac_clean]}'.")
                errors += 1
            macs[mac_clean] = name
            
        # Validar Redes e IPs
        networks = node.get('networks', [])
        if not networks:
            print(f"[!] Warning [{name}]: El nodo no tiene redes definidas.")
            warnings += 1
            
        for i, net in enumerate(networks):
            net_name = net.get('name')
            ip = net.get('ip')
            
            if not net_name:
                print(f"[-] Error [{name}]: Red #{i} sin nombre ('name').")
                errors += 1
                
            if ip:
                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    print(f"[-] Error [{name}]: IP '{ip}' inválida.")
                    errors += 1
                
                ip_key = f"{net_name}/{ip}"
                if ip_key in ips:
                    print(f"[-] Error [{name}]: Conflicto de IP. '{ip}' ya asignada en la red '{net_name}' para el nodo '{ips[ip_key]}'.")
                    errors += 1
                ips[ip_key] = name

        # Validar especificaciones VirtualBox
        specs = node.get('production_specs', {})
        if not specs:
            print(f"[!] Warning [{name}]: Sin especificaciones de hardware production_specs.")
            warnings += 1
            
    print(f"\n[*] Validación finalizada: {errors} errores, {warnings} advertencias.")
    return errors == 0
