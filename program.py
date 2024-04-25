from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from tkinter import PhotoImage
from hardwaremonitor_linux import HardwareMonitor_Linux, CPUInfo, GPUInfo, DriveInfo, AlarmItem
import time
from threading import Thread
from ezpronotification import EZProNotification
import platform
import sys
import xml.etree.ElementTree as ET
import logging
import os

class Program:
    def __init__(self, root):
        self.root = root
        self.setup_logger()
        self.hardwaremonitor = HardwareMonitor_Linux()
        self.setup_ui()
        self.read_ezpro_parameters()
        self.read_alarm_items_parameters()
        self.read_switches_parameters()
        self.read_logging_parameters()
        self.isRunning = False
        self.monitor_thread = None
        self.update_thread = None
        self.start_monitoring()

    # 設置 logger
    def setup_logger(self):
        try:
            self.logger_main = logging.getLogger('MAIN')
            self.logger_main.setLevel(logging.INFO)
            self.filehandler = logging.FileHandler(f'main_{time.strftime("%Y%m%d")}.log')
            self.filehandler.setLevel(logging.INFO)
            self.formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
            self.filehandler.setFormatter(self.formatter)
            self.logger_main.addHandler(self.filehandler)
            print('setup logger_main success')
        except Exception as e:
            print(f'setup logger_main error: {e}')

    # 更新 treeview 顯示資料
    def update_treeview(self):
        try:
            self.treeview_overview.item(self.row_cpu, values=['CPU', f"{self.hardwaremonitor.cpu.usage}%", f"{self.hardwaremonitor.cpu.temperature}C"])
            self.treeview_overview.item(self.row_ram, values=['RAM', f"{self.hardwaremonitor.ram.usage}%", "-"])
            self.treeview_overview.item(self.row_gpu, values=['GPU', f"{self.hardwaremonitor.gpu.usage}%", f"{self.hardwaremonitor.gpu.temperature}C"])
            for drive in self.hardwaremonitor.drives:
                driveInfo = self.hardwaremonitor.drives[drive]
                self.treeview_overview.item(self.row_drives[driveInfo.name], values=[f'{driveInfo.name}', f"{driveInfo.usage}%", f"{driveInfo.temperature}C"])
        except Exception as e:
            print(f"update treeview fail -> {e}")
    
    # 開始監控 & 更新顯示
    def start_monitoring(self):
        self.isRunning = True
        self.hardwaremonitor.isRunning = True
        if not self.monitor_thread and not self.update_thread:
            self.monitor_thread = Thread(target=self.hardwaremonitor.start_monitor)
            self.monitor_thread.start()
            self.update_thread = Thread(target=self.update_data)
            self.update_thread.start()

    # 更新資料
    def update_data(self):
        while self.isRunning:
            self.update_treeview()
            time.sleep(1)  

    # 讀取 EZPro 相關參數設定 
    def read_ezpro_parameters(self):
        try:
            tree = ET.parse('parameters.xml')
            root = tree.getroot()
        except FileNotFoundError:
            self.logger_main.error("read ezpro parameters error: file not found")  
            return

        if root.find('EZPro_IP') is not None:
            self.hardwaremonitor.ezpro.ip = root.find('EZPro_IP').text
        if root.find('EZPro_Port') is not None:
            self.hardwaremonitor.ezpro.port = root.find('EZPro_Port').text
        if root.find('EZPro_Username') is not None:
            self.hardwaremonitor.ezpro.username = root.find('EZPro_Username').text
        if root.find('EZPro_Password') is not None:
            self.hardwaremonitor.ezpro.password = root.find('EZPro_Password').text  

        self.update_ezpro_server_name_label()

        self.logger_main.info('read ezpro parameters finished')

    # 讀取 通報項目 相關參數設定-1
    def read_alarm_items_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()
            except FileNotFoundError:
                self.logger_main.error("read alarm item parameters error: file not found") 
                return

            alarmItems = root.findall('AlarmItem')
            if len(alarmItems) > 0:
                for item in alarmItems:
                    self.hardwaremonitor.notification_items.append(AlarmItem(item.get('name'), item.get('target'), item.get('threshold')))
                    self.treeview_notify_items.insert(parent='', index='end', values=[item.get('name'), item.get('target'), item.get('threshold')])

            self.logger_main.info('read alarm item parameters finished')
        except Exception as e:
            self.logger_main.error(f'read alarm items parameters error: {e}')

    # 讀取 通報項目 相關參數設定-2
    def read_switches_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()
            except FileNotFoundError:
                self.logger_main.error('read switches parameters error: file not found')
                return
            
            if root.find('Enable_NotifyToEZPro') is not None:
                self.hardwaremonitor.enableNotifyToEzPro.set(int(root.find('Enable_NotifyToEZPro').text))
            if root.find('Enable_LoggingNotification') is not None:
                self.hardwaremonitor.enableLoggingNotification.set(int(root.find('Enable_LoggingNotification').text))
        
            self.logger_main.info('read switches parameters finished')
        except Exception as e:
            self.logger_main.error(f'read switches paramters error: {e}')
            return
    
    # 讀取 Logging 相關參數設定
    def read_logging_parameters(self):
        try:
            tree = ET.parse('parameters.xml')
            root = tree.getroot()
        except FileNotFoundError:
            self.logger_main.error("read logging parameters error: file not found")
            return

        logging_period = root.find('Logging_Period')
        if logging_period is not None and logging_period.text in self.option_logging_periods:
            self.hardwaremonitor.logging_period = root.find('Logging_Period').text
        else:
            self.logger_main.error(f'read logging parameters error: invalid data')
        
        self.logger_main.info('read logging parameters finished')

    # 儲存 EZPro 相關參數設定 
    def save_ezpro_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()  
            except FileNotFoundError:
                self.logger_main.error("parameters.xml not found, creating new one.")
                root = ET.Element('parameters')
                tree = ET.ElementTree(root)

            if root.find('EZPro_IP') is not None:
                root.find('EZPro_IP').text = self.hardwaremonitor.ezpro.ip
            else:
                ET.SubElement(root, 'EZPro_IP').text = self.hardwaremonitor.ezpro.ip 

            if root.find('EZPro_Port') is not None:
                root.find('EZPro_Port').text = self.hardwaremonitor.ezpro.port
            else:
                ET.SubElement(root, 'EZPro_Port').text = self.hardwaremonitor.ezpro.port

            if root.find('EZPro_Username') is not None:
                root.find('EZPro_Username').text = self.hardwaremonitor.ezpro.username
            else:
                ET.SubElement(root, 'EZPro_Username').text = self.hardwaremonitor.ezpro.username

            if root.find('EZPro_Password') is not None:
                root.find('EZPro_Password').text = self.hardwaremonitor.ezpro.password
            else:
                ET.SubElement(root, 'EZPro_Password').text = self.hardwaremonitor.ezpro.password

            tree.write('parameters.xml', encoding='utf-8', xml_declaration=True)
            self.logger_main.info("save ezpro parameters success")

        except Exception as e:
            self.logger_main.error(f"save ezpro parameters error: {e}")

    # 儲存 通報項目 相關參數設定-1 
    def save_alarm_items_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()  
            except FileNotFoundError:
                self.logger_main.error("parameters.xml not found, creating new one.")
                root = ET.Element('parameters')
                tree = ET.ElementTree(root)


            notification_keys = {f"{item.name}_{item.target}_{item.threshold}" for item in self.hardwaremonitor.notification_items}

            # 移除
            items_to_remove = [item for item in root.findall('AlarmItem') if f"{item.get('name')}_{item.get('target')}_{item.get('threshold')}" not in notification_keys]
            for item in items_to_remove:
                root.remove(item)

            existing_items = {f"{item.get('name')}_{item.get('target')}_{item.get('threshold')}": item for item in root.findall('AlarmItem')}

            # 新增
            for item in self.hardwaremonitor.notification_items:
                item_key = f"{item.name}_{item.target}_{item.threshold}"
                if item_key not in existing_items:
                    node = ET.SubElement(root, 'AlarmItem')
                    node.set('name', item.name)
                    node.set('target', item.target)
                    node.set('threshold', item.threshold)

            tree.write('parameters.xml', encoding='utf-8', xml_declaration=True)
            self.logger_main.info("save alarm items success")

        except Exception as e:
            self.logger_main.error("save alarm items error: {e}")

    # 儲存 通報項目 相關參數設定-2
    def save_switches_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()  
            except FileNotFoundError:
                self.logger_main.error("parameters.xml not found, creating new one.")
                root = ET.Element('parameters')
                tree = ET.ElementTree(root)

            if root.find('Enable_NotifyToEZPro') is not None:
                root.find('Enable_NotifyToEZPro').text = str(self.hardwaremonitor.enableNotifyToEzPro.get())
            else:
                ET.SubElement(root, 'Enable_NotifyToEZPro').text = str(self.hardwaremonitor.enableNotifyToEzPro.get())

            if root.find('Enable_LoggingNotification') is not None:
                root.find('Enable_LoggingNotification').text = str(self.hardwaremonitor.enableLoggingNotification.get())
            else:
                ET.SubElement(root, 'Enable_LoggingNotification').text = str(self.hardwaremonitor.enableLoggingNotification.get())

            tree.write('parameters.xml', encoding='utf-8', xml_declaration=True)
            self.logger_main.info("save switches success")
        except Exception as e:
            self.logger_main.error(f'save switches parameters error: {e}')

    # 儲存 Logging 相關參數設定
    def save_logging_parameters(self):
        try:
            try:
                tree = ET.parse('parameters.xml')
                root = tree.getroot()  
            except FileNotFoundError:
                self.logger_main.error("parameters.xml not found, creating new one.")
                root = ET.Element('parameters')
                tree = ET.ElementTree(root)
            
            if root.find('Logging_Period') is not None:
                root.find('Logging_Period').text = self.hardwaremonitor.logging_period
            else:
                ET.SubElement(root, 'Logging_Period').text = self.hardwaremonitor.logging_period 

            tree.write('parameters.xml', encoding='utf-8', xml_declaration=True)
            self.logger_main.info("save logging parameters success")

        except Exception as e:
            self.logger_main.error("save logging parameters error: {e}")

    # 介面佈局、控件事件綁定
    def setup_ui(self):

        # UI setup code here
        self.root.title("Hardware Monitor")

        path1_main_icon = './_internal/images/main.png'
        path2_main_icon = 'main.png'
        main_icon = None
        if os.path.exists(path1_main_icon):
            main_icon = PhotoImage(file=path1_main_icon)
        elif os.path.exists(path2_main_icon):
            main_icon = PhotoImage(file=path2_main_icon)
        if main_icon is not None: 
            self.root.iconphoto(False, main_icon)
        
        root_width = 540
        root_height = 300
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        main_x = (screen_width - root_width) // 2
        main_y = (screen_height - root_height) // 2
        self.root.geometry(f'{root_width}x{root_height}+{main_x}+{main_y}')
        self.root.resizable(0, 0)
        # self.root.config(bg="azure3")
        # treeview initial
        self.treeview_overview = ttk.Treeview(self.root, columns=('type', 'usage', 'temperature'), show='headings') 
        # self.treeview_overview.column('#0')
        self.treeview_overview.column('type', width=180, anchor='center')
        self.treeview_overview.column('usage', width=180, anchor='center')
        self.treeview_overview.column('temperature', width=180, anchor='center')
        # self.treeview_overview.heading('#0', text='Item')
        self.treeview_overview.heading('type', text="Type")
        self.treeview_overview.heading('usage', text="Usage")
        self.treeview_overview.heading('temperature', text="Temperature")
        self.treeview_overview.pack(fill='both', expand=True)
        self.treeview_overview.bind('<Button-1>', self.on_left_click)

        # 填入 cpu 項目
        data_cpu = ["CPU", "-", "-"]
        self.row_cpu = self.treeview_overview.insert(parent='', index='end', values=data_cpu)

        # 填入 ram 項目
        data_ram = ["RAM", "-", "-"]
        self.row_ram = self.treeview_overview.insert(parent='', index='end', values=data_ram)
        
        # 填入 gpu 項目
        data_gpu = [f"GPU", "-", "-"]
        self.row_gpu = self.treeview_overview.insert(parent='', index='end', values=data_gpu)
            
        # 填入 drive 項目    
        partitions = self.hardwaremonitor.get_devices()
        self.row_drives = {}
        for partition in partitions:
            data = [f"{partition.device}", "-", "-"]
            item = self.treeview_overview.insert(parent='', index='end', values=data)
            self.row_drives[partition.device] = item

        # Setup menu
        self.menubar = Menu(self.root)
        self.root.config(menu=self.menubar)
        self.menu_settings = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="設定", menu=self.menu_settings)
        self.menu_settings.add_command(label="EZPro設定", command=self.show_ezpro_server_window)
        self.menu_settings.add_command(label="通報設定", command=self.show_notification_window)
        self.menu_settings.add_command(label="Log輸出設定", command=self.show_logging_period_window)
        self.update_ezpro_server_name_label()
        
        self.window_setup_ezpro_server = Toplevel(self.root)
        self.window_setup_ezpro_server.withdraw()
        self.window_setup_ezpro_server.title("EZPro設定")
        
        path1_sub_icon_ezpro = './_internal/images/ezpro_setting.png'
        path2_sub_icon_ezpro = 'ezpro_setting.png'
        sub_icon_ezpro = None
        if os.path.exists(path1_sub_icon_ezpro):
            sub_icon_ezpro = PhotoImage(file=path1_sub_icon_ezpro)
        elif os.path.exists(path2_sub_icon_ezpro):
            sub_icon_ezpro = PhotoImage(file=path2_sub_icon_ezpro)
        if sub_icon_ezpro is not None: 
            self.window_setup_ezpro_server.iconphoto(False, sub_icon_ezpro)

        self.window_setup_ezpro_server.resizable(0,0)
        # self.window_setup_ezpro_server.config(bg="azure3")
        self.window_setup_ezpro_server.protocol("WM_DELETE_WINDOW", self.close_ezpro_server)
        self.label_ezpro_server_IP = Label(self.window_setup_ezpro_server, text="Server IP:")
        self.label_ezpro_server_IP.grid(row=0, column=0)
        self.entry_ezpro_server_IP = Entry(self.window_setup_ezpro_server)
        self.entry_ezpro_server_IP.grid(row=0, column=1, columnspan=2)
        self.label_ezpro_server_Port = Label(self.window_setup_ezpro_server, text="Port:")
        self.label_ezpro_server_Port.grid(row=0, column=3)
        self.entry_ezpro_server_Port = Entry(self.window_setup_ezpro_server)
        self.entry_ezpro_server_Port.grid(row=0, column=4, columnspan=2)
        self.label_ezpro_username = Label(self.window_setup_ezpro_server, text="Username:")
        self.label_ezpro_username.grid(row=1, column=0)
        self.entry_ezpro_username = Entry(self.window_setup_ezpro_server)
        self.entry_ezpro_username.grid(row=1, column=1, columnspan=2)
        self.label_ezpro_password = Label(self.window_setup_ezpro_server, text="Password:")
        self.label_ezpro_password.grid(row=1, column=3)
        self.entry_ezpro_password = Entry(self.window_setup_ezpro_server)
        self.entry_ezpro_password.grid(row=1, column=4, columnspan=2)
        self.btn_ezpro_connect = Button(self.window_setup_ezpro_server, text="Connect", command=self.test_ezpro_server_connection)
        self.btn_ezpro_connect.grid(row=2, column=5)
        self.window_setup_ezpro_server.update()
        window_setup_ezpro_server_x = (self.window_setup_ezpro_server.winfo_screenwidth() - self.window_setup_ezpro_server.winfo_width()) // 2
        window_setup_ezpro_server_y = (self.window_setup_ezpro_server.winfo_screenheight() - self.window_setup_ezpro_server.winfo_height()) // 2
        self.window_setup_ezpro_server.geometry(f'+{window_setup_ezpro_server_x}+{window_setup_ezpro_server_y}')

        self.window_setup_notification = Toplevel(self.root)
        self.window_setup_notification.withdraw()
        self.window_setup_notification.title("通報設定")

        path1_sub_icon_notify = './_internal/images/notify_setting.png'
        path2_sub_icon_notify = 'notify_setting.png'
        sub_icon_notify = None
        if os.path.exists(path1_sub_icon_notify):
            sub_icon_notify = PhotoImage(file=path1_sub_icon_notify)
        elif os.path.exists(path2_sub_icon_notify):
            sub_icon_notify = PhotoImage(file=path2_sub_icon_notify)
        if sub_icon_notify is not None: 
            self.window_setup_notification.iconphoto(False, sub_icon_notify)

        self.window_setup_notification.resizable(0,0)
        # self.window_setup_notification.config(bg="azure3")
        self.window_setup_notification.protocol("WM_DELETE_WINDOW", self.close_notification)
        self.frame_settings = Frame(self.window_setup_notification)
        self.frame_settings.pack(fill='both', expand=True)
        self.option_notify_items = ["CPU", "RAM", "GPU", "Drive"]
        self.combo_notify_items = ttk.Combobox(self.frame_settings, values=self.option_notify_items, state='readonly')
        self.combo_notify_items.pack(side='left')
        self.combo_notify_items.bind('<<ComboboxSelected>>', self.on_combobox_change)
        self.option_notify_targets = ["Usage", "Temperature"]
        self.combo_notify_targets = ttk.Combobox(self.frame_settings, values=self.option_notify_targets, state='readonly')
        self.combo_notify_targets.pack(side='left')
        self.combo_notify_targets.bind('<<ComboboxSelected>>', self.on_combobox_change)
        self.entry_notify_threshold = Entry(self.frame_settings, state=DISABLED)
        self.entry_notify_threshold.pack(side='left')
        self.label_notify_threshold_unit = Label(self.frame_settings, text="")
        self.label_notify_threshold_unit.pack(side='left')
        self.btn_notify_add = Button(self.frame_settings, state=DISABLED, text="Add", command=self.add_notify_item)
        self.btn_notify_add.pack(side='right')
        self.entry_notify_threshold.bind('<KeyRelease>', self.on_entry_change)
        self.frame_treeview = Frame(self.window_setup_notification)
        self.frame_treeview.pack(fill='both', expand=True)
        self.treeview_notify_items = ttk.Treeview(self.frame_treeview, columns=('Item', 'Target', 'Threshold'), show='headings')
        self.treeview_notify_items.heading('Item', text="Item")
        self.treeview_notify_items.heading('Target', text="Target")
        self.treeview_notify_items.heading('Threshold', text="Threshold")
        self.treeview_notify_items.column('Item', anchor='center')
        self.treeview_notify_items.column('Target', anchor='center')
        self.treeview_notify_items.column('Threshold', anchor='center')
        self.treeview_notify_items.pack(fill='both', expand=True)
        self.menu_selected_item = Menu(self.treeview_notify_items, tearoff=0)
        self.menu_selected_item.add_command(label='刪除', command=self.delete_notify_item)
        self.menu_selected_item_posted = False  # 用來追蹤 menu_selected_item post 狀態
        self.treeview_notify_items.bind('<Button-3>', self.show_delete_menu)
        self.treeview_notify_items.bind('<Button-1>', self.on_left_click)
        self.frame_checkbuttons = Frame(self.window_setup_notification)
        self.frame_checkbuttons.pack(fill='both', expand=True)
        self.checkbutton_enable_logging_notification = Checkbutton(self.frame_checkbuttons, text="通報時寫入Log紀錄", variable=self.hardwaremonitor.enableLoggingNotification, onvalue=1, offvalue=0, command=self.save_switches_parameters)
        self.checkbutton_enable_logging_notification.pack(side='right')
        self.checkbutton_enable_notify_to_ezpro = Checkbutton(self.frame_checkbuttons, text="通報EZPro", variable=self.hardwaremonitor.enableNotifyToEzPro, onvalue=1, offvalue=0, command=self.save_switches_parameters)
        self.checkbutton_enable_notify_to_ezpro.pack(side='right')
        self.window_setup_notification.update()
        window_setup_notification_x = (self.window_setup_notification.winfo_screenwidth() - self.window_setup_notification.winfo_width()) // 2
        window_setup_notification_y = (self.window_setup_notification.winfo_screenheight() - self.window_setup_notification.winfo_height()) // 2
        self.window_setup_notification.geometry(f'+{window_setup_notification_x}+{window_setup_notification_y}')

        self.window_setup_logging_period = Toplevel(self.root)
        self.window_setup_logging_period.withdraw()
        self.window_setup_logging_period.title("Log輸出設定")
        
        path1_sub_icon_logging = './_internal/images/logging_setting.png'
        path2_sub_icon_logging = 'logging_setting.png'
        sub_icon_logging = None
        if os.path.exists(path1_sub_icon_logging):
            sub_icon_logging = PhotoImage(file=path1_sub_icon_logging)
        elif os.path.exists(path2_sub_icon_logging):
            sub_icon_logging = PhotoImage(file=path2_sub_icon_logging)
        if sub_icon_logging is not None: 
            self.window_setup_logging_period.iconphoto(False, sub_icon_logging)

        self.window_setup_logging_period.resizable(0,0)
        # self.window_setup_logging_period.config(bg="azure3")
        self.window_setup_logging_period.protocol("WM_DELETE_WINDOW", self.close_logging_period)
        self.label_logging_period_introduce = Label(self.window_setup_logging_period, text="Logging Period(Minute):")
        self.label_logging_period_introduce.grid(row=0, column=0)
        self.option_logging_periods = ["10", "30", "60"]
        self.combo_logging_period = ttk.Combobox(self.window_setup_logging_period, values=self.option_logging_periods, state='readonly')
        self.combo_logging_period.grid(row=0, column=1)
        self.combo_logging_period.bind('<<ComboboxSelected>>', self.on_combobox_change)
        self.btn_set_logging_period = Button(self.window_setup_logging_period, text="設定", command=self.set_logging_period, state=DISABLED)
        self.btn_set_logging_period.grid(row=0, column=2)
        self.label_current_logging_period_introduce = Label(self.window_setup_logging_period, text="Current Logging Period:", anchor='e')
        self.label_current_logging_period_introduce.grid(row=1, column=1)
        self.label_current_logging_period_value = Label(self.window_setup_logging_period, text="")
        self.label_current_logging_period_value.grid(row=1, column=2)
        self.window_setup_logging_period.update()
        window_setup_logging_period_x = (self.window_setup_logging_period.winfo_screenwidth() - self.window_setup_logging_period.winfo_width()) // 2
        window_setup_logging_period_y = (self.window_setup_logging_period.winfo_screenheight() - self.window_setup_logging_period.winfo_height()) // 2
        self.window_setup_logging_period.geometry(f'+{window_setup_logging_period_x}+{window_setup_logging_period_y}')

    def update_ezpro_server_name_label(self):
        if self.hardwaremonitor.ezpro.ip is not None:
            self.menu_settings.entryconfig(index=0, label=f"EZPro設定 - {self.hardwaremonitor.ezpro.ip}")
        else:
            self.menu_settings.entryconfig(index=0, label="EZPro設定")

    def setup_ezpro_server(self):
        try:
            self.hardwaremonitor.ezpro.ip = self.entry_ezpro_server_IP.get()
            self.hardwaremonitor.ezpro.port = self.entry_ezpro_server_Port.get()
            self.hardwaremonitor.ezpro.username = self.entry_ezpro_username.get()
            self.hardwaremonitor.ezpro.password = self.entry_ezpro_password.get()
            self.logger_main.info(f"setup ezpro server => ip:{self.hardwaremonitor.ezpro.ip}, port:{self.hardwaremonitor.ezpro.port}, username:{self.hardwaremonitor.ezpro.username}, password:{self.hardwaremonitor.ezpro.password}")
        except Exception as e:
            self.logger_main.error(f"setup ezpro server error: {e}")

    def test_ezpro_server_connection(self):
        result = EZProNotification.test_ezpro_server_connection(self.entry_ezpro_server_IP.get(), self.entry_ezpro_server_Port.get(), self.entry_ezpro_username.get(), self.entry_ezpro_password.get())
        if result == '1':
            messagebox.showerror("ERROR", "內容輸入錯誤", parent=self.window_setup_ezpro_server)
            return
        elif result == '2':
            messagebox.showerror("ERROR", "IP地址無法訪問", parent=self.window_setup_ezpro_server)
            return
        elif result == '3':
            self.setup_ezpro_server()
            self.save_ezpro_parameters()
            self.update_ezpro_server_name_label()
            messagebox.showinfo("連線測試", "伺服器設定成功", parent=self.window_setup_ezpro_server)
        else:
            messagebox.showerror("ERROR", f"伺服器連線失敗\nResponse:{result}", parent=self.window_setup_ezpro_server)
    
    def update_unit_view(self):
        if self.combo_notify_targets.get() == "Usage":
            self.label_notify_threshold_unit.config(text="%")
        elif self.combo_notify_targets.get() == "Temperature":
            self.label_notify_threshold_unit.config(text="C")
        else:
            self.label_notify_threshold_unit.config(text="")

    def on_left_click(self, event):
        # monitor overview
        if event.widget == self.treeview_overview:
            row_id = self.treeview_overview.identify_row(event.y)
            if not row_id:
                self.treeview_overview.selection_set('')
        # notify item
        if event.widget == self.treeview_notify_items:
            # 檢查點擊位置，關閉菜單
            x, y = event.x_root, event.y_root
            if not (self.menu_selected_item.winfo_x() < x < self.menu_selected_item.winfo_x() + self.menu_selected_item.winfo_width() and
                    self.menu_selected_item.winfo_y() < y < self.menu_selected_item.winfo_y() + self.menu_selected_item.winfo_height()):
                if self.menu_selected_item_posted == True:
                    self.menu_selected_item.unpost()
                    self.menu_selected_item_posted = False
                else:
                    row_id = self.treeview_notify_items.identify_row(event.y)
                    if not row_id:
                        self.treeview_notify_items.selection_set('')

    def add_notify_item(self):
        selected_item = self.combo_notify_items.get()
        selected_target = self.combo_notify_targets.get()
        notify_threshold = self.entry_notify_threshold.get()
        alarm_item = AlarmItem(selected_item, selected_target, notify_threshold)
        for item in self.hardwaremonitor.notification_items:
            if alarm_item.name == item.name and alarm_item.target == item.target:
                messagebox.showerror("ERROR", "selected item is already exist", parent=self.window_setup_notification)
                return
        self.hardwaremonitor.notification_items.append(alarm_item)
        new_item = [selected_item, selected_target, notify_threshold]
        self.treeview_notify_items.insert(parent='', index='end', values=new_item)
        self.save_alarm_items_parameters()
        self.logger_main.info(f"add notify item: {selected_item}, target: {selected_target}, threshold: {notify_threshold}")
        self.combo_notify_items.set('')
        self.combo_notify_targets.set('')
        self.entry_notify_threshold.delete(0,'end')
        self.entry_notify_threshold.config(state=DISABLED)

    def show_delete_menu(self, event):
        row_id = self.treeview_notify_items.identify_row(event.y)
        if row_id:
            self.treeview_notify_items.focus(row_id)
            self.treeview_notify_items.selection_set(row_id)
            self.menu_selected_item.post(event.x_root, event.y_root)
            self.menu_selected_item_posted = True

    def delete_notify_item(self):
        try:
            id = self.treeview_notify_items.focus()
            selected_item = self.treeview_notify_items.item(id)['values']
            if selected_item:
                item = AlarmItem(selected_item[0], selected_item[1], selected_item[2])
                for alarmItem in self.hardwaremonitor.notification_items: 
                    if item.name == alarmItem.name and item.target == alarmItem.target:
                        self.hardwaremonitor.notification_items.remove(alarmItem)
                        self.save_alarm_items_parameters()
            self.treeview_notify_items.delete(id)
            self.logger_main.info(f"delete notify item: {item.name}, target: {item.target}, threshold: {item.threshold}")
        except Exception as e:
            self.logger_main.error(f'delete notify item error: {e}')

    def set_logging_period(self):
        set_period = ""
        try:
           set_period = self.combo_logging_period.get()
        except Exception as e:
            messagebox.showerror("ERROR", f"{e}", parent=self.window_setup_logging_period)
            return
        if self.hardwaremonitor.logging_period != set_period:
            self.hardwaremonitor.logging_period = set_period
            self.hardwaremonitor.stopwatch.reset()
            self.label_current_logging_period_value.config(text=f"{self.hardwaremonitor.logging_period} min")
            self.save_logging_parameters()
            self.combo_logging_period.set('')
            self.btn_set_logging_period.config(state=DISABLED)
            self.logger_main.info(f"set logging period: {self.hardwaremonitor.logging_period} min")

    def on_combobox_change(self, event):
        # notification
        if event.widget == self.combo_notify_items or event.widget == self.combo_notify_targets:
            if self.combo_notify_items.get() != "" and self.combo_notify_targets.get() != "":
                if self.combo_notify_items.get() == 'RAM' and self.combo_notify_targets.get() == 'Temperature':
                    self.entry_notify_threshold.config(state=DISABLED)
                    self.btn_notify_add.config(state=DISABLED)
                else:
                    self.entry_notify_threshold.config(state=NORMAL)
                    self.btn_notify_add.config(state=DISABLED)
            else:
                self.entry_notify_threshold.config(state=DISABLED)
                self.btn_notify_add.config(state=DISABLED)
            self.update_unit_view()
        # logging
        if event.widget == self.combo_logging_period:
            if self.combo_logging_period.get() != "":
                self.btn_set_logging_period.config(state=NORMAL)
            else:
                self.btn_set_logging_period.config(state=DISABLED)
    
    def on_entry_change(self, event):
        current_value = self.entry_notify_threshold.get()
        try:
            num = int(current_value)  
            if self.combo_notify_targets.get() == "Usage" and 0 < num <= 100:  # 百分比
                self.btn_notify_add.config(state=NORMAL)
            elif self.combo_notify_targets.get() == "Temperature" and 0 <= num:  # 溫度
                self.btn_notify_add.config(state=NORMAL)
            else:
                self.btn_notify_add.config(state=DISABLED) 
        except ValueError:
            self.btn_notify_add.config(state=DISABLED) 

    def show_ezpro_server_window(self):
        if self.window_setup_ezpro_server.state() == 'withdrawn':
            self.entry_ezpro_server_IP.insert('0', self.hardwaremonitor.ezpro.ip)
            self.entry_ezpro_server_Port.insert('0', self.hardwaremonitor.ezpro.port)
            self.entry_ezpro_username.insert('0', self.hardwaremonitor.ezpro.username)
            self.entry_ezpro_password.insert('0', self.hardwaremonitor.ezpro.password)
            self.window_setup_ezpro_server.deiconify()
        else:
            self.window_setup_ezpro_server.lift()
            self.window_setup_ezpro_server.focus()

    def show_notification_window(self):
        if self.window_setup_notification.state() == 'withdrawn':
            self.window_setup_notification.deiconify()
        else:
            self.window_setup_notification.lift()
            self.window_setup_notification.focus()

    def show_logging_period_window(self):
        if self.window_setup_logging_period.state() == 'withdrawn':
            self.label_current_logging_period_value.config(text=f"{self.hardwaremonitor.logging_period} min")
            self.window_setup_logging_period.deiconify()
        else:
            self.window_setup_logging_period.lift()
            self.window_setup_logging_period.focus()

    def close_ezpro_server(self):
        self.window_setup_ezpro_server.withdraw()
        self.entry_ezpro_server_IP.delete('0', 'end')
        self.entry_ezpro_server_Port.delete('0', 'end')
        self.entry_ezpro_username.delete('0', 'end')
        self.entry_ezpro_password.delete('0', 'end')

    def close_notification(self):
        self.window_setup_notification.withdraw()
        self.combo_notify_items.set('')
        self.combo_notify_targets.set('')
        self.entry_notify_threshold.delete('0','end')
        self.entry_notify_threshold.config(state=DISABLED)
        self.btn_notify_add.config(state=DISABLED)
        self.menu_selected_item.unpost()
        self.treeview_notify_items.selection_set('')
        self.label_notify_threshold_unit.config(text="")

    def close_logging_period(self):
        self.window_setup_logging_period.withdraw()
        self.combo_logging_period.set('')
        self.btn_set_logging_period.config(state=DISABLED)

    def on_closing(self):
        self.isRunning = False
        if self.isRunning == False:
            self.hardwaremonitor.stop_monitor()
            self.monitor_thread.join()
            self.update_thread.join()
            self.root.destroy()

def check_if_platform_is_windows() -> bool:
    if platform.system().lower()=='windows': 
        return True
    else:
        return False

if (check_if_platform_is_windows()):
    messagebox.showerror("Error", "This application is not support on Windows platform.")
    sys.exit()

# Usage
root = Tk()
app = Program(root)
root.protocol("WM_DELETE_WINDOW", app.on_closing)
root.mainloop()