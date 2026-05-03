"""
LLM Server 管理模块
- 自动启动/停止 llama-server
- 支持文本模型和视觉模型切换
- 健康检查
"""

import os
import sys
import time
import signal
import subprocess
import threading
import urllib.request
import json
import shutil
from config import get_bundled_dir, get_config_dir, load_config


# 模型模式
MODE_TEXT = "text"
MODE_VISION = "vision"

# llama-server 默认端口
LLM_PORT = 8080


class LLMManager:
    """管理 llama-server 进程生命周期"""

    def __init__(self):
        self._process = None
        self._current_mode = None
        self._lock = threading.Lock()
        self._port = LLM_PORT
        self._model_dir = self._find_model_dir()
        self._llama_server = self._find_llama_server()

    def _find_model_dir(self):
        """查找模型目录：bundled > 配置目录 > 同级 models/"""
        bundled = get_bundled_dir()
        if bundled:
            candidate = os.path.join(bundled, "models")
            if os.path.isdir(candidate):
                return candidate

        # 开发模式：项目根目录 models/
        dev_models = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
        if os.path.isdir(dev_models):
            return os.path.abspath(dev_models)

        # 配置目录下的 models
        config_models = os.path.join(get_config_dir(), "models")
        os.makedirs(config_models, exist_ok=True)
        return config_models

    def _find_llama_server(self):
        """查找 llama-server 可执行文件"""
        bundled = get_bundled_dir()
        if bundled:
            # bundled/llama-server/llama-server (带 dylib 的目录)
            candidate = os.path.join(bundled, "llama-server", "llama-server")
            if os.path.isfile(candidate):
                return candidate
            # bundled/llama-server (单文件)
            candidate = os.path.join(bundled, "llama-server")
            if os.path.isfile(candidate):
                return candidate

        # PATH 中查找
        path = shutil.which("llama-server")
        if path:
            return path

        # macOS 常见路径
        for p in ["/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"]:
            if os.path.isfile(p):
                return p

        return None

    def _get_text_model_path(self):
        """获取文本模型路径"""
        cfg = load_config()
        # 用户自定义路径
        custom = cfg.get("llm", {}).get("model_path", "")
        if custom and os.path.isfile(custom):
            return custom

        # 默认：bundled 模型
        candidate = os.path.join(self._model_dir, "Qwen2.5-7B-Instruct-GGUF",
                                 "qwen2.5-7b-instruct-q4_0.gguf")
        if os.path.isfile(candidate):
            return candidate

        # 尝试其他量化
        gguf_dir = os.path.join(self._model_dir, "Qwen2.5-7B-Instruct-GGUF")
        if os.path.isdir(gguf_dir):
            for f in sorted(os.listdir(gguf_dir)):
                if f.endswith(".gguf") and "q4" in f.lower():
                    return os.path.join(gguf_dir, f)

        return None

    def _get_vision_model_path(self):
        """获取视觉模型路径"""
        candidate = os.path.join(self._model_dir, "Qwen2-VL-7B-Instruct-GGUF",
                                 "Qwen2-VL-7B-Instruct-Q4_K_M.gguf")
        if os.path.isfile(candidate):
            return candidate
        return None

    def _get_vision_mmproj_path(self):
        """获取视觉模型 mmproj 路径"""
        candidate = os.path.join(self._model_dir, "Qwen2-VL-7B-Instruct-GGUF",
                                 "mmproj-Qwen2-VL-7B-Instruct-f16.gguf")
        if os.path.isfile(candidate):
            return candidate
        return None

    @property
    def port(self):
        return self._port

    @property
    def current_mode(self):
        return self._current_mode

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def get_api_base(self):
        """获取当前 LLM API base URL"""
        return f"http://127.0.0.1:{self._port}/v1"

    def get_chat_url(self):
        """获取 chat completions URL"""
        return f"http://127.0.0.1:{self._port}/v1/chat/completions"

    def health_check(self, timeout=2):
        """检查 llama-server 是否健康"""
        try:
            url = f"http://127.0.0.1:{self._port}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return data.get("status") == "ok"
        except Exception:
            return False

    def start(self, mode=MODE_TEXT, wait=True, timeout=60):
        """
        启动 llama-server
        mode: 'text' 或 'vision'
        wait: 是否等待服务就绪
        timeout: 等待超时秒数
        """
        with self._lock:
            # 已在运行且模式相同
            if self.is_running and self._current_mode == mode:
                if self.health_check():
                    return True

            # 需要切换模式或重启
            self._stop_internal()

            if not self._llama_server:
                print("[LLMManager] 错误: 找不到 llama-server")
                return False

            if mode == MODE_TEXT:
                model_path = self._get_text_model_path()
                if not model_path:
                    print("[LLMManager] 错误: 找不到文本模型")
                    return False
                cmd = [
                    self._llama_server,
                    "-m", model_path,
                    "-c", "8192",
                    "--host", "127.0.0.1",
                    "--port", str(self._port),
                ]
            elif mode == MODE_VISION:
                model_path = self._get_vision_model_path()
                mmproj_path = self._get_vision_mmproj_path()
                if not model_path or not mmproj_path:
                    print("[LLMManager] 错误: 找不到视觉模型")
                    return False
                cmd = [
                    self._llama_server,
                    "-m", model_path,
                    "--mmproj", mmproj_path,
                    "-c", "4096",
                    "--host", "127.0.0.1",
                    "--port", str(self._port),
                ]
            else:
                return False

            print(f"[LLMManager] 启动 {mode} 模式: {os.path.basename(model_path)}")

            # 设置环境（排除代理）
            env = os.environ.copy()
            for key in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                        "HTTPS_PROXY", "https_proxy"]:
                env.pop(key, None)

            # ggml 后端插件搜索路径（与 llama-server 同目录）
            llama_dir = os.path.dirname(self._llama_server)
            env["GGML_BACKEND_PATH"] = llama_dir

            # macOS: 清除 quarantine/provenance xattr（防止 Gatekeeper 阻止）
            if sys.platform == "darwin":
                try:
                    subprocess.run(
                        ["xattr", "-cr", llama_dir],
                        capture_output=True, timeout=10
                    )
                except Exception:
                    pass

            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    preexec_fn=os.setsid if sys.platform != "win32" else None,
                )
                self._current_mode = mode
            except Exception as e:
                print(f"[LLMManager] 启动失败: {e}")
                return False

        if wait:
            return self._wait_ready(timeout)
        return True

    def _wait_ready(self, timeout=60):
        """等待服务就绪"""
        start = time.time()
        while time.time() - start < timeout:
            if self._process and self._process.poll() is not None:
                stderr = self._process.stderr.read().decode(errors="replace")
                print(f"[LLMManager] 进程意外退出: {stderr[-500:]}")
                return False
            if self.health_check():
                print(f"[LLMManager] 服务就绪 (耗时 {time.time()-start:.1f}s)")
                return True
            time.sleep(0.5)
        print(f"[LLMManager] 等待超时 ({timeout}s)")
        return False

    def ensure_running(self, mode=MODE_TEXT):
        """确保指定模式的服务正在运行"""
        if self.is_running and self._current_mode == mode and self.health_check():
            return True
        return self.start(mode)

    def switch_mode(self, mode):
        """切换模型模式"""
        if self._current_mode == mode and self.is_running and self.health_check():
            return True
        return self.start(mode)

    def stop(self):
        """停止 llama-server"""
        with self._lock:
            self._stop_internal()

    def _stop_internal(self):
        """内部停止方法（需要在锁内调用）"""
        if self._process is not None:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                else:
                    self._process.terminate()
                self._process.wait(timeout=10)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._current_mode = None
            print("[LLMManager] 已停止")

    def get_status(self):
        """获取当前状态信息"""
        return {
            "running": self.is_running,
            "mode": self._current_mode,
            "port": self._port,
            "model_dir": self._model_dir,
            "llama_server": self._llama_server,
            "text_model": self._get_text_model_path(),
            "vision_model": self._get_vision_model_path(),
            "healthy": self.health_check() if self.is_running else False,
        }


# 全局单例
_manager = None


def get_llm_manager():
    """获取全局 LLMManager 实例"""
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager
