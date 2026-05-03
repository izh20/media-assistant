"""
MediaAssistant 配置管理模块
- 读写 config.json（用户配置持久化）
- 环境变量覆盖（桌面应用模式）
- 提供默认值
"""

import os
import json
import shutil


def get_config_dir():
    """获取配置文件目录"""
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.expanduser('~/Library/Application Support')
    config_dir = os.path.join(base, 'MediaAssistant')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_data_dir():
    """获取数据目录（可被环境变量覆盖）"""
    env_dir = os.environ.get('MEDIA_ASSISTANT_DATA_DIR')
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir
    data_dir = os.path.join(os.path.expanduser('~/Documents'), 'MediaAssistant')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_port():
    """获取服务端口（环境变量 > 配置文件 > 默认 8090）"""
    env_port = os.environ.get('MEDIA_ASSISTANT_PORT')
    if env_port:
        return int(env_port)
    config = load_config()
    return config.get("app", {}).get("port", 8090)


def get_bundled_dir():
    """获取捆绑资源目录"""
    return os.environ.get('MEDIA_ASSISTANT_BUNDLED_DIR', '')


DEFAULT_CONFIG = {
    "llm": {
        "api_base": "http://127.0.0.1:8080/v1",
        "chat_path": "/chat/completions",
        "api_key": "",
        "model": "",
        "timeout": 180
    },
    "vision": {
        "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
        "timeout": 180
    },
    "whisper": {
        "model_path": "bundled",
        "device": "auto",
        "compute_type": "auto"
    },
    "app": {
        "port": 8090,
        "auto_update": True,
        "language": "zh",
        "frame_interval": 60
    }
}


def load_config():
    """加载配置，合并默认值"""
    config_path = os.path.join(get_config_dir(), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        merged = {}
        for key in DEFAULT_CONFIG:
            if isinstance(DEFAULT_CONFIG[key], dict):
                merged[key] = {**DEFAULT_CONFIG[key], **(user_config.get(key, {}))}
            else:
                merged[key] = user_config.get(key, DEFAULT_CONFIG[key])
        return merged
    return {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}


def save_config(config):
    """保存配置到文件"""
    config_path = os.path.join(get_config_dir(), 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def build_llm_url(config=None):
    """构建 LLM chat completions 完整 URL"""
    if config is None:
        config = load_config()
    llm = config["llm"]
    return llm["api_base"].rstrip("/") + "/" + llm["chat_path"].lstrip("/")


def get_vision_url(config=None):
    """获取 Vision endpoint URL"""
    if config is None:
        config = load_config()
    return config["vision"]["endpoint_url"]


def get_llm_api_key(config=None):
    """获取 LLM API Key"""
    if config is None:
        config = load_config()
    return config["llm"].get("api_key", "")


def get_llm_model(config=None):
    """获取 LLM model 名称（空字符串表示不指定）"""
    if config is None:
        config = load_config()
    return config["llm"].get("model", "")


def find_ffmpeg():
    """查找 ffmpeg 可执行路径：bundled 优先，常见路径，fallback PATH"""
    bundled = get_bundled_dir()
    if bundled:
        import platform
        if platform.system() == "Darwin":
            candidate = os.path.join(bundled, "ffmpeg", "mac-arm64", "ffmpeg")
        else:
            candidate = os.path.join(bundled, "ffmpeg", "win-x64", "ffmpeg.exe")
        if os.path.isfile(candidate):
            return candidate
    # fallback: PATH 中的 ffmpeg
    path = shutil.which("ffmpeg")
    if path:
        return path
    # macOS 常见路径（打包后 PATH 可能不含 homebrew）
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.isfile(p):
            return p
    return "ffmpeg"


def find_ffprobe():
    """查找 ffprobe 可执行路径：bundled 优先，常见路径，fallback PATH"""
    bundled = get_bundled_dir()
    if bundled:
        import platform
        if platform.system() == "Darwin":
            candidate = os.path.join(bundled, "ffmpeg", "mac-arm64", "ffprobe")
        else:
            candidate = os.path.join(bundled, "ffmpeg", "win-x64", "ffprobe.exe")
        if os.path.isfile(candidate):
            return candidate
    path = shutil.which("ffprobe")
    if path:
        return path
    for p in ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"]:
        if os.path.isfile(p):
            return p
    return "ffprobe"


def get_whisper_model_path():
    """获取 Whisper 模型路径：bundled > 配置自定义 > HuggingFace 默认"""
    config = load_config()
    model_path = config["whisper"].get("model_path", "bundled")

    if model_path == "bundled":
        bundled = get_bundled_dir()
        if bundled:
            candidate = os.path.join(bundled, "models", "faster-whisper-large-v3-turbo")
            if os.path.isdir(candidate):
                return candidate
        # 开发模式：检查项目 bundled 目录
        dev_bundled = os.path.join(os.path.dirname(__file__), "bundled", "models", "faster-whisper-large-v3-turbo")
        if os.path.isdir(dev_bundled):
            return dev_bundled
        # bundled 目录无模型，回退到 HuggingFace 缓存名
        return "deepdml/faster-whisper-large-v3-turbo-ct2"

    # 用户自定义路径
    if os.path.exists(model_path):
        return model_path
    return model_path  # 可能是 HuggingFace model ID


def get_whisper_device_config():
    """自动检测最佳 Whisper 运行设备和精度"""
    config = load_config()
    device = config["whisper"].get("device", "auto")
    compute_type = config["whisper"].get("compute_type", "auto")

    if device == "auto":
        try:
            import ctranslate2
            cuda_types = ctranslate2.get_supported_compute_types("cuda")
            if "float16" in cuda_types or "int8_float16" in cuda_types:
                device = "cuda"
                if compute_type == "auto":
                    compute_type = "float16"
            else:
                device = "cpu"
                if compute_type == "auto":
                    compute_type = "int8"
        except Exception:
            device = "cpu"
            if compute_type == "auto":
                compute_type = "int8"
    elif compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type
