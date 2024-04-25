import requests
from requests.auth import HTTPDigestAuth
from ezproserver import EZProServer
import socket
import platform
import subprocess
import json

class EZProNotification:
    
    def __init__(self, description = "") -> None:
        self.source = socket.gethostname()
        self.caption = "HarewareMonitor Notification"
        self.description = description

    @staticmethod
    def ping_ip(ip_address) -> bool:
        if ip_address is None or ip_address == "": return False
        param = '-n' if platform.system().lower()=='windows' else '-c'
        command = ['ping', param, '1', ip_address]
        print(f"ping command: {command}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"ping result: {result}")
        if result.returncode == 0 and not any(msg in result.stdout for msg in ["無法連線", "Destination host unreachable", "Request timed out"]):
            print(f"{ip_address} is reachable.")
            return True
        else:
            print(f"{ip_address} is not reachable.")
            return False

    @staticmethod
    def test_ezpro_server_connection(ip, port, username, password) -> str:  # 1.內容輸入有誤 2.IP地址無法訪問 3.伺服器連線成功 else.伺服器連線失敗
        if (ip == "" or port == "" or username == "" or password == ""):
            return '1'
        if (not EZProNotification.ping_ip(ip)):
            return '2'
        test_server = EZProServer(ip, port, username, password)
        json_string = json.dumps(EZProNotification("test connect message").__dict__)
        response = EZProNotification.send_notification(test_server, json_string)
        if response is not None and response.status_code == 200:
            return '3'
        else:
            return f'{response}'

    @staticmethod
    def send_notification(ezpro:EZProServer, message:str):
        url = f"http://{ezpro.ip}:{ezpro.port}/api/createEvent"
        print(f"{url}")
        print(f"{message}")
        auth = HTTPDigestAuth(f"{ezpro.username}", f"{ezpro.password}")
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, data=message, auth=auth, headers=headers)
            print(f'{response}')
            return response
        except Exception as e:
            return f"error - {e}"