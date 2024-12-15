import logging
import os
import subprocess
from lxml import etree

log = logging.getLogger('manage-p2')

class VM: 
  def __init__(self, name):
    self.name = name
    log.debug(f"Inicializando VM: {self.name}")


  def create_vm (self, image, interfaces):
    image_name = f"{self.name}.qcow2"
    log.debug(f"Creando imagen para VM {self.name}: Base {image}, Output {image_name}")
    
    try:
      subprocess.check_call(
        ["qemu-img", "create", "-F", "qcow2", "-f", "qcow2", "-b",image, image_name])
      log.info(f"Imagen creada: {image_name}")
        
    except subprocess.CalledProcessError as e:
      log.error(f"Error al crear imagen para VM {self.name}: {e}")
      return
    
    log.debug(f"Configurando VM {self.name} con interfaces: {interfaces}")
    for i in interfaces:
      log.debug(f"  Configuración de interfaz: addr={i['addr']}, mask={i['mask']}")
    
    
    def create_xml(name_vm, xml="plantilla-vm-pc1.xml"):
      xml_name = f"{name_vm}.xml"
      log.debug(f"Creando XML para VM {name_vm}: Base {xml}, Output {xml_name}")
      
      try:
        subprocess.check_call(["cp", xml, xml_name])
        log.info(f"Archivo XML creado: {xml_name}")
          
      except subprocess.CalledProcessError as e:
        log.error(f"Error al crear archivo XML para VM {name_vm}: {e}")
        return
      
      log.debug("create_xml " + name_vm + " (xml: " + xml + ")")
      
      # Cargamos el fichero xml de la VM para modificarlo
      log.debug(f"Cargando archivo XML: {xml_name}")
      tree = etree.parse(xml_name)
      
      # Imprimimos el XML cargado en formato legible
      log.debug(f"Contenido inicial del archivo XML {xml_name}:\n{etree.tounicode(tree, pretty_print=True)}")
      
      # Obtenemos el nodo raiz e imprimimos su nombre y el valor del atributo 'tipo'
      root = tree.getroot()
      log.debug(f"Nodo raíz: {root.tag}, Atributo 'tipo': {root.get('tipo')}")
      
      # Buscamos la etiqueta imprimimos su valor y luego lo cambiamos
      name = root.find("name")
      log.debug(f"Etiqueta <name> encontrada: {name.text}")
      name.text = name_vm
      log.debug(f"Etiqueta <name> actualizada: {name.text}") 
      
      # Configuramos la ruta del archivo qcow2
      current_dir = os.path.dirname(os.path.abspath(__file__))
      image_path = os.path.join(current_dir, f"{name_vm}.qcow2")
      source=root.find("./devices/disk/source")
      log.debug(f"Etiqueta <source> antes del cambio: {source.get('file')}")
      source.set("file", image_path)
      log.debug(f"Etiqueta <source> actualizada: {source.get('file')}")
      
      # Añadimos un elemento <virtualport> al nodo <interface>
      interface=root.find("./devices/interface")
      virtualport = etree.Element("virtualport", type='openvswitch')
      interface.append(virtualport)
      log.debug(f"Elemento <virtualport> añadido al nodo <interface>.")

      
      # Configuramos el bridge de red según el tipo de VM
      if name_vm in ("s1", "s2", "s3", "s4", "s5"):
        # Modificamos Interface
        bridge=root.find("./devices/interface/source")
        bridge.set("bridge", "lan2")
        log.info(f"Bridge configurado para {name_vm}: lan2")
        log.debug(f"Etiqueta <source> actualizada: {bridge.get('bridge')}")
          
      else:
        # Modificamos Interface
        bridge=root.find("./devices/interface/source")
        bridge.set("bridge", "lan1")
        log.info(f"Bridge configurado para {name_vm}: lan1")
        log.debug(f"Etiqueta <source> actualizada: {bridge.get('bridge')}")
        
        if (name_vm == "lb"):
          # Añadimos una nueva interfaz para el balanceador
          devices=root.find("devices")
          interface = etree.Element("interface", type="bridge")
          
          source = etree.SubElement(interface, "source", bridge="lan2")
          model = etree.SubElement(interface, "model", type="virtio")
          virtualport = etree.SubElement(interface, "virtualport", type='openvswitch')
          
          devices.append(interface)
          log.info(f"Interfaz adicional configurada para {name_vm} en bridge lan2.")
          log.debug(f"Interfaz añadida: {etree.tounicode(interface, pretty_print=True)}")

      
      # Log del XML con todos los cambios realizados
      log.debug(f"XML modificado para {name_vm}:\n{etree.tounicode(tree, pretty_print=True)}")
      
      # Guardar los cambios en el archivo XML
      tree.write(xml_name, pretty_print=True, xml_declaration=True, encoding="UTF-8")
      log.info(f"Archivo XML {xml_name} guardado exitosamente.")

      # Ejecutar virsh define para registrar la máquina virtual
      try:
        subprocess.check_call(["sudo", "virsh", "undefine", name_vm])
      except subprocess.CalledProcessError as e:
        log.debug(f"VM {name_vm} no estaba previamente definida, omitiendo undefine.")
        
      try:
        subprocess.check_call(["sudo", "virsh", "define", xml_name])
        log.info(f"VM {name_vm} definida exitosamente.")
      except subprocess.CalledProcessError as e:
        log.error(f"Error al definir VM {name_vm}: {e}")
      
    create_xml(self.name)


  def start_vm(self):
    log.debug(f"Iniciando VM {self.name}")
    
    try:
      # Variables de red
      netmask = "255.255.255.0"
      if self.name.startswith("s"):
          server_number = int(self.name[1:])
          ip_addr = f"10.1.2.{server_number + 10}"
          gateway = "10.1.2.1"
      elif self.name == "lb":
          # Balanceador (router)
          eth0_ip = "10.1.1.1"
          eth1_ip = "10.1.2.1"
          gateway = None
      elif self.name == "c1":
          ip_addr = "10.1.1.2"
          gateway = "10.1.1.1"
      else:
          log.error(f"Unknown VM name format: {self.name}")
          return

      # Generar ficheros temporales
      config_dir = f"tmp_configs/{self.name}"
      os.makedirs(config_dir, exist_ok=True)

      # Crear /etc/hostname
      hostname_path = os.path.join(config_dir, "hostname")
      with open(hostname_path, "w") as f:
          f.write(self.name)

      # Crear /etc/network/interfaces
      interfaces_path = os.path.join(config_dir, "interfaces")
      with open(interfaces_path, "w") as f:
          f.write("auto lo\niface lo inet loopback\n")
            
          if self.name == "lb":
              # Configuración para el balanceador
              f.write("\nauto eth0\n")
              f.write(f"iface eth0 inet static\n")
              f.write(f"    address {eth0_ip}\n")
              f.write(f"    netmask {netmask}\n")
              
              f.write("\nauto eth1\n")
              f.write(f"iface eth1 inet static\n")
              f.write(f"    address {eth1_ip}\n")
              f.write(f"    netmask {netmask}\n")
          else:
              # Configuración para servidores o cliente
              f.write("\nauto eth0\n")
              f.write(f"iface eth0 inet static\n")
              f.write(f"    address {ip_addr}\n")
              f.write(f"    netmask {netmask}\n")
              if gateway:
                  f.write(f"    gateway {gateway}\n")

      # Copiar configuraciones a la imagen de la VM
      qcow2_path = f"{self.name}.qcow2"
      subprocess.check_call(["sudo", "virt-copy-in", "-a", qcow2_path, hostname_path, "/etc"])
      subprocess.check_call(["sudo", "virt-copy-in", "-a", qcow2_path, interfaces_path, "/etc/network"])
      log.debug(f"Hostname y configuración de red copiados para {self.name}")

      # Modificar /etc/hosts
      edit_cmd = f"s/127.0.1.1.*/127.0.1.1 {self.name}/"
      subprocess.check_call(["sudo", "virt-edit", "-a", qcow2_path, "/etc/hosts", "-e", edit_cmd])
      log.debug(f"/etc/hosts configurado para {self.name}")

      # Configurar balanceador como router y como balanceador de carga
      if self.name == "lb":
        # Habilitar ip_forward en /etc/sysctl.conf
        edit_cmd = "s/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/"
        subprocess.check_call(["sudo", "virt-edit", "-a", qcow2_path, "/etc/sysctl.conf", "-e", edit_cmd])
        log.debug("Configuración de ip_forward aplicada al balanceador (LB)")
        
        # Configurar HAProxy
        haproxy_cfg = """
frontend lb
    bind *:80
    mode http
    default_backend webservers

backend webservers
    mode http
    balance roundrobin
    server s1 10.1.2.11:80 check
    server s2 10.1.2.12:80 check
    server s3 10.1.2.13:80 check
"""
        with open("haproxy.cfg", "w") as f:
          f.write(haproxy_cfg)
          
        subprocess.check_call(["sudo", "virt-copy-in", "-a", qcow2_path, "haproxy.cfg", "/etc/haproxy/"])
        log.debug("Configuración de HAProxy copiada a lb")

        # Reiniciar HAProxy al arranque
        subprocess.check_call(["sudo", "virt-edit", "-a", qcow2_path, "/etc/rc.local", "-e", 
                                "s|^exit 0|sudo service haproxy restart\nexit 0|"])
        log.debug("HAProxy se reiniciará automáticamente al arranque")

      # Configurar Apache en s1, s2, s3
      if self.name.startswith("s"):
        index_content = f"<html><body><h1>Server {self.name}</h1></body></html>"
        with open("index.html", "w") as f:
            f.write(index_content)
        subprocess.check_call(["sudo", "virt-copy-in", "-a", qcow2_path, "index.html", "/var/www/html/"])
        log.debug(f"Página personalizada copiada a {self.name}")

        # Reiniciar Apache al arranque
        subprocess.check_call(["sudo", "virt-edit", "-a", qcow2_path, "/etc/rc.local", "-e", 
                                "s|^exit 0|sudo service apache2 restart\nexit 0|"])
        log.debug(f"Apache se reiniciará automáticamente en {self.name}")
      
      # Arrancar la máquina virtual
      subprocess.check_call(["sudo", "virsh", "start", self.name])
      log.info(f"VM {self.name} iniciada exitosamente.")
    
      # Comprobar la configuración de red
      network = subprocess.check_output(["sudo", "virt-cat", "-a", qcow2_path, "/etc/network/interfaces"])
      log.debug(network.decode("utf-8"))
      

    except subprocess.CalledProcessError as e:
      log.error(f"Error al configurar o iniciar VM {self.name}: {e}")
    except Exception as e:
      log.error(f"Error al configurar o iniciar VM {self.name}: {e}")
      
    
  def show_console_vm (self):
    log.debug(f"Abriendo consola para VM {self.name}")
    try:
      # Abrir un nuevo terminal para la consola de la VM
      log.debug(f"Abriendo consola para VM {self.name} en un nuevo terminal")
      
      # Comando para abrir un nuevo terminal con virsh console
      subprocess.Popen(
        ["xterm", "-e", f"sudo virsh console {self.name}"],
          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
      )
      log.info(f"Consola de VM {self.name} abierta en un nuevo terminal.")
    except FileNotFoundError:
        log.error("Error: xterm no está instalado. Instálalo para abrir consolas.")
    except subprocess.CalledProcessError as e:
        log.error(f"Error al abrir consola para VM {self.name}: {e}")


  def stop_vm (self):
    log.debug(f"Deteniendo VM {self.name}")
    try:
      # Apagar la máquina virtual
      subprocess.check_call(["sudo", "virsh", "shutdown", self.name])
      log.info(f"VM {self.name} detenida exitosamente.")
        
    except subprocess.CalledProcessError as e:
      log.error(f"Error al detener VM {self.name}: {e}")
      return
    

  def destroy_vm (self):
    log.debug(f"Destruyendo VM {self.name}")

    # Apagar y eliminar las máquinas virtuales
    try:
      subprocess.check_call(["sudo", "virsh", "destroy", self.name])
      log.info(f"VM {self.name} destruida.")
    except subprocess.CalledProcessError as e:
      log.error(f"Error al destruir VM {self.name}: {e}")

    # Eliminar la definición de la VM
    try:
      subprocess.check_call(["sudo", "virsh", "undefine", self.name])
      log.info(f"Definición de VM {self.name} eliminada.")
    except subprocess.CalledProcessError as e:
      log.error(f"Error al eliminar definición de VM {self.name}: {e}")

    # Borrar los archivos creados (imagenes qcow2, xml, configuraciones temporales)
    log.info("Iniciando eliminación de archivos creados...")
    for file in os.listdir("."):
        if file.endswith(".qcow2") or file.endswith(".xml") or file.startswith("tmp_configs"):
            try:
                file_path = os.path.join(".", file)
                if os.path.isdir(file_path):
                  # Eliminar directorios recursivamente
                  subprocess.check_call(["rm", "-rf", file_path])
                  log.info(f"Directorio eliminado: {file}")

                else:
                  # Eliminar archivos
                  os.remove(file_path)
                  log.info(f"Archivo eliminado: {file}")

                log.debug(f"Archivo o directorio eliminado: {file_path}")
            except Exception as e:
              log.error(f"No se pudo eliminar {file}: {e}")
            
    log.info("Escenario liberado correctamente.")


