# 01. Arquitectura y Diseño del Sistema

El sistema que hemos construido para la **Fase 1** (Aprovisionamiento Baremetal) no es una simple colección de scripts bash, sino una arquitectura distribuida orientada a datos. 

Este diseño soluciona el problema fundamental de VirtualBox: **las máquinas virtuales no pueden controlarse fácilmente desde dentro de otra máquina virtual**.

---

## 1. Topología de Red

Según el enunciado, el proyecto cuenta con 3 "zonas" de red. Hemos implementado estas zonas utilizando adaptadores virtuales:

1. **Internet (NAT VBox)**: Proporciona salida al exterior.
2. **Red MAIN (`intnet_main` - 192.168.1.0/24)**: Red donde viven los Load Balancers, Frontends Web y puestos de trabajo (Hotdesks). Esta red **debe tener acceso a Internet**.
3. **Red INTERNAL (`intnet_internal` - 192.168.2.0/24)**: Red donde vive el clúster de Base de Datos y la Monitorización. Esta red **está aislada de Internet** y solo puede comunicarse con MAIN.

### El Reto del Aceso a Internet
Durante el aprovisionamiento baremetal, **todos** los nodos (incluso los de la red internal) necesitan acceso temporal a Internet para descargar paquetes (`apt install`). 
* **Solución (Fase de Instalación)**: El Jumpstart actúa como un router NAT temporal gracias a unas reglas de `iptables` configuradas en el script de bootstrap.
* **Solución (Fase de Producción)**: Una vez apagado el Jumpstart, el Load Balancer dispone de una interfaz NAT dedicada y asume el rol de Gateway a Internet para la red MAIN, dejando a la red INTERNAL aislada según los requisitos.

---

## 2. Los 3 Pilares del Sistema

### Pilar 1: VBox API Server (El Host)
* **Ubicación:** Tu ordenador físico.
* **Componentes:** `provisioning/vbox_api_server.py` y `host_service.sh`.
* **Función:** Expone una API REST en el puerto `7070`. Recibe peticiones JSON y las traduce a comandos locales de `VBoxManage`. Es el único componente con el poder real de crear VMs, eliminarlas, encenderlas y alterar su orden de arranque.

### Pilar 2: El Orquestador
* **Ubicación:** Todo el repositorio de código, ejecutado principalmente vía `provisioner.py`.
* **Función:** Es el cerebro que lee las especificaciones en `config/nodes/` y `config/networks.yml`. Genera dinámicamente:
  * Archivos de configuración de Netplan para Cloud-Init.
  * Archivos `dhcpd.conf` con asignaciones de IP estáticas por MAC.
  * Menús de arranque PXELINUX personalizados por nodo.
* Llama a la VBox API para ejecutar las acciones sobre VirtualBox.

### Pilar 3: El Servidor Jumpstart
* **Ubicación:** Máquina Virtual de VirtualBox conectada a todas las redes.
* **Función:** Proporciona los servicios clásicos de red necesarios para el arranque por red:
  * **DHCP (`isc-dhcp-server`)**: Entrega IPs.
  * **TFTP (`tftpd-hpa`)**: Entrega el binario de PXE y el Kernel de Ubuntu.
  * **HTTP (`apache2`)**: Sirve los ficheros ISO y los YAMLs de Cloud-Init.
  * **Config Manager Daemon (`provisioner.py listen-callbacks`)**: Demonio en el puerto `8081` que escucha los avisos de "Instalación Completada" de los nodos para inyectarles configuración con Ansible.

---

## 3. El Flujo de Aprovisionamiento Mágico

Lo que hace que nuestra solución destaque es el ciclo de vida **100% desatendido**. Esto es lo que ocurre internamente cuando ejecutamos `./provisioner.py deploy`:

1. **Creación**: El orquestador lee los YAMLs y pide a la Host API que cree las VMs vacías en VirtualBox. Configura el orden de arranque: **1º RED, 2º DISCO**.
2. **Encendido en Headless**: La Host API enciende todas las VMs en segundo plano de forma silenciosa para no saturar tu escritorio.
3. **PXE Boot**: Las VMs no tienen SO, así que buscan por la red. El DHCP del Jumpstart les da una IP y el TFTP les entrega el instalador de Ubuntu.
4. **Cloud-Init (Autoinstall)**: Ubuntu arranca en RAM, descarga el archivo `user-data` específico de ese nodo desde Apache, y particiona el disco, instala paquetes y configura SSH de forma totalmente autónoma.
5. **El Late-Command**: Cuando la instalación finaliza, un comando programado en el `user-data` lanza un evento HTTP POST al **Callback Server** (puerto 8081 del Jumpstart) y luego ejecuta `shutdown -P now` para apagar la VM con seguridad.
6. **El Cambio de Boot (Boot Swap)**: El Callback Server recibe la llamada de éxito e invoca al orquestador (`finalize-node`). Este orquestador contacta con la Host API y le ordena: *"La VM se ha apagado. Cambia su orden de arranque a **1º DISCO, 2º RED** y vuelve a encenderla"*.
7. **Listo para Ansible**: La VM se vuelve a encender, esta vez arrancando desde su disco duro con Ubuntu perfectamente instalado, lista para recibir playbooks de configuración por SSH.
