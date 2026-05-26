# 🚀 Orquestador de Infraestructura Baremetal Dinámica y Desatendida (GAR - P1)

Este repositorio contiene la fase de **aprovisionamiento baremetal e infraestructura virtual** para el Proyecto Práctico de la asignatura **Gestión y Administración de Redes (GAR)**. 

Hemos diseñado e implementado una solución **100% orientada a datos (YAML-driven)** en Python 3 y Bash que automatiza por completo la creación de las redes de VirtualBox, el despliegue de las máquinas virtuales cliente en segundo plano y el bootstrap de un servidor **Jumpstart** (PXE, DHCP, TFTP, HTTP) capaz de instalar Ubuntu Server 22.04 LTS de forma totalmente desatendida (`Autoinstall` / `cloud-init`).

---

## 📂 Directorio del Proyecto

La estructura actual de la raíz del proyecto es limpia y modular, habiendo eliminado cualquier residuo obsoleto del prototipo inicial:

```text
trabajo/
├── docs/                          # 📘 Documentación del proyecto y enunciado
│   ├── GAR_P1.pdf
│   ├── plan.md
│   ├── walkthrough.md
│   └── task.md
├── config/                        # ⚙️ Configuración y definiciones YAML
│   ├── networks.yml               # Definición de subredes
│   └── nodes/                     # Directorio con archivos YAML de nodos
├── templates/                     # 📄 Plantillas base de Autoinstall
│   ├── meta-data
│   └── user-data
├── scripts/                       # 🛠️ Scripts auxiliares y de bootstrap
│   ├── bootstrap_jumpstart.sh     # Inicialización del Jumpstart
│   └── provision_callback.py      # Servidor HTTP de callback
├── services/                      # ⚙️ Archivos de configuración de systemd
│   ├── provision-callback.service
│   └── vbox-api.service
├── host_service.sh                # 🛠️ Script de gestión fácil para el Host
├── gar_orchestrator/              # 📦 Código fuente del orquestador
├── provisioner.py                 # 🚀 CLI principal de aprovisionamiento
├── vbox_api_server.py             # 🔌 Servidor API para VirtualBox
├── README.md                      # Este portal de inicio
└── .gitignore                     # Escudo de exclusión (salida local, etc.)
```

---

## 🛠️ Características Principales

1. **Modelado Dinámico YAML-driven**:
   * Las subredes (`networks.yml`) y cada nodo de la maqueta (`nodes/*.yml`) se definen de forma desacoplada. Añadir, modificar o eliminar nodos o subredes escala la infraestructura de manera automática sin tocar una sola línea de código.
2. **Aprovisionador Modular en Python (`provisioner.py`)**:
   * Implementa un cargador YAML inteligente con parser de *fallback* nativo (para poder ejecutarse en entornos mínimos sin dependencias como `PyYAML`).
   * Soporta validación estricta de IPs y MACs (`--action validate`) para evitar conflictos de red.
   * Maneja el ciclo de vida de VirtualBox (`deploy`/`undeploy`) recreando discos VDI y redes de forma limpia.
   * Inicia las VMs en segundo plano (`headless`) y redirige los archivos de log de VirtualBox (`VirtualBoxVM-<pid>.log`) al directorio correspondiente de cada máquina, manteniendo la raíz del proyecto libre de ruido.
3. **Bootstrap Automatizado del Jumpstart (`bootstrap_jumpstart.sh`)**:
   * Un único script de Bash a ejecutar en el servidor que automatiza el direccionamiento estático en Netplan, instala las dependencias (`isc-dhcp-server`, `tftpd-hpa`, `apache2`), descarga la ISO oficial de Ubuntu, extrae los kernels de red y arranca la orquestación.

---

## 📖 Documentación de Referencia (Quick Links)

Para profundizar en la implementación y preparar la defensa del proyecto, consulta la documentación oficial en la carpeta `docs/`:

* 📋 **[Plan de Implementación](file:///home/Chadry/esi/gyar/trabajo/docs/plan.md)**: Conoce el formato detallado de definición de nodos, la parametrización de subredes y el comportamiento interno del orquestador en cada fase.
* 🚀 **[Guía de Walkthrough y Defensa](file:///home/Chadry/esi/gyar/trabajo/docs/walkthrough.md)**: Guía paso a paso para desplegar la maqueta en el Host anfitrión, inicializar el Jumpstart y la **estrategia para realizar con éxito la defensa en vivo ante el profesor** instalando una máquina vacía de prueba.
* ✅ **[Roadmap y Checklist de Tareas](file:///home/Chadry/esi/gyar/trabajo/docs/task.md)**: El listado completo de hitos de desarrollo implementados y verificados.

---

## ⚡ Comandos Rápidos de Uso

### En el Host Anfitrión (Con VirtualBox)

1. **Gestionar el Servidor API de VirtualBox**:
   Para que el Jumpstart pueda controlar las VMs en tu Host físico, el servidor API debe estar activo. Puedes gestionarlo fácilmente como un servicio de systemd de usuario con nuestro script:
   ```bash
   # Instalar y activar el servicio en segundo plano (solo la primera vez)
   ./host_service.sh install

   # Ver el estado del servicio o reiniciarlo
   ./host_service.sh status
   ./host_service.sh restart

   # Ver los logs en tiempo real (Ctrl+C para salir)
   ./host_service.sh logs
   ```

2. **Validar consistencia de los YAML de nodos y redes**:
   ```bash
   ./provisioner.py validate
   ```

2. **Desplegar y arrancar la maqueta cliente en VirtualBox (Headless)**:
   ```bash
   ./provisioner.py deploy
   ```

3. **Eliminar y limpiar de raíz las VMs clientes de VirtualBox**:
   ```bash
   ./provisioner.py undeploy
   ```

4. **Iniciar las VMs de la maqueta (excepto jumpstart)**:
   ```bash
   # Iniciar todas las VMs en segundo plano (headless)
   ./provisioner.py start
   # Iniciar una VM específica en modo interfaz gráfica (GUI)
   ./provisioner.py start web-frontend-1 --type gui
   ```

5. **Detener las VMs de la maqueta (excepto jumpstart)**:
   ```bash
   # Apagar todas las VMs inmediatamente (poweroff)
   ./provisioner.py stop
   # Guardar estado de una VM específica (suspend)
   ./provisioner.py stop cluster-worker-1 --mode savestate
   ```

### En el Servidor Jumpstart (Máquina de Aprovisionamiento)

1. **Configurar todos los servicios PXE/DHCP/HTTP en caliente**:
   ```bash
    sudo ./scripts/bootstrap_jumpstart.sh
   ```
