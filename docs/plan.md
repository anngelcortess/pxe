# Plan de Implementación: Orquestador Dinámico de Infraestructura en Python (YAML-driven)

Este plan de implementación define la arquitectura dinámica y completamente escalable adoptada para la práctica de **Gestión y Administración de Redes (GAR)**. En lugar de configuraciones y scripts rígidos o "hardcodeados", utilizamos una solución orientada a datos donde **cada nodo de la red se define en su propio archivo YAML** y las **subredes se parametrizan en un networks.yml independiente**. Un script unificado en **Python** procesa estos archivos para orquestar toda la infraestructura.

Esta aproximación cumple plenamente con los requisitos del proyecto y con la dinámica de la defensa (donde se os exigirá crear una VM vacía con la MAC de una de vuestras máquinas para demostrar la autoinstalación baremetal ante el profesor de forma ágil).

---

## Diseño del Sistema Dinámico (YAML-driven)

### Estructura del Repositorio de la Práctica

```
trabajo/
├── GAR_P1.pdf                     # Enunciado original de la práctica
├── README.md                      # README inicial
├── .gitignore                     # Escudo de exclusión de Git (logs, VDIs, ISOs)
├── orchestrate.py                 # Orquestador Python (renombrado y en la raíz del proyecto)
│
├── docs/                          # Documentación Git y defensa
│   ├── plan.md                    # Este plan de diseño
│   ├── walkthrough.md             # Guía del orquestador y defensa
│   └── task.md                    # Checklist de tareas de control de calidad
│
└── baremetal/                     # Todo el aprovisionamiento PXE y Autoinstall
    ├── bootstrap_jumpstart.sh     # Script de bootstrap del Jumpstart (llama a orchestrate.py)
    ├── networks.yml               # Parametrización dinámica de subredes
    ├── nodes/                     # Las 18 definiciones de nodos YAML
    ├── templates/                 # Plantillas de user-data parametrizadas
    ├── dhcp/                      # Salida DHCP local para pruebas
    ├── pxe/                       # Salida menús PXE locales para pruebas
    └── autoinstall/               # Salida Autoinstall locales para pruebas
```

### Formato de Definición de un Nodo (`baremetal/nodes/*.yml`)

Cada nodo se define de la siguiente manera. Ejemplo para `baremetal/nodes/cluster-master-1.yml`:

```yaml
name: cluster-master-1
type: cluster-node          # Determina qué plantilla de user-data aplicar
mac: "08:00:27:00:02:0A"     # MAC fija para el aprovisionamiento
networks:
  - name: intnet_internal    # Conectado a la red interna de VirtualBox
    ip: "192.168.2.10"
    netmask: "255.255.255.0"
    gateway: "192.168.2.254"
    dns: ["8.8.8.8", "8.8.4.4"]
vbox_specs:
  cpus: 2
  ram_mb: 1024               # RAM optimizada para evitar soplos de hardware
  disk_gb: 20
```

---

## Arquitectura de `orchestrate.py` (El Orquestador)

Este script en Python se ejecuta con propósitos complementarios según el entorno de trabajo:

### 1. En la Máquina Anfitriona (Host)
Permite la automatización completa de VirtualBox llamando internamente a `VBoxManage`.
* **Comando de Despliegue**: `python3 orchestrate.py --action deploy`
  * **Acción**: 
    1. Lee los ficheros YAML del directorio `baremetal/nodes/` de forma relativa a su ubicación.
    2. Comprueba si alguna VM ya existe en VirtualBox de un despliegue anterior.
    3. Si existe, **la apaga automáticamente y la elimina por completo** junto con su disco virtual `.vdi` para garantizar un despliegue limpio desde cero.
    4. Crea y registra la nueva VM con sus especificaciones de CPU, RAM y disco.
    5. Asocia de forma determinista la dirección MAC y tarjeta de red del YAML.
    6. Configura el orden de arranque: **Red (PXE) primero, disco duro segundo**.
    7. **Enciende la VM automáticamente en segundo plano (headless)**, enviando sus logs de arranque al directorio del propio disco virtual para mantener el código de tu proyecto limpio.
