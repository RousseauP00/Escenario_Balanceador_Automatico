#!/usr/bin/env python

from lib_vm import VM, NET
import logging, sys
import subprocess
import json
import os

def init_log():
    """
    Configura el sistema de logging.
    Modo 'debug: false': Mensajes breves de información.
    Modo 'debug: true': Mensajes detallados de depuración.
    """
    try:
        # Leer configuración desde el archivo JSON
        with open('manage-p2.json') as f:
            config = json.load(f)
            debug_mode = config.get("debug", False)
    except FileNotFoundError:
        print("Archivo 'manage-p2.json' no encontrado. Usando configuración por defecto.")
        debug_mode = False

    # Configurar el nivel de logging
    log_level = logging.DEBUG if debug_mode else logging.INFO

    logging.basicConfig(level=log_level)
    log = logging.getLogger('auto_p2')
    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', "%Y-%m-%d %H:%M:%S")
    ch.setFormatter(formatter)
    log.addHandler(ch)
    log.propagate = False


def pause():
    """
    Pausa la ejecución del programa para permitir al usuario revisar el estado.
    """
    programPause = input("-- Press <ENTER> to continue...")


def preconfig():
    """
    Configura el entorno inicial para el balanceador de tráfico.
    Modo 'debug: false': Informa sobre el progreso general de la configuración.
    Modo 'debug: true': Proporciona información detallada sobre cada paso y sus resultados.
    """
    try:
        # Verificar si el archivo qcow2 ya está en el directorio actual
        if not os.path.exists("cdps-vm-base-pc1.qcow2"):
            subprocess.check_call(["cp", "/lab/cdps/pc1/cdps-vm-base-pc1.qcow2", "."])
            print("Archivo cdps-vm-base-pc1.qcow2 copiado correctamente.")  
            logging.debug("Archivo cdps-vm-base-pc1.qcow2 copiado desde /lab/cdps/pc1.")
        else:
            print("Archivo cdps-vm-base-pc1.qcow2 ya existe, no se copia de nuevo.")
            logging.debug("Archivo cdps-vm-base-pc1.qcow2 ya presente en el directorio de trabajo.")

        # Verificar si el archivo XML ya está en el directorio actual
        if not os.path.exists("plantilla-vm-pc1.xml"):
            subprocess.check_call(["cp", "/lab/cdps/pc1/plantilla-vm-pc1.xml", "."])
            print("Archivo plantilla-vm-pc1.xml copiado correctamente.")
            logging.debug("Archivo plantilla-vm-pc1.xml copiado desde /lab/cdps/pc1.")        
        else:
            print("Archivo plantilla-vm-pc1.xml ya existe, no se copia de nuevo.")
            logging.debug("Archivo plantilla-vm-pc1.xml copiado desde /lab/cdps/pc1.")

        # Ejecutar prepare-vnx-debian solo si es necesario
        prepare_vnx_path = "/lab/cnvr/bin/prepare-vnx-debian"
        if os.path.exists(prepare_vnx_path) and os.access(prepare_vnx_path, os.X_OK):
            subprocess.check_call([prepare_vnx_path])
            print("prepare-vnx-debian ejecutado correctamente.")
            logging.debug("Comando prepare-vnx-debian ejecutado para preparar el entorno de virtualización.")
        else:
            print(f"No se puede ejecutar {prepare_vnx_path}. Verifica que exista y tenga permisos de ejecución.")
            logging.debug(f"Comando prepare-vnx-debian no encontrado o sin permisos de ejecución en {prepare_vnx_path}.")
        
    except subprocess.CalledProcessError as e:
        print(f"Failed to execute: {e}")
        logging.error(f"Error al ejecutar comando: {e}")


# Leer el archivo manage-p2.json para obtener el número de servidores
def get_number_of_servers():
    """
    Lee el número de servidores desde el archivo JSON.
    Modo 'debug: false': Indica el número leído.
    Modo 'debug: true': Incluye detalles de la estructura del archivo.
    """
    with open('manage-p2.json') as f:
        config = json.load(f)
    logging.info(f"Número de servidores configurados: {config.get('number_of_servers', 0)}")
    logging.debug(f"Configuración JSON completa: {config}")
    return config.get("number_of_servers", 0)



vms = {} # Diccionario global para almacenar las VMs y redes.
STATE_FILE = "vm_state.json"  # Archivo para guardar el estado de las VMs

# Guardar el estado de las VMs en un archivo JSON
def save_state():
    """
    Guarda el estado actual de las VMs en un archivo JSON.
    Modo 'debug: false': Confirma el guardado del estado.
    Modo 'debug: true': Describe el contenido guardado en detalle.
    """
    state = {name: {"name": vm.name} for name, vm in vms.items()}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)
    logging.info(f"Estado guardado en {STATE_FILE}")
    logging.debug(f"Contenido del estado guardado: {state}")


