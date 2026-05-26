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

echo -e "${BLUE}=== INICIANDO BOOTSTRAP DEL SERVIDOR JUMPSTART ===${NC}"

# 1. Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[-] Error: Este script debe ser ejecutado como root o con sudo.${NC}"
    exit 1
fi

# 2. Identificar las interfaces de red de la máquina
# Adaptadores VirtualBox del Jumpstart (4 interfaces):
# - enp0s3:  NAT         (Salida a Internet - DHCP automático)
# - enp0s8:  Host-Only   (Acceso SSH desde el Host - IP estática 192.168.56.10, fuera del rango DHCP .101-.254)
# - enp0s9:  intnet_main (Red Main - IP estática 192.168.1.254)
# - enp0s10: intnet_internal (Red Internal - IP estática 192.168.2.254)
echo -e "${YELLOW}[*] Configurando interfaces de red (Netplan)...${NC}"

# 2.1 Desactivar la configuración de red automática de cloud-init para que no pise nuestro Netplan al reiniciar
if [ -d /etc/cloud/cloud.cfg.d ]; then
    echo -e "${YELLOW}[*] Desactivando configuración de red de cloud-init para persistencia...${NC}"
    echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
fi

# Eliminar el archivo por defecto de cloud-init para evitar conflictos
rm -f /etc/netplan/50-cloud-init.yaml

cat <<EOF > /etc/netplan/99-manual-networks.yaml
network:
    version: 2
    ethernets:
        enp0s3:
            dhcp4: true
        enp0s8:
            dhcp4: false
            addresses:
                - 192.168.56.10/24
        enp0s9:
            dhcp4: false
            addresses:
                - 192.168.1.254/24
        enp0s10:
            dhcp4: false
            addresses:
                - 192.168.2.254/24
EOF

echo -e "${GREEN}[+] Archivo Netplan generado. Aplicando configuración...${NC}"
netplan apply
sleep 2

# 3. Instalación de dependencias del sistema
echo -e "${YELLOW}[*] Actualizando repositorios e instalando paquetes necesarios...${NC}"
apt-get update
apt-get install -y \
    tftpd-hpa \
    isc-dhcp-server \
    apache2 \
    syslinux \
    pxelinux \
    syslinux-common \
    wget \
    python3 \
    python3-yaml \
    git

# 4. Configurar el Servidor TFTP
echo -e "${YELLOW}[*] Configurando servidor TFTP (tftpd-hpa)...${NC}"
mkdir -p /srv/tftp/pxelinux.cfg
mkdir -p /srv/tftp/images

