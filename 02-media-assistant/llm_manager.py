"""
LLM Server 管理模块
- 自动启动/停止 llama-server
- 统一模型管理（纯文本模式）
- 健康检查
- 所有权管理（ownership record）
- 空闲自动回收
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
import atexit
import traceback
from datetime import datetime
from pathlib import Path
from config import get_bundled_dir, get_config_dir, load_config


# llama-server 默认端口
LLM_PORT = 8080
IDLE_TIMEOUT_SECONDS = 300  # 5 分钟空闲自动停止

_RUNTIME_LOG_DIR = Path('/tmp/llm-logs')
_RUNTIME_LOG_FILE = _RUNTIME_LOG_DIR / 'video_subtitle.log'


def _append_runtime_log(tag, message):
    try:
        _RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with _RUNTIME_LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] [{tag}] {message}\n')
    except Exception:
        pass


def _append_runtime_exception(tag, context, exc):
    detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    _append_runtime_log(tag, f"{context}\n{detail}")


def _pid_alive(pid):
    """检查指定 pid 的进程是否仍存活"""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _get_ownership_record_path():
    """ownership record 文件路径"""
    runtime_dir = os.path.join(get_config_dir(), "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    return os.path.join(runtime_dir, "llm-owner.json")


class LLMManager:
    """管理 llama-server 进程生命周期"""

    # 状态枚举
    STATUS_STOPPED = "stopped"
    STATUS_STARTING = "starting"
    STATUS_READY = "ready"
    STATUS_STOPPING = "stopping"
    STATUS_ERROR = "error"

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._port = LLM_PORT
        self._model_dir = self._find_model_dir()
        self._llama_server = self._find_llama_server()
        self._status = self.STATUS_STOPPED
        # 空闲回收相关
        self._last_used_at = 0.0
        self._inflight_requests = 0
        self._idle_reaper_thread = None
        self._idle_reaper_stop = threading.Event()
        # 启动时清理 stale record
        self._cleanup_stale_record()

    # ==================== 模型/服务路径查找 ====================

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
            candidate = os.path.join(bundled, "llama-server", "llama-server")
            if os.path.isfile(candidate):
                return candidate
            candidate = os.path.join(bundled, "llama-server")
            if os.path.isfile(candidate):
                return candidate

        path = shutil.which("llama-server")
        if path:
            return path

        for p in ["/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"]:
            if os.path.isfile(p):
                return p

        return None

    def _get_text_model_path(self):
        """获取文本模型路径"""
        cfg = load_config()
        custom = cfg.get("llm", {}).get("model_path", "")
        if custom and os.path.isfile(custom):
            return custom

        candidate = os.path.join(self._model_dir, "Qwen2.5-7B-Instruct-GGUF",
                                 "qwen2.5-7b-instruct-q4_k_m.gguf")
        if os.path.isfile(candidate):
            return candidate

        gguf_dir = os.path.join(self._model_dir, "Qwen2.5-7B-Instruct-GGUF")
        if os.path.isdir(gguf_dir):
            preferred_files = [
                "qwen2.5-7b-instruct-q4_k_m.gguf",
                "qwen2.5-7b-instruct-q5_k_m.gguf",
                "qwen2.5-7b-instruct-q4_0.gguf",
            ]
            for filename in preferred_files:
                candidate = os.path.join(gguf_dir, filename)
                if os.path.isfile(candidate):
                    return candidate

            for f in sorted(os.listdir(gguf_dir)):
                lower_name = f.lower()
                if f.endswith(".gguf") and "qwen2-vl" not in lower_name and "mmproj" not in lower_name:
                    return os.path.join(gguf_dir, f)

        return None

    # ==================== Ownership Record ====================

    def _write_ownership_record(self, llm_pid, model_path, status):
        """写入 ownership record"""
        record = {
            "app_pid": os.getpid(),
            "llm_pid": llm_pid,
            "port": self._port,
            "model_path": model_path or "",
            "started_at": time.time(),
            "last_used_at": time.time(),
            "inflight_requests": 0,
            "status": status,
        }
        path = _get_ownership_record_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(record, f, indent=2)
            _append_runtime_log("LLM", f"owner-record-created pid={llm_pid} app_pid={os.getpid()}")
        except Exception as e:
            _append_runtime_log("LLM", f"owner-record-write-failed: {e}")

    def _read_ownership_record(self):
        """读取 ownership record，不存在则返回 None"""
        path = _get_ownership_record_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _update_record_status(self, status):
        """更新 record 中的 status 字段"""
        record = self._read_ownership_record()
        if record:
            record["status"] = status
            path = _get_ownership_record_path()
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, indent=2)
            except Exception:
                pass

    def _update_record_last_used(self):
        """更新 record 中的 last_used_at 和 inflight_requests"""
        record = self._read_ownership_record()
        if record:
            record["last_used_at"] = self._last_used_at
            record["inflight_requests"] = self._inflight_requests
            path = _get_ownership_record_path()
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, indent=2)
            except Exception:
                pass

    def _remove_ownership_record(self):
        """删除 ownership record"""
        path = _get_ownership_record_path()
        try:
            if os.path.isfile(path):
                os.unlink(path)
                _append_runtime_log("LLM", "owner-record-removed")
        except Exception:
            pass

    def _cleanup_stale_record(self):
        """启动时检测并清理 stale record"""
        record = self._read_ownership_record()
        if not record:
            return

        app_pid = record.get("app_pid")
        llm_pid = record.get("llm_pid")

        # app_pid 仍存活且不是当前进程 → 另一个实例的 record，不动
        if app_pid and app_pid != os.getpid() and _pid_alive(app_pid):
            _append_runtime_log("LLM", f"owner-record-belongs-to-other app_pid={app_pid}")
            return

        # app_pid 已死（崩溃残留）
        if app_pid and not _pid_alive(app_pid):
            _append_runtime_log("LLM", f"owner-record-stale app_pid={app_pid} (dead)")
            # 若 llm_pid 仍存活，安全停止
            if llm_pid and _pid_alive(llm_pid):
                _append_runtime_log("LLM", f"stopping-orphan-llm pid={llm_pid}")
                try:
                    os.kill(llm_pid, signal.SIGTERM)
                    # 等待最多 5 秒
                    for _ in range(10):
                        if not _pid_alive(llm_pid):
                            break
                        time.sleep(0.5)
                    if _pid_alive(llm_pid):
                        os.kill(llm_pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            self._remove_ownership_record()
            return

        # app_pid 是当前进程（正常重启场景，上次 atexit 没执行完）
        if app_pid == os.getpid():
            # llm_pid 还活着 → 尝试恢复
            if llm_pid and _pid_alive(llm_pid):
                _append_runtime_log("LLM", f"owner-record-loaded recovering pid={llm_pid}")
                # 不做恢复，直接清理让它重新启动
            self._remove_ownership_record()

    # ==================== 所有权判定 ====================

    def is_owned_process(self):
        """判断当前是否拥有正在运行的 LLM 进程"""
        if self._process is not None and self._process.poll() is None:
            return True
        record = self._read_ownership_record()
        if not record:
            return False
        return (record.get("app_pid") == os.getpid()
                and _pid_alive(record.get("llm_pid")))

    def detect_external_conflict(self):
        """检测端口是否被外部进程占用"""
        if self.is_owned_process():
            return False
        # 检查端口是否有服务
        if not self.health_check(timeout=1):
            return False
        # 端口有服务但不是我们的 → 冲突
        _append_runtime_log("LLM", f"external-port-conflict port={self._port}")
        return True

    # ==================== 属性 ====================

    @property
    def port(self):
        return self._port

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    @property
    def status(self):
        # 如果 _process 已死但状态还是 ready/starting，修正
        if self._status in (self.STATUS_READY, self.STATUS_STARTING):
            if not self.is_running and not self.health_check(timeout=1):
                self._status = self.STATUS_STOPPED
                self._remove_ownership_record()
        return self._status

    # ==================== 健康检查 ====================

    def get_api_base(self):
        return f"http://127.0.0.1:{self._port}/v1"

    def get_chat_url(self):
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

    # ==================== 推理计数（线程安全） ====================

    def acquire_inference(self):
        """推理开始前调用，增加计数，刷新时间"""
        with self._lock:
            self._inflight_requests += 1
            self._last_used_at = time.time()
            self._update_record_last_used()

    def release_inference(self):
        """推理结束后调用（在 finally 中），减少计数"""
        with self._lock:
            self._inflight_requests = max(0, self._inflight_requests - 1)
            self._last_used_at = time.time()
            self._update_record_last_used()

    # ==================== 启动 ====================

    def start(self, wait=True, timeout=60):
        """启动 llama-server，仅在端口空闲时"""
        with self._lock:
            # 已在运行且健康
            if self.is_running and self.health_check():
                self._status = self.STATUS_READY
                return True

            # 外部冲突检测
            if not self.is_running and self.health_check(timeout=1):
                # 端口上有服务但不是我们的进程
                print(f"[LLMManager] 端口 {self._port} 被外部进程占用，无法启动")
                _append_runtime_log("LLM", f"start-blocked external-port-conflict port={self._port}")
                self._status = self.STATUS_ERROR
                return False

            # 停止我们管理的旧进程
            self._stop_internal()

            if not self._llama_server:
                print("[LLMManager] 错误: 找不到 llama-server")
                _append_runtime_log("LLM", "start-failed reason=llama-server-missing")
                self._status = self.STATUS_ERROR
                return False

            model_path = self._get_text_model_path()
            if not model_path:
                print("[LLMManager] 错误: 找不到模型")
                _append_runtime_log("LLM", "start-failed reason=model-missing")
                self._status = self.STATUS_ERROR
                return False

            cmd = [
                self._llama_server,
                "-m", model_path,
                "-c", "8192",
                "--host", "127.0.0.1",
                "--port", str(self._port),
            ]

            print(f"[LLMManager] 启动: {os.path.basename(model_path)}")
            _append_runtime_log("LLM", f"start-request model={model_path}")

            env = os.environ.copy()
            for key in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                        "HTTPS_PROXY", "https_proxy"]:
                env.pop(key, None)

            llama_dir = os.path.dirname(self._llama_server)
            env["GGML_BACKEND_PATH"] = llama_dir

            if sys.platform == "darwin":
                try:
                    subprocess.run(["xattr", "-cr", llama_dir],
                                   capture_output=True, timeout=10)
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
                self._status = self.STATUS_STARTING
                self._last_used_at = time.time()
                # Popen 成功后写 ownership record
                self._write_ownership_record(self._process.pid, model_path, self.STATUS_STARTING)
                _append_runtime_log("LLM", f"process-started pid={self._process.pid} model={model_path}")
            except Exception as e:
                print(f"[LLMManager] 启动失败: {e}")
                _append_runtime_exception("LLM", f"start-exception model={model_path}", e)
                self._status = self.STATUS_ERROR
                return False

        if wait:
            result = self._wait_ready(timeout)
            if result:
                self._start_idle_reaper()
            return result
        else:
            # 异步启动：后台等待就绪后再启动 reaper
            def _bg_wait():
                if self._wait_ready(timeout):
                    self._start_idle_reaper()
            threading.Thread(target=_bg_wait, daemon=True).start()
            return True

    def _wait_ready(self, timeout=60):
        """等待服务就绪"""
        start = time.time()
        while time.time() - start < timeout:
            if self._process and self._process.poll() is not None:
                stderr = self._process.stderr.read().decode(errors="replace")
                print(f"[LLMManager] 进程意外退出: {stderr[-500:]}")
                _append_runtime_log("LLM", f"process-exit stderr={stderr[-2000:].strip() or 'empty'}")
                self._status = self.STATUS_ERROR
                self._remove_ownership_record()
                return False
            if self.health_check():
                elapsed = time.time() - start
                print(f"[LLMManager] 服务就绪 (耗时 {elapsed:.1f}s)")
                _append_runtime_log("LLM", f"ready elapsed={elapsed:.1f}s")
                self._status = self.STATUS_READY
                self._update_record_status(self.STATUS_READY)
                return True
            time.sleep(0.5)
        print(f"[LLMManager] 等待超时 ({timeout}s)")
        _append_runtime_log("LLM", f"wait-timeout timeout={timeout}s")
        self._status = self.STATUS_ERROR
        return False

    def ensure_running_for_inference(self):
        """推理入口专用：确保服务运行（按需启动）"""
        # 1. 我方进程健康 → 直接可用
        if self.is_running and self.health_check():
            self._status = self.STATUS_READY
            return True
        # 2. 我方进程在运行但尚未就绪（仍在加载模型） → 等待
        if self.is_running:
            return self._wait_ready(timeout=60)
        # 3. 外部冲突
        if self.detect_external_conflict():
            return False
        # 4. 没有进程也无健康服务 → 启动
        return self.start()

    # ==================== 停止 ====================

    def stop(self):
        """停止 llama-server（仅停止我方拥有的进程）"""
        with self._lock:
            if not self.is_owned_process() and not self.is_running:
                # 没有我们的进程，检查是否外部占用
                if self.health_check(timeout=1):
                    _append_runtime_log("LLM", "stop-skipped-external-owner")
                    print("[LLMManager] 端口上运行的是外部进程，跳过停止")
                    return False
                return True
            self._stop_idle_reaper()
            self._status = self.STATUS_STOPPING
            self._update_record_status(self.STATUS_STOPPING)
            self._stop_internal()
            self._status = self.STATUS_STOPPED
            self._remove_ownership_record()
            return True

    def _stop_internal(self):
        """内部停止方法（需要在锁内调用）"""
        if self._process is not None:
            prev_pid = self._process.pid
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
            print("[LLMManager] 已停止")
            _append_runtime_log("LLM", f"stopped pid={prev_pid}")

    # ==================== 空闲回收 ====================

    def _start_idle_reaper(self):
        """启动空闲回收线程"""
        if self._idle_reaper_thread and self._idle_reaper_thread.is_alive():
            return
        self._idle_reaper_stop.clear()
        self._idle_reaper_thread = threading.Thread(target=self._idle_reaper_loop, daemon=True)
        self._idle_reaper_thread.start()

    def _stop_idle_reaper(self):
        """停止空闲回收线程"""
        self._idle_reaper_stop.set()

    def _idle_reaper_loop(self):
        """后台线程：每 30 秒检查空闲超时"""
        while not self._idle_reaper_stop.wait(30):
            with self._lock:
                if not self.is_running:
                    break
                if self._inflight_requests > 0:
                    _append_runtime_log("LLM", f"idle-timer-refresh inflight={self._inflight_requests}")
                    continue
                idle_seconds = time.time() - self._last_used_at
                if idle_seconds >= IDLE_TIMEOUT_SECONDS:
                    print(f"[LLMManager] 空闲 {idle_seconds:.0f}s，自动停止")
                    _append_runtime_log("LLM", f"idle-auto-stop idle={idle_seconds:.0f}s")
                    self._status = self.STATUS_STOPPING
                    self._stop_internal()
                    self._status = self.STATUS_STOPPED
                    self._remove_ownership_record()
                    break

    # ==================== 状态查询（只读） ====================

    def get_status(self):
        """获取当前状态信息（只读，不启动服务）"""
        model_path = self._get_text_model_path()
        owned = self.is_owned_process()
        healthy = self.health_check(timeout=1) if (self.is_running or owned) else False
        external_conflict = self.detect_external_conflict() if not owned else False
        idle_seconds = (time.time() - self._last_used_at) if self._last_used_at > 0 and self.is_running else 0

        return {
            "status": self.status,
            "running": self.is_running,
            "owned_by_app": owned,
            "port": self._port,
            "model_dir": self._model_dir,
            "llama_server": self._llama_server,
            "model": model_path,
            "healthy": healthy,
            "external_conflict": external_conflict,
            "idle_seconds": round(idle_seconds),
            "inflight_requests": self._inflight_requests,
        }

    def get_check_services_status(self):
        """为 check_services 提供只读 LLM 状态（不启动服务）"""
        model_path = self._get_text_model_path()

        if not model_path:
            return False, "local-model-missing", "离线 · 未找到模型", False

        owned = self.is_owned_process()
        external_conflict = False

        if owned:
            healthy = self.health_check(timeout=2)
            cur_status = self.status
            if healthy:
                model_name = os.path.basename(model_path)
                idle_secs = time.time() - self._last_used_at if self._last_used_at > 0 else 0
                idle_tag = " · 空闲中" if (idle_secs > 30 and self._inflight_requests == 0) else ""
                return True, f"local-ready; model={model_name}", f"就绪{idle_tag} · {model_name}", False
            elif cur_status == self.STATUS_STARTING:
                model_name = os.path.basename(model_path)
                return False, f"local-starting; model={model_name}", f"启动中 · {model_name}", False
            else:
                model_name = os.path.basename(model_path)
                return False, f"local-not-ready; model={model_name}", f"离线 · {model_name}", False
        else:
            # 不是我们的进程，检查外部冲突
            external_conflict = self.detect_external_conflict()
            model_name = os.path.basename(model_path)
            if external_conflict:
                return False, f"local-port-conflict-external-owner; port={self._port}", \
                       f"端口 {self._port} 被外部进程占用", True
            else:
                # 端口空闲，模型存在但未启动
                return False, f"local-stopped; model={model_name}", f"未启动 · {model_name}", False


# 全局单例
_manager = None


def get_llm_manager():
    """获取全局 LLMManager 实例"""
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager
