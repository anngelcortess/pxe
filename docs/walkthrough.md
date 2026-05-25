# Walkthrough: Sistema de Aprovisionamiento Baremetal Dinámico (YAML & Python)

Este documento resume las implementaciones realizadas en esta fase del proyecto de **Gestión y Administración de Redes (GAR)** para la automatización baremetal de la infraestructura mediante VirtualBox, PXE, DHCP, TFTP, HTTP y el instalador desatendido (`Autoinstall`) de Ubuntu Server 22.04 LTS.

---

## 🛠️ Archivos y Estructuras Creados

Hemos implementado una infraestructura dinámicamente parametrizada que se estructura bajo la carpeta de la raíz de la siguiente manera:

1. **Directorio de Nodos (`baremetal/nodes/`)**:
   Contiene un archivo YAML por cada máquina virtual de la maqueta, con sus especificaciones de CPU, RAM, disco virtual, redes de VirtualBox y direccionamiento IP/MAC:
   * [jumpstart.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/jumpstart.yml)
   * [load-balancer.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/load-balancer.yml)
   * [web-frontend-1.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/web-frontend-1.yml)
   * [web-frontend-2.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/web-frontend-2.yml)
   * [cluster-master-1.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/cluster-master-1.yml)
   * [cluster-master-2.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/cluster-master-2.yml)
   * [cluster-worker-1.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/cluster-worker-1.yml)
   * [cluster-worker-2.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/cluster-worker-2.yml)
   * [storage-node.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/storage-node.yml)
   * [monitoring.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/nodes/monitoring.yml)
   * **Hot-desks**: 8 archivos YAML (`hotdesk-1.yml` a `hotdesk-8.yml`) generados automáticamente por script.

