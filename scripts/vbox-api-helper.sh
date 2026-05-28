#!/usr/bin/env bash
# ==============================================================================
# Script de gestión para el servicio vbox-api en el Host
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="vbox-api"
SERVICE_FILE="${REPO_DIR}/provisioning/services/${SERVICE_NAME}.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
TARGET_FILE="${SYSTEMD_DIR}/${SERVICE_NAME}.service"

case "${1:-}" in
    install)
        echo "[*] Instalando servicio de usuario..."
        mkdir -p "${SYSTEMD_DIR}"
        sed "s|REPO_PATH|${REPO_DIR}|g" "${SERVICE_FILE}" > "${TARGET_FILE}"
        systemctl --user daemon-reload
        systemctl --user enable --now "${SERVICE_NAME}"
        echo "[+] Servicio instalado y activado en segundo plano!"
        ;;
    uninstall)
        echo "[*] Desinstalando servicio..."
        systemctl --user disable --now "${SERVICE_NAME}" || true
        rm -f "${TARGET_FILE}"
        systemctl --user daemon-reload
        echo "[+] Servicio desinstalado."
        ;;
    start)
        echo "[*] Iniciando servicio..."
        systemctl --user start "${SERVICE_NAME}"
        ;;
    stop)
        echo "[*] Deteniendo servicio..."
        systemctl --user stop "${SERVICE_NAME}"
        ;;
    restart)
        echo "[*] Reiniciando servicio..."
        systemctl --user restart "${SERVICE_NAME}"
        echo "[+] Servicio reiniciado!"
        ;;
    status)
        systemctl --user status "${SERVICE_NAME}"
        ;;
    logs)
        if [[ "${2:-}" == "-f" ]]; then
            echo "[*] Mostrando logs en tiempo real (Ctrl+C para salir)..."
            journalctl --user -u "${SERVICE_NAME}" -f
        else
            echo "[*] Mostrando logs estáticos..."
            journalctl --user -u "${SERVICE_NAME}" --no-pager
        fi
        ;;
    *)
        echo "Uso: $0 {install|uninstall|start|stop|restart|status|logs [-f]}"
        exit 1
        ;;
esac
