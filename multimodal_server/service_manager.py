#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import threading
import signal
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
import json
from loguru import logger

class ServiceManager:

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.processes: Dict[str, subprocess.Popen] = {}
        self.services_status: Dict[str, bool] = {}
        self.running = False

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.work_dir = Path(config.get('work_dir', './workspace'))
        self.work_dir.mkdir(exist_ok=True)

        self.comfyui_config = config.get('comfyui', {})
        self.comfyui_port = self.comfyui_config.get('port', 8188)
        self.comfyui_host = self.comfyui_config.get('host', '127.0.0.1')

    def start_comfyui(self) -> bool:
        try:

            current_dir = Path.cwd()

            cmd = [
                sys.executable, "main.py",
                "--disable-xformers"
            ]

            vram_mode = self.comfyui_config.get('vram_mode', '--lowvram')
            if vram_mode:
                cmd.append(vram_mode)

            cmd.extend(["--listen", self.comfyui_host])
            cmd.extend(["--port", str(self.comfyui_port)])

            comfyui_work_dir = current_dir / "ComfyUI"

            self.logger.info(f"ComfyUI start command: {' '.join(cmd)}")

            main_py_path = comfyui_work_dir / "main.py"
            if not main_py_path.exists():
                self.logger.info(" ComfyUI needs to be set up first...")
            else:
                self.logger.info(f" Found ComfyUI task_main.py at {main_py_path}")

            self.logger.info("Launching ComfyUI process...")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=comfyui_work_dir
            )

            self.processes['comfyui'] = process
            self.logger.info(f"ComfyUI process started with PID: {process.pid}")

            if self.wait_for_service(f"http://{self.comfyui_host}:{self.comfyui_port}", "ComfyUI"):
                self.services_status['comfyui'] = True
                return True
            else:
                try:
                    out, err = process.communicate(timeout=5)
                    self.logger.error(f" ComfyUI failed to start within timeout")
                except subprocess.TimeoutExpired:
                    self.logger.error(" ComfyUI process communication timeout")
                return False

        except Exception as e:
            self.logger.error(f" Exception while starting ComfyUI: {e}")
            return False

    def wait_for_service(self, url: str, service_name: str, timeout: int = 60) -> bool:

        start_time = time.time()
        attempt_count = 0

        while time.time() - start_time < timeout:
            attempt_count += 1
            elapsed_time = time.time() - start_time

            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    self.logger.info(f" {service_name} service is ready! (took {elapsed_time:.1f}s)")
                    return True
                else:
                    self.logger.debug(f"{service_name} returned status code: {response.status_code}")
            except requests.exceptions.ConnectionError as e:
                self.logger.debug(f"{service_name} connection error: {e}")
            except requests.exceptions.Timeout as e:
                self.logger.debug(f"{service_name} timeout: {e}")
            except requests.exceptions.RequestException as e:
                self.logger.debug(f"{service_name} request error: {e}")
            except Exception as e:
                self.logger.debug(f"{service_name} unexpected error: {e}")

            time.sleep(2)

        return False

    def start_all_services(self) -> bool:

        self.running = True

        self.logger.info("Starting ComfyUI service...")
        if not self.start_comfyui():
            return False

        return True

    def stop_service(self, service_name: str):
        if service_name in self.processes:
            process = self.processes[service_name]
            self.logger.info(f" Stopping {service_name} service (PID: {process.pid})")

            try:
                self.logger.info(f"Sending SIGTERM to {service_name} process...")
                process.terminate()
                process.wait(timeout=10)
                self.logger.info(f"{service_name} service stopped gracefully")
            except subprocess.TimeoutExpired:
                self.logger.warning(f" {service_name} service didn't stop gracefully, force killing...")
                process.kill()
                process.wait()
                self.logger.info(f" {service_name} service force killed")

            self.services_status[service_name] = False
            del self.processes[service_name]
            self.logger.info(f" {service_name} service cleanup completed")
        else:
            self.logger.info(f"  {service_name} service not found in running processes")

    def stop_all_services(self):

        self.running = False

        if not self.processes:
            return

        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)

    def get_service_status(self) -> Dict[str, Any]:
        status = {
            'running': self.running,
            'services': {}
        }

        if not self.processes:
            return status

        for service_name, process in self.processes.items():
            if process.poll() is None:
                status['services'][service_name] = {
                    'running': True,
                    'pid': process.pid
                }
            else:
                status['services'][service_name] = {
                    'running': False,
                    'exit_code': process.returncode
                }

        return status

    def check_service_health(self) -> bool:

        try:
            comfyui_healthy = False
            if 'comfyui' in self.services_status and self.services_status['comfyui']:
                try:
                    response = requests.get(f"http://{self.comfyui_host}:{self.comfyui_port}", timeout=30)
                    comfyui_healthy = response.status_code == 200
                except Exception as e:
                    self.logger.warning(f" ComfyUI health check failed: {e}")
            else:
                self.logger.info("  ComfyUI not in services status")

            overall_healthy = comfyui_healthy

            return overall_healthy

        except Exception as e:
            self.logger.error(f" Health check failed: {e}")
            return False

    def __enter__(self):
        if not self.start_all_services():
            raise RuntimeError("Failed to start services")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all_services()


DEFAULT_CONFIG = {
    'work_dir': './workspace',
    'comfyui': {
        'host': '127.0.0.1',
        'port': 8188,
        'device': '0',
        'warmup': False
    }
}

def create_service_manager(config: Optional[Dict[str, Any]] = None) -> ServiceManager:
    if config is None:
        config = DEFAULT_CONFIG

    return ServiceManager(config)