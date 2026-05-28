# 🚀 Orquestador de Infraestructura Baremetal (GAR)

Bienvenidos al repositorio del proyecto de **Gestión y Administración de Redes (GAR)**. 

Este proyecto implementa una solución de **aprovisionamiento baremetal automatizado** 100% orientada a datos (YAML-driven) que permite desplegar, configurar e instalar un clúster de máquinas virtuales en VirtualBox de forma totalmente desatendida.

---

## 📖 Documentación Oficial

Hemos dividido la documentación en módulos específicos para facilitar la lectura y comprensión del sistema. Por favor, revisa los documentos en orden:

1. 🏗️ **[01. Arquitectura y Diseño](file:///home/Chadry/esi/gyar/trabajo/docs/01_arquitectura.md)**: Explicación técnica de la topología de red, el modelo cliente-servidor (Host API) y el ciclo de vida del aprovisionamiento (PXE, Autoinstall).
2. 🚀 **[02. Guía de Despliegue](file:///home/Chadry/esi/gyar/trabajo/docs/02_guia_despliegue.md)**: El paso a paso exhaustivo para desplegar la infraestructura desde cero y la estrategia para realizar la defensa de la práctica.
3. ⚙️ **[03. Referencia de Configuración YAML](file:///home/Chadry/esi/gyar/trabajo/docs/03_referencia_yaml.md)**: Manual para entender cómo añadir o modificar nodos, configurar múltiples tarjetas de red (NAT + Internas) y el uso de plantillas de Cloud-Init.
4. ✅ **[04. Roadmap y Tareas](file:///home/Chadry/esi/gyar/trabajo/docs/04_roadmap_y_tareas.md)**: Estado actual del desarrollo, hitos conseguidos y los próximos pasos de cara a la configuración con Ansible (Fase 2).

---

## 📂 Árbol de Directorios

La estructura del proyecto está diseñada para ser completamente escalable:

```text
GAR/
├── docs/                          # 📘 Documentación del proyecto
│   ├── 01_arquitectura.md
│   ├── 02_guia_despliegue.md
│   ├── 03_referencia_yaml.md
│   ├── 04_roadmap_y_tareas.md
│   ├── 05_reparto_fase2.md
│   └── GAR_P1.pdf / .txt          # Enunciado original
├── config/                        # ⚙️ Definiciones YAML orientadas a datos
│   ├── networks.yml               # Parametrización de subredes (main, internal)
│   └── nodes/                     # Directorio con los YAML de los 18 nodos
├── provisioning/                  # 🚀 Fase 1: Aprovisionamiento Baremetal
│   ├── orchestrator/              # 📦 Núcleo del orquestador en Python
│   ├── scripts/                   # 🛠️ Scripts auxiliares (bootstrap)
│   ├── services/                  # ⚙️ Archivos para demonios systemd
│   ├── templates/                 # 📄 Plantillas base de PXE y Autoinstall
│   └── vbox_api_server.py         # 🔌 Servidor API REST en el Host físico
├── ansible/                       # ⚙️ Fase 2: Configuración de Servicios
│   └── playbooks/                 # Playbooks y roles de configuración
├── provisioner.py                 # 🚀 CLI principal de aprovisionamiento
├── vbox-api-helper.sh             # 🛠️ Script instalador para la API del Host
├── AGENTS.md                      # Instrucciones para Agentes de IA
├── README.md                      # Este portal de inicio
└── .gitignore                     # Archivo de ignorados
```

---

## ⚡ Inicio Rápido (Quick-Start)

Si ya has leído la [Guía de Despliegue](file:///home/Chadry/esi/gyar/trabajo/docs/02_guia_despliegue.md), estos son los comandos de uso diario:

### En el Host Anfitrión (Tu PC)
```bash
# Iniciar/Instalar la API de VirtualBox en segundo plano
./vbox-api-helper.sh install

# Validar que los archivos YAML no tienen colisiones de IP
./provisioner.py validate

# Desplegar la maqueta completa (crea VMs vacías e inicia el PXE Boot)
./provisioner.py deploy

# Destruir toda la maqueta y liberar disco (CUIDADO)
./provisioner.py undeploy
```

### En el Servidor Jumpstart
```bash
# Levantar servicios de red (DHCP, TFTP, Apache) y generar configuraciones
sudo ./provisioning/scripts/bootstrap_jumpstart.sh
```
