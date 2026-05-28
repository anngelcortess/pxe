#!/usr/bin/env bash
# ==============================================================================
# Script de Bootstrap para el Servidor JUMPSTART (Servidor PXE/DHCP/TFTP/HTTP)
# Asignatura: Gestión y Administración de Redes (GAR)
# ==============================================================================
# Este script automatiza la instalación y configuración de todos los servicios
# necesarios en el nodo Jumpstart para actuar como aprovisionador baremetal.
# Debe ejecutarse con privilegios de administrador (sudo/root) dentro del Jumpstart.
# ==============================================================================

# Detener ejecución ante cualquier error
set -euo pipefail

# Colores para salida por consola
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

# ==============================================================================
# Micro-Bootstrap: Instala Ansible y delega en el Playbook
# ==============================================================================

echo -e "${YELLOW}[*] Actualizando repositorios base e instalando Ansible...${NC}"
apt-get update > /dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y ansible git > /dev/null

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo -e "${YELLOW}[*] Lanzando Playbook de aprovisionamiento del Jumpstart...${NC}"
echo -e "${GREEN}    Ansible se encargará de configurar redes, TFTP, DHCP y descargar ISOs.${NC}"
echo -e "--------------------------------------------------------------------------------"

# Ejecutar el playbook en modo local
cd "$REPO_DIR"
ansible-playbook -i localhost, -c local ansible/playbooks/jumpstart.yml

echo -e "--------------------------------------------------------------------------------"
echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}===  BOOTSTRAP DEL JUMPSTART COMPLETADO CON ÉXITO ===${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "${BLUE}Servicios activos en el Jumpstart:${NC}"
echo -e "  - DHCP/PXE:               ${GREEN}192.168.1.254${NC} y ${GREEN}192.168.2.254${NC}"
echo -e "  - HTTP (ISOs/Autoinstall): ${GREEN}:80${NC}"
echo -e "  - Callback aprovisionamiento: ${GREEN}:8081/node-ready${NC}"
echo ""
echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  ACCIÓN REQUERIDA EN EL HOST (solo una vez por equipo)   ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
echo -e "${BLUE}El Jumpstart necesita comunicarse con el Host para cambiar el${NC}"
echo -e "${BLUE}boot order de las VMs. Para ello, arranca el VBox API Server${NC}"
echo -e "${BLUE}en tu ordenador anfitrión usando nuestro script de control:${NC}"
echo ""
echo -e "${GREEN}  cd /ruta/al/repositorio${NC}"
echo -e "${GREEN}  ./vbox-api-helper.sh install    # Para instalar y activar el servicio en segundo plano${NC}"
echo -e "${GREEN}  ./vbox-api-helper.sh logs       # Para ver los logs en tiempo real${NC}"
echo ""
echo -e "${BLUE}Verifica desde el Jumpstart que el servidor responde:${NC}"
echo -e "${GREEN}  curl http://192.168.56.1:7070/health${NC}"
echo ""
echo -e "${BLUE}Próximo paso: Arrancar los nodos cliente en modo red PXE.${NC}"
echo -e "${GREEN}====================================================${NC}"
