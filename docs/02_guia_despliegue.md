# 02. Guía de Despliegue Paso a Paso

Esta guía explica de forma detallada cómo operar la infraestructura desde el punto de vista del administrador. Las herramientas han sido abstraídas en un único CLI para que la experiencia sea similar a usar herramientas como Terraform o Vagrant.

---

## FASE 1: Preparación del Anfitrión (Host)

Nuestra arquitectura delega las operaciones pesadas de hipervisor en una API REST que corre directamente en el ordenador físico.

1. Abre un terminal en la raíz del proyecto en tu máquina física (Host).
2. Instala y levanta el servicio API de VirtualBox:
   ```bash
   ./scripts/vbox-api-helper.sh install
   ```
3. Comprueba que está funcionando:
   ```bash
   curl http://localhost:7070/health
   # Respuesta esperada: {"status": "ok", "message": "VBox API Server is running"}
   ```

*(Opcional: Si quieres monitorizar en tiempo real los comandos que recibe VirtualBox, usa `./scripts/vbox-api-helper.sh logs -f`).*

---

## FASE 2: Preparación del Servidor Jumpstart

El Jumpstart es el enrutador central y el director de orquesta. Es la única máquina que debemos levantar manualmente (a partir de la Ubuntu base del primer laboratorio).

1. Arranca tu VM Jumpstart.
2. Clona este repositorio dentro de la máquina.
3. Entra a la VM por SSH, sitúate en la raíz del proyecto y ejecuta el bootstrap de inicialización:
   ```bash
   sudo ./scripts/bootstrap_jumpstart.sh
   ```

**¿Qué ocurre en este paso?**
* Se configura Netplan con la IP estática.
* Se configuran servicios base de red (`dhcp`, `tftpd`, `apache2`).
* Se instalan las dependencias de Python, Jinja2 y Ansible.
* Se instala y activa el **Coordinador Global** (`provisioning-coordinator.service`).

Puedes ver los logs del Coordinador en todo momento (¡altamente recomendado para ver "Matrix" fluir!):
```bash
sudo journalctl -u provisioning-coordinator -f
```

---

## FASE 3: Despliegue y Orquestación Continua

Con el entorno preparado, el despliegue de las máquinas (las 17 o solo unas pocas) es completamente desatendido.

1. En el terminal del Jumpstart, ejecuta:
   ```bash
   ./provisioner.py deploy
   ```
   *(También puedes indicar un solo nodo: `./provisioner.py deploy cluster-master-1`)*

**¿Qué sucede a continuación? (Automatización Total)**
1. **Validación:** El orquestador chequea la sintaxis de tus YAMLs y cruza IPs y MACs buscando solapamientos.
2. **Generación PXE:** Compila todas las plantillas dinámicamente y las vuelca en `/var/www/html`.
3. **Petición en Lote:** Envía la lista de tareas al Coordinador en background. Ya puedes cerrar la terminal si quieres, el Coordinador se encargará de todo.
4. **Ventana Deslizante:** El Coordinador crea y arranca las VMs en pequeños grupos de 3 (para no colapsar la RAM del anfitrión).
5. **Autoinstall y Callbacks:** Las VMs arrancan por red, se instalan solas vía Subiquity/Cloud-Init, y cuando terminan, envían una notificación HTTP al Coordinador y **se apagan solas**.
6. **Ansible:** Una vez todas las máquinas de la cola han emitido su señal de vida, el Coordinador las enciende todas a la vez e inyecta la configuración de Ansible por SSH.

---

## 🛠️ Comandos de Mantenimiento Diarios

El CLI principal (`provisioner.py`) soporta operaciones masivas eficientes (utilizando endpoints batch contra la API del Host):

* **Destrucción Total (Scorched Earth):**
  Borra todas las VMs y elimina los discos duros de forma segura (con bloqueos anti-lock).
  ```bash
  ./provisioner.py undeploy
  ```
* **Destrucción Quirúrgica (Reparación):**
  Si has roto una máquina experimentando, bórrala y vuelve a desplegarla en segundos:
  ```bash
  ./provisioner.py undeploy load-balancer
  ./provisioner.py deploy load-balancer
  ```
* **Control de Energía Sincronizado:**
  Por defecto, hemos configurado el sistema para apagar las máquinas de forma "elegante" y segura para no corromper bases de datos, simulando una pulsación del botón de apagado (ACPI).
  ```bash
  ./provisioner.py stop                   # Apagado ordenado (acpipowerbutton)
  ./provisioner.py stop --mode poweroff   # Tiro de cable instantáneo (peligroso)
  ./provisioner.py stop --mode savestate  # Hiberna todas las VMs en disco
  ./provisioner.py start                  # Despierta todas las VMs
  ```

---

## 🎓 Estrategia de Defensa en la Clase

Para la demostración final presencial de esta Fase 2, se sugiere este enfoque:

1. Mantén la maqueta completamente desplegada pero apagada (hibernada o ACPI).
2. Haz `undeploy` y `deploy` de **una sola máquina auxiliar** (ej. un hotdesk) delante de los profesores. Mostrará toda la magia (DHCP, TFTP, Cloud-Init y Ansible) sin tener que esperar 20 minutos por el clúster entero.
3. Muestra los logs divididos en dos pantallas:
   * **Consola Host:** `journalctl --user -u vbox-api -f` (Se ven las órdenes VBoxManage).
   * **Consola Jumpstart:** `sudo journalctl -u provisioning-coordinator -f` (Se ve la cola deslizante, los callbacks y Ansible).
4. Mientras el nodo solitario termina, enciende el resto del clúster con `./provisioner.py start` para demostrar que los servicios principales ya están en producción.