# Cargar el estado de las VMs desde un archivo JSON
def load_state():
    """
    Carga el estado de las VMs desde un archivo JSON si existe.
    Modo 'debug: false': Indica si el estado fue cargado o no.
    Modo 'debug: true': Proporciona detalles del estado cargado.
    """
    global vms
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        for name, data in state.items():
            vms[name] = VM(data["name"])
        logging.info(f"Estado cargado desde {STATE_FILE}")
        logging.debug(f"Estado cargado: {state}")
    else:
        logging.warning(f"No se encontró el archivo {STATE_FILE}. Ejecuta 'create' primero.")


# Borrar el archivo de estado antes de guardar nuevas configuraciones
def clear_state_file():
    """
    Elimina el archivo de estado JSON si existe.
    Modo 'debug: false': Indica si el archivo fue eliminado o no existe.
    Modo 'debug: true': Proporciona detalles adicionales del proceso.
    """
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logging.info(f"Archivo de estado {STATE_FILE} eliminado.")
        logging.debug(f"Archivo {STATE_FILE} eliminado correctamente del sistema de archivos.")  
    else:
        logging.info(f"Archivo de estado {STATE_FILE} no existe, nada que borrar.")
        logging.debug(f"Intento de eliminar {STATE_FILE} fallido: archivo no encontrado.")


def create():
    """
    Crea las VMs y redes definidas en el escenario.
    Modo 'debug: false': Informa de la creación general de cada elemento.
    Modo 'debug: true': Describe cada paso, incluyendo direcciones de red asignadas y estado del proceso.
    """
    clear_state_file()
    number_of_servers = get_number_of_servers()  # Leer el número de servidores del archivo JSON 
    logging.info(f"Creando {number_of_servers} servidores web.")
    logging.debug(f"Configuración inicial para {number_of_servers} servidores.")    

    # Creamos tantas VM como aparezca en el archivo de configuración
    for i in range(1, number_of_servers + 1):
        vm_name = f's{i}'
        server = VM(vm_name)
        vms[vm_name] = server  # Crea la VM y la asigna a la variable global
        ifs = []
        ifs.append( { "addr": f"10.1.2.{i+10}", "mask": "255.255.255.0" } )
        server.create_vm('cdps-vm-base-pc1.qcow2', ifs )
        logging.info(f"VM creada: {vm_name}")
        logging.debug(f"VM {vm_name} creada con dirección {ifs[0]['addr']} y máscara {ifs[0]['mask']}.")

    lb = VM('lb')
    vms['lb'] = lb
    c1 = VM('c1')
    vms['c1'] = c1

    
    lan1 = NET('lan1')
    vms['lan1'] = lan1
    lan2 = NET('lan2')
    vms['lan2'] = lan2
    lan1.create_net('lan1', "10.1.1.0", "24")
    lan2.create_net('lan2', "10.1.2.0", "24")
    logging.debug("Redes LAN1 (10.1.1.0/24) y LAN2 (10.1.2.0/24) creadas.")

    ifs = []
    ifs.append( { "addr": "10.1.1.1", "mask": "255.255.255.0" } )
    ifs.append( { "addr": "10.1.2.1", "mask": "255.255.255.0" } )
    lb.create_vm('cdps-vm-base-pc1.qcow2', ifs )
    logging.info("Balanceador de tráfico 'lb' configurado.")
    logging.debug(f"Balanceador 'lb' configurado con interfaces {ifs}.")
    
    
    ifs = []
    ifs.append( { "addr": "10.1.1.2", "mask": "255.255.255.0" } )
    c1.create_vm('cdps-vm-base-pc1.qcow2', ifs )
    logging.info("VM de cliente 'c1' configurada.")
    logging.debug(f"Cliente 'c1' configurado con dirección {ifs[0]['addr']}.")
    
    save_state()  # Guardar el estado después de crear las VMs
    pause()


def start():
    """
    Arranca todas las VMs del escenario.
    Modo 'debug: false': Notifica el estado de cada VM al ser arrancada.
    Modo 'debug: true': Proporciona detalles sobre los comandos y configuraciones aplicadas.
    """
    load_state()  # Cargar el estado antes de iniciar las VMs
    number_of_servers = get_number_of_servers()
    logging.info(f"Iniciando {number_of_servers} servidores web y demás elementos del escenario.")
    
    for i in range(1, number_of_servers + 1):
        vm_name = f's{i}'
        if vm_name in vms:
            server = vms[vm_name]
            server.start_vm()
            server.show_console_vm()
            logging.info(f"VM {vm_name} arrancada.")
            logging.debug(f"VM {vm_name} arrancada correctamente con consola activada.")
        else:
            logging.error(f"VM {vm_name} no encontrada en el diccionario de estado.")

    if 'lb' in vms:
        lb = vms['lb']
        lb.start_vm()
        lb.show_console_vm()
        logging.info("Balanceador de tráfico 'lb' arrancado.")
        logging.debug("Balanceador 'lb' iniciado correctamente y consola activada.")
    else:
        logging.error("Error: Balanceador 'lb' no encontrado en el diccionario de estado.")

    if 'c1' in vms:
        c1 = vms['c1']
        c1.start_vm()
        c1.show_console_vm()
        logging.info("VM 'c1' arrancada.")
        logging.debug("Cliente 'c1' arrancado con consola activada.")
    else:
        logging.error("Error: VM 'c1' no encontrada en el diccionario de estado.")
    
    try:
        subprocess.check_call(["sudo", "ip", "link", "set", "lan1", "up"])
        subprocess.check_call(["sudo", "ip", "addr", "add", "10.1.1.3/24", "dev", "lan1"])
        subprocess.check_call(["sudo", "ip", "route", "add", "10.1.0.0/16", "via", "10.1.1.1"])
        subprocess.check_call(["sudo", "ip", "link", "set", "lan2", "up"])
        logging.info("Host configurado para conectarse a LAN1.")
        logging.debug("Host conectado a LAN1 con IP 10.1.1.3 y ruta predeterminada 10.1.1.1.")    
    except subprocess.CalledProcessError as e:
        logging.error(f"Error al configurar el host para LAN1: {e}")


def stop():
    """
    Detiene todas las VMs en el escenario.
    Modo 'debug: false': Informa sobre las VMs detenidas y errores si no se encuentran.
    Modo 'debug: true': Proporciona detalles sobre cada operación de parada.
    """
    load_state()
    number_of_servers = get_number_of_servers()
    logging.info("Deteniendo las VMs del escenario.")
    
    for i in range(1, number_of_servers + 1):
        vm_name = f's{i}'
        if vm_name in vms:
            server = vms[vm_name]
            server.stop_vm()
            logging.info(f"VM {vm_name} parada.")
            logging.debug(f"La máquina virtual {vm_name} se detuvo correctamente.")
        else:
            logging.error(f"VM {vm_name} no encontrada en el diccionario 'vms'.")
    
    if 'lb' in vms:
        lb = vms['lb']
        lb.stop_vm()
        logging.info("Balanceador 'lb' parado.")
        logging.debug("Balanceador de tráfico 'lb' detenido correctamente.")
    else:
        logging.error("Balanceador 'lb' no encontrado en el diccionario 'vms'.")

    if 'c1' in vms:
        c1 = vms['c1']
        c1.stop_vm()
        logging.info("Cliente 'c1' parado.")
        logging.debug("La máquina virtual cliente 'c1' se detuvo correctamente.")
    else:
        logging.error("Cliente 'c1' no encontrado en el diccionario 'vms'.")
    
    save_state()
    pause()
    
    
def destroy():
    """
    Libera y elimina todas las VMs y recursos del escenario, incluidas las redes.
    Modo 'debug: false': Notifica la eliminación de cada recurso.
    Modo 'debug: true': Detalla los procesos de liberación y eliminación.
    """
    load_state()
    number_of_servers = get_number_of_servers()
    logging.info("Eliminando las VMs y recursos del escenario.")
    
    for i in range(1, number_of_servers + 1):
        vm_name = f's{i}'
        if vm_name in vms:
            server = vms[vm_name]
            server.destroy_vm()
            logging.info(f"VM {vm_name} eliminada.")
            logging.debug(f"La máquina virtual {vm_name} fue liberada y eliminada correctamente.")
        else:
            logging.error(f"VM {vm_name} no encontrada en el diccionario 'vms'.")

    if 'lb' in vms:
        lb = vms['lb']
        lb.destroy_vm()
        logging.info("Balanceador 'lb' eliminado.")
        logging.debug("El balanceador de tráfico 'lb' fue liberado y eliminado correctamente.")
    else:
        logging.error("Balanceador 'lb' no encontrado en el diccionario 'vms'.")
    
    if 'c1' in vms:
        c1 = vms['c1']
        c1.destroy_vm()
        logging.info("Cliente 'c1' eliminado.")
        logging.debug("La máquina virtual cliente 'c1' fue liberada y eliminada correctamente.")
    else:
        logging.error("Cliente 'c1' no encontrado en el diccionario 'vms'.")    
    
    try:
        lan1 = NET('lan1')
        lan2 = NET('lan2')
        lan1.destroy_net()
        lan2.destroy_net()
    except Exception as e:
        logging.error(f"Error al eliminar las redes: {e}")

    clear_state_file()
    pause()
    

if __name__ == "__main__":
    """
    Punto de entrada principal del script. Verifica los comandos pasados y ejecuta la acción correspondiente.
    """
    if len(sys.argv) != 2:
        print("Usage: python3 manage-p2.py <command>")
        print("Commands: create, start, stop, destroy")
        sys.exit(1)

    init_log()
    command = sys.argv[1]
    
    if command == "create":
        preconfig()
        create()
    elif command == "start":
        start()
    elif command == "stop":
        stop()
    elif command == "destroy":
        destroy()
    else:
        logging.error(f"Comando desconocido: {command}")
        sys.exit(1)
    
    logging.info("CDPS - Programa ejecutado correctamente.")
    