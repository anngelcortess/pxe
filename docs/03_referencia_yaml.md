# 03. Referencia de Configuración YAML

Todo el sistema de aprovisionamiento gira en torno a un diseño orientado a datos (`data-driven`). Esto significa que **nunca modificamos código fuente para añadir, borrar o alterar máquinas** de nuestra maqueta. Todo se define mediante archivos legibles (`YAML`).

## 1. Definición de Redes (`config/networks.yml`)

Este archivo parametriza las características globales de nuestras subredes, desacoplando los rangos de IPs y puertas de enlace de la lógica de código.

```yaml
networks:
  - name: main
    interface: enp0s9
    subnet: "192.168.1.0"
    netmask: "255.255.255.0"
    gateway: "192.168.1.254"
    range_start: "192.168.1.101"
    range_end: "192.168.1.253"
```
**Efecto:** El orquestador lee este fichero y genera en el servidor DHCP (`dhcpd.conf`) un bloque `subnet 192.168.1.0 netmask 255.255.255.0` dinámicamente.

---

## 2. Definición de Nodos (`config/nodes/*.yml`)

Cada máquina virtual tiene su propia identidad en un fichero independiente dentro de `config/nodes/`. El orquestador lee **todos** los ficheros con extensión `.yml` que encuentre en esa carpeta.

Anatomía de un fichero de nodo:

```yaml
name: load-balancer           # 1. Hostname de la máquina
type: load-balancer           # 2. Plantilla que usará para la instalación (user-data)
mac: "08:00:27:00:01:0A"      # 3. Dirección MAC estática (¡Debe ser única!)
networks:                     # 4. Declaración de Tarjetas de Red
  - name: intnet_main         # 1ª NIC (enp0s3): Tipo red interna VirtualBox
    ip: "192.168.1.10"        # IP que se le reservará en el DHCP
    netmask: "255.255.255.0"  
    dns: ["8.8.8.8", "8.8.4.4"]
  - name: NAT                 # 2ª NIC (enp0s8): Tipo NAT de VirtualBox (novedad de la v2.0)
    type: nat
vbox_specs:                   # 5. Hardware de VirtualBox
  cpus: 1
  ram_mb: 7168
  disk_gb: 15
```

### Configuración Multi-NIC (Múltiples Tarjetas de Red)
Nuestro motor de plantillas de Netplan es capaz de configurar dinámicamente múltiples tarjetas de red si las declaras en el YAML. Seguirán la nomenclatura clásica de VirtualBox:
- Primera red del YAML -> Adaptador 1 -> `enp0s3`
- Segunda red del YAML -> Adaptador 2 -> `enp0s8`
- Tercera red del YAML -> Adaptador 3 -> `enp0s9`

Si usas el parámetro `type: nat` (como en el ejemplo de arriba), el orquestador configurará esa interfaz con `dhcp4: true` en el Netplan de Ubuntu para recibir salida a Internet desde VirtualBox. Si usas red interna, la configurará con `dhcp4: false` y le asignará estáticamente la `ip` definida.

---

## 3. Plantilla Cloud-Init (`provisioning/templates/user-data`)

Esta plantilla está pre-cargada con marcadores especiales que el orquestador sustituye "en caliente" (interpolación) justo antes de entregárselas a las máquinas durante la instalación.

### Variables Interpolables:
* `{{ HOSTNAME }}`: Sustituido por el nombre del nodo.
* `{{ SSH_PUB_KEY }}`: Sustituido por la clave RSA pública generada en el Jumpstart (`/root/.ssh/id_rsa.pub`), permitiendo conexiones seguras de Ansible sin contraseña.
* `{{ INTERFACES_CONFIG }}`: Sustituido por el bloque de Netplan en formato YAML con todas las interfaces generadas a partir de la sección `networks`.

### Comandos de "Cierre" Mágico (Late Commands)
En la parte inferior de todas nuestras plantillas de `user-data` encontrarás este bloque crítico:

```yaml
late-commands:
  # Desactiva temporizadores que bloquean APT
  - curtin in-target --target=/target -- systemctl disable apt-daily.timer
  # Inyecta un script en rc.local para avisar al Jumpstart tras el primer arranque
  - echo 'curl -s -X POST http://192.168.1.254:8081/node-ready/{{ HOSTNAME }}' >> /target/etc/rc.local
  # Apaga la máquina para que el Host API pueda cambiar el orden de arranque a Disco
  - shutdown -P now
```

Estas líneas son las responsables de hacer posible nuestro ciclo de vida 100% desatendido, conectando el fin de la instalación de Ubuntu con el servicio de orquestación de nuestra API.