class NET:
  def __init__(self, name):
    self.name = name
    log.debug(f"Inicializando red: {self.name}")

  def create_net(self, bridge_name, ip_address, netmask):
    log.debug(f"Creando red: Bridge={bridge_name}, IP={ip_address}, Netmask={netmask}")
      
    try:
      #Crear el bridge con Open vSwitch
      subprocess.check_call(["sudo", "ovs-vsctl", "add-br", bridge_name])
      # Asignar dirección IP al bridge
      subprocess.check_call(["sudo", "ip", "addr", "add", f"{ip_address}/{netmask}", "dev", bridge_name])
      # Activar el bridge
      subprocess.check_call(["sudo", "ip", "link", "set", "dev", bridge_name, "up"])
      log.info(f"Red {self.name} creada exitosamente con Bridge {bridge_name}.")
    
    except subprocess.CalledProcessError as e:
      log.error(f"Error al crear la red {self.name}: {e}")

  def destroy_net(self):
    # Eliminar los bridges creados
    log.info(f"Iniciando eliminación del bridge: {self.name}")
    try:
      subprocess.check_call(["sudo", "ovs-vsctl", "del-br", self.name])
      log.info(f"Bridge eliminado: {self.name}")
      log.debug(f"Bridge {self.name} eliminado exitosamente.")
    except subprocess.CalledProcessError as e:
      log.error(f"No se pudo eliminar el bridge {self.name}: {e}")
      

