# 🚀 Orquestador de Infraestructura Baremetal Dinámica y Desatendida (GAR - P1)

Este repositorio contiene la fase de **aprovisionamiento baremetal e infraestructura virtual** para el Proyecto Práctico de la asignatura **Gestión y Administración de Redes (GAR)**. 

Hemos diseñado e implementado una solución **100% orientada a datos (YAML-driven)** en Python 3 y Bash que automatiza por completo la creación de las redes de VirtualBox, el despliegue de las máquinas virtuales cliente en segundo plano y el bootstrap de un servidor **Jumpstart** (PXE, DHCP, TFTP, HTTP) capaz de instalar Ubuntu Server 22.04 LTS de forma totalmente desatendida (`Autoinstall` / `cloud-init`).

---

## 📂 Directorio del Proyecto

La estructura actual de la raíz del proyecto es limpia y modular, habiendo eliminado cualquier residuo obsoleto del prototipo inicial:

```text
trabajo/
├── GAR_P1.pdf                     # Enunciado oficial del proyecto
├── README.md                      # Este portal de inicio
├── .gitignore                     # Escudo de exclusión (logs de VirtualBox, ISOs, VDIs)
├── orchestrate.py                 # Orquestador dinámico en Python 3 (renombrado y movido)
│
├── docs/                          # 📘 Documentación detallada del sistema
│   ├── plan.md                    # Plan de diseño arquitectónico y YAMLs
│   ├── walkthrough.md             # Guía paso a paso, despliegue y defensa ante el profesor
│   └── task.md                    # Checklist y control de calidad de tareas completadas
│
└── baremetal/                     # 🛠️ Código fuente de aprovisionamiento
    ├── bootstrap_jumpstart.sh     # Script automatizado de bootstrap del servidor Jumpstart
    ├── networks.yml               # Parametrización dinámica de subredes
    ├── nodes/                     # Directorio con los 18 archivos YAML de definición de nodos
    ├── templates/                 # Plantillas de autoinstalación (user-data y meta-data)
    ├── dhcp/                      # Directorio de salida DHCP (pruebas locales)
    ├── pxe/                       # Directorio de salida menús PXELINUX (pruebas locales)
    └── autoinstall/               # Directorio de salida perfiles interpolados (pruebas locales)
```

---

## 🛠️ Características Principales

1. **Modelado Dinámico YAML-driven**:
   * Las subredes (`networks.yml`) y cada nodo de la maqueta (`nodes/*.yml`) se definen de forma desacoplada. Añadir, modificar o eliminar nodos o subredes escala la infraestructura de manera automática sin tocar una sola línea de código.
2. **Orquestador Modular en Python (`orchestrate.py`)**:
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

1. **Validar consistencia de los YAML de nodos y redes**:
   ```bash
   ./orchestrate.py validate
   ```

2. **Desplegar y arrancar la maqueta cliente en VirtualBox (Headless)**:
   ```bash
   ./orchestrate.py deploy
   ```

3. **Eliminar y limpiar de raíz las VMs clientes de VirtualBox**:
   ```bash
   ./orchestrate.py undeploy
   ```

### En el Servidor Jumpstart (Máquina de Aprovisionamiento)

1. **Configurar todos los servicios PXE/DHCP/HTTP en caliente**:
   ```bash
   sudo ./baremetal/bootstrap_jumpstart.sh
   ```
