#!/usr/bin/env bash
# ==============================================================================
# Script de gestión para el servicio provisioning-coordinator en el Jumpstart
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="provisioning-coordinator"
SERVICE_FILE="${REPO_DIR}/provisioning/services/${SERVICE_NAME}.service"
TARGET_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Pedir elevación de privilegios solo para acciones que lo requieren
if [[ "$EUID" -ne 0 && "${1:-}" =~ ^(install|uninstall|start|stop|restart)$ ]]; then
    echo "Por favor, ejecuta esta acción con sudo o como root."
    exit 1
fi

case "${1:-}" in
    install)
        echo "[*] Instalando servicio a nivel de sistema..."
        sed "s|__REPO_DIR__|${REPO_DIR}|g" "${SERVICE_FILE}" > "${TARGET_FILE}"
        systemctl daemon-reload
        systemctl enable --now "${SERVICE_NAME}"
        echo "[+] Servicio orquestador instalado y activado correctamente!"
        ;;
    uninstall)
        echo "[*] Desinstalando servicio orquestador..."
        systemctl disable --now "${SERVICE_NAME}" || true
        rm -f "${TARGET_FILE}"
        systemctl daemon-reload
        echo "[+] Servicio desinstalado."
        ;;
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
        if [[ "${2:-}" == "-f" ]]; then
            echo "[*] Mostrando logs en tiempo real del Orquestador (Ctrl+C para salir)..."
            journalctl -u "${SERVICE_NAME}" -f
        else
            echo "[*] Mostrando logs estáticos del Orquestador..."
            journalctl -u "${SERVICE_NAME}" --no-pager
        fi
        ;;
    *)
        echo "========================================================"
        echo "  Controlador del Orquestador de GAR (Jumpstart)        "
        echo "========================================================"
        echo "Uso: $0 {install|uninstall|start|stop|restart|status|logs [-f]}"
        echo ""
        echo "Nota: El comando install crea los enlaces en /etc/systemd/system"
        exit 1
        ;;
esac