2. **Configuración de Redes (`baremetal/networks.yml`)**:
   * [networks.yml](file:///home/Chadry/esi/gyar/trabajo/baremetal/networks.yml): Fichero que define de forma parametrizada los prefijos de subred, máscaras, gateways y rangos de leasing DHCP para cada una de las subredes de la maqueta, desacoplándolas por completo del script de Python.

3. **Directorio de Plantillas (`baremetal/templates/`)**:
   Contiene las plantillas de configuración desatendida (`user-data` y `meta-data`) para cloud-init/subiquity de los diferentes tipos de nodos fijos, con marcadores como `{{ HOSTNAME }}`, `{{ INTERFACES_CONFIG }}` y `{{ SSH_PUB_KEY }}` que el orquestador interpola en caliente:
   * [user-data-cluster-node](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-cluster-node) (con desactivación de swap incluida)
   * [user-data-load-balancer](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-load-balancer)
   * [user-data-web-frontend](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-web-frontend)
   * [user-data-monitoring](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-monitoring)
   * [user-data-storage](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-storage)
   * [user-data-hotdesk](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/user-data-hotdesk)
   * [common-meta-data](file:///home/Chadry/esi/gyar/trabajo/baremetal/templates/common-meta-data)

4. **Orquestador Principal (`orchestrate.py`)**:
   * [orchestrate.py](file:///home/Chadry/esi/gyar/trabajo/orchestrate.py): Un script unificado en Python 3 en la raíz del proyecto que implementa cuatro comandos principales (`--action validate`, `deploy`, `undeploy`, `generate-configs`). Cuenta con un parser YAML fallback nativo para poder correr sin dependencias de terceros (`PyYAML`) en cualquier sistema.

5. **Script de Bootstrap del Jumpstart (`baremetal/bootstrap_jumpstart.sh`)**:
   * [bootstrap_jumpstart.sh](file:///home/Chadry/esi/gyar/trabajo/baremetal/bootstrap_jumpstart.sh): Script de Bash robusto diseñado para ejecutarse una vez dentro del servidor Jumpstart (`root`/`sudo`). Instala todos los servicios, configura Netplan, descarga la ISO oficial de Ubuntu 22.04 LTS, extrae el kernel/initrd al TFTP y ejecuta el orquestador en caliente.

---

## 🚀 Guía de Uso Paso a Paso

Para desplegar la maqueta desde cero y realizar la defensa en vivo de forma fluida, debéis seguir los siguientes pasos:

### Paso 1: Crear las Máquinas Virtuales en el Host (Anfitrión)
Desde la consola de tu equipo anfitrión (donde corre VirtualBox), sitúate en el directorio del proyecto y ejecuta el orquestador para realizar el despliegue limpio de las VMs:
```bash
python3 orchestrate.py --action deploy
```
> [!IMPORTANT]
> **¿Qué hace la acción `--action deploy`?**
> - Lee todos los archivos YAML de `baremetal/nodes/` (excepto `jumpstart`).
> - **Control Inteligente de Jumpstart**: Comprueba automáticamente si la VM de aprovisionamiento `jumpstart` está encendida. Si está apagada, la **enciende automáticamente en segundo plano (headless)** para garantizar que el servidor DHCP/PXE responda a los clientes. Si la VM ni siquiera está creada en VirtualBox, detiene el despliegue con un aviso explicativo.
> - Comprueba si alguna VM de la maqueta ya existe de un despliegue anterior.
> - Si existe, **la apaga automáticamente y la elimina por completo** junto con su disco VDI de VirtualBox, garantizando un despliegue limpio de la maqueta de producción desde cero.
> - Crea y registra las nuevas VMs vacías con la CPU, RAM y disco virtual requeridos, asociando la MAC fija en la red interna que le toca y pre-configurando el orden de arranque: **PXE por red primero, Disco Duro segundo.**
> - **Enciende automáticamente cada máquina virtual** en segundo plano (modo headless/detached), evitando abrir decenas de ventanas gráficas en tu escritorio y permitiendo que la autoinstalación por red progrese de forma extremadamente limpia y eficiente en segundo plano.
> - **Redirección de Logs de VirtualBox**: Ejecuta el proceso de inicio de las máquinas con el directorio de trabajo (`cwd`) posicionado en la carpeta individual de cada VM, evitando así que los molestos archivos de registro de VirtualBox (`VirtualBoxVM-<pid>.log`) se generen en la raíz del repositorio y manteniéndolo completamente limpio.

> [!TIP]
> **Despliegue Quirúrgico de un Solo Nodo (Altamente Recomendado para la Defensa):**
> Si solo quieres desplegar o recrear una VM específica sin alterar el estado de las demás (por ejemplo, para recrear únicamente el balanceador de carga o un puesto de hotdesk), puedes añadir el parámetro `--node <nombre-nodo>`:
> ```bash
> python3 orchestrate.py --action deploy --node load-balancer
> ```
> De esta forma, el orquestador apagará, eliminará y volverá a crear **únicamente** la VM de `load-balancer`, dejando intacto el resto de tu clúster que ya esté configurado por Ansible. Esto mismo aplica para la acción de limpieza selectiva:
> ```bash
> python3 orchestrate.py --action undeploy --node load-balancer
> ```

### Paso extra: Limpieza Total (Undeploy)
Si en algún momento quieres desmontar por completo la maqueta de VirtualBox de tu Host anfitrión para liberar espacio en disco o recursos, ejecuta el comando de desinstalación:
```bash
python3 orchestrate.py --action undeploy
```
> [!NOTE]
> Este comando apagará de forma segura y eliminará de raíz todas las VMs de la maqueta (excepto tu nodo `jumpstart` manual, que se mantendrá siempre a salvo).

### Paso 2: Encender e Iniciar el Servidor Jumpstart
1. Enciende la máquina virtual `jumpstart` desde la interfaz de VirtualBox.
2. Inicia sesión con el usuario administrador (ej. `admin`/`admin123` o el que tenga configurado).
3. Transfiere la carpeta del proyecto `baremetal/` (y `orchestrate.py` en la raíz) al Jumpstart (mediante git, una carpeta compartida de VirtualBox o SCP).
4. Dentro del Jumpstart, como root (`sudo -i`), ve a la carpeta `baremetal/` y ejecuta el script de bootstrap:
   ```bash
   sudo ./bootstrap_jumpstart.sh
   ```
> [!IMPORTANT]
> **¿Qué hace este script de forma automatizada?**
> - Configura las tres interfaces de red de tu Jumpstart (NAT para internet, `enp0s8` en red Main con IP `192.168.1.254`, y `enp0s9` en red Internal con IP `192.168.2.254`).
> - Instala `isc-dhcp-server`, `tftpd-hpa` y `apache2`.
> - Genera la clave pública SSH corporativa en `/root/.ssh/id_rsa.pub` (esencial para que luego tu compañero trabaje con Ansible).
> - Descarga de forma segura la ISO de Ubuntu 22.04.5 LTS si no está en caché, la monta temporalmente y copia el kernel (`vmlinuz`) e `initrd` al servidor TFTP.
> - Ejecuta `orchestrate.py --action generate-configs` (vía `../orchestrate.py` desde `baremetal/`) que lee los YAMLs y genera en caliente `/etc/dhcp/dhcpd.conf`, todos los menús PXE y todas las plantillas de `user-data` de autoinstalación.
> - Levanta y arranca todos los servicios.

---

## 🎓 Cómo Realizar la Defensa en Vivo ante el Profesor

Según las especificaciones de la defensa que nos has compartido:
> *"La demostración puede tener las máquinas virtuales de la maqueta apagadas pero, para demostrar que la instalación baremetal funciona, crearemos una VM desde cero con una MAC de una máquina de la maqueta para comprobar que se construye como se espera..."*

Vuestro sistema dinámico es **perfecto** para esta dinámica:

1. **La Preparación**: Podéis tener las VMs definitivas ya platformadas y totalmente configuradas en VirtualBox (con Ansible) en estado apagado.
2. **La VM vacía de prueba**:
   * Cuando el profesor os pida comprobar la instalación baremetal, cread una VM vacía nueva en VirtualBox y ponedle manualmente en la configuración de red (Adaptador 1) la MAC de uno de vuestros nodos, por ejemplo, la del Load Balancer: `08:00:27:00:01:0A`.
   * Conectad esa interfaz a la red interna `intnet_main`.
3. **El Arranque**:
   * Encended la VM vacía. Al no tener sistema operativo, intentará arrancar por red (PXE Boot).
   * La VM contactará con el Jumpstart, el cual le asignará la IP `192.168.1.10` basándose en la MAC, le cargará el cargador PXE, leerá el archivo específico `/srv/tftp/pxelinux.cfg/01-08-00-27-00-01-0a` y le dará la instrucción de instalar Ubuntu 22.04 Server de forma desatendida usando el perfil de `/var/www/html/autoinstall/load-balancer/user-data`.
4. **La Comprobación**:
   * El profesor verá arrancar el instalador Subiquity y cómo progresa de forma **100% autónoma** configurando la red estática, teclado, disco y cargando la llave SSH de administración.
   * Una vez iniciada la fase de copia de paquetes (lo que demuestra que el aprovisionamiento baremetal funciona a la perfección), podéis **apagar** esa máquina temporal.
5. **El Cierre**:
   * Encendéis vuestro nodo Load Balancer definitivo (previamente aprovisionado y configurado por Ansible) y demostráis la práctica completa funcionando.

---

## ✅ Pruebas de Calidad Realizadas

Hemos ejecutado las siguientes pruebas en el entorno local de tu espacio de trabajo para asegurar que el código es robusto y está listo:

1. **Validación Sintáctica de los YAMLs**:
   * Comando: `python3 orchestrate.py --action validate`
   * Resultado: **Éxito (0 errores, 0 advertencias).** Verifica que todas las IPs son únicas, las MACs son correctas, y no hay colisiones entre la red `main` y la `internal`.
2. **Generación en Caliente Local de Pruebas**:
   * Comando: `python3 orchestrate.py --action generate-configs`
   * Resultado: **Éxito.** Generó localmente en las carpetas `dhcp/`, `pxe/` y `autoinstall/` bajo la subcarpeta del orquestador las 17 configuraciones independientes de los clientes (excluyendo el nodo Jumpstart), verificando que el motor de interpolación de plantillas Netplan es correcto.
