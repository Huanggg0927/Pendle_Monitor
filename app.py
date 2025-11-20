# Linebot - Flask - PendleAPI 結合的查詢機器人
import os
import json
import http.client
from flask import Flask, request, abort

# 引入 LINE 相關套件
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- LINE Bot 設定 ---
# 請務必從 LINE Developers 網站取得這些資訊
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

app = Flask(__name__)

# 初始化 LINE Bot API
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 您的 API 核心邏輯 (將其封裝為一個函數) ---
def get_pendle_prices(chain_id: str, market: str) -> str:
    """根據 chain_id 和 market 取得 Pendle 的價格數據並格式化"""
    try:
        conn = http.client.HTTPSConnection("api-v2.pendle.finance")
        path = f"/core/v1/sdk/{chain_id}/markets/{market}/swapping-prices"
        conn.request("GET", path)
        res = conn.getresponse()
        
        if res.status == 200:
            data = res.read()
            data_dict = json.loads(data.decode("utf-8"))
            
            # 格式化回傳給用戶的訊息
            apy = data_dict.get('impliedApy', 0) * 100
            pt_rate = data_dict.get('underlyingTokenToPtRate', 0)
            
            # 建立一個易讀的文字訊息
            message = (
                f"🔗 市場數據查詢結果：\n"
                f"----------------------------------------\n"
                f"Chain ID: {chain_id}\n"
                f"Market ID: {market}\n"
                f"Implied APY: **{apy:.2f}%**\n"
                f"Underlying -> PT Rate: **{pt_rate:.4f}**\n"
                f"（更多數據請見原始 JSON）"
            )
            return message
        else:
            return f"❌ API 查詢失敗，狀態碼: {res.status}。請檢查 Chain ID/Market ID 是否正確。"
    except Exception as e:
        return f"🚨 發生錯誤：{e}"
    finally:
        conn.close()

# --- LINE Webhook 接收點 ---
@app.route("/callback", methods=['POST'])
def callback():
    """處理 LINE 傳送過來的 Webhook 請求"""
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/secret.")
        abort(400)
    return 'OK'

# --- 處理文字訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理用戶傳送的文字訊息"""
    text = event.message.text.strip()
    
    # 預期用戶輸入格式：[chain_id] [market_address]
    parts = text.split()
    
    if len(parts) == 2:
        chain_id = parts[0]
        market = parts[1]
        
        # 呼叫您的核心函數
        result_message = get_pendle_prices(chain_id, market)
        
    elif text.lower() == 'help':
        result_message = "請輸入 Chain ID 和 Market Address，以空格隔開。\n範例：8453 0x53fb20ff03ef94ef224557cc6262e0f11c20f718"
    else:
        result_message = "輸入格式不正確。請輸入 'help' 查看範例。"
        
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=result_message)
    )

if __name__ == "__main__":
    # 預設在本機環境運行 (端口 8000)
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)