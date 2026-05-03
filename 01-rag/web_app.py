#!/usr/bin/env python3
"""
RAG Web 服务
提供 Web 界面供局域网用户使用知识库问答

启动后访问: http://<本机IP>:8088
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 配置
LLM_URL = "http://127.0.0.1:8082/v1/chat/completions"
EMBEDDING_URL = "http://127.0.0.1:8081/v1/embeddings"
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "knowledge_base"

app = FastAPI(title="RAG 知识库", description="本地 AI 知识库问答系统")

# CORS 配置，允许局域网访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_txt(file_path) -> List[str]:
    """解析 TXT 文件"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # 按换行分割，每行作为一段
    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    return paragraphs

def parse_pdf(file_path) -> List[str]:
    """解析 PDF 文件"""
    try:
        import PyPDF2
        paragraphs = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    # 按段落分割
                    for para in text.split('\n\n'):
                        if para.strip():
                            paragraphs.append(para.strip())
        return paragraphs
    except ImportError:
        return ["PDF 解析失败，请安装 PyPDF2"]

def parse_docx(file_path) -> List[str]:
    """解析 DOCX 文件"""
    try:
        from docx import Document
        paragraphs = []
        doc = Document(file_path)
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text.strip())
        return paragraphs
    except ImportError:
        return ["DOCX 解析失败，请安装 python-docx"]

def parse_document(file_path) -> List[str]:
    """根据文件扩展名解析文档"""
    ext = Path(file_path).suffix.lower()
    if ext == '.txt':
        return parse_txt(file_path)
    elif ext == '.pdf':
        return parse_pdf(file_path)
    elif ext == '.docx':
        return parse_docx(file_path)
    elif ext == '.md':
        return parse_txt(file_path)
    else:
        return [f"不支持的文件格式: {ext}"]

# HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG 知识库问答</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        header h1 { font-size: 2em; margin-bottom: 10px; }
        header p { opacity: 0.9; }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .chat-container {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
        }
        .message {
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 10px;
        }
        .user { background: #e3f2fd; margin-left: 50px; }
        .assistant { background: #f5f5f5; margin-right: 50px; }
        .sources {
            background: #fff3e0;
            padding: 10px 15px;
            border-radius: 8px;
            margin-top: 10px;
            font-size: 0.9em;
        }
        .sources h4 { color: #e65100; margin-bottom: 5px; }
        .source-item { margin: 5px 0; padding-left: 15px; }
        .input-area {
            display: flex;
            gap: 10px;
        }
        input[type="text"] {
            flex: 1;
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
        }
        input[type="text"]:focus { border-color: #667eea; outline: none; }
        button {
            padding: 15px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: scale(1.05); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        textarea {
            width: 100%;
            min-height: 100px;
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 14px;
            resize: vertical;
            margin-top: 10px;
        }
        .file-upload {
            border: 2px dashed #ccc;
            border-radius: 10px;
            padding: 30px;
            text-align: center;
            margin-top: 15px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .file-upload:hover { border-color: #667eea; background: #f8f8f8; }
        .file-upload.dragover { border-color: #667eea; background: #e8e8ff; }
        .file-list {
            margin-top: 10px;
            max-height: 200px;
            overflow-y: auto;
        }
        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            margin-bottom: 5px;
        }
        .file-item button {
            padding: 5px 15px;
            font-size: 12px;
            background: #f44336;
        }
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            margin-left: 10px;
        }
        .status.online { background: #4caf50; color: white; }
        .status.offline { background: #f44336; color: white; }
        .service-info {
            background: #f5f5f5;
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 0.9em;
        }
        .ip-address {
            font-family: monospace;
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 4px;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .clear-btn {
            background: #f44336;
            padding: 10px 20px;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e0e0e0;
            border-radius: 10px;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s;
        }
        .upload-btn {
            background: #4caf50;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>RAG 知识库问答</h1>
            <p>基于本地 Qwen2.5-7B + Qdrant 的智能问答系统</p>
            <span id="status" class="status offline">检测中...</span>
        </header>

        <div class="card">
            <h3>服务状态</h3>
            <div class="service-info">
                <p>• Qdrant: <span id="qdrant-status">检测中...</span></p>
                <p>• Embedding: <span id="embedding-status">检测中...</span></p>
                <p>• LLM: <span id="llm-status">检测中...</span></p>
                <p>• 访问地址: <span class="ip-address" id="ip-address">获取中...</span></p>
            </div>
        </div>

        <div class="card">
            <h3>知识库问答 <button onclick="clearChat()" class="clear-btn" style="float:right;font-size:12px;padding:5px 15px;">清空对话</button></h3>
            <div class="chat-container" id="chat-container">
                <div class="message assistant">
                    您好！我是基于本地知识库的 AI 助手。请在下方输入您的问题，我会从知识库中查找相关信息并回答。
                </div>
            </div>
            <div class="input-area">
                <input type="text" id="question" placeholder="请输入您的问题..." onkeypress="handleKeyPress(event)">
                <button onclick="askQuestion()" id="ask-btn">提问</button>
            </div>
        </div>

        <div class="card">
            <h3>添加文档到知识库</h3>

            <div class="upload-area" id="upload-area">
                <p>📄 拖拽文件到此处或点击选择文件</p>
                <p style="font-size: 0.8em; color: #888; margin-top: 5px;">支持: TXT, PDF, DOCX, MD</p>
                <input type="file" id="file-input" multiple accept=".txt,.pdf,.docx,.md" style="display: none;">
            </div>

            <div class="file-list" id="file-list"></div>

            <div style="margin-top: 15px;">
                <button onclick="uploadFiles()" class="upload-btn">上传并添加到知识库</button>
                <button onclick="addTextDocs()" style="background: #4caf50; margin-left: 10px;">添加文本</button>
            </div>

            <div id="upload-progress" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-bar-fill" id="progress-fill" style="width: 0%"></div>
                </div>
                <p id="progress-text" style="font-size: 0.9em; margin-top: 5px;">准备上传...</p>
            </div>
        </div>

        <div class="card">
            <h3>批量添加文本</h3>
            <textarea id="doc-text" placeholder="在此粘贴文档内容，每段一条..."></textarea>
            <div style="margin-top: 15px;">
                <button onclick="addDocuments()" style="background: #4caf50;">添加文本到知识库</button>
            </div>
        </div>
    </div>

    <script>
        let chatHistory = [];
        let selectedFiles = [];

        async function checkStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('qdrant-status').textContent = data.qdrant ? '✅ 在线' : '❌ 离线';
                document.getElementById('embedding-status').textContent = data.embedding ? '✅ 在线' : '❌ 离线';
                document.getElementById('llm-status').textContent = data.llm ? '✅ 在线' : '❌ 离线';
                document.getElementById('status').textContent = '系统就绪';
                document.getElementById('status').className = 'status online';
            } catch (e) {
                document.getElementById('status').textContent = '服务异常';
                document.getElementById('status').className = 'status offline';
            }
        }

        async function getIPAddress() {
            try {
                const res = await fetch('/api/ip');
                const data = await res.json();
                document.getElementById('ip-address').textContent = data.ip + ':8088';
            } catch (e) {
                document.getElementById('ip-address').textContent = 'localhost:8088';
            }
        }

        function addMessage(role, content, sources = []) {
            const container = document.getElementById('chat-container');
            const msg = document.createElement('div');
            msg.className = `message ${role}`;

            let html = `<p>${content.replace(/\\n/g, '<br>')}</p>`;

            if (sources && sources.length > 0) {
                html += `<div class="sources"><h4>📚 参考资料:</h4>`;
                sources.forEach((s, i) => {
                    html += `<div class="source-item">${i+1}. ${s.text.substring(0, 100)}...</div>`;
                });
                html += `</div>`;
            }

            msg.innerHTML = html;
            container.appendChild(msg);
            container.scrollTop = container.scrollHeight;
        }

        function setLoading(loading) {
            const btn = document.getElementById('ask-btn');
            btn.disabled = loading;
            btn.innerHTML = loading ? '<span class="loading"></span>' : '提问';
        }

        async function askQuestion() {
            const question = document.getElementById('question').value.trim();
            if (!question) return;

            addMessage('user', question);
            chatHistory.push({ role: 'user', content: question });
            document.getElementById('question').value = '';
            setLoading(true);

            try {
                const res = await fetch('/api/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question, history: chatHistory })
                });
                const data = await res.json();
                addMessage('assistant', data.answer, data.sources);
                chatHistory.push({ role: 'assistant', content: data.answer });
            } catch (e) {
                addMessage('assistant', '抱歉，服务出错: ' + e.message);
            }

            setLoading(false);
        }

        function handleKeyPress(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                askQuestion();
            }
        }

        function clearChat() {
            chatHistory = [];
            document.getElementById('chat-container').innerHTML = `
                <div class="message assistant">
                    对话已清空。请继续提问！
                </div>
            `;
        }

        async function addDocuments() {
            const text = document.getElementById('doc-text').value.trim();
            if (!text) {
                alert('请输入文档内容');
                return;
            }

            const docs = text.split('\\n').filter(d => d.trim());

            try {
                const res = await fetch('/api/add_docs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ documents: docs })
                });
                const data = await res.json();
                alert(`成功添加 ${data.count} 条文档到知识库！`);
                document.getElementById('doc-text').value = '';
            } catch (e) {
                alert('添加失败: ' + e.message);
            }
        }

        // 文件上传处理
        const uploadArea = document.getElementById('upload-area');
        const fileInput = document.getElementById('file-input');

        uploadArea.addEventListener('click', () => fileInput.click());

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener('change', () => {
            handleFiles(fileInput.files);
        });

        function handleFiles(files) {
            selectedFiles = Array.from(files);
            const fileList = document.getElementById('file-list');
            fileList.innerHTML = '';

            selectedFiles.forEach((file, index) => {
                const div = document.createElement('div');
                div.className = 'file-item';
                div.innerHTML = `
                    <span>📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)</span>
                    <button onclick="removeFile(${index})">删除</button>
                `;
                fileList.appendChild(div);
            });
        }

        function removeFile(index) {
            selectedFiles.splice(index, 1);
            handleFiles(selectedFiles);
        }

        async function uploadFiles() {
            if (selectedFiles.length === 0) {
                alert('请先选择文件');
                return;
            }

            const progressDiv = document.getElementById('upload-progress');
            const progressFill = document.getElementById('progress-fill');
            const progressText = document.getElementById('progress-text');

            progressDiv.style.display = 'block';

            let totalDocs = 0;
            let processedFiles = 0;

            for (const file of selectedFiles) {
                progressText.textContent = `正在处理: ${file.name}`;

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const res = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();

                    if (data.error) {
                        alert(`处理 ${file.name} 时出错: ${data.error}`);
                    } else {
                        totalDocs += data.count;
                    }
                } catch (e) {
                    alert(`上传 ${file.name} 失败: ${e.message}`);
                }

                processedFiles++;
                progressFill.style.width = `${(processedFiles / selectedFiles.length) * 100}%`;
            }

            progressText.textContent = `完成！共添加 ${totalDocs} 条文档`;
            progressFill.style.width = '100%';

            setTimeout(() => {
                progressDiv.style.display = 'none';
                progressFill.style.width = '0%';
            }, 3000);

            selectedFiles = [];
            document.getElementById('file-list').innerHTML = '';
            fileInput.value = '';

            if (totalDocs > 0) {
                alert(`成功添加 ${totalDocs} 条文档到知识库！`);
            }
        }

        // 初始化
        checkStatus();
        getIPAddress();
        setInterval(checkStatus, 30000);
    </script>
</body>
</html>
"""

def post_json(url, data, method='POST'):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method=method
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode('utf-8'))

def get_embedding(text):
    result = post_json(EMBEDDING_URL, {
        "input": text,
        "model": "nomic-embed-text-v1.5.f16.gguf"
    })
    return result["data"][0]["embedding"]

def search_knowledge(query, top_k=3):
    query_embedding = get_embedding(query)
    payload = {
        "vector": query_embedding,
        "limit": top_k,
        "with_payload": True
    }
    result = post_json(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search",
        payload
    )
    return result.get("result", [])

def create_collection():
    payload = {
        "vectors": {
            "size": 768,
            "distance": "Cosine"
        }
    }
    try:
        post_json(f"{QDRANT_URL}/collections/{COLLECTION_NAME}", payload, 'PUT')
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise

def add_docs_to_collection(docs):
    create_collection()

    points = []
    for i, doc in enumerate(docs):
        if not doc.strip():
            continue
        try:
            embedding = get_embedding(doc)
            points.append({
                "id": i,
                "vector": embedding,
                "payload": {"text": doc}
            })
        except Exception as e:
            print(f"Error embedding doc {i}: {e}")

    if points:
        payload = {"points": points}
        post_json(f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points", payload, 'PUT')

    return len(points)

def ask_llm(context, query, history=None):
    prompt = f"""基于以下上下文信息回答问题。如果上下文中没有相关信息，请说明不知道。

上下文：
{context}

问题：{query}

回答："""

    messages = [{"role": "system", "content": "你是一个友好的AI助手，基于提供的上下文信息回答问题。"}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    result = post_json(LLM_URL, {
        "model": "qwen2.5-7b-instruct-q4_0.gguf",
        "messages": messages,
        "stream": False
    })
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_TEMPLATE

@app.get("/api/status")
async def get_status():
    status = {"qdrant": False, "embedding": False, "llm": False}

    try:
        urllib.request.urlopen(f"{QDRANT_URL}/collections", timeout=5)
        status["qdrant"] = True
    except:
        pass

    try:
        get_embedding("test")
        status["embedding"] = True
    except:
        pass

    try:
        post_json(LLM_URL, {
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}]
        })
        status["llm"] = True
    except:
        pass

    return status

@app.get("/api/ip")
async def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return {"ip": ip}

@app.post("/api/ask")
async def ask(question: dict):
    q = question.get("question", "")
    history = question.get("history", [])

    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        results = search_knowledge(q, top_k=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")

    if results:
        context = "\n".join([r['payload']['text'] for r in results])
        sources = [{"text": r['payload']['text']} for r in results]
    else:
        context = "知识库中没有找到相关信息。"
        sources = []

    try:
        answer = ask_llm(context, q, history if len(history) <= 4 else None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成回答失败: {e}")

    return {"answer": answer, "sources": sources}

@app.post("/api/add_docs")
async def add_docs(data: dict):
    docs = data.get("documents", [])

    if not docs:
        raise HTTPException(status_code=400, detail="文档不能为空")

    count = add_docs_to_collection(docs)
    return {"count": count, "message": f"成功添加 {count} 条文档"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # 保存上传的文件
    temp_path = f"/tmp/{file.filename}"

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 解析文档
        paragraphs = parse_document(temp_path)

        if not paragraphs or (len(paragraphs) == 1 and "不支持" in paragraphs[0]):
            return {"error": f"无法解析文件: {file.filename}"}

        # 添加到知识库
        count = add_docs_to_collection(paragraphs)

        return {"count": count, "filename": file.filename}

    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║          RAG 知识库 Web 服务已启动                      ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  本机访问: http://localhost:8088                         ║
║                                                          ║
║  局域网访问: http://{ip}:8088                          ║
║                                                          ║
║  按 Ctrl+C 停止服务                                     ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8088, log_level="info")