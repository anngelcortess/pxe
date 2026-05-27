# 05. Propuesta de Reparto: Fase 2 (Configuration Management)

**Equipo:** 5 personas
**Herramienta Base:** Ansible (Todos crearán roles y playbooks para su parte).
**Nodos Totales:** 17

**Tecnologías a usar:**
- Ansible
- Docker Swarm
- Nginx
- CheckMK + SNMP
- UFW
- GlusterFS

La estrategia es que cada miembro asuma un "Rol" como especialista de una pieza clave de la infraestructura. De esta forma, cada uno puede programar su parte en Ansible casi de forma independiente, uniéndolo todo al final en un `site.yml`.

---

### 🛡️ Rol 1: Network & Edge Security (1 Nodo principal)
**Nodos a cargo:** `load-balancer`
**Tecnologías:** Nginx (Proxy), UFW, iptables (NAT).
**Misión:** Es el guardián de la red.
- Configurar el nodo para que actúe como enrutador NAT (dando Internet a la red MAIN cuando se apague el Jumpstart).
- Instalar y configurar Nginx como balanceador de carga HTTP/HTTPS para repartir el tráfico hacia los dos Web Frontends (Req. 4a y 6).
- Configurar UFW para bloquear todo el tráfico externo excepto los puertos web.
*Dificultad técnica alta (redes), pero muy focalizado en un solo nodo.*

### 🕸️ Rol 2: Web Layer & CMS (2 Nodos principales + Scripting)
**Nodos a cargo:** `web-frontend-1`, `web-frontend-2`
**Tecnologías:** Nginx (Web Server), PHP/CMS, Bash/Python (TrafficMix).
**Misión:** Que la web funcione y reciba visitas.
- Instalar el servidor web y las dependencias del CMS (ej. WordPress) en los frontales (Req. 4b).
- Conectar el CMS a la base de datos (que montará el Rol 3) y al almacenamiento (Rol 4).
- Desarrollar el script `TrafficMix` (Req. 15) que se ejecutará desde fuera para simular tráfico.
*Carga de trabajo media, mucho trabajo de configuración de aplicación.*

### 🐝 Rol 3: Clustering & Database HA (4 Nodos)
**Nodos a cargo:** `cluster-master-1`, `cluster-master-2`, `cluster-worker-1`, `cluster-worker-2`
**Tecnologías:** Docker Swarm, MySQL/MariaDB.
**Misión:** El motor de los datos en Alta Disponibilidad (Req. 2 y 3).
- Crear un rol de Ansible que instale Docker en los 4 nodos y los federe formando un clúster Swarm.
- Desplegar la Base de Datos SQL en formato clúster (Alta disponibilidad) dentro de los nodos.
- (Opcional) Si el CMS se despliega en contenedores, coordinar con el Rol 2 para desplegar los servicios en el Swarm.
*Carga de trabajo alta, Docker Swarm y DB Clustering es el núcleo duro de la práctica.*

### 💾 Rol 4: Storage & Redundancy (1 Nodo servidor, varios clientes)
**Nodos a cargo:** `storage-node` (+ integraciones)
**Tecnologías:** GlusterFS.
**Misión:** Que no se pierda ni un archivo (Req. 12).
- Instalar y configurar GlusterFS en el `storage-node` para exportar volúmenes de red.
- Crear las tareas de Ansible para **montar** esos volúmenes compartidos en los nodos Web y en el Clúster. 
- *Importante:* GlusterFS suele requerir más de un nodo para replicación real, pero al tener solo un `storage-node`, este rol se encargará de configurar el volumen distribuido y asegurar que los Frontends leen y escriben los archivos del CMS en el mismo sitio.
*Carga técnica media-alta. Es el pegamento que une los datos de los demás.*

### 📊 Rol 5: Observability & Hotdesks (9 Nodos)
**Nodos a cargo:** `monitoring`, `hotdesk-1` a `hotdesk-8`
**Tecnologías:** CheckMK, SNMP.
**Misión:** Vigilar que todo funciona y configurar los clientes (Req. 5, 10 y 11).
- Instalar el servidor central de CheckMK en el nodo `monitoring`.
- Desarrollar un "Rol de Ansible universal" que instale el agente SNMP y lo configure en los **17 nodos** de la maqueta para enviar métricas de CPU, RAM y Red al servidor.
- Configurar lo básico en los 8 Hotdesks (ej. crear usuarios de sistema, instalar utilidades de red básicas).
*Muchos nodos, pero tareas muy automatizables y repetitivas. Ideal para dominar Ansible.*

---

### 🤝 ¿Cómo trabajar en equipo sin pisarse?
Dentro del repositorio, cread una carpeta `ansible/`. Dentro, cada uno crea sus "roles" independientemente:
- `ansible/roles/loadbalancer/` (Rol 1)
- `ansible/roles/cms/` (Rol 2)
- `ansible/roles/swarm/` (Rol 3)
- `ansible/roles/storage/` (Rol 4)
- `ansible/roles/monitoring/` (Rol 5)

Y luego tendréis un único archivo `site.yml` que llama a los roles de cada uno sobre los nodos correspondientes. Cero conflictos de código.
