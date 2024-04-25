import subprocess  # cpu usage、cpu temperature、ram usage、gpu usage、gpu temperature
import psutil  # drive usage
from pySMART import Device  # drive temperature
from pySMART import DeviceList  # get drive model
import GPUtil  # gpu model
import time
import tkinter 
import logging
from ezpronotification import EZProNotification
from ezproserver import EZProServer
import json

class HardwareMonitor_Linux():

    def __init__(self) -> None:
        self.setup_logger()
        self.ezpro = EZProServer()
        self.cpu = CPUInfo()
        self.ram = RAMInfo()
        self.gpu = GPUInfo()
        self.drives = {}  # Dictionary 
        self.process = None
        self.findRAM = False
        self.findGR3D_FREQ = False
        self.isRunning = False
        self.enableLoggingNotification = tkinter.IntVar()
        self.enableNotifyToEzPro = tkinter.IntVar()
        self.notification_items = []  # a list of AlarmItem 
        self.logging_period = '10'  # default 10 minute
        self.stopwatch = Stopwatch()

    # 設置 logger
    def setup_logger(self):
        try:
            self.logger_hardwaremonitor = logging.getLogger('HARDWAREMONITOR')
            self.logger_hardwaremonitor.setLevel(logging.INFO)
            self.filehandler = logging.FileHandler(f'hardwaremonitor_{time.strftime("%Y%m%d")}.log')
            self.filehandler.setLevel(logging.INFO)
            self.formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
            self.filehandler.setFormatter(self.formatter)
            self.logger_hardwaremonitor.addHandler(self.filehandler)
            print('setup logger_hardwaremonitor success')
        except Exception as e:
            print(f'setup logger_hardwaremonitor error: {e}')

    # 開始監控
    def start_monitor(self):
        self.stopwatch.start()
        while True and self.isRunning:
            if self.process is None:
                self.process = subprocess.Popen(['tegrastats'], stdout=subprocess.PIPE, text=True)
            output_line = self.process.stdout.readline()
            hardwareInfos = output_line.split(' ')

            for info in hardwareInfos:
                if "RAM" in info:
                    self.findRAM = True
                    continue

                if "/" in info and "MB" in info and self.findRAM:
                    self.findRAM = False
                    ramArr = info.replace("MB", "").split("/")
                    self.ram.usage = round(float(ramArr[0]) * 100 / float(ramArr[1]), 1)
                    print(f"RAM: {self.ram.usage}%")

                if "[" in info and "]" in info:
                    arrCPUs = info.replace("[", "").replace("]", "").split(",")
                    total = 0
                    for core in arrCPUs:
                        total += int(core.split("%@")[0])
                    self.cpu.usage = round(total / len(arrCPUs), 1)
                    print(f"CPU: {self.cpu.usage}%")

                if "CPU@" in info:
                    self.cpu.temperature = int(float(info.split("@")[1].replace("C","")))
                    print(f"CPU_Temperature: {self.cpu.temperature}C")

                if "GR3D_FREQ" in info:
                    self.findGR3D_FREQ = True

                if "%@" in info and self.findGR3D_FREQ:
                    self.findGR3D_FREQ = False
                    arrGPU = info.split("%@")
                    self.gpu.usage = round(float(arrGPU[0]), 1)
                    print(f"GPU: {self.gpu.usage}%")

                if "GPU@" in info and "C" in info:
                    arr = info.split("@")
                    self.gpu.temperature = int(float(arr[1].replace("C", "")))
                    print(f"GPU_Temperature: {self.gpu.temperature}C")

            self.get_drives_info()

            self.stopwatch.stop()
            # print(f'{self.stopwatch.elapsed_time}')
            if self.stopwatch.elapsed_time > int(self.logging_period)*60:
                self.stopwatch.reset()
                self.stopwatch.start()
                dreiveInfo_string = ""
                for drive in self.drives:
                    driveInfo = self.drives[drive]
                    dreiveInfo_string += f"{driveInfo.name} usage: {driveInfo.usage}, temperature: {driveInfo.temperature}" 
                message = f"cpu usage:{self.cpu.usage}, cpu temperature:{self.cpu.temperature}; ram usage:{self.ram.usage}; gpu usage:{self.gpu.usage}, gpu temperature:{self.gpu.temperature}; {dreiveInfo_string}"
                self.logger_hardwaremonitor.info(message)
                # print(message)
            else:
                self.stopwatch.start()

            if self.enableNotifyToEzPro.get() == 1:
                self.send_notification()

            time.sleep(1)

    # 停止監控
    def stop_monitor(self):
        self.isRunning = False
        if self.process is not None:
            self.process.terminate()
            self.process.wait()

    # 取得所有硬碟 (初始化用)
    def get_devices(self) -> list:
        return psutil.disk_partitions()

    # 取得硬碟資訊(名稱、使用量、溫度)
    def get_drives_info(self):
        try:

            partitions = psutil.disk_partitions()

            for partition in partitions:

                if 'cdrom' in partition.opts or partition.fstype == '':
                    continue

                usage = psutil.disk_usage(partition.mountpoint)
                print(f"drive({partition.device}) usage: {round(usage.percent)}%")

                temperature = 0

                if not self.is_smartmontools_installed():
                    print("Please install smartmontools to proceed.")
                else:
                    temperature = self.get_specific_device_temperature(partition.device) or 0         

                # create/update value
                self.drives[partition.device] = DriveInfo(partition.device, round(usage.percent, 1), temperature)  

        except Exception as e:
            self.logger_hardwaremonitor.error(f'get drives info error: {e}')

    # 檢查是否安裝 smartmontools
    def is_smartmontools_installed(self):
        try:
            subprocess.run(['smartctl', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            self.logger_hardwaremonitor.error("smartctl is installed but there was a problem running it.")
            return False
        except FileNotFoundError:
            self.logger_hardwaremonitor.error("smartmontools is not installed.")
            return False
        
    # 取得硬碟溫度 by using pySMART    
    def get_specific_device_temperature(self, device_name: str) -> int:
        try:
            return Device(device_name).temperature
        except Exception as e:
            print(f'get device temperature error: {e}')
            self.logger_hardwaremonitor.error(f'get device temperature error: {e}')
            return 0 
        
    # 取得 cpu model 
    def get_cpu_model(self) -> str:
        try:
            with open("/proc/cpuinfo") as file:
                for line in file:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        except Exception as e:
            self.logger_hardwaremonitor.error(f"get cpu model error: {e}")
            return None

    # 取得 gpu model
    def get_gpus_model(self) -> list:
        try:
            gpus = GPUtil.getGPUs()
            return [gpu.name for gpu in gpus]
        except Exception as e:
            self.logger_hardwaremonitor.error(f"get gpu model error: {e}")
            return []
    
    # 取得 drive model
    def get_drives_model(self) -> list:
        try:
            drives = DeviceList()
            return [drive.model for drive in drives]
        except Exception as e:
            self.logger_hardwaremonitor.error(f"get drive model error: {e}")
            return []

    # 通報 EZPro
    def send_notification(self):
        try:
            if (len(self.notification_items) > 0):
                for item in self.notification_items:
                        if item.name == 'CPU' and item.target == 'Usage':
                            if self.cpu.usage >= int(item.threshold):
                                ezpro_notification = EZProNotification(f"CPU usage: {self.cpu.usage}%")
                                ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                if self.enableLoggingNotification.get() == 1:
                                    if response is not None and response.status_code == 200:
                                        self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                    else:
                                        self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}")
                        elif item.name == 'CPU' and item.target == 'Temperature':
                            if self.cpu.temperature >= int(item.threshold):
                                ezpro_notification = EZProNotification(f"CPU temperature: {self.cpu.temperature}%")
                                ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                if self.enableLoggingNotification.get() == 1:
                                    if response is not None and response.status_code == 200:
                                        self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                    else:
                                        self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}")
                        elif item.name == 'RAM':
                            if self.ram.usage >= int(item.threshold):
                                ezpro_notification = EZProNotification(f"RAM usage: {self.ram.usage}%")
                                ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                if self.enableLoggingNotification.get() == 1:
                                    if response is not None and response.status_code == 200:
                                        self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                    else:
                                        self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}") 
                        elif item.name == 'GPU' and item.target == 'Usage':
                            if self.gpu.usage >= int(item.threshold):
                                ezpro_notification = EZProNotification(f"GPU usage: {self.gpu.usage}%")
                                ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                if self.enableLoggingNotification.get() == 1:
                                    if response is not None and response.status_code == 200:
                                        self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                    else:
                                        self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}") 
                        elif item.name == 'GPU' and item.target == 'Temperature':
                            if self.gpu.temperature >= int(item.threshold):
                                ezpro_notification = EZProNotification(f"GPU temperature: {self.gpu.temperature}%")
                                ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                if self.enableLoggingNotification.get() == 1:
                                    if response is not None and response.status_code == 200:
                                        self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                    else:
                                        self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}")
                        elif item.name == 'Drive' and item.target == 'Usage':
                             for drive in self.drives:
                                driveInfo = self.drives[drive]
                                if driveInfo.usage >= int(item.threshold):
                                    ezpro_notification = EZProNotification(f"{driveInfo.name} usage: {driveInfo.usage}%")
                                    ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                    response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                    if self.enableLoggingNotification.get() == 1:
                                        if response is not None and response.status_code == 200:
                                            self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                        else:
                                            self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}")
                        elif item.name == 'Drive' and item.target == 'Temperature':
                            for drive in self.drives:
                                driveInfo = self.drives[drive]
                                if driveInfo.temperature >= int(item.threshold):
                                    ezpro_notification = EZProNotification(f"{driveInfo.name} temperature: {driveInfo.temperature}%")
                                    ezpro_notification_json = json.dumps(ezpro_notification.__dict__)
                                    response = EZProNotification.send_notification(self.ezpro, ezpro_notification_json)
                                    if self.enableLoggingNotification.get() == 1:
                                        if response is not None and response.status_code == 200:
                                            self.logger_hardwaremonitor.info(f"send notification sucess: {ezpro_notification_json}")
                                        else:
                                            self.logger_hardwaremonitor.error(f"send notification fail: {response}, notification content: {ezpro_notification_json}")
        except Exception as e:
            self.logger_hardwaremonitor.error(f"send notification fail -> {e}")

