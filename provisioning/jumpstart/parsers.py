import os
import sys

import yaml

def load_node_file(filepath):
    """Carga y procesa un archivo YAML de nodo usando PyYAML."""
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)

def load_all_nodes(nodes_dir):
    """Carga todos los nodos del directorio especificado, buscando recursivamente y aplicando defaults."""
    import copy
    nodes = []
    if not os.path.isdir(nodes_dir):
        print(f"[-] Error: El directorio {nodes_dir} no existe.")
        return nodes
    
    settings_path = os.path.join(os.path.dirname(nodes_dir), "settings.yml")
    settings = load_settings_file(settings_path)
    defaults = settings.get('defaults', {})
    
    def _deep_merge(d1, d2):
        for k, v in d2.items():
            if isinstance(v, dict) and k in d1 and isinstance(d1[k], dict):
                _deep_merge(d1[k], v)
            else:
                d1[k] = v
        return d1

    # Recorrer directorios recursivamente, ordenando para mantener la predictibilidad
    for root, dirs, files in os.walk(nodes_dir):
        dirs.sort()
        for filename in sorted(files):
            if filename.endswith('.yml') or filename.endswith('.yaml'):
                filepath = os.path.join(root, filename)
                try:
                    node_data = load_node_file(filepath)
                    if node_data and 'name' in node_data:
                        merged_node = copy.deepcopy(defaults)
                        node_final = _deep_merge(merged_node, node_data)
                        nodes.append(node_final)
                except Exception as e:
                    print(f"[-] Error al parsear {filename}: {e}")
    return nodes

def load_networks_file(filepath):
    """Carga la definición de redes desde networks.yml. Retorna una lista de redes."""
    if not os.path.exists(filepath):
        print(f"[-] Error: No se encontró el archivo de definición de redes en {filepath}.")
        return []
        
    try:
        data = load_node_file(filepath)
        if data and 'networks' in data:
            return data['networks']
    except Exception as e:
        print(f"[-] Advertencia al parsear redes en {filepath}: {e}.")
    
    return []

def load_settings_file(filepath):
    """Carga la configuración global desde settings.yml."""
    if not os.path.exists(filepath):
        print(f"[-] Advertencia: No se encontró {filepath}. Se usarán valores por defecto locales.")
        return {}
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[-] Error al parsear settings en {filepath}: {e}.")
        return {}
