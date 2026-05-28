#!/usr/bin/env bash
# ==============================================================================
# Script de gestión para el servicio provisioning-coordinator en el Jumpstart
# ==============================================================================
set -euo pipefail

SERVICE_NAME="provisioning-coordinator"

# Pedir elevación de privilegios solo para acciones que lo requieren
if [[ "$EUID" -ne 0 && "${1:-}" =~ ^(start|stop|restart)$ ]]; then
    echo "Por favor, ejecuta esta acción con sudo."
    exit 1
fi

case "${1:-}" in
    start)
        echo "[*] Iniciando orquestador..."
        systemctl start "${SERVICE_NAME}"
        ;;
    stop)
        echo "[*] Deteniendo orquestador..."
        systemctl stop "${SERVICE_NAME}"
        ;;
    restart)
        echo "[*] Reiniciando orquestador..."
        systemctl restart "${SERVICE_NAME}"
        echo "[+] Orquestador reiniciado!"
        ;;
    status)
        systemctl status "${SERVICE_NAME}" || true
        ;;
    logs)
        echo "[*] Mostrando logs en tiempo real del Orquestador (Ctrl+C para salir)..."
        journalctl -u "${SERVICE_NAME}" -f
        ;;
    *)
        echo "========================================================"
        echo "  Controlador del Orquestador de GAR (Jumpstart)        "
        echo "========================================================"
        echo "Uso: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Nota: A diferencia del host_service, la instalación de este"
        echo "      demonio se realiza automáticamente vía Ansible al"
        echo "      hacer el bootstrap del Jumpstart."
        exit 1
        ;;
esac
