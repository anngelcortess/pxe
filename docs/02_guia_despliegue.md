# 02. Guía de Despliegue Paso a Paso

Esta guía explica de forma detallada cómo utilizar nuestra infraestructura desde el punto de vista del operador, y finaliza con la estrategia recomendada para hacer la demostración presencial (defensa de la práctica) ante el profesorado.

---

## FASE 1: Preparación del Anfitrión (Host)

Para que nuestra orquestación funcione, el script de Python que corre en el Jumpstart necesita poder comunicarse con tu VirtualBox local.

1. Abre un terminal en la raíz del proyecto en tu máquina física (Host).
2. Ejecuta el instalador del servicio API de VirtualBox:
   ```bash
   ./host_service.sh install
   ```
3. Comprueba que está funcionando haciendo una llamada de salud a la API:
   ```bash
   curl http://localhost:7070/health
   # Debería devolver: {"status": "ok", "message": "VBox API Server is running"}
   ```

*(Opcional: Si quieres ver en tiempo real qué órdenes está recibiendo VirtualBox, puedes abrir otra pestaña de terminal y usar `./host_service.sh logs`).*

---

## FASE 2: Inicialización del Servidor Jumpstart

El Jumpstart es el corazón de nuestra red. Es la única máquina que habremos creado "a mano" previamente clonando de una Ubuntu Server 22.04 base (del primer lab). 

1. Arranca tu VM Jumpstart desde la interfaz de VirtualBox.
2. Sube la carpeta de este proyecto a la VM (usando `git clone`, carpetas compartidas de VBox o `scp`).
   > [!IMPORTANT]
   > Si usas `scp` o un ZIP, asegúrate de que la carpeta resultante en la máquina virtual se llame **obligatoriamente `gar`** (ej. `/home/admin/gar`), ya que los servicios de Ansible la buscarán en esa ruta exacta. Lo más sencillo es clonar directamente el repositorio: `git clone git@github.com:jorgeGimene/gar.git`.
3. Entra a la VM por SSH o consola gráfica, sitúate en la raíz del proyecto y ejecuta:
   ```bash
   sudo ./provisioning/scripts/bootstrap_jumpstart.sh
   ```

**¿Qué hace el Bootstrap Script?**
* Configura la IP estática del servidor en Netplan.
* Instala las herramientas de red necesarias (`isc-dhcp-server`, `tftpd-hpa`, `apache2`).
* Habilita enmascaramiento NAT (`iptables`) para que los nodos en instalación tengan salida a Internet.
* Extrae el kernel instalador de Ubuntu.
* Levanta el microservicio `provision-callback.service` en el puerto 8081.

## FASE 3: Despliegue de la Maqueta Baremetal

Con el Host y el Jumpstart preparados, podemos ordenar la creación de todas las máquinas virtuales definidas en `config/nodes/`.

1. En el terminal del Jumpstart, ejecuta:
   ```bash
   ./provisioner.py deploy
   ```
o para evitar desplegar 17 nodos a la vez:
   ```bash
   ./provisioner.py deploy <nodo, ej: load-balancer> 
   ```

**¿Qué hace este comando?**
* **Validación**: Comprueba que no has escrito IPs duplicadas ni MACs mal formateadas.
* **Seguridad Anticolisiones**: Si detecta que ya existen VMs de un despliegue anterior, te avisará y te pedirá confirmación (`y/N`) antes de eliminarlas (para no destruir trabajo sin querer).
* **Creación**: Habla con la Host API y le ordena ejecutar los `VBoxManage createvm`, creando los discos duros virtuales y configurando las tarjetas de red.
* **Encendido Silencioso**: Enciende las máquinas en modo **Headless** (sin ventana gráfica). Todas las máquinas arrancarán e intentarán hacer boot por red (PXE), quedándose a la espera.

---


### FASE 4: La Instalación Mágica
Con el Jumpstart levantado, las VMs que se habían quedado esperando en PXE en la FASE 3 comenzarán a comunicarse con él.
1. Recibirán su IP mediante DHCP.
2. Descargarán y ejecutarán el instalador desatendido de Ubuntu (Subiquity).
3. Se instalarán solas, avisarán al puerto 8081 al terminar y se apagarán solas.
4. Volverán a encenderse mágicamente, esta vez arrancando desde el disco duro.

*(Nota: Este proceso puede tardar entre 5 y 15 minutos dependiendo de la potencia de tu Host y la velocidad de descarga de Internet).*

---

## 🛠️ Comandos de Mantenimiento

Nuestro CLI `provisioner.py` tiene otras acciones útiles para el día a día:

* **Limpieza Total (Desmontar Maqueta)**:
  ```bash
  ./provisioner.py undeploy
  ```
* **Acciones Quirúrgicas (Solo un nodo)**:
  Si rompemos el load-balancer haciendo pruebas y queremos reinstalar **solo** ese nodo sin afectar al resto:
  ```bash
  ./provisioner.py undeploy load-balancer
  ./provisioner.py deploy load-balancer
  ```
* **Control de Energía**:
  ```bash
  ./provisioner.py stop --mode savestate   # Guarda el estado de la RAM de todas las VMs
  ./provisioner.py start                   # Despierta todas las VMs
  ```

---

## 🎓 Estrategia para la Defensa Presencial

Para demostrar al profesorado que nuestra autoinstalación baremetal es real y 100% dinámica, recomendamos seguir estos pasos durante la evaluación:

1. Tener la maqueta ya completamente instalada y configurada por Ansible en estado apagado.
2. Crear **manualmente** una nueva VM vacía en VirtualBox delante del profesor.
3. Copiar la dirección MAC de uno de los archivos YAML (por ejemplo `08:00:27:00:01:0A` del `load-balancer.yml`) y ponérsela a mano a esa VM temporal en la interfaz de VirtualBox.
4. Conectar esa VM a la red interna correspondiente.
5. **Encenderla**. El profesor observará en directo cómo la VM hace PXE, el Jumpstart la reconoce por su MAC, le entrega la configuración exacta de Load Balancer, y se auto-instala sin que toquemos el teclado.
6. Una vez empiece a instalar paquetes (demostrando que el aprovisionamiento baremetal funciona), apagar esa VM temporal.
7. Encender la maqueta real definitiva y enseñar los servicios de la Fase 2 funcionando.
