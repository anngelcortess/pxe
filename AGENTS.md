# 🤖 Instrucciones para Agentes IA (AGENTS.md)

Este archivo proporciona contexto crítico, reglas de arquitectura y convenciones del proyecto para cualquier Asistente o Agente de Inteligencia Artificial que vaya a contribuir a este repositorio. 

**Lee esto con atención antes de proponer cambios en el código.**

---

## 1. Contexto del Proyecto
* **Asignatura:** Gestión y Administración de Redes (GAR).
* **Objetivo:** Desplegar una infraestructura empresarial simulada (Load Balancer, Web Frontends, DB Cluster, Storage, Monitoring, Hotdesks) usando **VirtualBox**.
* **Estado Actual:** Fase 1 (Aprovisionamiento Baremetal) **COMPLETADA**. Fase 2 (Configuración con Ansible) **EN PROGRESO**.
* **Estructura del Repositorio:** Este es el repositorio de pruebas `GAR-pruebas`. El código validado aquí se trasvasa posteriormente al repositorio oficial `gar` para la entrega.

---

## 2. Reglas de Arquitectura (INQUEBRANTABLES)

1. **Todo es Data-Driven (YAML):** 
   * **PROHIBIDO** hardcodear nombres de máquinas, IPs o MACs en scripts.
   * La infraestructura se define **exclusivamente** en `config/networks.yml` y `config/nodes/*.yml`.
2. **Limitación de VirtualBox (El problema del Jumpstart):**
   * El orquestador corre en la máquina "Jumpstart" (una VM). Las VMs no pueden ejecutar `VBoxManage` de forma nativa para crear otras VMs en el Host físico.
   * **Solución actual:** Usamos un microservicio en el anfitrión (`vbox-api.service` en el puerto 7070). El orquestador habla con él. **NO intentes cambiar este diseño**.
3. **Flujo de Autoinstalación y Ventana Deslizante:**
   * Usamos PXELINUX + Ubuntu Autoinstall (Cloud-Init/Subiquity).
   * Desplegar 17 VMs a la vez colapsa la RAM del ordenador físico. Para evitarlo, el `provisioning-coordinator` implementa una **ventana deslizante dinámica** en memoria. Crea y arranca nodos en lotes de 3.
   * Al finalizar la instalación, las VMs **se apagan a sí mismas** (`shutdown -P now`) e instantes antes envían un POST a `http://192.168.1.254:8081/node-ready`. 
   * El Coordinador capta este evento, avanza la cola, ajusta la configuración de la VM (pasando de PXE a Disco, y ampliando la RAM) y, cuando **TODAS** han terminado, las enciende en bloque e invoca a Ansible de forma asíncrona.

---

## 3. Reglas de Red

1. **Red `main` (`192.168.1.0/24`):** Debe tener acceso a Internet. Durante la Fase 1 lo obtiene del Jumpstart (NAT temporal). En la Fase 2, lo obtendrá del Load Balancer de forma definitiva.
2. **Red `internal` (`192.168.2.0/24`):** Red **AISLADA**. Solo puede comunicarse con la red `main`. No le configures pasarelas a Internet directas (saltaría los requisitos).

---

## 4. Convenciones de Código

* **Python:** 
  * Se requiere Python 3.10+.
  * Código altamente estructurado en módulos (`baremetal.py`, `coordinator.py`, `ansible_runner.py`).
* **Ansible (Fase 2):** 
  * **NO se debe usar contraseña por SSH**. El Jumpstart inyecta su clave pública en todos los nodos durante el Autoinstall. Ansible se autentica por llaves.
  * Todas las IPs están predefinidas estáticamente en el DHCP/Cloud-Init a partir de la configuración YAML.

---

## 5. Dónde buscar la Documentación
No asumas cómo funciona el proyecto. Lee primero la documentación en `docs/`:
- `docs/01_arquitectura.md`: Diseño profundo de la máquina de estados y ventana deslizante.
- `docs/02_guia_despliegue.md`: Pasos operativos de los CLI y systemd.
- `docs/04_roadmap_y_tareas.md`: Lo que falta por hacer con los playbooks de Ansible.

---

## 6. Estructura de Carpetas (Fronteras Lógicas)
Es vital respetar estas fronteras:
- `provisioning/`: Lógica del sistema de orquestación en Python (API, Coordinador) y plantillas base (Jinja2).
- `ansible/`: Todo lo relacionado con la Fase 2. Aquí irán los playbooks y los roles para desplegar servicios.
- `config/`: El punto de verdad universal.
- `scripts/`: Helpers en bash para arrancar servicios (`bootstrap_jumpstart.sh`, etc).