# Copiar archivos del bootloader PXE
cp /usr/lib/PXELINUX/pxelinux.0 /srv/tftp/
cp /usr/lib/syslinux/modules/bios/*.c32 /srv/tftp/

# Escribir archivo de configuración de TFTP
cat <<EOF > /etc/default/tftpd-hpa
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="/srv/tftp"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure"
EOF

systemctl restart tftpd-hpa
systemctl enable tftpd-hpa
echo -e "${GREEN}[+] Servidor TFTP configurado y reiniciado.${NC}"

# 5. Configurar interfaces en el servidor DHCP
echo -e "${YELLOW}[*] Especificando interfaces para el servidor DHCP...${NC}"
cat <<EOF > /etc/default/isc-dhcp-server
# Escuchar en las dos redes internas (main e internal)
INTERFACESv4="enp0s9 enp0s10"
INTERFACESv6=""
EOF

# 6. Preparar directorios de instalación y descargar ISO de Ubuntu 22.04 LTS
ISO_DIR="/var/www/html/ubuntu-22.04"
KERNEL_DIR="/srv/tftp/images/ubuntu-22.04"

mkdir -p "$ISO_DIR"
mkdir -p "$KERNEL_DIR"

ISO_PATH="${ISO_DIR}/ubuntu-22.04.5-live-server-amd64.iso"

if [ ! -f "$ISO_PATH" ]; then
    echo -e "${YELLOW}[*] Descargando ISO de Ubuntu Server 22.04 LTS (1.4 GB)...${NC}"
    echo -e "${YELLOW}    Esto puede tardar unos minutos dependiendo de la conexión.${NC}"
    wget -q --show-progress -O "$ISO_PATH" https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso
    echo -e "${GREEN}[+] Descarga completada.${NC}"
else
    echo -e "${GREEN}[+] ISO de Ubuntu Server 22.04 ya presente. Omitiendo descarga.${NC}"
fi

# Extraer vmlinuz e initrd de la ISO
echo -e "${YELLOW}[*] Extrayendo kernel e initrd de la ISO...${NC}"
MOUNT_DIR="/mnt/ubuntu-iso-temp"
mkdir -p "$MOUNT_DIR"

mount -o loop,ro "$ISO_PATH" "$MOUNT_DIR"
cp "${MOUNT_DIR}/casper/vmlinuz" "$KERNEL_DIR/"
cp "${MOUNT_DIR}/casper/initrd" "$KERNEL_DIR/"
umount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"
echo -e "${GREEN}[+] Kernel e initrd extraídos y ubicados en el servidor TFTP.${NC}"

# 7. Asegurar permisos correctos en directorios compartidos
chown -R tftp:tftp /srv/tftp
chmod -R 755 /srv/tftp
chown -R www-data:www-data /var/www/html
chmod -R 755 /var/www/html

# 8. Generar las llaves SSH SSH en Jumpstart si no existen
if [ ! -f /root/.ssh/id_rsa ]; then
    echo -e "${YELLOW}[*] Generando par de llaves SSH para automatización con Ansible...${NC}"
    mkdir -p /root/.ssh
    ssh-keygen -t rsa -b 2048 -f /root/.ssh/id_rsa -N ""
    echo -e "${GREEN}[+] Llave SSH generada.${NC}"
fi

# 9. Ejecutar el Aprovisionador dinámico en Python para generar DHCP, menús PXE y Autoinstalls
echo -e "${YELLOW}[*] Ejecutando aprovisionador de nodos para generar configuraciones finales...${NC}"

# Dar permisos de ejecución al script si no los tiene
chmod +x ../provisioner.py

# Ejecutar la acción de generación de configuraciones del aprovisionador en caliente
../provisioner.py generate-configs

# 10. Iniciar y habilitar todos los servicios del Jumpstart
echo -e "${YELLOW}[*] Iniciando y habilitando servicios de red...${NC}"
systemctl restart isc-dhcp-server || {
    echo -e "${RED}[-] Advertencia: isc-dhcp-server falló al iniciar. Esto es normal si no hay clientes conectados físicamente aún.${NC}"
}
systemctl enable isc-dhcp-server

systemctl restart apache2
systemctl enable apache2

echo -e "${YELLOW}[*] Instalando servicio de callback de aprovisionamiento (provision-callback)...${NC}"

# Determinar ruta del repositorio (un nivel arriba del directorio scripts)
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Actualizar la ruta del ExecStart en el .service según la ubicación real del repo
CALLBACK_SERVICE_SRC="${REPO_DIR}/services/provision-callback.service"
sed "s|/root/trabajo|${REPO_DIR}|g" "$CALLBACK_SERVICE_SRC" > /etc/systemd/system/provision-callback.service

systemctl daemon-reload
systemctl enable provision-callback
systemctl restart provision-callback
echo -e "${GREEN}[+] Servicio provision-callback activo en el puerto 8081.${NC}"
echo -e "    Diagnóstico: curl http://localhost:8081/health"

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
echo -e "${GREEN}  ./host_service.sh install    # Para instalar y activar el servicio en segundo plano${NC}"
echo -e "${GREEN}  ./host_service.sh logs       # Para ver los logs en tiempo real${NC}"
echo ""

echo -e "${BLUE}Verifica desde el Jumpstart que el servidor responde:${NC}"
echo -e "${GREEN}  curl http://192.168.56.1:7070/health${NC}"
echo ""
echo -e "${BLUE}Próximo paso: Arrancar los nodos cliente en modo red PXE.${NC}"
echo -e "${GREEN}====================================================${NC}"

echo -e "Haciendo el script ejecutable..."
chmod +x "$0"
