"""
MCP MySQL 查询系统 - 聊天界面
使用 Flask 创建简单的 Web 聊天界面
"""
from flask import Flask, render_template_string, request, jsonify
import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

load_dotenv()

app = Flask(__name__)

# 初始化 DeepSeek 客户端
llm_client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL")
)
MODEL_NAME = os.getenv("DEEPSEEK_MODEL")

def mcp_to_function(tool):
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }
    }

async def agent_loop(session: ClientSession, user_query: str) -> str:
    tools_list = await session.list_tools()
    functions = [mcp_to_function(t) for t in tools_list.tools]
    messages = [
        {
            "role": "system",
            "content": """你是数据库数据分析智能助手，可以调用MySQL工具完成分析任务。
执行流程：
1. 不清楚表结构先调用 list_all_tables 查看所有表
2. 确定目标表后调用 get_table_schema 获取字段结构
3. 根据需求生成安全SELECT语句调用 execute_select_sql 查询数据
4. 拿到数据后做数据分析、汇总、趋势解读，禁止编造数据
仅使用工具返回真实数据回答用户问题。"""
        },
        {"role": "user", "content": user_query}
    ]

    max_round = 10
    for _ in range(max_round):
        resp = await llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=functions,
            tool_choice="auto"
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})
        
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            func_args = eval(tool_call.function.arguments)
            tool_res = await session.call_tool(func_name, arguments=func_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(tool_res.content)
            })
    return "达到最大执行轮数，任务终止"

async def process_query(user_query: str) -> str:
    server_params = StdioServerParameters(command="python", args=["mysql_mcp_server.py"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await agent_loop(session, user_query)
            return result

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP MySQL 数据分析助手</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .chat-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 600px;
        }
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .chat-header h1 {
            margin: 0;
            font-size: 1.5em;
            font-weight: 600;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .message {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            line-height: 1.5;
        }
        .user-message {
            align-self: flex-end;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 18px 18px 4px 18px;
        }
        .bot-message {
            align-self: flex-start;
            background: #f0f0f0;
            color: #333;
            border-radius: 18px 18px 18px 4px;
        }
        .bot-message pre {
            background: #e8e8e8;
            padding: 10px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 5px 0;
        }
        .chat-input {
            padding: 15px;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
        }
        .chat-input input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.3s;
        }
        .chat-input input:focus {
            border-color: #667eea;
        }
        .chat-input button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: transform 0.2s;
        }
        .chat-input button:hover {
            transform: scale(1.05);
        }
        .chat-input button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .typing-indicator {
            display: flex;
            gap: 4px;
            padding: 12px 16px;
            background: #f0f0f0;
            border-radius: 18px 18px 18px 4px;
            align-self: flex-start;
        }
        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: #667eea;
            border-radius: 50%;
            animation: typing 1.4s ease-in-out infinite;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
        }
        .status-bar {
            font-size: 12px;
            color: #666;
            text-align: center;
            padding: 10px;
            background: #f8f8f8;
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>📊 MCP MySQL 数据分析助手</h1>
            <p style="margin: 5px 0 0 0; opacity: 0.8; font-size: 14px;">连接到数据库: inspection_system</p>
        </div>
        <div class="chat-messages" id="chatMessages">
            <div class="bot-message">
                你好！我是你的数据库数据分析助手。请问你想查询什么？
                <br><br>
                示例问题：
                <ul>
                    <li>查看数据库有哪些表</li>
                    <li>查看 t_user 表的结构</li>
                    <li>统计订单总金额</li>
                </ul>
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="userInput" placeholder="输入你的查询..." autocomplete="off">
            <button id="sendBtn" onclick="sendMessage()">发送</button>
        </div>
        <div class="status-bar">
            🟢 已连接到 MySQL 数据库 | 支持自然语言查询
        </div>
    </div>

    <script>
        async function sendMessage() {
            const input = document.getElementById('userInput');
            const message = input.value.trim();
            if (!message) return;

            const chatMessages = document.getElementById('chatMessages');
            const sendBtn = document.getElementById('sendBtn');

            // 添加用户消息
            const userMsg = document.createElement('div');
            userMsg.className = 'message user-message';
            userMsg.textContent = message;
            chatMessages.appendChild(userMsg);

            // 清空输入
            input.value = '';
            sendBtn.disabled = true;

            // 添加打字指示器
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'typing-indicator';
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            chatMessages.appendChild(typingIndicator);

            // 滚动到底部
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {
                // 发送请求
                const response = await fetch('/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: message })
                });

                const data = await response.json();

                // 移除打字指示器
                typingIndicator.remove();

                // 添加助手消息
                const botMsg = document.createElement('div');
                botMsg.className = 'message bot-message';
                botMsg.textContent = data.result;
                
                chatMessages.appendChild(botMsg);
            } catch (error) {
                typingIndicator.remove();
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message bot-message';
                errorMsg.textContent = '❌ 查询失败，请稍后重试。';
                chatMessages.appendChild(errorMsg);
            } finally {
                sendBtn.disabled = false;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }

        // 按 Enter 发送
        document.getElementById('userInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>
    """)

@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
    user_query = data.get('query', '')
    
    # 使用 asyncio 运行异步函数
    result = asyncio.run(process_query(user_query))
    
    return jsonify({'result': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
