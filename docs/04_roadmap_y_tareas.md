# 04. Roadmap y Tareas del Proyecto (GAR)

Este documento registra el progreso de desarrollo del proyecto "Gestión y Administración de Redes" frente a los requisitos del enunciado oficial.

---

## ✅ FASE 1: Aprovisionamiento Baremetal (Completado)

Hemos finalizado al 100% la primera fase de infraestructura base del proyecto, implementando un motor robusto y dinámico que cumple holgadamente con los requisitos.

### Hitos Conseguidos:
- [x] **Arquitectura Dinámica YAML-Driven**: Redes y Nodos se definen vía código sin tocar scripts.
- [x] **VBox API Server**: Microservicio REST para sortear la limitación de VirtualBox (controlar VMs desde dentro de otra VM).
- [x] **Orquestador CLI (`provisioner.py`)**: Herramienta unificada para Validar, Desplegar y Configurar la red entera.
- [x] **Script de Bootstrap del Jumpstart**: Automatización total de la instalación de DHCP, TFTP, Apache y enrutamiento NAT temporal.
- [x] **Motor Multi-NIC y Redes Complejas**: Soporte en el orquestador para configurar múltiples tarjetas físicas por VM (intnet, NAT) en los archivos Netplan generados dinámicamente.
- [x] **Autoinstalador Inteligente (Cloud-Init)**: Plantillas para particionar, instalar paquetes y configurar cuentas de forma 100% desatendida.
- [x] **Callback Server y Boot-Swap**: Intercepción del evento "fin de instalación" para apagar el equipo, ordenar al Host el cambio de orden de arranque a "Disco Duro", y volver a arrancar de forma mágica y sin intervención humana.

---

## ⏳ FASE 2: Configuración de Servicios / Ansible (Pendiente)

La segunda fase del proyecto consiste en aprovisionar los servicios finales dentro de las máquinas que nuestra Fase 1 ha instalado con éxito, utilizando Ansible. El Stack tecnológico exacto a utilizar todavía debe ser decidido por el equipo.

### Roadmap de Tareas (Basado en el Enunciado):
- [ ] **Setup Inicial de Ansible**: 
  - [x] Crear estructura de carpetas (`playbooks/`, `roles/`, `inventory/`).
  - [ ] Generar el inventario dinámico o estático leyendo nuestros propios archivos YAML de la Fase 1.
- [ ] **Configuración del Balanceador (Requisitos 6, 7 y 9)**:
  - Instalar HAProxy o Nginx (a decidir).
  - Configurar las reglas de iptables/NAT para actuar como pasarela a Internet para la red MAIN.
- [ ] **Servidores Web/Frontales (Requisitos 9 y 12)**:
  - Instalar Apache o Nginx + PHP/FPM.
  - Conectar los Frontales al Balanceador.
- [ ] **Clúster de Base de Datos HA (Requisitos 10 y 11)**:
  - Definir tecnología (MariaDB Galera, MySQL InnoDB Cluster o PostgreSQL Patroni).
  - Configurar 2 nodos Master y 2 nodos Worker en la red INTERNAL.
- [ ] **Sistema Gestor de Contenidos (CMS)**:
  - Elegir tecnología (WordPress, Ghost, etc).
  - Desplegar la aplicación web en los Frontales conectada al clúster de Base de Datos.
- [ ] **Servidor de Almacenamiento (Requisito 10)**:
  - Configurar NFS, iSCSI o GlusterFS en el `storage-node`.
  - Montar el almacenamiento compartido en los servidores web o en el clúster.
- [ ] **Plataforma de Monitorización**:
  - Instalar servidor principal en el nodo `monitoring`.
  - Desplegar agentes recolectores (ej: SNMP, NodeExporter) en todas las máquinas a través de Ansible.
- [ ] **Pruebas de Carga de Tráfico (Requisito 15)**:
  - Crear un script `TrafficMix` (bash/python) para generar uso continuo sobre la aplicación.
