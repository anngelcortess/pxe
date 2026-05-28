# 01. Arquitectura y Diseño del Sistema (Fase 1 y Fase 2)

El sistema que hemos construido no es una simple colección de bash scripts, sino una **arquitectura distribuida orientada a eventos** y estructurada en una máquina de estados.

Este diseño soluciona el problema fundamental de VirtualBox: **las máquinas virtuales no pueden controlarse fácilmente desde dentro de otra máquina virtual**. Y añade una capa de inteligencia artificial/automatización que respeta los límites de hardware del Host.

---

## 1. Topología de Red

Según el enunciado, el proyecto cuenta con 3 "zonas" de red. Hemos implementado estas zonas utilizando adaptadores virtuales de VirtualBox:

1. **Internet (NAT VBox)**: Proporciona salida al exterior.
2. **Red MAIN (`intnet_main` - 192.168.1.0/24)**: Red donde viven los Load Balancers, Frontends Web y puestos de trabajo (Hotdesks). Esta red **debe tener acceso a Internet**.
3. **Red INTERNAL (`intnet_internal` - 192.168.2.0/24)**: Red donde vive el clúster de Base de Datos y la Monitorización. Esta red **está aislada de Internet** y solo puede comunicarse con MAIN.

### El Reto del Acceso a Internet
Durante el aprovisionamiento baremetal, **todos** los nodos (incluso los de la red internal) necesitan acceso temporal a Internet para descargar paquetes (`apt install`). 
* **Solución (Fase de Instalación)**: El Jumpstart actúa como un router NAT temporal gracias a unas reglas de `iptables` configuradas en el script de bootstrap.
* **Solución (Fase de Producción)**: Una vez finalizada la provisión, el Load Balancer asume el rol de Gateway a Internet para la red MAIN, dejando a la red INTERNAL aislada según los requisitos.

---

## 2. Los Pilares del Sistema (Desacoplamiento)

### Pilar 1: VBox API Server (El Host)
* **Ubicación:** Tu ordenador físico (fuera de las VMs).
* **Deminio:** `vbox-api.service` (`provisioning/vbox_api_server.py`).
* **Función:** Expone una API REST en el puerto `7070` de la red Host-Only (`192.168.56.1`). Recibe peticiones JSON en lote (batching) y las traduce a comandos locales de `VBoxManage`. Es el único con permisos para crear VMs, encenderlas, apagarlas (ACPI/Hard) o modificar su memoria RAM/CPU.
* **Seguridad Anticolisiones:** Integra bucles de reintentos para no corromper VirtualBox cuando se le piden apagados y borrados masivos simultáneos (evita el temido error de "Lock").

### Pilar 2: El Coordinador Global (`provisioning-coordinator`)
* **Ubicación:** Servidor Jumpstart (Máquina Virtual).
* **Demonio:** `provisioning-coordinator.service` en el puerto `8081`.
* **Módulos Clave:**
  * `coordinator.py`: Maneja el ciclo de vida, la Máquina de Estados Global (`IDLE` -> `PXE_INSTALLING` -> `ANSIBLE_PROVISIONING`) y el encolamiento dinámico (Ventana Deslizante).
  * `baremetal.py`: Librería cliente que dialoga con la VBox API del Host.
  * `ansible_runner.py`: Ejecutor programático que dispara los playbooks cuando el clúster entero está levantado.
* **Función:** Es el cerebro en segundo plano que mantiene en memoria el estado del despliegue. Escucha los "Callbacks" de los nodos cuando terminan de instalar Ubuntu y decide si avanzar la cola o arrancar Ansible.

### Pilar 3: El Intérprete y UI (`provisioner.py`)
* **Ubicación:** Servidor Jumpstart (CLI Terminal).
* **Función:** Es la interfaz de usuario. Al ejecutar `./provisioner.py deploy`, lee los YAML en `config/nodes/`, compila las plantillas PXE/DHCP mediante Jinja2 y le envía la lista de despliegue al Coordinador Global por HTTP.

---

## 3. El Flujo de Aprovisionamiento Inteligente (Ventana Deslizante)

Desplegar 17 máquinas virtuales a la vez fundiría la RAM y el disco de cualquier portátil. Para evitar esto, hemos implementado una **Ventana Deslizante en Memoria** con *Batching*.

Esto es lo que ocurre internamente con un despliegue completo de 17 nodos:

1. **Inyección en Cola**: El CLI compila el Cloud-Init y mete los 17 nodos en la lista `pending_nodes` del Coordinador.
2. **PXE Batching (Instalación por Bloques)**: El Coordinador saca solo N nodos (por defecto 3) y les ordena a la VBox API que los cree (con memoria reducida para ahorrar RAM) y los encienda en PXE.
3. **Autoinstall**: Los 3 nodos hacen PXE, se descargan Ubuntu y se instalan de forma paralela.
4. **El Callback (Node-Ready)**: Al terminar, el último comando de Cloud-Init en cada nodo lanza un `POST /node-ready` al Coordinador y **la VM se apaga sola**.
5. **Avanzar Ventana**: Al recibir el Callback, el Coordinador ordena a la Host API cambiar el orden de arranque de esa VM a disco duro y ajustar la RAM de producción. Luego, extrae el siguiente nodo de la cola y lo arranca.
6. **Encendido Global y Ansible**: Cuando la cola está vacía y TODOS los 17 nodos se han instalado y apagado, el Coordinador los enciende todos de golpe y delega el control en `ansible_runner.py` para configurarlos por SSH.
