import os
import sys

# Intentar importar PyYAML. Si no está instalado, se usa un parser YAML básico fallback para evitar fallos de dependencias.
try:
    import yaml
except ImportError:
    yaml = None

def parse_simple_yaml(filepath):
    """
    Parser fallback muy simple para ficheros YAML básicos de definición de nodos.
    Soporta pares clave-valor y listas indentadas de un nivel.
    """
    data = {}
    current_key = None
    current_list = None
    current_map_in_list = None

    with open(filepath, 'r') as f:
        for line in f:
            line_raw = line.split('#')[0] # Eliminar comentarios
            if not line_raw.strip():
                continue
            
            # Detectar indentación
            indent = len(line_raw) - len(line_raw.lstrip())
            line_stripped = line_raw.strip()

            if line_stripped.startswith('-'):
                # Es un elemento de lista
                item_content = line_stripped[1:].strip()
                if current_list is not None:
                    if ':' in item_content:
                        # Lista de mapas (ej. interfaces)
                        if indent > 2:
                            # Continuación de mapa en lista
                            key, val = item_content.split(':', 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if val.startswith('[') and val.endswith(']'):
                                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                            if current_map_in_list is not None:
                                current_map_in_list[key] = val
                        else:
                            # Nuevo elemento de mapa en lista
                            key, val = item_content.split(':', 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if val.startswith('[') and val.endswith(']'):
                                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                            current_map_in_list = {key: val}
                            current_list.append(current_map_in_list)
                    else:
                        # Lista simple
                        item_content = item_content.strip('"').strip("'")
                        current_list.append(item_content)
                continue

            if ':' in line_stripped:
                key, val = line_stripped.split(':', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if not val: # Inicio de un bloque (mapa o lista)
                    current_key = key
                    current_list = []
                    data[current_key] = current_list
                    current_map_in_list = None
                else:
                    if val.startswith('[') and val.endswith(']'): # Lista inline ej [8.8.8.8, 8.8.4.4]
                        val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
                    elif val.lower() == 'true':
                        val = True
                    elif val.lower() == 'false':
                        val = False
                    else:
                        try:
                            val = int(val)
                        except ValueError:
                            pass
                    
                    if indent > 0 and current_map_in_list is not None:
                        current_map_in_list[key] = val
                    else:
                        data[key] = val
                        current_list = None
                        current_key = None

    # Limpieza de listas vacías si resultaron ser mapas simples
    for k in list(data.keys()):
        if isinstance(data[k], list) and len(data[k]) == 0:
            # Re-analizar si era un mapa indentado en vez de lista
            pass
    return data

def load_node_file(filepath):
    """Carga y procesa un archivo YAML de nodo, usando PyYAML o el parser de fallback."""
    if yaml:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    else:
        return parse_simple_yaml(filepath)

def load_all_nodes(nodes_dir):
    """Carga todos los nodos del directorio especificado."""
    nodes = []
    if not os.path.isdir(nodes_dir):
        print(f"[-] Error: El directorio {nodes_dir} no existe.")
        return nodes
    
    for filename in sorted(os.listdir(nodes_dir)):
        if filename.endswith('.yml') or filename.endswith('.yaml'):
            filepath = os.path.join(nodes_dir, filename)
            try:
                node_data = load_node_file(filepath)
                if node_data and 'name' in node_data:
                    nodes.append(node_data)
            except Exception as e:
                print(f"[-] Error al parsear {filename}: {e}")
    return nodes

def load_networks_file(filepath):
    """Carga la definición de redes desde networks.yml. Retorna una lista de redes."""
    if not os.path.exists(filepath):
        print(f"[-] Error: No se encontró el archivo de definición de redes en {filepath}.")
        return []
        
    try:
        data = load_node_file(filepath) # load_node_file ya procesa YAML con fallback simple
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
        if yaml:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        else:
            print("[-] Advertencia: PyYAML no instalado, no se puede parsear settings.yml complejo.")
            return {}
    except Exception as e:
        print(f"[-] Error al parsear settings en {filepath}: {e}.")
        return {}
