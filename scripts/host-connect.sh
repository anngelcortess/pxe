#!/usr/bin/env bash
# ==============================================================================
# Herramienta rápida para el Host (tbworkers)
# Enciende el jumpstart, lanza VirtualBox opcionalmente y te conecta por SSH
# ==============================================================================
set -e

VM_NAME="jumpstart"
JUMPSTART_IP="192.168.56.10" # IP de la red Host-Only por defecto
SSH_USER="admin"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Uso: $0 [--gui]"
    echo ""
    echo "Opciones:"
    echo "  --gui    Abre la interfaz gráfica de VirtualBox en segundo plano (requiere X11)"
    exit 0
fi

# 1. Abrir GUI si se solicita
if [[ "${1:-}" == "--gui" ]]; then
    if pgrep -x "VirtualBox" > /dev/null || pgrep -x "VirtualBoxVM" > /dev/null; then
        echo "[✓] VirtualBox Manager ya está abierto."
    else
        echo "[*] Abriendo VirtualBox Manager en segundo plano (X11)..."
        if command -v VirtualBox >/dev/null 2>&1; then
            VirtualBox &
        else
            echo "[-] Error: Comando 'VirtualBox' no encontrado."
        fi
    fi
fi

# 2. Comprobar estado de la VM
echo "[*] Comprobando estado de la máquina virtual '$VM_NAME'..."
# Fallback a poweroff si el grep no encuentra el estado o la VM no existe aún
VM_STATE=$(VBoxManage showvminfo "$VM_NAME" --machinereadable 2>/dev/null | grep "^VMState=" | cut -d'"' -f2 || echo "poweroff")

if [[ "$VM_STATE" == "poweroff" || "$VM_STATE" == "aborted" || "$VM_STATE" == "saved" ]]; then
    echo "[+] La VM estaba apagada. Encendiendo '$VM_NAME' en modo headless..."
    VBoxManage startvm "$VM_NAME" --type headless
elif [[ "$VM_STATE" == "running" ]]; then
    echo "[✓] La máquina '$VM_NAME' ya está en ejecución."
else
    echo "[!] Estado inusual detectado ($VM_STATE). Intentando continuar..."
fi

# 3. Esperar al SSH usando el pseudo-dispositivo de red de bash (sin depender de netcat)
echo -n "[*] Esperando a que el puerto SSH esté abierto en ${JUMPSTART_IP} "
while ! timeout 1 bash -c "</dev/tcp/${JUMPSTART_IP}/22" 2>/dev/null; do
    echo -n "."
    sleep 2
done
echo " ¡Puerto abierto!"

# 4. Conectar
echo "[🚀] Entrando por SSH a ${SSH_USER}@${JUMPSTART_IP}..."
echo "--------------------------------------------------------"
exec ssh -o StrictHostKeyChecking=no "${SSH_USER}@${JUMPSTART_IP}"
