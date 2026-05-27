# 🤖 Instrucciones para Agentes IA (AGENTS.md)

Este archivo proporciona contexto crítico, reglas de arquitectura y convenciones del proyecto para cualquier Asistente o Agente de Inteligencia Artificial que vaya a contribuir a este repositorio. 

**Lee esto con atención antes de proponer cambios en el código.**

---

## 1. Contexto del Proyecto
* **Asignatura:** Gestión y Administración de Redes (GAR).
* **Objetivo:** Desplegar una infraestructura empresarial simulada (Load Balancer, Web Frontends, DB Cluster, Storage, Monitoring, Hotdesks) usando **VirtualBox**.
* **Estado Actual:** Fase 1 (Aprovisionamiento Baremetal Desatendido vía PXE/Cloud-Init) **COMPLETADA**. Fase 2 (Configuración de Servicios con Ansible) **PENDIENTE**.

---

## 2. Reglas de Arquitectura (INQUEBRANTABLES)

1. **Todo es Data-Driven (YAML):** 
   * **PROHIBIDO** hardcodear nombres de máquinas, IPs o MACs en scripts de Python o Bash.
   * La infraestructura se define **exclusivamente** en `config/networks.yml` y `config/nodes/*.yml`.
2. **Limitación de VirtualBox (El problema del Jumpstart):**
   * El orquestador corre en la máquina "Jumpstart" (una VM). Las VMs no pueden ejecutar `VBoxManage` para crear otras VMs en el Host.
   * **Solución actual:** Usamos un servidor REST en el anfitrión físico (`vbox_api_server.py` en el puerto 7070). El orquestador habla con él. **NO intentes cambiar este diseño**, es fundamental.
3. **Flujo de Autoinstalación:**
   * Usamos PXELINUX + Ubuntu Autoinstall (Cloud-Init/Subiquity).
   * Al finalizar la instalación, las VMs **deben apagarse** (`shutdown -P now`) y lanzar un POST a `http://192.168.1.254:8081`. 
   * El microservicio `provision_callback.py` del Jumpstart capta este POST, pide al Host que cambie el orden de arranque a "Disco Duro" y reenciende la VM. **NO rompas este flujo o causarás bucles de reinstalación infinitos**.

---

## 3. Reglas de Red

1. **Red `main` (`192.168.1.0/24`):** Debe tener acceso a Internet. Durante la Fase 1 lo obtiene del Jumpstart (NAT). En la Fase 2, lo obtendrá del Load Balancer (que tiene una NIC NAT extra).
2. **Red `internal` (`192.168.2.0/24`):** Red **AISLADA**. Solo puede comunicarse con la red `main`. No le configures pasarelas a Internet directas.
3. **Múltiples NICs:** El generador de configuraciones (`gar_orchestrator/config_generator.py`) soporta múltiples tarjetas por VM. Si añades redes tipo `nat`, se configurarán por DHCP en Netplan; las internas serán estáticas.

---

## 4. Convenciones de Código

* **Python:** 
  * Se requiere Python 3.10+.
  * **Cero Dependencias Externas** para el orquestador (usamos nuestro propio parser YAML nativo para evitar obligar a instalar `PyYAML`).
* **Bash:** 
  * Usa `set -euo pipefail` en todos los scripts de Bash.
  * Colorea las salidas por consola para mejorar la legibilidad.
* **Ansible (Fase 2):** 
  * Las contraseñas de las VMs instaladas son `admin`. El usuario es `admin`.
  * Sin embargo, **NO se debe usar contraseña por SSH**. El Jumpstart inyecta su clave pública en todos los nodos durante el Autoinstall. Ansible debe autenticarse por llaves.

---

## 5. Dónde buscar la Documentación
No asumas cómo funciona el proyecto. Lee primero la documentación oficial que se encuentra en la carpeta `docs/`:
- `docs/01_arquitectura.md`: Diseño profundo del sistema.
- `docs/02_guia_despliegue.md`: Pasos operativos.
- `docs/03_referencia_yaml.md`: Formato de los archivos.
- `docs/04_roadmap_y_tareas.md`: Lo que falta por hacer.