* **Comando de Limpieza**: `python3 orchestrate.py --action undeploy`
  * **Acción**: Apaga de forma segura y elimina de raíz todas las VMs registradas en VirtualBox que pertenezcan a la maqueta (protegiendo siempre a tu servidor `jumpstart` manual).

### 2. Dentro de la Máquina Jumpstart (Servidor PXE)
Genera dinámicamente todos los archivos de configuración para los servicios del servidor.
* **Comando**: `python3 ../orchestrate.py --action generate-configs` (ejecutado desde el directorio `baremetal/` o relativo al script)
* **Acción**:
  1. Lee `baremetal/networks.yml` de forma relativa para cargar dinámicamente las subredes, máscaras, gateways, DNS y rangos de leasing DHCP.
  2. Lee todos los YAML de `baremetal/nodes/`.
  3. **DHCP**: Genera el bloque de subredes completo y dinámico en `/etc/dhcp/dhcpd.conf` con reservas IP estáticas por MAC.
  4. **PXELINUX**: Escribe un menú de arranque personalizado en `/srv/tftp/pxelinux.cfg/01-<mac>` que pasa parámetros Subiquity apuntando a su perfil de autoinstalación unívoco.
  5. **Autoinstall**: Crea la carpeta `/var/www/html/autoinstall/<node_name>/`. Lee la plantilla `templates/user-data-<type>`, sustituye los placeholders de Netplan (`{{ HOSTNAME }}`, `{{ INTERFACES_CONFIG }}`, `{{ SSH_PUB_KEY }}`) y escribe el `user-data` definitivo.
  6. **Reinicio de Servicios**: Reinicia `isc-dhcp-server` y `tftpd-hpa` para aplicar las nuevas configuraciones dinámicas.

---

## Proposed Changes

### 1. Directorio de Nodos

#### Ficheros YAML de especificación en [baremetal/nodes/](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes)
Definiciones parametrizadas y listas con la RAM optimizada para evitar la sobrecarga del ordenador de la demo:
- `jumpstart.yml`, `load-balancer.yml`, `web-frontend-1.yml`, `web-frontend-2.yml`, `cluster-master-1.yml`, `cluster-master-2.yml`, `cluster-worker-1.yml`, `cluster-worker-2.yml`, `storage-node.yml`, `monitoring.yml` y los 8 puestos `hotdesk-[1-8].yml`.

### 2. Directorio de Plantillas de Autoinstalación

#### Plantillas bajo [baremetal/templates/](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates)
Plantillas parametrizadas con placeholders que se interpolan en caliente:
- `user-data-load-balancer`, `user-data-web-frontend`, `user-data-cluster-node` (con desactivación de swap), `user-data-monitoring`, `user-data-storage`, `user-data-hotdesk` y `common-meta-data`.

### 3. El Script Orquestador en Python

#### [orchestrate.py](file:///home/Chadry/esi/gyar/trabajo/orchestrate.py)
Script completo en la raíz del proyecto en Python 3 con un parser YAML nativo de fallback, control de procesos `VBoxManage`, eliminación de previas y arranque headless silencioso con redirección de logs.

### 4. Script de Bootstrap del Jumpstart

#### [bootstrap_jumpstart.sh](file:///home/Chadry/esi/gyar/trabajo/baremetal/bootstrap_jumpstart.sh)
Script robusto para ejecutarse en el servidor que instala dependencias de red, descarga y extrae el kernel de Ubuntu 22.04 LTS e invoca el orquestador en caliente.

---

## Plan de Verificación

### Pruebas Automatizadas
1. **Validación Sintáctica**: El script en Python incluye la acción `--action validate` para validar que:
   - No hay colisiones de direcciones IP o MACs.
   - Las plantillas y campos obligatorios existen.

### Verificación Manual de la Defensa
1. Ejecutar en el host `python3 orchestrate.py --action deploy` para verificar la creación y encendido silencioso de todo el entorno en VirtualBox.
2. Ejecutar `bootstrap_jumpstart.sh` en el servidor y comprobar que levanta todos los servicios.
3. Crear una VM vacía con la MAC de `load-balancer` y encenderla para validar que arranca por PXE y se autoinstala de forma 100% desatendida.