class CPUInfo:
    def __init__(self, name = "", usage = 0, temperature = 0) -> None:
        self.name = name
        self.usage = usage
        self.temperature = temperature

class RAMInfo:
    def __init__(self, name = "", usage = 0, temperature = 0) -> None:
        self.name = name
        self.usage = usage
        self. temperature = temperature
                    
class GPUInfo:
    def __init__(self, name = "", usage = 0, temperature = 0) -> None:
        self.name = name
        self.usage = usage
        self.temperature = temperature
        
class DriveInfo:
    def __init__(self, name = "", usage = 0, temperature = 0) -> None:
        self.name = name
        self.usage = usage
        self.temperature = temperature

class AlarmItem:
    def __init__(self, name="", target="", threshold=0) -> None:
        self.name = name
        self.target = target
        self.threshold = threshold

class Stopwatch:
    def __init__(self):
        self.start_time = None
        self.elapsed_time = 0

    def start(self):
        if self.start_time is None:
            self.start_time = time.perf_counter()  # 單位: 秒

    def stop(self):
        if self.start_time is not None:
            self.elapsed_time += time.perf_counter() - self.start_time
            self.start_time = None

    def reset(self):
        self.start_time = None
        self.elapsed_time = 0

    def elapsed(self):
        if self.start_time is None:
            return self.elapsed_time
        else:
            return self.elapsed_time + (time.perf_counter() - self.start_time)